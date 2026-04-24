"""
Step 4b — Write TouristAccommodation_Units (and CommercialFloorArea_SqFt when
available) to the output feature class.

Sources
-------
  TouristUnits_2012to2025.csv   — wide format, APN x CY2012..CY2025
  CommercialFloorArea CSV       — same wide format (path set in config when ready)

Processing
----------
  1. Load CSV, melt to long format (APN, Year, value)
  2. Apply El Dorado APN fix (same padding/depadding logic as s02)
  3. Apply genealogy from master table (same apn_genealogy_tahoe.csv used in s02b)
  4. Build {(APN, Year): value} lookup
  5. Write to OUTPUT_FC in a single UpdateCursor pass — null / missing = 0

For tourist units the write is simple: CSV value wins, no FC-native reconciliation.
"""
import math
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))

from pathlib import Path

import arcpy
import pandas as pd

from config import (
    OUTPUT_FC, FC_APN, FC_YEAR, CSV_YEARS,
    EL_PAD_YEAR,
    TOURIST_UNITS_CSV, COMMERCIAL_SQFT_CSV,
    GENEALOGY_TAHOE,
    FC_TOURIST_UNITS, FC_COMMERCIAL_SQFT,
    CSV_TOURIST_YEAR_PREFIX, CSV_COMMERCIAL_YEAR_PREFIX,
    QA_DATA_DIR,
)
from utils import get_logger, build_el_dorado_fix, apply_el_dorado_fix
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))  # steps/
from s02b_genealogy import _load_master_table, _apply_vectorized

log = get_logger("s04b_tourist_commercial")


def _safe_num(val) -> float:
    if val is None:
        return 0.0
    try:
        v = float(val)
        return 0.0 if math.isnan(v) else v
    except (TypeError, ValueError):
        return 0.0


# ── CSV loaders ───────────────────────────────────────────────────────────────

def _load_wide_csv(csv_path: str, label: str, year_prefix: str,
                   pad_map: dict, depad_map: dict,
                   gen: pd.DataFrame = None) -> dict:
    """
    Load a wide-format APN x CY<year> CSV.
    Returns {(APN, Year): value} lookup.
    """
    if not Path(csv_path).exists():
        log.info("  %s CSV not found at %s — skipping", label, csv_path)
        return {}

    df_wide = pd.read_csv(csv_path, dtype=str)

    # Normalise APN column — may be named "APN" or "Row Labels"
    if "APN" not in df_wide.columns:
        first = df_wide.columns[0]
        df_wide = df_wide.rename(columns={first: "APN"})

    df_wide = df_wide.dropna(subset=["APN"])
    df_wide = df_wide[df_wide["APN"].str.strip() != ""]

    year_cols = [c for c in df_wide.columns if c.upper().startswith(year_prefix.upper())]
    if not year_cols:
        raise ValueError(
            f"{label} CSV: no year columns found. "
            f"Expected columns starting with '{year_prefix}'. "
            f"Check CSV format at {csv_path}"
        )

    log.info("  %s CSV: %d parcels, %d year columns", label, len(df_wide), len(year_cols))

    df = df_wide.melt(
        id_vars="APN",
        value_vars=year_cols,
        var_name="Year_Label",
        value_name="Value",
    )
    df["Year"]  = df["Year_Label"].str.extract(r"(\d{4})").astype(int)
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce").fillna(0)
    df = df[df["Year"].isin(CSV_YEARS)][["APN", "Year", "Value"]].copy()
    df["APN"]   = df["APN"].astype(str).str.strip()

    df = apply_el_dorado_fix(df, pad_map, depad_map, EL_PAD_YEAR)
    if gen is not None and not gen.empty:
        df, _ = _apply_vectorized(df, gen, old_col="apn_old", new_col="apn_new")
        log.info("  Genealogy applied for %s", label)

    # Drop zero rows (no-match rows stay 0 in FC, no need to write them)
    df_nonzero = df[df["Value"] > 0]
    lookup = {(row.APN, row.Year): row.Value for row in df_nonzero.itertuples(index=False)}
    log.info("  %s lookup: %d non-zero (APN, Year) entries", label, len(lookup))
    return lookup


# ── Crosswalk application ─────────────────────────────────────────────────────

def _apply_crosswalk(lookup: dict, label: str) -> dict:
    """
    Apply S03's QA_APN_Crosswalk to a (APN, Year) -> value lookup.

    For each crosswalk row (CSV_APN → FC_APN, Year): if the lookup has a value
    keyed on (CSV_APN, Year), sum that value onto (FC_APN, Year) so the write
    step lands on the FC parcel that actually exists for that year.  Without
    this, genealogy-remapped APNs whose target row is absent from OUTPUT_FC
    have their units silently dropped by UpdateCursor.
    """
    xw_path = Path(QA_DATA_DIR) / "QA_APN_Crosswalk.csv"
    if not xw_path.exists():
        log.info("  %s: QA_APN_Crosswalk.csv not found — skipping crosswalk application.", label)
        return lookup

    xw = pd.read_csv(xw_path, dtype=str)
    moved = 0
    for _, row in xw.iterrows():
        csv_apn = str(row["CSV_APN"]).strip()
        fc_apn  = str(row["FC_APN"]).strip()
        year    = int(row["Year"])
        if csv_apn == fc_apn:
            continue
        val = lookup.get((csv_apn, year))
        if val and val > 0:
            lookup[(fc_apn, year)] = lookup.get((fc_apn, year), 0) + val
            moved += 1

    log.info("  %s: crosswalk applied — %d values summed onto FC parent APN rows",
             label, moved)
    return lookup


# ── FC writer ─────────────────────────────────────────────────────────────────

def _write_to_fc(tourist_lookup: dict, commercial_lookup: dict) -> None:
    year_list    = ", ".join(str(y) for y in CSV_YEARS)
    where_clause = f"{FC_YEAR} IN ({year_list})"

    t_updated = c_updated = 0

    with arcpy.da.UpdateCursor(
            OUTPUT_FC,
            [FC_APN, FC_YEAR, FC_TOURIST_UNITS, FC_COMMERCIAL_SQFT],
            where_clause) as cur:

        for apn, yr, _, _ in cur:
            if not apn or not yr:
                continue
            key = (str(apn).strip(), int(yr))

            t_val = tourist_lookup.get(key, 0)
            c_val = commercial_lookup.get(key, 0)

            if t_val > 0: t_updated += 1
            if c_val > 0: c_updated += 1

            cur.updateRow([apn, yr, int(t_val), float(c_val)])

    log.info("  %s: %d rows with non-zero value written", FC_TOURIST_UNITS,   t_updated)
    log.info("  %s: %d rows with non-zero value written", FC_COMMERCIAL_SQFT, c_updated)


# ── Public entry point ────────────────────────────────────────────────────────

def run() -> None:
    log.info("=== Step 4b: Update Tourist & Commercial attributes ===")

    pad_map, depad_map = build_el_dorado_fix(OUTPUT_FC, FC_APN)
    log.info("El Dorado pad map: %d APNs, depad map: %d APNs",
             len(pad_map), len(depad_map))

    gen = _load_master_table(GENEALOGY_TAHOE)
    if not gen.empty:
        log.info("Genealogy master: %d apply-ready rows", len(gen))
    else:
        log.info("Genealogy master not found — APN corrections skipped")

    tourist_lookup    = _load_wide_csv(TOURIST_UNITS_CSV,    "Tourist units",
                                       CSV_TOURIST_YEAR_PREFIX,   pad_map, depad_map, gen)
    commercial_lookup = _load_wide_csv(COMMERCIAL_SQFT_CSV,  "Commercial sqft",
                                       CSV_COMMERCIAL_YEAR_PREFIX, pad_map, depad_map, gen)

    # Re-route post-genealogy APNs whose target FC row is missing to their
    # spatial parent (same rescue S03 does for residential csv_lookup).
    tourist_lookup    = _apply_crosswalk(tourist_lookup,    "Tourist units")
    commercial_lookup = _apply_crosswalk(commercial_lookup, "Commercial sqft")

    if not tourist_lookup and not commercial_lookup:
        log.info("No tourist or commercial data to write — skipping FC update.")
        log.info("Step 4b complete.")
        return

    log.info("Writing to OUTPUT_FC...")
    _write_to_fc(tourist_lookup, commercial_lookup)
    log.info("Step 4b complete.")
