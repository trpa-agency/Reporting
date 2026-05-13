"""
build_unit_transaction_relations.py — Many-to-many junction between the
Residential Units inventory and the analyst's 2025 Transactions and Allocations
Details xlsx.

One row per (Residential_Unit_ID, Transaction_ID) pair. Sorted chronologically
within each unit (Sequence 1..N), and flagged Is_Latest=True on the most
recent transaction per unit. Transaction metadata copied in so the table is
self-sufficient for analysis (no re-join to the source xlsx required).

Inputs (both produced earlier):
  - residential_units_inventory_2025.csv  (one row per current 2025 unit)
  - 2025 Transactions and Allocations Details.xlsx (one row per transaction)

Output:
  data/processed_data/residential_unit_transactions.csv

Assignment logic (v1, intentionally simple):
  All transactions on an APN are linked to every unit on that APN. This is
  over-inclusive in the case where one parcel had transactions of different
  types affecting different sub-sets of units (e.g. an allocation of 1 unit
  and a separate banking event for a different unit on the same parcel).
  A future v2 could use Transaction.Quantity + chronology to bind specific
  transactions to specific units.

Run:
    PYTHONIOENCODING=utf-8 \\
    "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" \\
    parcel_development_history_etl/scripts/build_unit_transaction_relations.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from config import (
    RESIDENTIAL_UNITS_INVENTORY_CSV,
    TRANSACTIONS_2025_XLSX,
    RESIDENTIAL_UNIT_TRANSACTIONS_CSV,
)
from utils import get_logger, canonical_apn

log = get_logger("build_unit_transaction_relations")


# Columns to bring across from the transactions xlsx (rename to snake_case
# for the output CSV).
TX_COLUMN_MAP = {
    "TransactionID":                  "Transaction_ID",
    "Transaction Type":               "Transaction_Type",
    "Development Type":               "Development_Type",
    "Detailed Development Type":      "Detailed_Development_Type",
    "Development Right":              "Development_Right",
    "Allocation Number":              "Allocation_Number",
    "Quantity":                       "Quantity",
    "Transaction Record ID":          "Transaction_Record_ID",
    "Transaction Created Date":       "Transaction_Created_Date",
    "Transaction Acknowledged Date":  "Transaction_Acknowledged_Date",
    "Year Built":                     "Year_Built",
    "TRPA/MOU Project #":             "TRPA_Project_Number",
    "Local Jurisdiction Project #":   "Local_Project_Number",
    "TRPA Status":                    "TRPA_Status",
    "TRPA Status Date":               "TRPA_Status_Date",
    "Local Status":                   "Local_Status",
    "Local Status Date":              "Local_Status_Date",
    "Status Jan 2026":                "Status_Jan_2026",
    "Notes":                          "Notes",
}


def main() -> None:
    log.info("=" * 70)
    log.info("BUILD RESIDENTIAL UNIT × TRANSACTION RELATIONS")
    log.info("=" * 70)

    # ── 1. Load the units inventory ──────────────────────────────────────
    log.info("Loading units inventory: %s", RESIDENTIAL_UNITS_INVENTORY_CSV)
    units = pd.read_csv(RESIDENTIAL_UNITS_INVENTORY_CSV,
                        dtype={"Residential_Unit_ID": str,
                               "APN": str, "APN_canon": str,
                               "Transaction_ID": str})
    units["Transaction_ID"] = units["Transaction_ID"].fillna("").astype(str)
    log.info("  %d unit rows loaded", len(units))

    units_with_tx = units[units["Transaction_ID"].str.strip() != ""]
    log.info("  %d unit rows have at least one Transaction_ID",
             len(units_with_tx))

    # ── 2. Load the transactions xlsx and index by TransactionID ─────────
    log.info("Loading transactions xlsx: %s", TRANSACTIONS_2025_XLSX)
    tx = pd.read_excel(TRANSACTIONS_2025_XLSX, sheet_name=0, dtype=str)
    tx.columns = [c.strip() for c in tx.columns]
    log.info("  %d transaction rows total in xlsx", len(tx))

    if "TransactionID" not in tx.columns:
        raise SystemExit("Transactions xlsx is missing required 'TransactionID' column.")

    # Strip whitespace, drop rows without a TransactionID
    tx["TransactionID"] = tx["TransactionID"].astype(str).str.strip()
    tx = tx[tx["TransactionID"].notna() & (tx["TransactionID"] != "") & (tx["TransactionID"] != "nan")]
    log.info("  %d transactions have a non-empty TransactionID", len(tx))

    # Canonicalize APN for sanity-check cross-reference
    if "APN" in tx.columns:
        tx["APN_canon_tx"] = tx["APN"].astype(str).str.strip().apply(canonical_apn)

    # Reduce to the columns we want; rename
    keep_cols = [c for c in TX_COLUMN_MAP if c in tx.columns]
    tx_sub = tx[keep_cols].rename(columns=TX_COLUMN_MAP)

    # Coerce types
    if "Quantity" in tx_sub.columns:
        tx_sub["Quantity"] = pd.to_numeric(tx_sub["Quantity"], errors="coerce")
    for date_col in ("Transaction_Created_Date", "Transaction_Acknowledged_Date",
                     "TRPA_Status_Date", "Local_Status_Date"):
        if date_col in tx_sub.columns:
            tx_sub[date_col] = pd.to_datetime(tx_sub[date_col], errors="coerce")
    if "Year_Built" in tx_sub.columns:
        tx_sub["Year_Built"] = pd.to_numeric(tx_sub["Year_Built"], errors="coerce").astype("Int64")

    # Build a lookup: TransactionID -> dict-of-fields
    tx_sub = tx_sub.drop_duplicates(subset=["Transaction_ID"], keep="first").set_index("Transaction_ID")
    tx_lookup = tx_sub.to_dict("index")
    log.info("  %d unique TransactionIDs after dedup", len(tx_lookup))

    # ── 3. Explode the inventory's semicolon-separated Transaction_ID ────
    rows = []
    misses = 0
    miss_examples: list[str] = []
    for r in units_with_tx.itertuples(index=False):
        ids = [t.strip() for t in r.Transaction_ID.split(";") if t.strip()]
        for tx_id in ids:
            meta = tx_lookup.get(tx_id)
            if meta is None:
                misses += 1
                if len(miss_examples) < 5:
                    miss_examples.append(tx_id)
                continue
            rows.append({
                "Residential_Unit_ID": r.Residential_Unit_ID,
                "APN":                 r.APN,
                "APN_canon":           r.APN_canon,
                "Transaction_ID":      tx_id,
                **meta,
            })

    if misses:
        log.warning("  %d TransactionIDs referenced from the inventory had no row "
                    "in the xlsx (e.g. %s). They were skipped.",
                    misses, ", ".join(miss_examples))

    df = pd.DataFrame(rows)
    log.info("Exploded to %d unit-transaction pairs", len(df))

    # ── 4. Order chronologically per unit, assign Sequence + Is_Latest ───
    # Use Transaction_Created_Date as the primary ordering key, falling back
    # to TRPA_Status_Date, then Local_Status_Date. Treat NaT as "very early"
    # so dated transactions sort to the end and pick up the higher sequence
    # number (you generally want Is_Latest on a dated row over an undated one).
    sort_cols = []
    for c in ("Transaction_Created_Date", "TRPA_Status_Date", "Local_Status_Date"):
        if c in df.columns:
            sort_cols.append(c)

    if sort_cols:
        df = df.sort_values(by=["Residential_Unit_ID"] + sort_cols,
                            kind="stable", na_position="first")

    df["Sequence"] = df.groupby("Residential_Unit_ID").cumcount() + 1
    df["Is_Latest"] = df["Sequence"] == df.groupby("Residential_Unit_ID")["Sequence"].transform("max")

    # ── 5. Synthetic primary key ─────────────────────────────────────────
    df["Relation_ID"] = (
        "RUT-" + df["Residential_Unit_ID"].str.replace("RU-", "", regex=False)
        + "-" + df["Sequence"].astype(str).str.zfill(2)
    )

    # ── 6. Column ordering ───────────────────────────────────────────────
    front = [
        "Relation_ID", "Residential_Unit_ID", "APN", "APN_canon",
        "Transaction_ID", "Sequence", "Is_Latest",
    ]
    rest = [c for c in df.columns if c not in front]
    df = df[front + rest]

    # ── 7. Write CSV ─────────────────────────────────────────────────────
    out = Path(RESIDENTIAL_UNIT_TRANSACTIONS_CSV)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)

    log.info("=" * 70)
    log.info("Wrote %d rows -> %s", len(df), out)
    log.info("=" * 70)
    log.info("Summary:")
    log.info("  unique units with relations:        %d",
             df["Residential_Unit_ID"].nunique())
    log.info("  unique transactions referenced:     %d",
             df["Transaction_ID"].nunique())
    log.info("  units with >1 transaction:          %d",
             (df.groupby("Residential_Unit_ID").size() > 1).sum())
    log.info("  max transactions on one unit:       %d",
             df.groupby("Residential_Unit_ID").size().max())
    if "Transaction_Type" in df.columns:
        log.info("  Transaction_Type distribution (top 8):")
        for k, v in df["Transaction_Type"].value_counts().head(8).items():
            log.info("    %-32s %d", k, v)
    if "Status_Jan_2026" in df.columns:
        log.info("  Status_Jan_2026 distribution:")
        for k, v in df["Status_Jan_2026"].value_counts(dropna=False).items():
            log.info("    %-15s %d", str(k), v)


if __name__ == "__main__":
    main()
