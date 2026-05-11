"""
build_residential_units_inventory.py — One row per currently-existing
residential unit in Tahoe (2025 state).

For each PDH 2025 parcel with Residential_Units > 0, emit N rows (N = units
on that parcel). Each row carries:

  Residential_Unit_ID  — synthetic `RU-<canonical-APN>-<seq>` (sequential)
  APN                  — current (2025) raw APN
  APN_canon            — canonical form (for joins)
  Previous_APNs        — semicolon-separated genealogy predecessors
  Original_Year_Built  — parcel's earliest structure year (COMBINED_YEAR_BUILT)
  Year_Redeveloped     — year current units came up after a demolition gap
  Era                  — Pre-1987 Plan / 1987 Plan / 2012 Plan / Unknown
  Source               — Existing / Allocation / Bonus Unit / Banked Unit /
                         Transfer / Conversion / Unknown
  Pool                 — TRPA / El Dorado / Placer / Washoe / Douglas / CSLT /
                         Banked Inventory / N/A (Pre-Allocation) / Unknown
  Transaction_ID       — semicolon-separated TransactionID(s) from
                         "2025 Transactions and Allocations Details.xlsx"
  Permit_Number        — TRPA/MOU and Local Jurisdiction permit IDs from the
                         transactions xlsx; semicolon-separated when both exist,
                         prefixed `TRPA-` and `LOCAL-` for clarity
  Building_IDs         — semicolon-separated Buildings_2019 IDs overlapping
                         parcel, each prefixed `BLDG-` (e.g. `BLDG-30876; BLDG-30890`)
  Address              — APO_ADDRESS from Parcels FeatureService
  COUNTY, JURISDICTION — from PDH

Output: data/processed_data/residential_units_inventory_2025.csv

Run with ArcGIS Pro Python:
    PYTHONIOENCODING=utf-8 \\
    "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" \\
    parcel_development_history_etl/scripts/build_residential_units_inventory.py
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# Make the parent package importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import arcpy
import pandas as pd

from config import (
    OUTPUT_FC,
    FC_APN, FC_YEAR, FC_UNITS, FC_COUNTY,
    CSV_PATH,                       # Final2026_Residential.csv
    GENEALOGY_TAHOE,
    BUILDINGS_FC,
    PARCELS_FS,
    PDH_2025_YRBUILT_CSV,
    RESIDENTIAL_UNITS_INVENTORY_CSV,
    TRANSACTIONS_2025_XLSX,
)
from utils import get_logger, canonical_apn

log = get_logger("build_residential_units_inventory")

YEAR = 2025


# ── 1. Load PDH 2025 with year-built (from prior step) ───────────────────────
def load_pdh_2025_yrbuilt() -> pd.DataFrame:
    """Read the joined PDH-2025 + COMBINED_YEAR_BUILT CSV. Filter to units > 0."""
    log.info("Loading PDH 2025 with year-built: %s", PDH_2025_YRBUILT_CSV)
    df = pd.read_csv(PDH_2025_YRBUILT_CSV, dtype={"APN": str, "APN_canon": str})
    for c in ("Residential_Units", "TouristAccommodation_Units"):
        df[c] = df[c].fillna(0).astype(int)
    df["CommercialFloorArea_SqFt"] = df["CommercialFloorArea_SqFt"].fillna(0)
    df = df[df["Residential_Units"] > 0].copy()
    log.info("  %d parcels with residential units in 2025", len(df))
    log.info("  %d total residential units to inventory", int(df["Residential_Units"].sum()))
    return df


# ── 2. Year_Redeveloped detection from year-by-year unit history ─────────────
def detect_year_redeveloped() -> dict:
    """
    Scan Final2026_Residential.csv (wide format APN × year). Return a dict
    {APN_canon: year_redeveloped} for parcels whose units dropped to 0 and
    came back up after at least one earlier non-zero year. The most recent
    rebuild year wins for multi-redev parcels.
    """
    log.info("Loading year-by-year unit history: %s", CSV_PATH)
    df = pd.read_csv(CSV_PATH)
    year_cols = [c for c in df.columns if "Final" in c]
    log.info("  detected year columns: %d (range %s..%s)",
             len(year_cols), year_cols[0], year_cols[-1])

    # Order columns by year (handle string-form year detection)
    def _yr(c: str) -> int:
        for tok in c.replace("Final", " ").split():
            if tok.isdigit():
                return int(tok)
        return -1
    year_cols = sorted(year_cols, key=_yr)
    years = [_yr(c) for c in year_cols]

    apn_col = "APN"
    df[apn_col] = df[apn_col].astype(str).str.strip()
    df["APN_canon"] = df[apn_col].apply(canonical_apn)
    # Coerce all unit columns to int
    for c in year_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    redev: dict = {}
    seen_nonzero = pd.Series(False, index=df.index)
    prev_col = year_cols[0]
    # Initialize seen_nonzero from first year
    seen_nonzero = df[prev_col] > 0
    for i in range(1, len(year_cols)):
        cur_col = year_cols[i]
        cur_yr = years[i]
        # Rebuild = prior was 0, current is non-zero, and SOMEWHERE earlier was non-zero
        prev = df[prev_col]
        cur = df[cur_col]
        is_rebuild = (prev == 0) & (cur > 0) & seen_nonzero
        for apn in df.loc[is_rebuild, "APN_canon"]:
            if apn:
                redev[apn] = cur_yr  # overwrite — most recent year wins
        seen_nonzero = seen_nonzero | (cur > 0)
        prev_col = cur_col

    log.info("  %d parcels show a redevelopment (unit-count rebuild) pattern", len(redev))
    return redev


# ── 3a. Previous_APNs from genealogy ─────────────────────────────────────────
def build_previous_apns_map() -> dict:
    """
    Return {current_canon_APN: [predecessor_canon_APN, ...]}.
    Walks genealogy chains backward from each apn_new up to 5 hops.
    """
    log.info("Loading genealogy: %s", GENEALOGY_TAHOE)
    g = pd.read_csv(GENEALOGY_TAHOE, dtype=str)
    g["apn_old_canon"] = g["apn_old"].apply(canonical_apn)
    g["apn_new_canon"] = g["apn_new"].apply(canonical_apn)
    g = g.dropna(subset=["apn_old_canon", "apn_new_canon"])
    g = g[g["apn_old_canon"] != g["apn_new_canon"]]

    # Index: apn_new → list of apn_old
    by_new: dict[str, list[str]] = {}
    for _, r in g.iterrows():
        by_new.setdefault(r["apn_new_canon"], []).append(r["apn_old_canon"])

    previous: dict[str, list[str]] = {}
    for apn_new in by_new:
        chain: list[str] = []
        seen = {apn_new}
        frontier = [apn_new]
        for hop in range(5):
            next_frontier = []
            for a in frontier:
                for old in by_new.get(a, []):
                    if old not in seen:
                        chain.append(old)
                        seen.add(old)
                        next_frontier.append(old)
            if not next_frontier:
                break
            frontier = next_frontier
        previous[apn_new] = chain

    log.info("  %d current APNs have genealogy predecessors", len(previous))
    return previous


# ── 3b. Status helpers — Era, Source, Pool ──────────────────────────────────
# Source priority for picking primary transaction per APN
_SOURCE_PRIORITY = ["Allocation", "Bonus Unit", "Banked Unit", "Transfer", "Conversion"]
_SOURCE_RANK = {s: i for i, s in enumerate(_SOURCE_PRIORITY)}

# Allocation Number prefix → Pool jurisdiction
_PREFIX_POOL = {
    "EL":  "El Dorado",
    "PL":  "Placer",
    "DG":  "Douglas",
    "WA":  "Washoe",
    "SLT": "CSLT",
}

# Development Right text keyword → Pool jurisdiction
_DEV_RIGHT_POOL_KEYWORDS = [
    ("el dorado",        "El Dorado"),
    ("placer",           "Placer"),
    ("douglas",          "Douglas"),
    ("washoe",           "Washoe"),
    ("south lake tahoe", "CSLT"),
    ("cslt",             "CSLT"),
    ("trpa pool",        "TRPA"),
]


def era_from_year(y) -> str:
    """Pre-1987 Plan / 1987 Plan / 2012 Plan / Unknown."""
    if pd.isna(y):
        return "Unknown"
    try:
        y = int(y)
    except (TypeError, ValueError):
        return "Unknown"
    if y <= 1987:
        return "Pre-1987 Plan"
    if y <= 2011:
        return "1987 Plan"
    return "2012 Plan"


def _safe_str(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


def _classify_source(tx_type, dev_type) -> str | None:
    t = _safe_str(tx_type)
    d = _safe_str(dev_type)
    if t in ("Residential Allocation", "Allocation", "Allocation Assignment"):
        return "Allocation"
    if t == "Residential Bonus Unit (RBU)" or d == "Residential Bonus Unit":
        return "Bonus Unit"
    if t == "Banking of Existing Development" or d == "Banked Unit":
        return "Banked Unit"
    if t == "Transfer" or d == "Transfer":
        return "Transfer"
    if t in ("Conversion", "Conversion With Transfer") or d in ("Converted To", "Converted From", "Conversion"):
        return "Conversion"
    return None


def _classify_pool(dev_right, alloc_num, source) -> str:
    if source == "Banked Unit":
        return "Banked Inventory"
    dr = _safe_str(dev_right).lower()
    for keyword, pool in _DEV_RIGHT_POOL_KEYWORDS:
        if keyword in dr:
            return pool
    if "bonus unit" in dr or "rbu" in dr:
        return "TRPA"
    # Fall back to Allocation Number prefix
    prefix = _safe_str(alloc_num).upper().split("-")[0]
    if prefix in _PREFIX_POOL:
        return _PREFIX_POOL[prefix]
    return "Unknown"


def build_status_maps() -> tuple[dict, dict]:
    """
    From the transactions xlsx, return:
      source_by_apn : {canon_APN: Source}     — highest-priority Source per APN
      pool_by_apn   : {canon_APN: Pool}       — Pool derived from the primary tx
    """
    log.info("Building Era/Source/Pool maps from %s", TRANSACTIONS_2025_XLSX)
    df = pd.read_excel(TRANSACTIONS_2025_XLSX, sheet_name=0, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    df["APN"] = df["APN"].astype(str).str.strip()
    df["APN_canon"] = df["APN"].apply(canonical_apn)
    df = df.dropna(subset=["APN_canon"])

    df["_source"] = df.apply(
        lambda r: _classify_source(r.get("Transaction Type"), r.get("Development Type")),
        axis=1,
    )
    df["_pool"] = df.apply(
        lambda r: _classify_pool(
            r.get("Development Right"), r.get("Allocation Number"), r["_source"]),
        axis=1,
    )

    source_by: dict = {}
    pool_by: dict = {}
    # Pick the row with the best (lowest-rank) Source per APN
    df["_rank"] = df["_source"].map(lambda s: _SOURCE_RANK.get(s, 99))
    df_sorted = df.sort_values(["APN_canon", "_rank"])
    for apn, group in df_sorted.groupby("APN_canon"):
        # First row (after sorting) is the primary
        primary = group.iloc[0]
        src = primary["_source"]
        if src is None:
            continue
        source_by[apn] = src
        pool_by[apn] = primary["_pool"]

    log.info("  %d APNs with classifiable Source", len(source_by))
    if source_by:
        counts: dict = {}
        for s in source_by.values():
            counts[s] = counts.get(s, 0) + 1
        for s in _SOURCE_PRIORITY:
            log.info("    %-12s : %d", s, counts.get(s, 0))
    return source_by, pool_by


# ── 3d. Permit_Number from transactions xlsx ────────────────────────────────
def build_permit_map() -> dict:
    """
    Return {canon_APN: "TRPA-<num>; LOCAL-<num>"} per APN, combining all
    transactions for that APN. Empty values stripped; duplicates removed.
    """
    log.info("Building Permit_Number map from %s", TRANSACTIONS_2025_XLSX)
    df = pd.read_excel(TRANSACTIONS_2025_XLSX, sheet_name=0, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    df["APN"] = df["APN"].astype(str).str.strip()
    df["APN_canon"] = df["APN"].apply(canonical_apn)
    df = df.dropna(subset=["APN_canon"])

    out: dict[str, str] = {}
    for apn, group in df.groupby("APN_canon"):
        permits: list[str] = []
        seen: set[str] = set()
        for _, r in group.iterrows():
            trpa  = _safe_str(r.get("TRPA/MOU Project #"))
            local = _safe_str(r.get("Local Jurisdiction Project #"))
            if trpa and trpa.lower() != "nan":
                tag = f"TRPA-{trpa}"
                if tag not in seen:
                    seen.add(tag); permits.append(tag)
            if local and local.lower() != "nan":
                tag = f"LOCAL-{local}"
                if tag not in seen:
                    seen.add(tag); permits.append(tag)
        if permits:
            out[apn] = "; ".join(permits)

    log.info("  %d APNs with at least one permit #", len(out))
    return out


# ── 3c. Transaction_ID from "2025 Transactions and Allocations Details" ──────
def build_transaction_id_map() -> dict:
    """
    Return {canon_APN: [TransactionID, ...]} from the 2025 Transactions and
    Allocations Details xlsx. Some rows lack TransactionID — those are skipped.
    """
    log.info("Loading transactions: %s", TRANSACTIONS_2025_XLSX)
    df = pd.read_excel(TRANSACTIONS_2025_XLSX, sheet_name=0, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    if "TransactionID" not in df.columns or "APN" not in df.columns:
        log.error("  Expected columns TransactionID + APN; saw: %s", list(df.columns))
        return {}

    df["APN"] = df["APN"].astype(str).str.strip()
    df["TransactionID"] = df["TransactionID"].astype(str).str.strip()
    # Filter to rows with a non-empty TransactionID
    df = df[df["TransactionID"].notna() & (df["TransactionID"] != "") & (df["TransactionID"] != "nan")]
    df["APN_canon"] = df["APN"].apply(canonical_apn)
    df = df.dropna(subset=["APN_canon"])

    tx: dict[str, list[str]] = {}
    for apn, group in df.groupby("APN_canon"):
        # Preserve order; dedupe
        seen, out = set(), []
        for t in group["TransactionID"]:
            if t not in seen:
                seen.add(t); out.append(t)
        tx[apn] = out

    n_apns = len(tx)
    n_tx = int(sum(len(v) for v in tx.values()))
    log.info("  %d unique APNs across %d transactions with TransactionID", n_apns, n_tx)
    return tx


# ── 4. Buildings_2019 spatial join to PDH 2025 polygons ──────────────────────
def build_building_id_map() -> dict:
    """
    Spatial-join Buildings_2019 → PDH YEAR=2025 with LARGEST_OVERLAP so each
    building footprint is assigned to exactly one parcel (the one it overlaps
    the most). Then invert: returns {APN_canon: "BLDG-<id>; BLDG-<id>; ..."}.

    This matches build_buildings_inventory.py's spatial logic — a building
    that straddles a parcel boundary appears only under its PRIMARY parcel,
    not both neighbors.
    """
    log.info("Spatial-joining Buildings_2019 -> PDH 2025 (LARGEST_OVERLAP) ...")
    if not arcpy.Exists(BUILDINGS_FC):
        log.warning("  Buildings FC not found: %s — skipping Building_IDs.", BUILDINGS_FC)
        return {}

    pdh_lyr  = "ru_pdh_2025_lyr"
    bldg_lyr = "ru_buildings_lyr"
    join_out = "memory/ru_buildings_join"
    for m in [pdh_lyr, bldg_lyr, join_out]:
        if arcpy.Exists(m):
            arcpy.management.Delete(m)

    arcpy.management.MakeFeatureLayer(OUTPUT_FC, pdh_lyr,
                                      where_clause=f"{FC_YEAR} = {YEAR}")
    arcpy.management.MakeFeatureLayer(BUILDINGS_FC, bldg_lyr)

    # Project buildings to parcel SR if needed
    parcel_sr = arcpy.Describe(OUTPUT_FC).spatialReference
    bldg_sr   = arcpy.Describe(BUILDINGS_FC).spatialReference
    if parcel_sr.factoryCode != bldg_sr.factoryCode:
        mem_proj = "memory/ru_bldg_proj"
        if arcpy.Exists(mem_proj):
            arcpy.management.Delete(mem_proj)
        log.info("  Projecting buildings (%s -> %s) ...", bldg_sr.name, parcel_sr.name)
        arcpy.management.Project(BUILDINGS_FC, mem_proj, parcel_sr)
        arcpy.management.Delete(bldg_lyr)
        arcpy.management.MakeFeatureLayer(mem_proj, bldg_lyr)

    # target = buildings (one row per building) — LARGEST_OVERLAP picks the
    # parcel with the most area-overlap for each building.
    arcpy.analysis.SpatialJoin(
        target_features=bldg_lyr,
        join_features=pdh_lyr,
        out_feature_class=join_out,
        join_operation="JOIN_ONE_TO_ONE",
        join_type="KEEP_ALL",
        match_option="LARGEST_OVERLAP",
    )

    fields = [f.name for f in arcpy.ListFields(join_out)]
    if FC_APN not in fields:
        log.warning("  APN field missing from join output; fields=%s", fields)
        return {}

    # Invert: each building (TARGET_FID) → its primary APN
    apn_to_bids: dict[str, list[str]] = {}
    n_matched = 0
    with arcpy.da.SearchCursor(join_out, ["TARGET_FID", FC_APN]) as cur:
        for bid, apn in cur:
            if apn is None or bid is None:
                continue
            canon = canonical_apn(str(apn).strip())
            if canon is None:
                continue
            apn_to_bids.setdefault(canon, []).append(str(int(bid)))
            n_matched += 1

    for m in [pdh_lyr, bldg_lyr, join_out]:
        if arcpy.Exists(m):
            arcpy.management.Delete(m)

    out = {
        a: "; ".join(f"BLDG-{bid}" for bid in sorted(set(b), key=lambda x: int(x)))
        for a, b in apn_to_bids.items()
    }
    log.info("  %d buildings matched -> %d parcels with at least one primary building",
             n_matched, len(out))
    return out


# ── 5. APO_ADDRESS from Parcels FeatureService ───────────────────────────────
def load_addresses() -> dict:
    """Paginated pull of APN → APO_ADDRESS from Parcels FeatureService."""
    log.info("Loading addresses from %s", PARCELS_FS)
    base = f"{PARCELS_FS}/query"
    common = {
        "where": "APN IS NOT NULL",
        "outFields": "APN,APO_ADDRESS",
        "returnGeometry": "false",
        "orderByFields": "OBJECTID ASC",
        "f": "json",
    }
    out: dict[str, str] = {}
    offset = 0
    page = 2000
    while True:
        params = {**common, "resultOffset": offset, "resultRecordCount": page}
        url = f"{base}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = json.loads(resp.read())
        feats = data.get("features", [])
        if not feats:
            break
        for f in feats:
            a = f["attributes"]
            apn = a.get("APN")
            addr = a.get("APO_ADDRESS")
            if apn:
                canon = canonical_apn(str(apn).strip())
                if canon and addr:
                    # Some APNs have multiple rows — keep first non-empty
                    out.setdefault(canon, str(addr).strip())
        log.info("  page offset=%d: +%d (running total %d unique APNs with address)",
                 offset, len(feats), len(out))
        if not data.get("exceededTransferLimit") and len(feats) < page:
            break
        offset += page
    log.info("  %d APNs with APO_ADDRESS", len(out))
    return out


# ── 6. Compose and explode ───────────────────────────────────────────────────
def main() -> None:
    log.info("=" * 70)
    log.info("BUILD RESIDENTIAL UNITS INVENTORY (2025)")
    log.info("=" * 70)

    df = load_pdh_2025_yrbuilt()
    redev = detect_year_redeveloped()
    previous = build_previous_apns_map()
    transactions = build_transaction_id_map()
    permits = build_permit_map()
    source_map, pool_map = build_status_maps()
    bldgs = build_building_id_map()
    addrs = load_addresses()

    # Per-APN lookups
    df["Year_Redeveloped"] = df["APN_canon"].map(redev).astype("Int64")
    df["Previous_APNs"] = df["APN_canon"].map(
        lambda a: ";".join(previous.get(a, [])) if previous.get(a) else "")
    df["Transaction_ID"] = df["APN_canon"].map(
        lambda a: ";".join(transactions.get(a, [])) if transactions.get(a) else "")
    df["Permit_Number"] = df["APN_canon"].map(permits).fillna("")
    df["Building_IDs"] = df["APN_canon"].map(bldgs).fillna("")
    df["Address"] = df["APN_canon"].map(addrs).fillna("")

    df = df.rename(columns={"COMBINED_YEAR_BUILT": "Original_Year_Built"})
    df["Original_Year_Built"] = pd.to_numeric(df["Original_Year_Built"],
                                              errors="coerce").astype("Int64")

    # Explode: one row per unit
    rows = []
    for r in df.itertuples(index=False):
        n = int(r.Residential_Units)
        era = era_from_year(r.Original_Year_Built)
        pre_alloc_era = era in ("Pre-1987 Plan", "1987 Plan")
        # Source: from transactions map, else "Existing" for pre-alloc eras, else "Unknown"
        source = source_map.get(r.APN_canon)
        if source is None:
            source = "Existing" if pre_alloc_era else "Unknown"
        # Pool: from transactions map; "N/A (Pre-Allocation)" for pre-alloc eras; else "Unknown"
        pool = pool_map.get(r.APN_canon)
        if pool is None:
            pool = "N/A (Pre-Allocation)" if pre_alloc_era else "Unknown"

        for seq in range(1, n + 1):
            rows.append({
                "Residential_Unit_ID":  f"RU-{r.APN_canon}-{seq:03d}",
                "APN":                  r.APN,
                "APN_canon":            r.APN_canon,
                "Previous_APNs":        r.Previous_APNs,
                "Original_Year_Built":  r.Original_Year_Built,
                "Year_Redeveloped":     r.Year_Redeveloped,
                "Era":                  era,
                "Source":               source,
                "Pool":                 pool,
                "Transaction_ID":       r.Transaction_ID,
                "Permit_Number":        r.Permit_Number,
                "Building_IDs":         r.Building_IDs,
                "Address":              r.Address,
                "COUNTY":               r.COUNTY,
                "JURISDICTION":         r.JURISDICTION,
            })

    out = pd.DataFrame(rows)
    log.info("Exploded to %d unit rows from %d parcels", len(out), len(df))

    # Cast nullable Int64 for clean CSV
    for col in ("Original_Year_Built", "Year_Redeveloped"):
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")

    out_path = Path(RESIDENTIAL_UNITS_INVENTORY_CSV)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)

    log.info("=" * 70)
    log.info("Wrote %d unit rows -> %s", len(out), out_path)
    log.info("=" * 70)

    # Quick summary
    log.info("Summary:")
    log.info("  units with Original_Year_Built populated: %d (%.1f%%)",
             int(out["Original_Year_Built"].notna().sum()),
             100 * out["Original_Year_Built"].notna().mean())
    log.info("  units with Year_Redeveloped populated:    %d (%.1f%%)",
             int(out["Year_Redeveloped"].notna().sum()),
             100 * out["Year_Redeveloped"].notna().mean())
    log.info("  units with Previous_APNs populated:       %d",
             int((out["Previous_APNs"] != "").sum()))
    log.info("  units with Transaction_ID populated:      %d",
             int((out["Transaction_ID"] != "").sum()))
    log.info("  units with Permit_Number populated:       %d",
             int((out["Permit_Number"] != "").sum()))
    log.info("  units with Building_IDs populated:        %d",
             int((out["Building_IDs"] != "").sum()))
    log.info("  units with Address populated:             %d",
             int((out["Address"] != "").sum()))

    log.info("Era distribution:")
    for k, v in out["Era"].value_counts().items():
        log.info("  %-30s %d (%.1f%%)", k, v, 100 * v / len(out))
    log.info("Source distribution:")
    for k, v in out["Source"].value_counts().items():
        log.info("  %-30s %d (%.1f%%)", k, v, 100 * v / len(out))
    log.info("Pool distribution:")
    for k, v in out["Pool"].value_counts().items():
        log.info("  %-30s %d (%.1f%%)", k, v, 100 * v / len(out))


if __name__ == "__main__":
    main()
