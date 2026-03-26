"""
Quick check: are the ~600 UNKNOWN APNs missing from FC in 2018+ all El Dorado?
"""
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parents[1]))

import arcpy
from config import OUTPUT_FC, FC_APN, FC_YEAR, QA_LOST_APNS

# Get UNKNOWN APNs
unknown_apns = set()
with arcpy.da.SearchCursor(QA_LOST_APNS, ["APN", "Issue_Category"]) as cur:
    for apn, cat in cur:
        if cat == "UNKNOWN":
            unknown_apns.add(str(apn).strip())

# Build FC presence + county
fc_info = {}  # apn -> {years: set, county: str}
with arcpy.da.SearchCursor(OUTPUT_FC, [FC_APN, FC_YEAR, "COUNTY"]) as cur:
    for apn, yr, county in cur:
        if not apn:
            continue
        a = str(apn).strip()
        if a in unknown_apns:
            if a not in fc_info:
                fc_info[a] = {"years": set(), "county": county or ""}
            fc_info[a]["years"].add(int(yr))

# APNs missing from FC in 2018 but present in 2017
missing_2018 = set()
county_of_missing = Counter()
for apn in unknown_apns:
    info = fc_info.get(apn, {"years": set(), "county": ""})
    if 2018 not in info["years"] and 2017 in info["years"]:
        missing_2018.add(apn)
        county_of_missing[info["county"]] += 1

print(f"APNs in FC for 2017 but NOT 2018: {len(missing_2018)}")
print(f"By county: {dict(county_of_missing)}")

# Check: do these APNs have a padded version in the FC for 2018?
print("\nChecking for padded variants in 2018+ ...")
fc_2018_apns = set()
with arcpy.da.SearchCursor(OUTPUT_FC, [FC_APN], "YEAR = 2018") as cur:
    for (apn,) in cur:
        if apn:
            fc_2018_apns.add(str(apn).strip())

from utils import el_pad, _EL_2D
padded_found = 0
for apn in missing_2018:
    if _EL_2D.match(apn):
        padded = el_pad(apn)
        if padded in fc_2018_apns:
            padded_found += 1

print(f"  Missing APNs whose padded version IS in 2018 FC: {padded_found}")
print(f"  (out of {len(missing_2018)} missing)")

# Now check: ALL unknown APNs missing from 2012 — by county
missing_2012_county = Counter()
for apn in unknown_apns:
    info = fc_info.get(apn, {"years": set(), "county": ""})
    if 2012 not in info["years"]:
        county = info["county"] if info["county"] else "NO_COUNTY"
        missing_2012_county[county] += 1

print(f"\nAPNs missing 2012 by county: {dict(missing_2012_county)}")
