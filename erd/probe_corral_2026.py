"""
probe_corral_2026.py - read-only investigation against the current Corral copy.

Targets sql24 / Corral_2026. Read-only: SELECTs only, ApplicationIntent=ReadOnly.

Goal: explain the ~488-row gap between the reverse-engineered allocation-grid
query (one row per dbo.ResidentialAllocation = 2,112) and the analyst's grid
export (~2,600 rows). Compares the analyst CSV's composition against
Corral_2026's ResidentialAllocation, and tests whether the gap is disbursed
pool capacity not yet instantiated as individual allocation rows.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["CORRAL_DATABASE"] = "Corral_2026"
os.environ.setdefault("CORRAL_SERVER", "sql24")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_corral import get_engine  # noqa: E402
from sqlalchemy import text  # noqa: E402

import pandas as pd  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
GRID_CSV = REPO / "data" / "raw_data" / "residentialAllocationGridExport.csv"

# AllocationStatus CASE (the reverse-engineered derivation) over ResidentialAllocation.
STATUS_SQL = """
SELECT
    CASE
        WHEN ra.TdrTransactionID IS NOT NULL
          OR ra.IsAllocatedButNoTransactionRecord = 1 THEN 'Allocated'
        WHEN ra.AssignedToJurisdictionID IS NULL       THEN 'Unreleased'
        WHEN cp.CommodityPoolName LIKE '%TRPA%'        THEN 'TRPA Pool'
        ELSE 'Unallocated'
    END AS AllocationStatus
FROM dbo.ResidentialAllocation ra
JOIN dbo.CommodityPool cp ON cp.CommodityPoolID = ra.CommodityPoolID
"""


def section(title: str) -> None:
    print(f"\n==== {title} ====")


def main() -> int:
    # --- the analyst's grid export -------------------------------------------
    section("ANALYST GRID CSV")
    try:
        df = pd.read_csv(GRID_CSV, dtype=str)
        print(f"{GRID_CSV.name}: {len(df):,} rows")
        print("\nAllocation Status:")
        print(df["Allocation Status"].value_counts(dropna=False).to_string())
        yr = pd.to_numeric(df["Issuance Year"], errors="coerce")
        print(f"\nIssuance Year span: {yr.min():.0f} - {yr.max():.0f}")
        print("\nDevelopment Right Pool:")
        print(df["Development Right Pool"].value_counts(dropna=False).to_string())
    except Exception as e:
        print(f"CSV ERROR: {e}")

    # --- Corral_2026 ----------------------------------------------------------
    section(f"CORRAL_2026 on {os.environ['CORRAL_SERVER']}")
    try:
        with get_engine().connect() as conn:
            print(f"connected - DB_NAME() = {conn.execute(text('SELECT DB_NAME()')).scalar()}")

            ra_n = conn.execute(
                text("SELECT COUNT(*) FROM dbo.ResidentialAllocation")
            ).scalar()
            yr = conn.execute(text(
                "SELECT MIN(IssuanceYear), MAX(IssuanceYear) FROM dbo.ResidentialAllocation"
            )).fetchone()
            print(f"ResidentialAllocation: {ra_n:,} rows, IssuanceYear {yr[0]} - {yr[1]}")

            print("\nAllocationStatus distribution (reverse-engineered CASE):")
            for status, n in conn.execute(text(
                f"SELECT AllocationStatus, COUNT(*) n FROM (\n{STATUS_SQL}\n) q "
                "GROUP BY AllocationStatus ORDER BY n DESC"
            )):
                print(f"  {status:18s} {n:>8,}")

            print("\nState-field breakdown:")
            for label, where in [
                ("TdrTransactionID present",              "TdrTransactionID IS NOT NULL"),
                ("IsAllocatedButNoTransactionRecord = 1", "IsAllocatedButNoTransactionRecord = 1"),
                ("AssignedToJurisdictionID IS NULL",      "AssignedToJurisdictionID IS NULL"),
            ]:
                n = conn.execute(text(
                    f"SELECT COUNT(*) FROM dbo.ResidentialAllocation WHERE {where}"
                )).scalar()
                print(f"  {label:40s} {n:>8,}")

            section("INSTANTIATED vs DISBURSED  (residential pools)")
            rows = conn.execute(text("""
                SELECT
                    cp.CommodityPoolName,
                    COUNT(ra.ResidentialAllocationID) AS instantiated,
                    (SELECT SUM(cpd.CommodityPoolDisbursementAmount)
                     FROM dbo.CommodityPoolDisbursement cpd
                     WHERE cpd.CommodityPoolID = cp.CommodityPoolID) AS disbursed
                FROM dbo.CommodityPool cp
                LEFT JOIN dbo.ResidentialAllocation ra ON ra.CommodityPoolID = cp.CommodityPoolID
                WHERE cp.CommodityID IN (
                    SELECT DISTINCT cp2.CommodityID
                    FROM dbo.CommodityPool cp2
                    JOIN dbo.ResidentialAllocation ra2 ON ra2.CommodityPoolID = cp2.CommodityPoolID
                )
                GROUP BY cp.CommodityPoolName, cp.CommodityPoolID
                ORDER BY cp.CommodityPoolName
            """)).fetchall()
            tot_inst = tot_disb = 0
            print(f"  {'Pool':42s} {'instantiated':>12s} {'disbursed':>10s} {'gap':>7s}")
            for name, inst, disb in rows:
                disb = disb or 0
                tot_inst += inst
                tot_disb += disb
                print(f"  {str(name)[:42]:42s} {inst:>12,} {disb:>10,} {disb - inst:>7,}")
            print(f"  {'TOTAL':42s} {tot_inst:>12,} {tot_disb:>10,} {tot_disb - tot_inst:>7,}")

            print("\nTransaction-column fix check (rows with no TdrTransactionID):")
            for txn, flag in conn.execute(text("""
                SELECT TOP 5
                    CASE WHEN tx.TdrTransactionID IS NULL THEN 'Start Transaction'
                         ELSE CONCAT(tx.LeadAgencyAbbreviation,'-',
                                     tx.TransactionTypeAbbreviation,'-',
                                     CAST(tx.TdrTransactionID AS varchar(10)))
                    END AS Txn,
                    ra.IsAllocatedButNoTransactionRecord AS Flag
                FROM dbo.ResidentialAllocation ra
                LEFT JOIN dbo.TdrTransaction tx ON tx.TdrTransactionID = ra.TdrTransactionID
                WHERE ra.TdrTransactionID IS NULL
            """)):
                print(f"  Transaction={txn!r}  IsAllocatedButNoTransactionRecord={flag}")
        return 0
    except Exception as e:
        print(f"CORRAL ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
