"""Validate claim: TdrTransaction* + ResidentialAllocation + Parcel + Commodity
reproduces Transactions_Allocations_Details.xlsx.

Read-only SELECT only; no CREATE VIEW issued.
Writes erd/validate_transactions_view.json.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

ERD = Path(__file__).resolve().parent
sys.path.insert(0, str(ERD))
from db_corral import get_engine  # noqa: E402

REPO = ERD.parent
XLSX = REPO / "data" / "raw_data" / "Transactions_Allocations_Details.xlsx"


VIEW_SQL = """
SELECT
    tt.LeadAgencyAbbreviation + '-' + tt.TransactionTypeAbbreviation + '-'
      + CAST(tt.TdrTransactionID AS varchar(20))           AS TransactionID,
    tt.ProjectNumber                                       AS ProjectNumber,
    tt.TransactionTypeAbbreviation                         AS TransactionTypeAbbrev,
    tty.TransactionTypeName                                AS TransactionType,
    p.ParcelNumber                                         AS APN,
    j.ResidentialAllocationAbbreviation                    AS Jurisdiction,
    c.CommodityDisplayName                                 AS DevelopmentRight,
    c.CommodityShortName                                   AS DevelopmentRightShort,
    ra.AllocationSequence                                  AS AllocationSequence,
    ra.IssuanceYear                                        AS AllocationYear,
    COALESCE(ttt.ReceivingQuantity, tta.AllocatedQuantity) AS Quantity,
    ac.AccelaID                                            AS AccelaRecordID,
    tt.ApprovalDate                                        AS TRPAStatusDate,
    ts.TransactionStateName                                AS TRPAStatus,
    pp.PermitNumber                                        AS LocalJurisdictionProjectNumber,
    pps.ParcelPermitStatusName                             AS LocalStatus,
    pp.LastUpdatedDate                                     AS LocalStatusDate,
    tt.Comments                                            AS Notes,
    tt.TdrTransactionID                                    AS TdrTransactionID
FROM dbo.TdrTransaction tt
LEFT JOIN dbo.TransactionType tty           ON tty.TransactionTypeID = tt.TransactionTypeID
LEFT JOIN dbo.TransactionState ts           ON ts.TransactionStateID = tt.TransactionStateID
LEFT JOIN dbo.TdrTransactionTransfer   ttt  ON ttt.TdrTransactionID  = tt.TdrTransactionID
LEFT JOIN dbo.TdrTransactionAllocation tta  ON tta.TdrTransactionID  = tt.TdrTransactionID
LEFT JOIN dbo.ResidentialAllocation    ra   ON ra.TdrTransactionID   = tt.TdrTransactionID
LEFT JOIN dbo.Parcel p                      ON p.ParcelID = COALESCE(ttt.ReceivingParcelID, tta.ReceivingParcelID)
LEFT JOIN dbo.Jurisdiction j                ON j.JurisdictionID = p.JurisdictionID
LEFT JOIN dbo.Commodity c                   ON c.CommodityID = tt.CommodityID
LEFT JOIN dbo.AccelaCAPRecord ac            ON ac.AccelaCAPRecordID = tt.AccelaCAPRecordID
LEFT JOIN dbo.ParcelPermit pp               ON pp.ParcelID = p.ParcelID AND pp.JurisdictionID = p.JurisdictionID
LEFT JOIN dbo.ParcelPermitStatus pps        ON pps.ParcelPermitStatusID = pp.ParcelPermitStatusID
"""


def norm(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    return re.sub(r"\s+", " ", str(x)).strip().lower()


def main() -> None:
    engine = get_engine()
    with engine.connect() as conn:
        corral = pd.read_sql(text(VIEW_SQL), conn)
    print(f"Corral view rows: {len(corral)}")
    print(f"  distinct TransactionID: {corral['TransactionID'].nunique(dropna=True)}")

    xlsx = pd.read_excel(XLSX, dtype=str)
    print(f"XLSX rows: {len(xlsx)}")
    print(f"  distinct TransactionID: {xlsx['TransactionID'].nunique(dropna=True)}")

    # Join by TransactionID (ProjectNumber)
    xlsx_match = xlsx.dropna(subset=["TransactionID"]).copy()
    xlsx_match["TransactionID"] = xlsx_match["TransactionID"].astype(str).str.strip()
    corral["TransactionID"] = corral["TransactionID"].astype(str).str.strip()

    corral_one = (
        corral.dropna(subset=["TransactionID"])
        .sort_values("TdrTransactionID")
        .drop_duplicates("TransactionID", keep="first")
    )
    # Rename overlapping xlsx columns so pandas merge doesn't suffix them.
    xlsx_match = xlsx_match.rename(
        columns={
            "APN": "APN_xlsx",
            "Jurisdiction": "Jurisdiction_xlsx",
            "Notes": "Notes_xlsx",
            "Quantity": "Quantity_xlsx",
        }
    )
    joined = xlsx_match.merge(corral_one, on="TransactionID", how="left")
    n_joined = joined["TdrTransactionID"].notna().sum()
    print(f"Join rate by TransactionID: {n_joined}/{len(xlsx_match)} = {n_joined/len(xlsx_match):.1%}")

    # Column-by-column comparison for the rows that joined.
    j = joined[joined["TdrTransactionID"].notna()]
    pairs = [
        ("Transaction Type",               "TransactionType"),
        ("APN_xlsx",                       "APN"),
        ("Jurisdiction_xlsx",              "Jurisdiction"),
        ("Development Right",              "DevelopmentRight"),
        ("Quantity_xlsx",                  "Quantity"),
        ("Transaction Record ID",          "AccelaRecordID"),
        ("TRPA Status",                    "TRPAStatus"),
        ("TRPA Status Date",               "TRPAStatusDate"),
        ("Local Jurisdiction Project #",   "LocalJurisdictionProjectNumber"),
        ("Local Status",                   "LocalStatus"),
        ("Local Status Date",              "LocalStatusDate"),
        ("Notes_xlsx",                     "Notes"),
    ]
    col_results = []
    for xlsx_col, db_col in pairs:
        xv = j[xlsx_col].map(norm)
        dv = j[db_col].map(norm) if db_col in j.columns else pd.Series([""]*len(j))
        either_present = (xv != "") | (dv != "")
        both_equal = xv == dv
        considered = int(either_present.sum())
        matched = int((both_equal & either_present).sum())
        col_results.append(
            {
                "xlsx_column": xlsx_col,
                "corral_column": db_col,
                "considered": considered,
                "matched": matched,
                "match_rate": round(matched / considered, 4) if considered else None,
            }
        )

    # Columns that are known to be missing from Corral
    csv_only = ["Allocation Number", "Transaction Created Date", "Transaction Acknowledged Date",
                "Development Type", "Detailed Development Type", "Status Jan 2026",
                "TRPA/MOU Project #", "Year Built", "PM Year Built"]
    # Show a sample row of mismatches per column
    samples = {}
    for xlsx_col, db_col in pairs:
        if db_col not in j.columns:
            continue
        bad = j[(j[xlsx_col].map(norm) != j[db_col].map(norm)) & ((j[xlsx_col].map(norm) != "") | (j[db_col].map(norm) != ""))]
        samples[xlsx_col] = bad[["TransactionID", xlsx_col, db_col]].head(3).to_dict("records")

    out = {
        "xlsx_rows": int(len(xlsx)),
        "xlsx_with_transaction_id": int(len(xlsx_match)),
        "corral_view_rows": int(len(corral)),
        "corral_distinct_transaction_ids": int(corral["TransactionID"].nunique(dropna=True)),
        "joined_rows": int(n_joined),
        "join_rate": round(n_joined / len(xlsx_match), 4) if len(xlsx_match) else None,
        "xlsx_columns_missing_in_corral": csv_only,
        "column_match": col_results,
        "mismatch_samples": samples,
    }
    (ERD / "validate_transactions_view.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8"
    )
    print("\nColumn match (of joined rows):")
    for r in col_results:
        rate = f"{r['match_rate']:.1%}" if r["match_rate"] is not None else "  n/a"
        print(f"  {r['xlsx_column']:<32} {r['matched']}/{r['considered']}  {rate}")
    print(f"\nWrote {ERD / 'validate_transactions_view.json'}")


if __name__ == "__main__":
    main()
