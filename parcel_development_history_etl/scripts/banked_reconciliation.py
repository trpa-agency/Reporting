"""
banked_reconciliation.py - reconcile LT Info banked development rights against
Corral source tables and the TDR transaction log.

Background
----------
The Cumulative_Accounting layer 7 ("Banked Development Rights") is staged
nightly from the LT Info `GetBankedDevelopmentRights` JSON service. That
service is backed by `Corral.ParcelCommodityInventory.BankedQuantity` joined
to `LandCapabilityType` / `Commodity`. The analyst (and TRPA leadership) has
flagged that the LT Info banked numbers do not match what they reconstruct
from the actual banking and TDR transfer history. This script enumerates
the discrepancies so they can be fixed at the source (LT Info / Corral).

What it compares
----------------
For each (canonical APN, Commodity) pair, builds a row showing:

  layer7_qty       sum RemainingBankedQuantity from Cumulative_Accounting layer 7
                   (staged copy of GetBankedDevelopmentRights)
  layer7_status    "Active" / "Inactive" / mixed - rolled up across sub-rows
  layer7_last      max LastUpdated date in layer 7
  pci_banked       sum BankedQuantity from Corral_2026.ParcelCommodityInventory
                   (the LT Info store-of-record)
  pci_adj          sum RemainingBankedQuantityAdjustment (manual corrections)
  pci_net          pci_banked + pci_adj
  pci_last         max LastUpdateDate in pci
  tx_received      sum positive Quantity from vTransactedAndBankedCommodities
                   (allocations + conversion-receipts + bank-acquisition
                   receivings - everything tagged ParcelAction='Receiving')
  tx_sent          sum negative Quantity from vTransactedAndBankedCommodities
                   (conversions / transfers / retirements / land-bank
                   acquisitions on the sending side)
  flags            pipe-delimited tags (see FLAG_* constants below)

The output is a CSV at `data/qa_data/banked_reconciliation_findings.csv`,
sorted by absolute delta between layer7_qty and pci_net so the rows that need
the most attention come first. A short markdown summary is written alongside.

Discrepancy taxonomy (FLAG_*)
-----------------------------
  LAYER7_VS_PCI_DELTA   layer7_qty != pci_net (the stage's source-of-truth
                        disagrees with Corral's primary store)
  LAYER7_ONLY           in layer 7 but not in pci (orphan staged row)
  PCI_ONLY              in pci.BankedQuantity > 0 but missing from layer 7
                        (LT Info JSON service is silently dropping a row)
  INACTIVE_BUT_REMAINING  layer 7 Status = Inactive yet qty > 0 (counted in
                          totals but the parcel itself is retired)
  STALE_LASTUPDATED     pci.LastUpdateDate older than STALE_YEARS_THRESHOLD
                        (default 5 yrs)
  NET_NEGATIVE          tx_sent magnitude exceeds plausible deposits
                        (banked balance went below zero in transaction log)
  RESALL_BANKED         "Residential Allocation" appears as a banked commodity
                        (residential allocations don't accumulate in a bank
                        per policy - data-quality smell)

Run
---
    PYTHONIOENCODING=utf-8 \\
      "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" \\
      parcel_development_history_etl/scripts/banked_reconciliation.py

Conventions per `Reporting/CLAUDE.md`: full Python path required, no
em-dashes, no staff names, `canonical_apn` from `utils.py` for APN
normalization, write outputs under `data/qa_data/`.
"""
from __future__ import annotations

import os
import sys
import urllib.parse
import datetime as _dt
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import QA_DATA_DIR  # noqa: E402
from utils import canonical_apn, get_logger  # noqa: E402

log = get_logger("banked_reconciliation")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LAYER_7_URL = (
    "https://maps.trpa.org/server/rest/services/Cumulative_Accounting"
    "/MapServer/7/query"
)
LAYER_7_PAGE_SIZE = 2000  # server-side max
LAYER_7_FIELDS = (
    "APN,Status,DevelopmentRight,LandCapability,RemainingBankedQuantity,"
    "DateBankedOrApproved,LastUpdated"
)

CORRAL_ODBC = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=sql24;DATABASE=Corral_2026;"
    "Trusted_Connection=yes;ApplicationIntent=ReadOnly;"
)

OUT_CSV = Path(QA_DATA_DIR) / "banked_reconciliation_findings.csv"
OUT_MD = Path(QA_DATA_DIR) / "banked_reconciliation_summary.md"

# Layer 7 "DevelopmentRight" labels <-> Corral Commodity names
# (Layer 7 is parenthetical / human-readable; Corral is CamelCase.)
COMMODITY_MAP = {
    "Commercial Floor Area (CFA)": "CommercialFloorArea",
    "Coverage (hard)": "CoverageHard",
    "Coverage (soft)": "CoverageSoft",
    "Coverage (potential)": "CoveragePotential",
    "Multi-Family Residential Unit of Use (MFRUU)": "MultiFamilyResidentialUnitOfUse",
    "Persons-at-one-time (PAOT)": "PersonsAtOneTime",
    "Potential Residential Unit of Use (PRUU)": "PotentialResidentialUnitOfUse",
    "Residential Allocation": "ResidentialAllocation",
    "Residential Bonus Unit (RBU)": "ResidentialBonusUnit",
    "Residential Floor Area (RFA)": "ResidentialFloorArea",
    "Restoration Credit": "RestorationCredit",
    "Single-Family Residential Unit of Use (SFRUU)": "SingleFamilyResidentialUnitOfUse",
    "Tourist Accommodation Unit (TAU)": "TouristAccommodationUnit",
    "Tourist Floor Area (TFA)": "TouristFloorArea",
}

STALE_YEARS_THRESHOLD = 5
DELTA_ABS_THRESHOLD = 1  # rows where |layer7 - pci_net| >= this get flagged

# Flag tags
FLAG_LAYER7_ONLY = "LAYER7_ONLY"
FLAG_PCI_ONLY = "PCI_ONLY"
FLAG_DELTA = "LAYER7_VS_PCI_DELTA"
FLAG_INACTIVE_REMAINING = "INACTIVE_BUT_REMAINING"
FLAG_STALE = "STALE_LASTUPDATED"
FLAG_NET_NEGATIVE = "NET_NEGATIVE"
FLAG_RESALL_BANKED = "RESALL_BANKED"


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def fetch_layer7() -> pd.DataFrame:
    """Paginate Layer 7 and return all features as a DataFrame.

    Returns columns: APN_raw, Status, DevelopmentRight, LandCapability,
    RemainingBankedQuantity, DateBankedOrApproved, LastUpdated (epoch ms).
    """
    log.info("Fetching Cumulative_Accounting layer 7 (paginated)...")
    rows: list[dict] = []
    offset = 0
    while True:
        params = {
            "where": "1=1",
            "outFields": LAYER_7_FIELDS,
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": LAYER_7_PAGE_SIZE,
            "resultOffset": offset,
            "orderByFields": "OBJECTID ASC",
        }
        r = requests.get(LAYER_7_URL, params=params, timeout=120)
        r.raise_for_status()
        j = r.json()
        feats = j.get("features", [])
        if not feats:
            break
        rows.extend(f["attributes"] for f in feats)
        if len(feats) < LAYER_7_PAGE_SIZE:
            break
        offset += LAYER_7_PAGE_SIZE
        log.info("  fetched %d so far...", len(rows))
    df = pd.DataFrame(rows)
    log.info("  layer 7 total rows: %d", len(df))
    df["APN_raw"] = df["APN"]
    df["apn"] = df["APN"].map(canonical_apn)
    df["commodity"] = df["DevelopmentRight"].map(COMMODITY_MAP).fillna(df["DevelopmentRight"])
    return df


def fetch_corral() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pull pci.BankedQuantity rollups and TDR transaction sums from Corral_2026."""
    log.info("Fetching Corral_2026 (ParcelCommodityInventory + vTransactedAndBanked)...")
    odbc_url = "mssql+pyodbc:///?odbc_connect=" + urllib.parse.quote_plus(CORRAL_ODBC)
    eng = create_engine(odbc_url, isolation_level="AUTOCOMMIT")

    # 1. Banked inventory per (ParcelNumber, Commodity)
    pci_sql = text(
        """
        SELECT p.ParcelNumber AS apn_raw,
               c.CommodityName AS commodity,
               SUM(pci.BankedQuantity) AS pci_banked,
               SUM(ISNULL(pci.RemainingBankedQuantityAdjustment, 0)) AS pci_adj,
               MAX(pci.LastUpdateDate) AS pci_last,
               MIN(pci.BankedDate) AS pci_banked_date,
               COUNT(*) AS pci_rows
        FROM ParcelCommodityInventory pci
        JOIN Parcel p ON pci.ParcelID = p.ParcelID
        JOIN LandCapabilityType lct ON pci.LandCapabilityTypeID = lct.LandCapabilityTypeID
        JOIN Commodity c ON lct.CommodityID = c.CommodityID
        WHERE pci.BankedQuantity IS NOT NULL
        GROUP BY p.ParcelNumber, c.CommodityName
        """
    )

    # 2. Transaction sums per (ParcelNumber, Commodity); receiving is +, sending is -
    # vTransactedAndBankedCommodities already encodes the sign on Quantity.
    tx_sql = text(
        """
        SELECT p.ParcelNumber AS apn_raw,
               c.CommodityName AS commodity,
               SUM(CASE WHEN v.Quantity > 0 THEN v.Quantity ELSE 0 END) AS tx_received,
               SUM(CASE WHEN v.Quantity < 0 THEN v.Quantity ELSE 0 END) AS tx_sent,
               COUNT(*) AS tx_rows,
               MAX(v.LastUpdateDate) AS tx_last
        FROM vTransactedAndBankedCommodities v
        JOIN Parcel p ON v.ParcelID = p.ParcelID
        JOIN Commodity c ON v.CommodityID = c.CommodityID
        WHERE v.ParcelAction <> 'Banked'
        GROUP BY p.ParcelNumber, c.CommodityName
        """
    )

    with eng.connect() as c:
        pci = pd.read_sql(pci_sql, c)
        tx = pd.read_sql(tx_sql, c)
    log.info("  pci rollups: %d  tx rollups: %d", len(pci), len(tx))
    pci["apn"] = pci["apn_raw"].map(canonical_apn)
    tx["apn"] = tx["apn_raw"].map(canonical_apn)
    return pci, tx


# ---------------------------------------------------------------------------
# Layer 7 rollup
# ---------------------------------------------------------------------------

def rollup_layer7(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate Layer 7 to one row per (apn, commodity)."""
    g = df.groupby(["apn", "commodity"], dropna=False)
    out = g.agg(
        layer7_qty=("RemainingBankedQuantity", "sum"),
        layer7_rows=("RemainingBankedQuantity", "size"),
        layer7_status_active=("Status", lambda s: (s == "Active").sum()),
        layer7_status_inactive=("Status", lambda s: (s == "Inactive").sum()),
        layer7_last=("LastUpdated", "max"),
    ).reset_index()
    return out


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

def reconcile(layer7: pd.DataFrame, pci: pd.DataFrame, tx: pd.DataFrame) -> pd.DataFrame:
    """Outer-join the three sources and flag discrepancies."""
    log.info("Reconciling...")
    pci = pci.drop(columns=[c for c in ("apn_raw",) if c in pci.columns])
    tx = tx.drop(columns=[c for c in ("apn_raw",) if c in tx.columns])
    pci["pci_net"] = pci["pci_banked"].fillna(0) + pci["pci_adj"].fillna(0)

    df = layer7.merge(pci, on=["apn", "commodity"], how="outer", suffixes=("", ""))
    df = df.merge(tx, on=["apn", "commodity"], how="left", suffixes=("", ""))

    for col in ("layer7_qty", "pci_banked", "pci_adj", "pci_net",
                "tx_received", "tx_sent", "layer7_rows",
                "layer7_status_active", "layer7_status_inactive"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["delta_layer7_pci"] = df["layer7_qty"] - df["pci_net"]

    # Build flag column
    def flagger(row: pd.Series) -> str:
        flags: list[str] = []
        in_l7 = row["layer7_rows"] > 0
        in_pci = row["pci_banked"] > 0
        if in_l7 and not in_pci:
            flags.append(FLAG_LAYER7_ONLY)
        if in_pci and not in_l7:
            flags.append(FLAG_PCI_ONLY)
        if in_l7 and in_pci and abs(row["delta_layer7_pci"]) >= DELTA_ABS_THRESHOLD:
            flags.append(FLAG_DELTA)
        if row["layer7_status_inactive"] > 0 and row["layer7_qty"] > 0:
            flags.append(FLAG_INACTIVE_REMAINING)
        if pd.notna(row.get("pci_last")):
            try:
                age = (_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None) - pd.to_datetime(row["pci_last"]).to_pydatetime()).days / 365.25
                if age > STALE_YEARS_THRESHOLD and row["pci_banked"] > 0:
                    flags.append(FLAG_STALE)
            except Exception:
                pass
        # Net negative: bank shouldn't go below zero from withdrawals alone
        if row["tx_sent"] < 0 and (abs(row["tx_sent"]) > row["tx_received"] + row["pci_banked"] + 1):
            flags.append(FLAG_NET_NEGATIVE)
        if row["commodity"] == "ResidentialAllocation" and row["layer7_qty"] > 0:
            flags.append(FLAG_RESALL_BANKED)
        return "|".join(flags)

    df["flags"] = df.apply(flagger, axis=1)

    # Sort by absolute delta descending (biggest discrepancies first), then by layer7_qty
    df["_abs_delta"] = df["delta_layer7_pci"].abs()
    df = df.sort_values(["_abs_delta", "layer7_qty"], ascending=[False, False]).drop(columns="_abs_delta")

    # Final column order
    cols = [
        "apn", "commodity",
        "layer7_qty", "layer7_rows", "layer7_status_active", "layer7_status_inactive",
        "layer7_last",
        "pci_banked", "pci_adj", "pci_net", "pci_rows", "pci_last",
        "tx_received", "tx_sent", "tx_rows", "tx_last",
        "delta_layer7_pci",
        "flags",
    ]
    for c in cols:
        if c not in df.columns:
            df[c] = pd.NA
    return df[cols]


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def write_summary(df: pd.DataFrame) -> None:
    """Console + markdown summary of what was found."""
    log.info("=" * 72)
    log.info("RECONCILIATION SUMMARY")
    log.info("=" * 72)

    # Per-category totals
    by_comm = df.groupby("commodity").agg(
        n=("apn", "size"),
        layer7=("layer7_qty", "sum"),
        pci_net=("pci_net", "sum"),
        delta=("delta_layer7_pci", "sum"),
        flagged=("flags", lambda s: (s != "").sum()),
    ).sort_values("flagged", ascending=False)
    log.info("\nBy commodity (sum across all (apn, commodity) pairs):")
    log.info("\n" + by_comm.to_string())

    # Flag tallies
    flag_counts: dict[str, int] = {}
    for flagstr in df["flags"]:
        if not flagstr:
            continue
        for f in flagstr.split("|"):
            flag_counts[f] = flag_counts.get(f, 0) + 1
    log.info("\nFlag counts:")
    for f, n in sorted(flag_counts.items(), key=lambda kv: -kv[1]):
        log.info("  %-30s %d", f, n)

    n_total = len(df)
    n_flagged = (df["flags"] != "").sum()
    log.info("\nTotal (apn, commodity) pairs: %d   |   flagged: %d   (%.1f%%)",
             n_total, n_flagged, 100 * n_flagged / max(n_total, 1))
    log.info("=" * 72)

    # Markdown
    md_lines = [
        "# Banked Development Rights Reconciliation",
        "",
        f"Generated {_dt.datetime.now().isoformat(timespec='seconds')}.",
        "",
        "## Inputs",
        "",
        "- Layer 7 (Cumulative_Accounting MapServer/7), staged from LT Info `GetBankedDevelopmentRights`",
        "- Corral_2026.ParcelCommodityInventory (`BankedQuantity` + `RemainingBankedQuantityAdjustment`)",
        "- Corral_2026.vTransactedAndBankedCommodities (TDR transaction history)",
        "",
        "Output: `data/qa_data/banked_reconciliation_findings.csv`",
        "",
        "## Flag taxonomy",
        "",
        "| Flag | Meaning |",
        "| --- | --- |",
        f"| `{FLAG_LAYER7_ONLY}` | row exists in layer 7 but not in `ParcelCommodityInventory.BankedQuantity` |",
        f"| `{FLAG_PCI_ONLY}` | `ParcelCommodityInventory.BankedQuantity > 0` but no row in layer 7 (JSON service dropping it) |",
        f"| `{FLAG_DELTA}` | layer 7 qty does not match `pci.BankedQuantity + adjustment` |",
        f"| `{FLAG_INACTIVE_REMAINING}` | layer 7 Status='Inactive' yet RemainingBankedQuantity > 0 |",
        f"| `{FLAG_STALE}` | `pci.LastUpdateDate` older than {STALE_YEARS_THRESHOLD} years with banked > 0 |",
        f"| `{FLAG_NET_NEGATIVE}` | TDR withdrawals exceed deposits+receipts (impossible) |",
        f"| `{FLAG_RESALL_BANKED}` | banked Residential Allocation (residential allocations don't bank per policy) |",
        "",
        "## Per-commodity totals",
        "",
        "| Commodity | n | layer7 | pci_net | delta | flagged |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for comm, row in by_comm.iterrows():
        md_lines.append(
            f"| {comm} | {int(row['n'])} | {row['layer7']:.0f} | {row['pci_net']:.0f} | {row['delta']:+.0f} | {int(row['flagged'])} |"
        )
    md_lines += [
        "",
        "## Flag counts",
        "",
        "| Flag | Count |",
        "| --- | ---: |",
    ]
    for f, n in sorted(flag_counts.items(), key=lambda kv: -kv[1]):
        md_lines.append(f"| `{f}` | {n} |")

    OUT_MD.write_text("\n".join(md_lines), encoding="utf-8")
    log.info("Summary written: %s", OUT_MD)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    layer7_raw = fetch_layer7()
    pci, tx = fetch_corral()

    layer7 = rollup_layer7(layer7_raw)
    findings = reconcile(layer7, pci, tx)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    findings.to_csv(OUT_CSV, index=False)
    log.info("Findings written: %s  (%d rows)", OUT_CSV, len(findings))

    write_summary(findings)

    n_flagged = (findings["flags"] != "").sum()
    return 0 if n_flagged == 0 else 0  # diagnostic script, never fails

if __name__ == "__main__":
    sys.exit(main())
