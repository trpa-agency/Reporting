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
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))

import pandas as pd

from config import (CSV_PATH, OUTPUT_FC, FC_APN, FC_YEAR,
                    EL_PAD_YEAR, CSV_YEARS, CSV_RESIDENTIAL_YEAR_MARKER)
from utils  import get_logger, build_el_dorado_fix, apply_el_dorado_fix
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))  # steps/
import s02b_genealogy

log = get_logger("s02_load_csv")


def run() -> tuple[pd.DataFrame, dict]:
    log.info("=== Step 2: Load CSV and build csv_lookup ===")

    # -- Load wide CSV --------------------------------------------------------
    df_wide   = pd.read_csv(CSV_PATH)
    year_cols = [c for c in df_wide.columns if CSV_RESIDENTIAL_YEAR_MARKER in c]
    if not year_cols:
        raise ValueError(
            f"Residential CSV: no year columns found. "
            f"Expected columns containing '{CSV_RESIDENTIAL_YEAR_MARKER}'. "
            f"Check CSV format at {CSV_PATH}"
        )
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
    log.info("Building El Dorado APN maps from output FC ...")
    pad_map, depad_map = build_el_dorado_fix(OUTPUT_FC, FC_APN)
    log.info("  APNs to pad   (Year>=%d): %d", EL_PAD_YEAR, len(pad_map))
    log.info("  APNs to depad (Year< %d): %d", EL_PAD_YEAR, len(depad_map))

    df_csv["APN_orig"] = df_csv["APN"].copy()
    df_csv = apply_el_dorado_fix(df_csv, pad_map, depad_map, EL_PAD_YEAR)
    changed = (df_csv["APN"] != df_csv["APN_orig"]).sum()
    log.info("  CSV rows APN-fixed: %d", changed)

    # Resolve duplicate (APN, Year) rows that arise when the source CSV already
    # contains both the 2-digit and 3-digit form of an El Dorado APN (coworker
    # manually split the format change across two rows).  The El Dorado fix
    # transforms one form into the other, creating two rows for the same key —
    # one with the real unit count and one with 0.  Keep the max (non-zero) value.
    n_before = len(df_csv)
    df_csv = (df_csv.groupby(["APN", "Year"], as_index=False)["Units_CSV"]
                    .max()
                    .assign(APN_orig=lambda d: d["APN"]))  # restore APN_orig col
    n_dupes = n_before - len(df_csv)
    if n_dupes:
        log.info("  EL split-format dedup: removed %d duplicate (APN, Year) rows "
                 "(kept max units per key)", n_dupes)

    # -- Genealogy APN corrections --------------------------------------------
    # Apply known old→new APN substitutions by year before building the lookup,
    # so csv_lookup references the correct current APN for each year.
    df_csv = s02b_genealogy.run(df_csv)

    # -- Post-genealogy dedup -------------------------------------------------
    # Genealogy substitution changes old_APN rows to new_APN.  If new_APN
    # already had a 0-unit row for that year (not treated as a conflict), df_csv
    # now has TWO rows for the same (APN, Year): the original 0-unit row and the
    # substituted non-zero row.  The dict comprehension below is last-write-wins,
    # so whichever row iterates last wins — the 0-unit row can silently overwrite
    # the real value.  Deduplicate by keeping the MAX so the non-zero value wins.
    n_before_gen = len(df_csv)
    df_csv = (df_csv.groupby(["APN", "Year"], as_index=False)["Units_CSV"]
                    .max()
                    .assign(APN_orig=lambda d: d["APN"]))
    n_dupes_gen = n_before_gen - len(df_csv)
    if n_dupes_gen:
        log.info("  Post-genealogy dedup: removed %d duplicate (APN, Year) rows "
                 "(kept max units per key)", n_dupes_gen)

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
