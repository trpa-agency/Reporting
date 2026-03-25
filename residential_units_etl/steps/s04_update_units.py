"""
Step 4 — Write Residential_Units to the output feature class.

Merge strategy (two curated sources):
  CSV + FC agree (same non-zero value) → BOTH_AGREE   write CSV value
  CSV has value, FC native = 0 / null  → CSV          write CSV value
  FC native has value, CSV has none    → FC_NATIVE     write FC native value
  Both have different non-zero values  → DISAGREE      write CSV value, flag

For years 2013–2017 the FC has no native unit data; those rows always
get source = CSV.

Two new fields are added to OUTPUT_FC so discrepancies are visible
directly on each parcel in ArcGIS Pro:
  FC_Native_Units  (LONG)  — unit value from SOURCE_FC before this ETL run
  Unit_Source      (TEXT)  — BOTH_AGREE | CSV | FC_NATIVE | DISAGREE
"""
import math
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))

import arcpy

from config import OUTPUT_FC, FC_APN, FC_YEAR, FC_UNITS, CSV_YEARS
from utils  import get_logger

log = get_logger("s04_update_units")


def _safe_int(val) -> int:
    if val is None:
        return 0
    try:
        if math.isnan(float(val)):
            return 0
    except (TypeError, ValueError):
        pass
    return int(val)


def _ensure_fields() -> None:
    """Add FC_Native_Units and Unit_Source to OUTPUT_FC if not present."""
    existing = {f.name for f in arcpy.ListFields(OUTPUT_FC)}
    if "FC_Native_Units" not in existing:
        arcpy.management.AddField(OUTPUT_FC, "FC_Native_Units", "LONG")
        log.info("Added field FC_Native_Units")
    if "Unit_Source" not in existing:
        arcpy.management.AddField(OUTPUT_FC, "Unit_Source", "TEXT",
                                  field_length=15)
        log.info("Added field Unit_Source")


def run(csv_lookup: dict) -> None:
    log.info("=== Step 4: Update Residential_Units ===")

    _ensure_fields()

    year_list    = ", ".join(str(y) for y in CSV_YEARS)
    where_clause = f"{FC_YEAR} IN ({year_list})"

    counts = {"CSV": 0, "FC_NATIVE": 0, "BOTH_AGREE": 0, "DISAGREE": 0, "ZERO": 0}
    updated = 0

    with arcpy.da.UpdateCursor(
            OUTPUT_FC,
            ["OID@", FC_APN, FC_YEAR, FC_UNITS,
             "FC_Native_Units", "Unit_Source"],
            where_clause) as cur:

        for oid, apn, yr, native_raw, _, _ in cur:
            if not apn or not yr:
                continue

            key    = (str(apn).strip(), int(yr))
            native = _safe_int(native_raw)   # FC value before this run
            csv_v  = csv_lookup.get(key)

            if csv_v is not None:
                csv_int = _safe_int(csv_v)
                if native > 0:
                    source = "BOTH_AGREE" if csv_int == native else "DISAGREE"
                else:
                    source = "CSV"
                merged = csv_int
            elif native > 0:
                merged = native
                source = "FC_NATIVE"
            else:
                merged = 0
                source = "CSV"

            if merged == 0 and source == "CSV":
                counts["ZERO"] += 1
            else:
                counts[source] += 1

            cur.updateRow([oid, apn, yr, merged, native, source])
            updated += 1

    log.info("Rows updated        : %d", updated)
    log.info("  BOTH_AGREE        : %d", counts["BOTH_AGREE"])
    log.info("  CSV (FC native=0) : %d", counts["CSV"])
    log.info("  FC_NATIVE         : %d  ← units FC has that CSV lacks",
             counts["FC_NATIVE"])
    log.info("  DISAGREE          : %d  ← both sources differ, CSV used",
             counts["DISAGREE"])
    log.info("  Zeroed            : %d", counts["ZERO"])
    log.info("Step 4 complete.")


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    import s02_load_csv as s02
    import s03_crosswalk as s03
    df_csv, lu = s02.run()
    lu = s03.run(df_csv, lu)
    run(lu)
