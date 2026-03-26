"""
Report: FC-native residential unit parcels in SOURCE_FC.

Extracts all APN x Year rows from SOURCE_FC that have non-null, non-zero
Residential_Units values.  These are the curated unit values from prior team
efforts that the service-built FC no longer carries.

Outputs:
  data/raw_data/fc_native_residential_units.csv
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(Path(__file__).parents[1]))

import arcpy
import pandas as pd

from config import SOURCE_FC, FC_APN, FC_YEAR, FC_UNITS, FC_NATIVE_YEARS

OUT_CSV = ROOT / "data" / "raw_data" / "fc_native_residential_units.csv"


def run():
    print(f"Reading SOURCE_FC: {SOURCE_FC}")
    print(f"FC_NATIVE_YEARS: {FC_NATIVE_YEARS}")

    # Build WHERE clause for native years only
    yr_list = ", ".join(str(y) for y in FC_NATIVE_YEARS)
    where = f"{FC_YEAR} IN ({yr_list}) AND {FC_UNITS} IS NOT NULL AND {FC_UNITS} <> 0"

    rows = []
    with arcpy.da.SearchCursor(
            SOURCE_FC, [FC_APN, FC_YEAR, FC_UNITS, "COUNTY"], where) as cur:
        for apn, yr, units, county in cur:
            if apn:
                rows.append({
                    "APN": str(apn).strip(),
                    "Year": int(yr),
                    "Residential_Units": units,
                    "County": county,
                })

    df = pd.DataFrame(rows)
    print(f"\nTotal rows with FC-native units: {len(df)}")
    print(f"Unique APNs: {df['APN'].nunique()}")
    print(f"\nRows per year:")
    print(df.groupby("Year").agg(
        rows=("APN", "count"),
        unique_apns=("APN", "nunique"),
        total_units=("Residential_Units", "sum"),
    ).to_string())

    print(f"\nRows per county:")
    print(df.groupby("County").agg(
        rows=("APN", "count"),
        unique_apns=("APN", "nunique"),
        total_units=("Residential_Units", "sum"),
    ).to_string())

    df.to_csv(OUT_CSV, index=False)
    print(f"\nWritten to {OUT_CSV}")


if __name__ == "__main__":
    run()
