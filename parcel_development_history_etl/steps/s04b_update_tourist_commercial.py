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
)
from utils import get_logger, el_pad, el_depad, _EL_2D, _EL_3D

log = get_logger("s04b_tourist_commercial")


def _safe_num(val) -> float:
    if val is None:
        return 0.0
    try:
        v = float(val)
        return 0.0 if math.isnan(v) else v
    except (TypeError, ValueError):
        return 0.0


# ── El Dorado APN fix ─────────────────────────────────────────────────────────

def _build_el_dorado_maps() -> tuple[dict, dict]:
    """Return (pad_map, depad_map) for El Dorado APNs, same as s02."""
    el_2d: set = set()
    with arcpy.da.SearchCursor(OUTPUT_FC, [FC_APN],
                               where_clause="COUNTY = 'EL'") as cur:
        for (apn,) in cur:
            if apn:
                a = str(apn).strip()
                if _EL_2D.match(a):
                    el_2d.add(a)
    pad_map   = {a: el_pad(a)   for a in el_2d}
    depad_map = {a: el_depad(a) for a in
                 {el_pad(a) for a in el_2d} if _EL_3D.match(el_pad(a))}
    return pad_map, depad_map


def _apply_el_dorado_fix(df: pd.DataFrame, pad_map: dict, depad_map: dict) -> pd.DataFrame:
    def _fix(row):
        a, y = row["APN"], row["Year"]
        if a in pad_map   and y >= EL_PAD_YEAR: return pad_map[a]
        if a in depad_map and y <  EL_PAD_YEAR: return depad_map[a]
        return a
    before = df["APN"].copy()
    df["APN"] = df.apply(_fix, axis=1)
    changed = (df["APN"] != before).sum()
    log.info("  El Dorado fix: %d rows APN-fixed", changed)
    return df


# ── Genealogy ─────────────────────────────────────────────────────────────────

def _load_genealogy() -> pd.DataFrame:
    """Load and filter the master genealogy table (in_fc_new=1)."""
    if not Path(GENEALOGY_TAHOE).exists():
        return pd.DataFrame()
    gen = pd.read_csv(GENEALOGY_TAHOE, dtype=str)
    gen.columns = gen.columns.str.strip()
    gen["is_primary"]      = pd.to_numeric(gen.get("is_primary",      pd.Series()), errors="coerce").fillna(0).astype(int)
    gen["in_fc_new"]       = pd.to_numeric(gen.get("in_fc_new",       pd.Series()), errors="coerce").fillna(0).astype(int)
    gen["source_priority"] = pd.to_numeric(gen.get("source_priority", pd.Series()), errors="coerce").fillna(4).astype(int)
    gen = gen[(gen["is_primary"] == 1) & (gen["in_fc_new"] == 1)].copy()
    gen["change_year"] = pd.to_numeric(gen["change_year"], errors="coerce")
    gen = gen.dropna(subset=["change_year"])
    gen["change_year"] = gen["change_year"].astype(int)
    return gen.sort_values(["source_priority", "change_year"])


def _apply_genealogy(df: pd.DataFrame, gen: pd.DataFrame, label: str) -> pd.DataFrame:
    """Apply pre-loaded genealogy table to df APN column."""
    if gen.empty:
        log.info("  Genealogy master not found — skipping for %s", label)
        return df

    remapped: set = set()
    subs = 0
    for _, rec in gen.iterrows():
        old, new, cy = rec["apn_old"], rec["apn_new"], int(rec["change_year"])
        if old == new or old in remapped:
            continue
        mask = (df["APN"] == old) & (df["Year"] >= cy)
        if not mask.any():
            continue
        existing_new = set(df.loc[df["APN"] == new, "Year"])
        safe = mask & ~df["Year"].isin(existing_new)
        if safe.any():
            df.loc[safe, "APN"] = new
            remapped.add(old)
            subs += 1

    log.info("  Genealogy: %d APN substitutions for %s", subs, label)
    return df


# ── CSV loaders ───────────────────────────────────────────────────────────────

def _load_wide_csv(csv_path: str, label: str,
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

    year_cols = [c for c in df_wide.columns if c.upper().startswith("CY")]
    if not year_cols:
        log.warning("  %s CSV has no CY<year> columns — skipping", label)
        return {}

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

    df = _apply_el_dorado_fix(df, pad_map, depad_map)
    if gen is not None:
        df = _apply_genealogy(df, gen, label)

    # Drop zero rows (no-match rows stay 0 in FC, no need to write them)
    df_nonzero = df[df["Value"] > 0]
    lookup = {(row.APN, row.Year): row.Value for row in df_nonzero.itertuples(index=False)}
    log.info("  %s lookup: %d non-zero (APN, Year) entries", label, len(lookup))
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

    pad_map, depad_map = _build_el_dorado_maps()
    gen = _load_genealogy()
    if not gen.empty:
        log.info("Genealogy master: %d apply-ready rows", len(gen))
    else:
        log.info("Genealogy master not found — APN corrections skipped")

    tourist_lookup    = _load_wide_csv(TOURIST_UNITS_CSV,    "Tourist units",   pad_map, depad_map, gen)
    commercial_lookup = _load_wide_csv(COMMERCIAL_SQFT_CSV,  "Commercial sqft", pad_map, depad_map, gen)

    if not tourist_lookup and not commercial_lookup:
        log.info("No tourist or commercial data to write — skipping FC update.")
        log.info("Step 4b complete.")
        return

    log.info("Writing to OUTPUT_FC...")
    _write_to_fc(tourist_lookup, commercial_lookup)
    log.info("Step 4b complete.")
