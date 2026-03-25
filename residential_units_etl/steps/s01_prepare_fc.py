"""
Step 1 — Prepare output feature class.

Copies Parcel_History_Attributed → Residential_Parcels_History,
keeping only rows for years in CSV_YEARS.  Drops and recreates
on every run so results are always fresh.
"""
import arcpy
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))

from config import SOURCE_FC, WORKING_FC, OUTPUT_FC, GDB, FC_YEAR, CSV_YEARS
from utils  import get_logger

log = get_logger("s01_prepare_fc")


def run() -> None:
    log.info("=== Step 1: Prepare output feature class ===")

    # Use cleaned working copy if available, otherwise fall back to original
    if arcpy.Exists(WORKING_FC):
        input_fc = WORKING_FC
        log.info("Using working copy: %s", WORKING_FC)
    else:
        input_fc = SOURCE_FC
        log.warning("Working copy not found — using original SOURCE_FC. "
                    "Run preprocess.py first for a cleaned input.")
        if not arcpy.Exists(SOURCE_FC):
            raise FileNotFoundError(f"Source FC not found: {SOURCE_FC}")

    # Drop existing output
    if arcpy.Exists(OUTPUT_FC):
        log.info("Deleting existing output FC: %s", OUTPUT_FC)
        arcpy.management.Delete(OUTPUT_FC)

    # Copy source → output, filtered to CSV_YEARS
    year_list    = ", ".join(str(y) for y in CSV_YEARS)
    where_clause = f"{FC_YEAR} IN ({year_list})"
    log.info("Copying %s → %s  WHERE %s", input_fc, OUTPUT_FC, where_clause)

    arcpy.conversion.FeatureClassToFeatureClass(
        in_features   = input_fc,
        out_path      = GDB,
        out_name      = "Residential_Parcels_History",
        where_clause  = where_clause,
    )

    # Verify
    count = int(arcpy.management.GetCount(OUTPUT_FC).getOutput(0))
    log.info("Output FC created with %d rows", count)

    # Quick year breakdown
    year_counts = {}
    with arcpy.da.SearchCursor(OUTPUT_FC, [FC_YEAR]) as cur:
        for (yr,) in cur:
            year_counts[yr] = year_counts.get(yr, 0) + 1

    log.info("Rows per year:")
    for yr in sorted(year_counts):
        log.info("  %d : %d rows", yr, year_counts[yr])

    log.info("Step 1 complete.")


if __name__ == "__main__":
    run()
