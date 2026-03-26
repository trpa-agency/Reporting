"""
Detailed diagnosis: for UNKNOWN APNs, compare the exact APN string
in the FC (per year) vs what the CSV El Dorado fix produces.
This reveals where the key mismatch in csv_lookup occurs.
"""
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parents[1]))

import arcpy
import pandas as pd

from config import (OUTPUT_FC, FC_APN, FC_YEAR, FC_UNITS, QA_LOST_APNS,
                    CSV_PATH, EL_PAD_YEAR)
from utils import _EL_2D, _EL_3D, el_pad, el_depad

# 1. Get UNKNOWN APNs
print("Reading QA_Lost_APNs for UNKNOWN ...")
unknown_apns = set()
with arcpy.da.SearchCursor(QA_LOST_APNS, ["APN", "Issue_Category"]) as cur:
    for apn, cat in cur:
        if cat == "UNKNOWN":
            unknown_apns.add(str(apn).strip())
print(f"  UNKNOWN APNs: {len(unknown_apns)}")

# 2. Read FC for these APNs — get per-year APN string, units, and COUNTY
print("Reading FC rows for UNKNOWN APNs ...")
fc_rows = []
with arcpy.da.SearchCursor(
        OUTPUT_FC, [FC_APN, FC_YEAR, FC_UNITS, "COUNTY"]) as cur:
    for apn, yr, units, county in cur:
        if not apn:
            continue
        a = str(apn).strip()
        if a in unknown_apns:
            fc_rows.append({
                "FC_APN": a, "Year": int(yr),
                "FC_Units": units or 0, "County": county or ""
            })
df_fc = pd.DataFrame(fc_rows)
print(f"  FC rows for UNKNOWN APNs: {len(df_fc)}")

# 3. Simulate S02 El Dorado fix to see what csv_lookup keys would be
print("Simulating S02 El Dorado fix ...")

# Build el_2d/el_3d sets from the FC (same as S02 does)
el_2d, el_3d = set(), set()
with arcpy.da.SearchCursor(OUTPUT_FC, [FC_APN],
                           where_clause="COUNTY = 'EL'") as cur:
    for (apn,) in cur:
        if apn:
            a = str(apn).strip()
            if _EL_2D.match(a):
                el_2d.add(a)
            elif _EL_3D.match(a):
                el_3d.add(a)
print(f"  EL 2-digit in FC: {len(el_2d)}")
print(f"  EL 3-digit in FC: {len(el_3d)}")

# Read raw CSV
df_csv = pd.read_csv(CSV_PATH, dtype=str)
csv_apn_set = set(df_csv["APN"].str.strip())

# Build pad/depad maps (same as S02)
pad_candidates = {a for a in csv_apn_set
                  if _EL_2D.match(str(a)) and a in el_2d}
depad_candidates = {a for a in csv_apn_set
                    if _EL_3D.match(str(a)) and el_depad(a) in el_2d}
pad_map = {a: el_pad(a) for a in pad_candidates}
depad_map = {a: el_depad(a) for a in depad_candidates}

# 4. For each UNKNOWN APN, check if csv_lookup key would match FC APN
print("\nChecking per-year match ...")
mismatch_patterns = Counter()
sample_mismatches = []

for apn in sorted(unknown_apns)[:200]:  # sample
    in_csv = apn in csv_apn_set

    # Get FC years and APNs
    apn_fc = df_fc[df_fc["FC_APN"] == apn]
    if apn_fc.empty:
        continue

    county = apn_fc["County"].iloc[0]

    for _, row in apn_fc.iterrows():
        yr = int(row["Year"])
        fc_units = int(row["FC_Units"])

        # What would csv_lookup key be?
        if apn in pad_map and yr >= EL_PAD_YEAR:
            csv_key_apn = pad_map[apn]
        elif apn in depad_map and yr < EL_PAD_YEAR:
            csv_key_apn = depad_map[apn]
        else:
            csv_key_apn = apn

        match = (csv_key_apn == apn)  # Does csv_lookup key == FC APN?

        if fc_units == 0 and not match:
            pattern = f"MISMATCH:csv={csv_key_apn},fc={apn}"
            mismatch_patterns[f"county={county}"] += 1
            if len(sample_mismatches) < 30:
                sample_mismatches.append({
                    "APN": apn, "Year": yr, "County": county,
                    "FC_APN": apn, "CSV_Key_APN": csv_key_apn,
                    "FC_Units": fc_units
                })
        elif fc_units == 0 and match:
            mismatch_patterns[f"KEYS_MATCH_BUT_ZERO:county={county}"] += 1

print("\nMismatch patterns (first 200 UNKNOWN APNs):")
for pat, cnt in mismatch_patterns.most_common():
    print(f"  {pat:50s} : {cnt}")

print("\nSample mismatches:")
for m in sample_mismatches[:15]:
    print(f"  APN={m['APN']}  Year={m['Year']}  County={m['County']}  "
          f"FC_APN={m['FC_APN']}  CSV_Key={m['CSV_Key_APN']}")

# 5. Check a different angle: are these APNs in the FC with DIFFERENT format?
print("\n\nChecking if UNKNOWN APNs exist in FC under a different APN string ...")
# Build a reverse lookup: for each UNKNOWN APN, find all similar APNs in the FC
all_fc_apns = set()
with arcpy.da.SearchCursor(OUTPUT_FC, [FC_APN]) as cur:
    for (apn,) in cur:
        if apn:
            all_fc_apns.add(str(apn).strip())

variant_found = 0
variant_not_found = 0
variant_samples = []
for apn in sorted(unknown_apns)[:200]:
    padded = el_pad(apn) if _EL_2D.match(apn) else None
    depadded = el_depad(apn) if _EL_3D.match(apn) else None

    variants = [v for v in [padded, depadded] if v and v in all_fc_apns and v != apn]
    if variants:
        variant_found += 1
        if len(variant_samples) < 10:
            variant_samples.append(f"  {apn} -> variant in FC: {variants}")
    else:
        variant_not_found += 1

print(f"  With variant in FC: {variant_found}")
print(f"  No variant:         {variant_not_found}")
for s in variant_samples:
    print(s)

# 6. Key insight: check COUNTY distribution and which years have units=0
print("\n\nPer-county breakdown of zero-unit years:")
for county in ["EL", "WA", "PL", "DG", "CC"]:
    county_unknown = df_fc[(df_fc["FC_APN"].isin(unknown_apns)) &
                           (df_fc["County"] == county)]
    if county_unknown.empty:
        continue
    zero = county_unknown[county_unknown["FC_Units"] == 0]
    nonzero = county_unknown[county_unknown["FC_Units"] > 0]
    zero_years = Counter(zero["Year"])
    print(f"\n  {county}: {len(zero)} zero-unit rows, {len(nonzero)} nonzero rows")
    print(f"    Zero-unit rows per year:")
    for yr in sorted(zero_years):
        print(f"      {yr}: {zero_years[yr]}")
    if not nonzero.empty:
        nz_years = Counter(nonzero["Year"])
        print(f"    Nonzero-unit rows per year:")
        for yr in sorted(nz_years):
            print(f"      {yr}: {nz_years[yr]}")
