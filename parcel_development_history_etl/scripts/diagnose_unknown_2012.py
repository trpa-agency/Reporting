"""
Confirm: how many UNKNOWN APNs are missing from the FC specifically in 2012?
And how many of those exist in the FC for 2013?
"""
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parents[1]))

import arcpy
import pandas as pd

from config import OUTPUT_FC, FC_APN, FC_YEAR, FC_UNITS, QA_LOST_APNS, CSV_YEARS

# 1. Get UNKNOWN APNs
unknown_apns = set()
with arcpy.da.SearchCursor(QA_LOST_APNS, ["APN", "Issue_Category"]) as cur:
    for apn, cat in cur:
        if cat == "UNKNOWN":
            unknown_apns.add(str(apn).strip())
print(f"UNKNOWN APNs: {len(unknown_apns)}")

# 2. Build FC presence map: APN -> set of years
fc_years = {}  # apn -> set of years present
fc_units = {}  # (apn, year) -> units
with arcpy.da.SearchCursor(OUTPUT_FC, [FC_APN, FC_YEAR, FC_UNITS]) as cur:
    for apn, yr, units in cur:
        if not apn:
            continue
        a = str(apn).strip()
        y = int(yr) if yr else 0
        if a in unknown_apns:
            fc_years.setdefault(a, set()).add(y)
            fc_units[(a, y)] = units or 0

# 3. For each UNKNOWN APN, check 2012 presence
missing_2012 = set()
has_2012 = set()
missing_2012_has_2013 = set()

for apn in unknown_apns:
    years = fc_years.get(apn, set())
    if 2012 not in years:
        missing_2012.add(apn)
        if 2013 in years:
            missing_2012_has_2013.add(apn)
    else:
        has_2012.add(apn)

print(f"\nMissing 2012 FC row: {len(missing_2012)} / {len(unknown_apns)}")
print(f"Has 2012 FC row:     {len(has_2012)}")
print(f"Missing 2012 but has 2013: {len(missing_2012_has_2013)}")

# 4. For APNs that HAVE 2012, why are they UNKNOWN?
if has_2012:
    print(f"\nAPNs with 2012 FC row ({len(has_2012)}):")
    print("  Checking which years are actually lost (FC_Units=0 but CSV>0) ...")

    # Read CSV to know which years have units > 0
    from config import CSV_PATH
    df_csv = pd.read_csv(CSV_PATH, dtype=str)
    year_cols = [c for c in df_csv.columns if "Final" in c]
    df_long = df_csv.melt(id_vars="APN", value_vars=year_cols,
                          var_name="YL", value_name="Units")
    df_long["Year"] = df_long["YL"].str.extract(r"(\d{4})").astype(int)
    df_long["Units"] = pd.to_numeric(df_long["Units"], errors="coerce").fillna(0)
    df_long["APN"] = df_long["APN"].astype(str).str.strip()
    csv_pos = set(zip(df_long.loc[df_long["Units"] > 0, "APN"],
                      df_long.loc[df_long["Units"] > 0, "Year"]))

    for apn in sorted(has_2012)[:20]:
        years = sorted(fc_years.get(apn, set()))
        lost = []
        for y in CSV_YEARS:
            if (apn, y) in csv_pos:
                u = fc_units.get((apn, y), -1)
                if u == 0 or (apn, y) not in fc_units:
                    lost.append(y)
        print(f"  {apn}: FC years={years}, lost years={lost}")

# 5. Summary: per-year missing count for all UNKNOWN APNs
print("\nPer-year: how many UNKNOWN APNs are missing from the FC?")
for yr in sorted(CSV_YEARS):
    missing = sum(1 for apn in unknown_apns if yr not in fc_years.get(apn, set()))
    has_zero = sum(1 for apn in unknown_apns
                   if yr in fc_years.get(apn, set()) and fc_units.get((apn, yr), 0) == 0)
    has_units = sum(1 for apn in unknown_apns
                    if yr in fc_years.get(apn, set()) and fc_units.get((apn, yr), 0) > 0)
    print(f"  {yr}: missing={missing:5d}  zero_units={has_zero:4d}  has_units={has_units:5d}")
