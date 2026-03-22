"""
Step 2 — Load CSV and build csv_lookup.

 - Reads ExistingResidential CSV (wide format)
 - Melts to long format (APN x Year x Units)
 - Applies El Dorado APN suffix fix (COUNTY='EL', Year >= 2018)
 - Returns df_csv and csv_lookup dict for downstream steps

Returns
-------
df_csv     : DataFrame  — long-format CSV with APN (fixed), Year, Units_CSV
csv_lookup : dict       — (APN, Year) → int units  (includes 0-unit rows)
"""
import re
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))

import arcpy
import pandas as pd

from config import (CSV_PATH, OUTPUT_FC, FC_APN, FC_YEAR, FC_COUNTY,
                    EL_PAD_YEAR, CSV_YEARS)
from utils  import get_logger

log = get_logger("s02_load_csv")

_2D = re.compile(r"^(\d{3}-\d{2,3})-(\d{2})$")
_3D = re.compile(r"^(\d{3}-\d{2,3})-0(\d{2})$")


def _pad(apn: str) -> str:
    m = _2D.match(apn)
    return f"{m.group(1)}-0{m.group(2)}" if m else apn


def _depad(apn: str) -> str:
    m = _3D.match(apn)
    return f"{m.group(1)}-{m.group(2)}" if m else apn


def _build_el_dorado_sets() -> tuple[set, set]:
    """
    Read the output FC to find El Dorado APNs (COUNTY='EL').
    Returns (el_2digit_apns, el_3digit_apns).
    """
    el_2d, el_3d = set(), set()
    with arcpy.da.SearchCursor(OUTPUT_FC, [FC_APN, FC_COUNTY]) as cur:
        for apn, county in cur:
            if county == "EL" and apn:
                apn = str(apn).strip()
                if _2D.match(apn):
                    el_2d.add(apn)
                elif _3D.match(apn):
                    el_3d.add(apn)
    return el_2d, el_3d


def run() -> tuple[pd.DataFrame, dict]:
    log.info("=== Step 2: Load CSV and build csv_lookup ===")

    # -- Load wide CSV --------------------------------------------------------
    df_wide   = pd.read_csv(CSV_PATH)
    year_cols = [c for c in df_wide.columns if "Final" in c]
    log.info("CSV: %d parcels, %d year columns (%s)",
             len(df_wide), len(year_cols),
             ", ".join(c[:4] for c in year_cols))

    # -- Melt to long format --------------------------------------------------
    df_csv = df_wide.melt(
        id_vars   = "APN",
        value_vars = year_cols,
        var_name  = "Year_Label",
        value_name= "Units_CSV",
    )
    df_csv["Year"]     = df_csv["Year_Label"].str.extract(r"(\d{4})").astype(int)
    df_csv["Units_CSV"]= pd.to_numeric(df_csv["Units_CSV"], errors="coerce").fillna(0).astype(int)
    df_csv = df_csv[df_csv["Year"].isin(CSV_YEARS)][["APN","Year","Units_CSV"]].copy()
    df_csv["APN"] = df_csv["APN"].astype(str).str.strip()
    log.info("Long format: %d rows  (%d–%d)",
             len(df_csv), df_csv["Year"].min(), df_csv["Year"].max())

    # -- El Dorado APN fix ---------------------------------------------------
    log.info("Building El Dorado APN sets from output FC ...")
    el_2d, el_3d = _build_el_dorado_sets()
    log.info("  EL 2-digit APNs in FC : %d", len(el_2d))
    log.info("  EL 3-digit APNs in FC : %d", len(el_3d))

    # Pad: CSV has 2-digit, FC has 3-digit for Year >= EL_PAD_YEAR
    pad_candidates = {a for a in df_csv["APN"].unique()
                      if _2D.match(str(a)) and a in el_2d}
    # Depad: CSV has 3-digit for all years, FC has 2-digit for Year < EL_PAD_YEAR
    depad_candidates = {a for a in df_csv["APN"].unique()
                        if _3D.match(str(a)) and _depad(a) in el_2d}

    pad_map   = {a: _pad(a)   for a in pad_candidates}
    depad_map = {a: _depad(a) for a in depad_candidates}
    log.info("  APNs to pad   (Year>=%d): %d", EL_PAD_YEAR, len(pad_map))
    log.info("  APNs to depad (Year< %d): %d", EL_PAD_YEAR, len(depad_map))

    df_csv["APN_orig"] = df_csv["APN"].copy()

    def _fix(row):
        a, y = row["APN"], row["Year"]
        if a in pad_map   and y >= EL_PAD_YEAR: return pad_map[a]
        if a in depad_map and y <  EL_PAD_YEAR: return depad_map[a]
        return a

    df_csv["APN"] = df_csv.apply(_fix, axis=1)
    changed = (df_csv["APN"] != df_csv["APN_orig"]).sum()
    log.info("  CSV rows APN-fixed: %d", changed)

    # -- Build csv_lookup -----------------------------------------------------
    csv_lookup = {
        (row.APN, row.Year): row.Units_CSV
        for row in df_csv.itertuples(index=False)
    }
    log.info("csv_lookup entries: %d", len(csv_lookup))
    log.info("Step 2 complete.")

    return df_csv, csv_lookup


if __name__ == "__main__":
    df, lu = run()
    print(df.head())
