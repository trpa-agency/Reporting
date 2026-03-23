"""
build_genealogy_master.py — One-time utility to create apn_genealogy_master.csv.

Parses free-text genealogy notes from two source CSVs, auto-detects change
years from the parcel history FC, and writes a structured master CSV that the
ETL (s02b) reads on every run.

Run this script whenever the notes CSVs are updated or to regenerate the master
from scratch:

    C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe \
        build_genealogy_master.py

After running, review apn_genealogy_master.csv in Excel and:
  - Correct any misparse (especially complex multi-step histories)
  - Fill in change_year manually for PARCEL_NEW rows (never in FC)
  - Adjust new_apn for 1:N splits if a non-primary successor should own the units
  - Add rows for known genealogy events not captured in the notes

Master CSV schema
-----------------
old_apn        : APN as it appears in ExistingResidential CSV (to be retired)
new_apn        : Successor APN that should receive units for Year >= change_year
change_year    : First year to use new_apn (old_apn's last FC year + 1)
change_type    : rename | split | merge | unknown
is_primary     : 1 = this successor receives all units; 0 = listed for reference
notes_excerpt  : First 120 chars of the original note (for analyst review)
source         : Which notes file the row came from
fc_last_year   : Last year old_apn appears in the parcel history FC (blank if never)
"""

import re
import sys
import os

sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))

import arcpy
import pandas as pd

from config import (
    GENEALOGY_NOTES_1, GENEALOGY_NOTES_2, GENEALOGY_MASTER,
    OUTPUT_FC, FC_APN, FC_YEAR,
)

# ── APN regex patterns ────────────────────────────────────────────────────────
# Extended (Douglas/Tahoe): 1418-34-110-039, 1318-22-002-002
# Standard (3-segment):     123-032-01, 097-122-028, 001-030-02
_APN_RE = re.compile(r'\b(\d{4}-\d{2}-\d{3}-\d{3}|\d{3}-\d{3}-\d{2,3})\b')

# "New APN: X" / "New APN's: X & Y" — capture text up to first "(" or end of line
_NEW_RE = re.compile(
    r'[Nn]ew\s+APN[s\'\s]*[:\-]\s*([^(\n]+)',
    re.MULTILINE,
)
# "Portions of this parcel are now part of APNs X, Y, Z."
_PORTIONS_RE = re.compile(
    r'[Pp]ortions?\s+of\s+this\s+parcel\s+are\s+now\s+part\s+of\s+APNs?\s+([^.(\n]+)',
    re.IGNORECASE,
)


def _parse_new_apns(notes: str) -> list:
    """Return ordered list of successor APNs extracted from free-text notes."""
    if not notes or (isinstance(notes, float)):
        return []
    notes = str(notes)
    collected = []
    for m in _NEW_RE.finditer(notes):
        collected.extend(_APN_RE.findall(m.group(1)))
    for m in _PORTIONS_RE.finditer(notes):
        collected.extend(_APN_RE.findall(m.group(1)))
    # Deduplicate preserving order
    seen, out = set(), []
    for a in collected:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def _build_fc_year_range(apns: set) -> tuple:
    """
    Return ({apn: last_year}, {apn: first_year}) for all specified APNs in FC.
    APNs absent from FC are not included in either dict.
    """
    last_yr  = {}
    first_yr = {}
    apn_list = list(apns)
    batch    = 500
    print(f"  Querying FC year range for {len(apn_list):,} APNs...")
    for i in range(0, len(apn_list), batch):
        chunk = apn_list[i : i + batch]
        sql   = " OR ".join(f"{FC_APN} = '{a}'" for a in chunk)
        with arcpy.da.SearchCursor(OUTPUT_FC, [FC_APN, FC_YEAR], sql) as cur:
            for apn, yr in cur:
                if apn and yr:
                    apn = str(apn).strip()
                    yr  = int(yr)
                    if apn not in last_yr  or yr > last_yr[apn]:
                        last_yr[apn]  = yr
                    if apn not in first_yr or yr < first_yr[apn]:
                        first_yr[apn] = yr
    return last_yr, first_yr


def _load_notes(path: str, note_col: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    df.columns = df.columns.str.strip()
    df = df.rename(columns={"APN": "old_apn", note_col: "notes"})
    df["old_apn"] = df["old_apn"].str.strip()
    df["notes"] = df["notes"].fillna("")
    return df[["old_apn", "notes"]]


def run():
    print("=== build_genealogy_master.py ===")

    # ── Load and merge both notes files ───────────────────────────────────────
    df1 = _load_notes(GENEALOGY_NOTES_1, "ParcelTrackerNotes")
    df1["source"] = "notes_1"
    df2 = _load_notes(GENEALOGY_NOTES_2, "ParcelNotes")
    df2["source"] = "notes_2"

    print(f"  notes_1 rows: {len(df1):,}")
    print(f"  notes_2 rows: {len(df2):,}")

    # Combine: for APNs in both files, prefer the one with more text
    df_all = pd.concat([df1, df2], ignore_index=True)
    # Keep longest note per APN
    df_all["note_len"] = df_all["notes"].str.len()
    df_all = (
        df_all.sort_values("note_len", ascending=False)
              .drop_duplicates(subset="old_apn", keep="first")
              .drop(columns="note_len")
              .reset_index(drop=True)
    )
    print(f"  Unique APNs after merge: {len(df_all):,}")

    # ── Parse new APNs from notes ──────────────────────────────────────────────
    df_all["new_apns"] = df_all["notes"].apply(_parse_new_apns)
    has_successors = df_all[df_all["new_apns"].map(len) > 0].copy()
    print(f"  APNs with parseable successors: {len(has_successors):,}")

    # ── Detect change years from FC ───────────────────────────────────────────
    # Query both old APNs (last year) and new APNs (first year) in one pass
    old_apns = set(has_successors["old_apn"])
    all_new  = {a for apns in has_successors["new_apns"] for a in apns}
    all_query_apns = old_apns | all_new

    fc_last, fc_first = _build_fc_year_range(all_query_apns)

    old_found = len([a for a in old_apns if a in fc_last])
    print(f"  Old APNs found in FC  : {old_found:,}  (of {len(old_apns):,})")
    print(f"  Old APNs never in FC  : {len(old_apns) - old_found:,}")

    # ── Build output rows ─────────────────────────────────────────────────────
    rows = []
    for _, rec in has_successors.iterrows():
        old_apn    = rec["old_apn"]
        new_apns   = rec["new_apns"]
        source     = rec["source"]
        notes_exc  = str(rec["notes"])[:120].replace("\n", " ")
        fc_last_yr = fc_last.get(old_apn)

        change_type = (
            "rename" if len(new_apns) == 1 else
            "split"  if len(new_apns) >  1 else
            "unknown"
        )

        for rank, new_apn in enumerate(new_apns):
            # Priority 1: last year old APN in FC + 1
            # Priority 2: first year new APN appears in FC
            # Priority 3: blank — needs manual fill
            if fc_last_yr is not None:
                change_year  = fc_last_yr + 1
                year_source  = "old_apn_last+1"
            elif new_apn in fc_first:
                change_year  = fc_first[new_apn]
                year_source  = "new_apn_first"
            else:
                change_year  = None
                year_source  = "unknown"

            rows.append({
                "old_apn"      : old_apn,
                "new_apn"      : new_apn,
                "change_year"  : change_year,
                "change_type"  : change_type,
                "is_primary"   : 1 if rank == 0 else 0,
                "year_source"  : year_source,
                "notes_excerpt": notes_exc,
                "source"       : source,
                "fc_last_year" : fc_last_yr if fc_last_yr is not None else "",
                "fc_new_first" : fc_first.get(new_apn, ""),
            })

    df_master = pd.DataFrame(rows)
    print(f"\n  Master rows total           : {len(df_master):,}")
    print(f"  Rename rows (1:1)           : {(df_master['change_type'] == 'rename').sum():,}")
    print(f"  Split rows (1:N)            : {(df_master['change_type'] == 'split').sum():,}")
    print(f"  change_year from old_apn    : {(df_master['year_source'] == 'old_apn_last+1').sum():,}")
    print(f"  change_year from new_apn    : {(df_master['year_source'] == 'new_apn_first').sum():,}")
    print(f"  change_year still unknown   : {(df_master['year_source'] == 'unknown').sum():,}  ← review these")

    df_master.to_csv(GENEALOGY_MASTER, index=False)
    print(f"\nWritten → {GENEALOGY_MASTER}")
    print("\nNext steps:")
    print("  1. Open apn_genealogy_master.csv in Excel")
    print("  2. Filter year_source = 'unknown' and fill in change_year manually")
    print("  3. Check split rows — confirm is_primary=1 row is the unit-bearing successor")
    print("  4. Save and run the ETL")


if __name__ == "__main__":
    run()
