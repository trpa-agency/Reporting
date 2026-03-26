"""
Diagnose the UNKNOWN lost APNs from the latest QA run.

UNKNOWN = APN has CSV units > 0, APN exists in FC geometry, but FC_Units = 0.
This means csv_lookup didn't match — likely an APN format mismatch.

Compares APN strings between CSV and FC to find the mismatch pattern.
"""
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(Path(__file__).parents[1]))

import arcpy
import pandas as pd

from config import (OUTPUT_FC, FC_APN, FC_YEAR, FC_UNITS, CSV_PATH,
                    QA_LOST_APNS, CSV_YEARS)

OUT_CSV = ROOT / "data" / "raw_data" / "unknown_apns_diagnosis.csv"


def run():
    # 1. Read UNKNOWN APNs from QA table
    print("Reading QA_Lost_APNs ...")
    unknown_apns = set()
    with arcpy.da.SearchCursor(
            QA_LOST_APNS, ["APN", "Issue_Category"]) as cur:
        for apn, cat in cur:
            if cat == "UNKNOWN":
                unknown_apns.add(str(apn).strip())
    print(f"  UNKNOWN APNs: {len(unknown_apns)}")

    # 2. Read FC: what APNs exist and which years, with units
    print("Reading FC for UNKNOWN APNs ...")
    fc_data = {}  # apn -> {year: units}
    with arcpy.da.SearchCursor(
            OUTPUT_FC, [FC_APN, FC_YEAR, FC_UNITS, "COUNTY"]) as cur:
        for apn, yr, units, county in cur:
            if not apn:
                continue
            apn = str(apn).strip()
            if apn in unknown_apns:
                if apn not in fc_data:
                    fc_data[apn] = {"county": county, "years": {}}
                fc_data[apn]["years"][int(yr)] = units or 0

    print(f"  UNKNOWN APNs found in FC: {len(fc_data)}")
    not_in_fc = unknown_apns - set(fc_data.keys())
    if not_in_fc:
        print(f"  UNKNOWN APNs NOT in FC: {len(not_in_fc)}")
        for a in sorted(not_in_fc)[:20]:
            print(f"    {a}")

    # 3. Read CSV to get the raw APN strings
    print("Reading raw CSV ...")
    df_csv = pd.read_csv(CSV_PATH, dtype=str)
    csv_apns = set(df_csv["APN"].str.strip())
    print(f"  CSV APNs: {len(csv_apns)}")

    # 4. Check overlap
    in_both = unknown_apns & csv_apns
    in_fc_only = unknown_apns - csv_apns
    print(f"\n  UNKNOWN APNs in raw CSV: {len(in_both)}")
    print(f"  UNKNOWN APNs NOT in raw CSV: {len(in_fc_only)}")

    # 5. For APNs in the CSV, check if the FC has them with different formatting
    # Build a set of all FC APNs
    print("\nBuilding full FC APN set ...")
    fc_all_apns = set()
    fc_apn_county = {}
    with arcpy.da.SearchCursor(OUTPUT_FC, [FC_APN, "COUNTY"]) as cur:
        for apn, county in cur:
            if apn:
                a = str(apn).strip()
                fc_all_apns.add(a)
                if a not in fc_apn_county:
                    fc_apn_county[a] = county

    # 6. Analyze patterns for UNKNOWN APNs in the CSV
    print("\nAnalyzing APN format patterns ...")
    patterns = Counter()
    records = []

    for apn in sorted(unknown_apns):
        in_csv = apn in csv_apns
        in_fc = apn in fc_all_apns
        county = fc_apn_county.get(apn, "")
        fc_years = fc_data.get(apn, {}).get("years", {})
        fc_year_list = sorted(fc_years.keys()) if fc_years else []
        fc_units_any = any(v > 0 for v in fc_years.values())

        # Check for format variants
        # Try padding (2-digit -> 3-digit)
        parts = apn.split("-")
        padded = None
        depadded = None
        if len(parts) == 3 and len(parts[2]) == 2:
            padded = f"{parts[0]}-{parts[1]}-0{parts[2]}"
        if len(parts) == 3 and len(parts[2]) == 3 and parts[2].startswith("0"):
            depadded = f"{parts[0]}-{parts[1]}-{parts[2][1:]}"

        padded_in_fc = padded and padded in fc_all_apns
        depadded_in_fc = depadded and depadded in fc_all_apns
        padded_in_csv = padded and padded in csv_apns
        depadded_in_csv = depadded and depadded in csv_apns

        if not in_fc and padded_in_fc:
            pattern = "CSV_2D_FC_3D"
        elif not in_fc and depadded_in_fc:
            pattern = "CSV_3D_FC_2D"
        elif in_fc and not in_csv and padded_in_csv:
            pattern = "FC_2D_CSV_3D"
        elif in_fc and not in_csv and depadded_in_csv:
            pattern = "FC_3D_CSV_2D"
        elif in_fc and in_csv and not fc_units_any:
            pattern = "MATCHED_BUT_ZERO_UNITS"
        elif in_fc and not in_csv:
            pattern = "IN_FC_NOT_CSV"
        elif not in_fc and in_csv:
            pattern = "IN_CSV_NOT_FC"
        else:
            pattern = "OTHER"

        patterns[pattern] += 1
        records.append({
            "APN": apn,
            "County": county or "",
            "In_CSV": in_csv,
            "In_FC": in_fc,
            "FC_Years": str(fc_year_list) if fc_year_list else "",
            "FC_Has_Units": fc_units_any,
            "Padded_Variant": padded or "",
            "Padded_In_FC": padded_in_fc or False,
            "Depadded_Variant": depadded or "",
            "Depadded_In_FC": depadded_in_fc or False,
            "Pattern": pattern,
        })

    print("\nPattern breakdown:")
    for pat, cnt in patterns.most_common():
        print(f"  {pat:30s} : {cnt}")

    # County breakdown
    df_out = pd.DataFrame(records)
    print("\nBy county:")
    print(df_out.groupby(["County", "Pattern"]).size().to_string())

    df_out.to_csv(OUT_CSV, index=False)
    print(f"\nWritten to {OUT_CSV}")

    # Show samples of each pattern
    for pat in patterns:
        sample = df_out[df_out["Pattern"] == pat].head(5)
        print(f"\n--- Sample: {pat} ---")
        for _, r in sample.iterrows():
            print(f"  APN={r['APN']}  County={r['County']}  "
                  f"InCSV={r['In_CSV']}  InFC={r['In_FC']}  "
                  f"Padded={r['Padded_Variant']}  PadInFC={r['Padded_In_FC']}")


if __name__ == "__main__":
    run()
