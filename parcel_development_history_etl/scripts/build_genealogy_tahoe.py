"""
Build the Tahoe Parcel Genealogy Master Table.

Consolidates all genealogy sources into a single canonical CSV:
    data/raw_data/apn_genealogy_tahoe.csv

Sources merged in priority order:
    1. MANUAL  — apn_genealogy_master.csv     (hand-curated, authoritative)
    2. ACCELA  — apn_genealogy_accela.csv     (Accela permit system, 2021-2025)
    3. LTINFO  — apn_genealogy_ltinfo.csv     (LTinfo parcel pairs, no dates yet)
    4. SPATIAL — apn_genealogy_spatial.csv    (auto-detected spatial overlap)

Key operations
--------------
1. Load and normalize all sources.
2. Canonicalize El Dorado APNs to 3-digit format (NNN-NNN-NNN) using FC county data.
   This fixes the Accela mixed-format problem before any matching happens.
3. Deduplicate: for each (apn_old, apn_new) pair keep the highest-priority source.
4. Populate validation columns from the GDB:
     in_fc_old  -- 1 if apn_old appears in the FC at least once
     in_fc_new  -- 1 if apn_new appears in the FC at least once
     lost_apn   -- 1 if apn_old is in QA_Lost_APNs (confirmed missing from FC
                  for some years) -- THE KEY FILTER for safe ETL application
5. Write master CSV.

ETL Usage
---------
s02b_genealogy applies records where:
    is_primary == 1  AND  change_year is set  AND  lost_apn == 1

The lost_apn filter prevents over-remapping valid APNs that are already
correctly matched in the FC under their existing identifier.

Schema
------
event_id      -- UUID grouping all APNs in one transaction (Accela GEN_TRAN_ID
                 where available, or auto-assigned 8-char hex for other sources)
apn_old       -- Old APN in canonical format (El Dorado always 3-digit)
apn_new       -- New APN in canonical format
apn_old_raw   -- APN as it appeared in the source file (pre-normalization)
apn_new_raw   -- APN as it appeared in the source file
county        -- EL, PL, WA, DO, CC (populated where derivable)
is_el_dorado  -- 1 if apn_old is an El Dorado parcel (drives ETL format handling)
change_year   -- Year the transition takes effect (null = skipped by ETL)
change_date   -- Full ISO date if known (from Accela); null otherwise
event_type    -- RENAME, SPLIT, MERGE, SUBDIVISION, COMPLEX
n_parents     -- # of parent APNs in this transaction
n_children    -- # of child APNs in this transaction
is_primary    -- 1 = apn_new is the canonical unit-history successor for apn_old
overlap_pct   -- Spatial overlap fraction (from spatial genealogy; null for others)
source        -- MANUAL, ACCELA, LTINFO, SPATIAL
source_priority -- 1=MANUAL, 2=ACCELA, 3=LTINFO, 4=SPATIAL
confidence    -- HIGH (manual-verified), MEDIUM (permit-system), LOW (spatial)
verified      -- 1 = analyst has reviewed this record
notes         -- Free text
added_date    -- ISO date when record entered the master
in_fc_old     -- 1 = apn_old confirmed in FC at least once
in_fc_new     -- 1 = apn_new confirmed in FC at least once
lost_apn      -- 1 = apn_old is in QA_Lost_APNs (safe to remap)

Re-run whenever:
- A new genealogy source is added (re-run parse_genealogy_sources.py first)
- QA_Lost_APNs is refreshed after an ETL run (updates lost_apn flags)

Run:
    C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe \\
        parcel_development_history_etl/build_genealogy_tahoe.py
"""
import sys
import re
import uuid
from pathlib import Path
from datetime import date

import arcpy
import pandas as pd

ROOT = Path(__file__).parents[2]
RAW  = ROOT / "data" / "raw_data"
OUT  = RAW / "apn_genealogy_tahoe.csv"

sys.path.insert(0, str(Path(__file__).parents[1]))
from config import (
    OUTPUT_FC, FC_APN, FC_COUNTY,
    GENEALOGY_MASTER, GENEALOGY_ACCELA, GENEALOGY_LTINFO, GENEALOGY_SPATIAL,
    QA_LOST_APNS,
)
from utils import el_pad as _pad, el_depad as _depad, _EL_2D as _2D, _EL_3D as _3D


# ── El Dorado lookup ──────────────────────────────────────────────────────────

def _build_el_dorado_canon(fc: str) -> dict:
    """
    Query FC for El Dorado APNs (COUNTY='EL').
    Returns dict mapping any El Dorado APN format -> canonical 3-digit form.
    """
    print("Building El Dorado canonical lookup from FC...")
    el_2d, el_3d = set(), set()
    with arcpy.da.SearchCursor(fc, [FC_APN, FC_COUNTY]) as cur:
        for apn, county in cur:
            if county == "EL" and apn:
                a = str(apn).strip()
                if _2D.match(a):   el_2d.add(a)
                elif _3D.match(a): el_3d.add(a)

    canon = {}
    for a in el_2d:
        canon[a]       = _pad(a)   # 2-digit -> 3-digit canonical
        canon[_pad(a)] = _pad(a)   # also map the 3-digit version of itself
    for a in el_3d:
        canon[a] = a               # already canonical
    print(f"  El Dorado 2-digit: {len(el_2d):,}  3-digit: {len(el_3d):,}  "
          f"canon entries: {len(canon):,}")
    return canon


def _canon(apn: str, el_canon: dict) -> str:
    """Canonicalize a single APN. El Dorado 2-digit -> 3-digit; others unchanged."""
    a = str(apn).strip()
    return el_canon.get(a, a)


# ── Load sources ──────────────────────────────────────────────────────────────

SOURCE_META = [
    ("MANUAL",  GENEALOGY_MASTER,  1, "HIGH"),
    ("ACCELA",  GENEALOGY_ACCELA,  2, "MEDIUM"),
    ("LTINFO",  GENEALOGY_LTINFO,  3, "MEDIUM"),
    ("SPATIAL", GENEALOGY_SPATIAL, 4, "LOW"),
]


def _load_source(name: str, path: str, priority: int, confidence: str,
                 el_canon: dict) -> pd.DataFrame:
    if not Path(path).exists():
        print(f"  {name}: not found — skipping")
        return pd.DataFrame()

    df = pd.read_csv(path, dtype=str)
    df.columns = df.columns.str.strip()
    if "old_apn" not in df.columns or "new_apn" not in df.columns:
        print(f"  {name}: missing old_apn/new_apn — skipping")
        return pd.DataFrame()

    df["old_apn"] = df["old_apn"].str.strip()
    df["new_apn"] = df["new_apn"].str.strip()
    df = df.dropna(subset=["old_apn", "new_apn"])
    df = df[df["old_apn"] != df["new_apn"]].copy()

    # Raw (pre-canonicalization)
    df["apn_old_raw"] = df["old_apn"]
    df["apn_new_raw"] = df["new_apn"]

    # Canonical
    df["apn_old"] = df["old_apn"].apply(lambda a: _canon(a, el_canon))
    df["apn_new"] = df["new_apn"].apply(lambda a: _canon(a, el_canon))

    # El Dorado flag: apn_old is in El Dorado if its raw or canonical form is in el_canon
    df["is_el_dorado"] = df.apply(
        lambda r: 1 if (r["old_apn"] in el_canon or r["apn_old"] in el_canon.values())
        else 0, axis=1)

    # Source metadata
    df["source"]          = name
    df["source_priority"] = priority
    df["confidence"]      = confidence
    df["verified"]        = 1 if name == "MANUAL" else 0
    df["added_date"]      = str(date.today())

    # change_year
    if "change_year" in df.columns:
        df["change_year"] = pd.to_numeric(df["change_year"], errors="coerce")
    else:
        df["change_year"] = pd.NA

    # change_date — not in current CSVs, placeholder for Accela REC_DATE if added later
    df["change_date"] = df.get("change_date", pd.NA)

    # event_type
    df["event_type"] = df["change_type"].str.strip() if "change_type" in df.columns else pd.NA

    # event_id: generate 8-char hex per pair (Accela GEN_TRAN_ID could be added here later)
    df["event_id"] = [uuid.uuid4().hex[:8] for _ in range(len(df))]

    # n_parents / n_children: derive from event_type
    type_parents  = {"rename": 1, "merge": None, "split": 1, "complex": None}
    type_children = {"rename": 1, "merge": 1,    "split": None, "complex": None}
    df["n_parents"]  = df["event_type"].map(type_parents)
    df["n_children"] = df["event_type"].map(type_children)

    # is_primary
    df["is_primary"] = pd.to_numeric(
        df.get("is_primary", pd.Series(1, index=df.index)), errors="coerce"
    ).fillna(1).astype(int)

    # overlap_pct
    df["overlap_pct"] = pd.to_numeric(
        df.get("overlap_pct", pd.Series(pd.NA, index=df.index)), errors="coerce"
    )

    # county — blank for now; could be inferred from FC cross-reference later
    df["county"] = ""

    # notes
    df["notes"] = df["notes"].str.strip() if "notes" in df.columns else ""

    n          = len(df)
    n_with_yr  = int(df["change_year"].notna().sum())
    n_el       = int(df["is_el_dorado"].sum())
    print(f"  {name}: {n:,} pairs  |  {n_with_yr:,} with change_year  |  {n_el:,} El Dorado")
    return df


# ── FC APN presence ───────────────────────────────────────────────────────────

def _fc_apn_set(fc: str, el_canon: dict) -> set:
    print("Reading FC APN set for in_fc_old / in_fc_new validation...")
    apns = set()
    with arcpy.da.SearchCursor(fc, [FC_APN]) as cur:
        for (a,) in cur:
            if a:
                apns.add(_canon(str(a).strip(), el_canon))
    print(f"  Unique canonical APNs in FC: {len(apns):,}")
    return apns


# ── QA_Lost_APNs ──────────────────────────────────────────────────────────────

def _lost_apn_set(el_canon: dict) -> set:
    lost = set()
    try:
        with arcpy.da.SearchCursor(QA_LOST_APNS, ["APN"]) as cur:
            for (a,) in cur:
                if a:
                    lost.add(_canon(str(a).strip(), el_canon))
        print(f"  QA_Lost_APNs: {len(lost):,} confirmed lost APNs")
    except Exception as e:
        print(f"  WARNING: Could not read QA_Lost_APNs: {e}")
    return lost


# ── Main ──────────────────────────────────────────────────────────────────────

OUT_COLS = [
    "event_id",
    "apn_old", "apn_new", "apn_old_raw", "apn_new_raw",
    "county", "is_el_dorado",
    "change_year", "change_date", "event_type",
    "n_parents", "n_children",
    "is_primary", "overlap_pct",
    "source", "source_priority", "confidence", "verified", "notes", "added_date",
    "in_fc_old", "in_fc_new", "lost_apn",
]


def main():
    el_canon = _build_el_dorado_canon(OUTPUT_FC)

    print("\nLoading genealogy sources...")
    frames = [_load_source(n, p, pr, c, el_canon)
              for n, p, pr, c in SOURCE_META]
    frames = [f for f in frames if not f.empty]

    if not frames:
        print("No sources loaded.")
        return

    master = pd.concat(frames, ignore_index=True)

    # Deduplicate: same (apn_old, apn_new) pair — keep highest priority source
    master = master.sort_values("source_priority")
    n_before = len(master)
    master = master.drop_duplicates(subset=["apn_old", "apn_new"], keep="first")
    n_deduped = n_before - len(master)
    print(f"\nDeduplication: {n_before:,} -> {len(master):,} pairs ({n_deduped:,} removed as lower-priority duplicates)")

    # Validate
    print()
    fc_apns  = _fc_apn_set(OUTPUT_FC, el_canon)
    lost_set = _lost_apn_set(el_canon)

    master["in_fc_old"] = master["apn_old"].apply(lambda a: 1 if a in fc_apns else 0)
    master["in_fc_new"] = master["apn_new"].apply(lambda a: 1 if a in fc_apns else 0)
    master["lost_apn"]  = master["apn_old"].apply(lambda a: 1 if a in lost_set else 0)

    # Ensure all output columns exist
    for col in OUT_COLS:
        if col not in master.columns:
            master[col] = pd.NA

    master[OUT_COLS].to_csv(OUT, index=False)

    # Summary
    ready = master[(master["lost_apn"] == 1) & master["change_year"].notna()]
    print(f"\n{'='*50}")
    print(f"Master table written -> {OUT}")
    print(f"{'='*50}")
    print(f"Total pairs:                 {len(master):,}")
    print(f"  with change_year:          {master['change_year'].notna().sum():,}")
    print(f"  without change_year:       {master['change_year'].isna().sum():,}")
    print(f"  in_fc_old = 1:             {master['in_fc_old'].eq(1).sum():,}")
    print(f"  in_fc_new = 1:             {master['in_fc_new'].eq(1).sum():,}")
    print(f"  is_el_dorado = 1:          {master['is_el_dorado'].eq(1).sum():,}")
    print(f"  lost_apn = 1 (will apply): {master['lost_apn'].eq(1).sum():,}")
    print(f"  READY (lost + year set):   {len(ready):,}")
    print()
    print("By source:")
    summary = master.groupby("source").agg(
        pairs        = ("apn_old",   "count"),
        with_year    = ("change_year", lambda x: x.notna().sum()),
        lost_apn_ct  = ("lost_apn",  "sum"),
        el_dorado_ct = ("is_el_dorado", "sum"),
    )
    summary.index.name = None
    print(summary.to_string())


if __name__ == "__main__":
    main()
