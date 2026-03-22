"""
Step 4 — Write Residential_Units to the output feature class.

Strategy:
  - Every row in the output FC is set to the CSV value for (APN, Year).
  - Rows with no CSV match are set to 0.
  - The csv_lookup already incorporates crosswalk entries from Step 3.
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


def run(csv_lookup: dict) -> None:
    log.info("=== Step 4: Update Residential_Units ===")

    year_list    = ", ".join(str(y) for y in CSV_YEARS)
    where_clause = f"{FC_YEAR} IN ({year_list})"

    matched = 0
    zeroed  = 0
    updated = 0

    with arcpy.da.UpdateCursor(
            OUTPUT_FC, ["OID@", FC_APN, FC_YEAR, FC_UNITS],
            where_clause) as cur:
        for oid, apn, yr, _ in cur:
            if apn and yr:
                key = (str(apn).strip(), int(yr))
                val = csv_lookup.get(key)
                if val is not None:
                    new_val = _safe_int(val)
                    matched += 1
                else:
                    new_val = 0
                    zeroed  += 1
                cur.updateRow([oid, apn, yr, new_val])
                updated += 1

    log.info("Rows updated        : %d", updated)
    log.info("  Matched to CSV    : %d", matched)
    log.info("  Defaulted to 0    : %d", zeroed)
    log.info("Step 4 complete.")


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    import s02_load_csv as s02
    import s03_crosswalk as s03
    df_csv, lu = s02.run()
    lu = s03.run(df_csv, lu)
    run(lu)
