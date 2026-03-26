"""
check_parcel_topology.py — Detect topology and data integrity issues
in Parcel_History_Attributed for each year in scope.

Checks
------
1. Duplicate APN-Year     Same APN appears >1 time in the same year
2. Within-year overlap    Two different APNs in the same year share area
                          above a sliver threshold (≥ 10 sq ft)
3. Area discontinuity     Stable APNs (present in both year N and N+1)
                          whose area changes by > 10% without a genealogy event

Writes three GDB QA tables:
  QA_Topo_DuplicateAPN   rows: APN, Year, Count, OIDs
  QA_Topo_Overlap        rows: Year, APN_A, APN_B, Overlap_SqFt
  QA_Topo_AreaShift      rows: APN, Year_Before, Year_After,
                               Area_Before, Area_After, Change_Pct

Run from ArcGIS Pro Python:
  & "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" `
    "C:/Users/mbindl/Documents/GitHub/Reporting/parcel_development_history_etl/check_parcel_topology.py"
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import arcpy

from config import (
    WORKING_FC as SOURCE_FC, FC_APN, FC_YEAR, CSV_YEARS, GDB,
    QA_TOPO_DUPLICATE, QA_TOPO_OVERLAP, QA_TOPO_AREA_SHIFT,
)

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("check_parcel_topology")

_MEM = "memory"

# Ignore overlaps smaller than this — excludes shared-boundary slivers
OVERLAP_AREA_MIN_SQFT = 10.0

# Flag area changes larger than this fraction for stable APNs
AREA_SHIFT_THRESHOLD = 0.10


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_table(gdb_path: str, table_name: str,
                 rows: list[dict], field_defs: list) -> None:
    if arcpy.Exists(gdb_path):
        arcpy.management.Delete(gdb_path)
    arcpy.management.CreateTable(GDB, table_name)
    for fname, ftype, flen in field_defs:
        if flen:
            arcpy.management.AddField(gdb_path, fname, ftype, field_length=flen)
        else:
            arcpy.management.AddField(gdb_path, fname, ftype)
    field_names = [f[0] for f in field_defs]
    with arcpy.da.InsertCursor(gdb_path, field_names) as ic:
        for r in rows:
            ic.insertRow([r.get(fn) for fn in field_names])
    log.info("Written %d rows → %s", len(rows), gdb_path)


# ── Check 1: Duplicate APN-Year ───────────────────────────────────────────────

def check_duplicate_apn_year() -> list[dict]:
    """
    Find APN-Year combos that appear more than once (different OBJECTIDs).
    Reads the full source FC once.
    """
    log.info("Check 1: Duplicate APN-Year ...")

    counts: dict[tuple, int]   = defaultdict(int)
    oids:   dict[tuple, list]  = defaultdict(list)

    with arcpy.da.SearchCursor(SOURCE_FC, ["OID@", FC_APN, FC_YEAR]) as cur:
        for oid, apn, year in cur:
            if apn and year is not None:
                key = (str(apn).strip(), int(year))
                counts[key] += 1
                oids[key].append(oid)

    rows = []
    for (apn, year), count in sorted(counts.items()):
        if count > 1:
            rows.append({
                "APN"  : apn,
                "Year" : year,
                "Count": count,
                "OIDs" : ", ".join(str(o) for o in oids[(apn, year)]),
            })

    log.info("  Duplicate APN-Year combos: %d", len(rows))
    return rows


# ── Check 2: Within-year parcel overlap ───────────────────────────────────────

def check_within_year_overlap(years: list[int]) -> list[dict]:
    """
    For each year, intersect the year layer with a copy of itself.
    Output polygons where APN_A != APN_B and area ≥ threshold are overlaps.

    Uses in-memory feature classes to avoid writing to disk.
    The Intersect self-join produces pairs (A,B) and (B,A) — deduplicated
    by keeping only rows where APN_A < APN_B.
    """
    log.info("Check 2: Within-year parcel overlap (%d years) ...", len(years))
    all_rows = []

    for year in years:
        t_yr  = time.time()
        tag   = str(year)
        lyr_a = f"{_MEM}/topo_a_{tag}"
        lyr_b = f"{_MEM}/topo_b_{tag}"
        out_fc = f"{_MEM}/topo_ix_{tag}"
        src_lyr = f"topo_src_{tag}"

        for fc in [lyr_a, lyr_b, out_fc]:
            if arcpy.Exists(fc):
                arcpy.management.Delete(fc)
        if arcpy.Exists(src_lyr):
            arcpy.management.Delete(src_lyr)

        arcpy.management.MakeFeatureLayer(
            SOURCE_FC, src_lyr, f"{FC_YEAR} = {year}")
        arcpy.management.CopyFeatures(src_lyr, lyr_a)
        arcpy.management.CopyFeatures(src_lyr, lyr_b)
        arcpy.management.Delete(src_lyr)

        arcpy.analysis.Intersect(
            [lyr_a, lyr_b], out_fc,
            join_attributes="ALL",
            output_type="INPUT")

        # Intersect renames the second input's APN field with _1 suffix
        id_fields = {f.name for f in arcpy.ListFields(out_fc)}
        apn_b_fld = f"{FC_APN}_1" if f"{FC_APN}_1" in id_fields else FC_APN

        year_rows = []
        with arcpy.da.SearchCursor(
                out_fc, [FC_APN, apn_b_fld, "SHAPE@AREA"]) as cur:
            for apn_a, apn_b, area in cur:
                if not apn_a or not apn_b or not area:
                    continue
                apn_a = str(apn_a).strip()
                apn_b = str(apn_b).strip()
                if apn_a >= apn_b:          # deduplicate; skip self-intersection
                    continue
                if area < OVERLAP_AREA_MIN_SQFT:
                    continue
                year_rows.append({
                    "Year"        : year,
                    "APN_A"       : apn_a,
                    "APN_B"       : apn_b,
                    "Overlap_SqFt": round(area, 1),
                })

        for fc in [lyr_a, lyr_b, out_fc]:
            if arcpy.Exists(fc):
                arcpy.management.Delete(fc)

        log.info("  %d : %d overlapping pairs  (%.1fs)",
                 year, len(year_rows), time.time() - t_yr)
        all_rows.extend(year_rows)

    log.info("  Total overlapping pairs across all years: %d", len(all_rows))
    return all_rows


# ── Check 3: Area discontinuity for stable APNs ───────────────────────────────

def check_area_continuity(years: list[int]) -> list[dict]:
    """
    For APNs that appear in both year N and year N+1 (stable — no genealogy
    event expected), flag those where geometry area changes by more than
    AREA_SHIFT_THRESHOLD.  A large area shift with no genealogy event means
    geometry was silently edited — a potential data integrity issue.

    Uses max area per APN-Year when duplicates exist (QA_Topo_DuplicateAPN
    will separately flag those).
    """
    log.info("Check 3: Area discontinuity for stable APNs ...")

    area_map: dict[tuple, float] = {}
    with arcpy.da.SearchCursor(
            SOURCE_FC, [FC_APN, FC_YEAR, "SHAPE@AREA"]) as cur:
        for apn, year, area in cur:
            if apn and year is not None and area and area > 0:
                key = (str(apn).strip(), int(year))
                if key not in area_map or area > area_map[key]:
                    area_map[key] = float(area)

    apns_by_year: dict[int, set] = defaultdict(set)
    for (apn, year) in area_map:
        apns_by_year[year].add(apn)

    all_rows = []
    for i in range(len(years) - 1):
        yr_n  = years[i]
        yr_n1 = years[i + 1]
        stable = apns_by_year[yr_n] & apns_by_year[yr_n1]

        for apn in stable:
            a_n  = area_map[(apn, yr_n)]
            a_n1 = area_map[(apn, yr_n1)]
            change_frac = abs(a_n1 - a_n) / a_n
            if change_frac > AREA_SHIFT_THRESHOLD:
                all_rows.append({
                    "APN"        : apn,
                    "Year_Before": yr_n,
                    "Year_After" : yr_n1,
                    "Area_Before": round(a_n,  1),
                    "Area_After" : round(a_n1, 1),
                    "Change_Pct" : round(change_frac * 100, 1),
                })

    all_rows.sort(key=lambda x: -x["Change_Pct"])
    log.info("  Stable APNs with area shift >%.0f%%: %d",
             AREA_SHIFT_THRESHOLD * 100, len(all_rows))
    return all_rows


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    t0    = time.time()
    years = sorted(CSV_YEARS)

    log.info("=== check_parcel_topology.py ===")
    log.info("Source FC : %s", SOURCE_FC)
    log.info("Years     : %d – %d  (%d years)", years[0], years[-1], len(years))
    log.info("")

    # ── Check 1 ───────────────────────────────────────────────────────────────
    dup_rows = check_duplicate_apn_year()
    _write_table(
        QA_TOPO_DUPLICATE, "QA_Topo_DuplicateAPN", dup_rows,
        [("APN",   "TEXT",  50),
         ("Year",  "LONG",  None),
         ("Count", "SHORT", None),
         ("OIDs",  "TEXT",  200)],
    )

    # ── Check 2 ───────────────────────────────────────────────────────────────
    overlap_rows = check_within_year_overlap(years)
    _write_table(
        QA_TOPO_OVERLAP, "QA_Topo_Overlap", overlap_rows,
        [("Year",         "LONG",   None),
         ("APN_A",        "TEXT",   50),
         ("APN_B",        "TEXT",   50),
         ("Overlap_SqFt", "DOUBLE", None)],
    )

    # ── Check 3 ───────────────────────────────────────────────────────────────
    shift_rows = check_area_continuity(years)
    _write_table(
        QA_TOPO_AREA_SHIFT, "QA_Topo_AreaShift", shift_rows,
        [("APN",         "TEXT",   50),
         ("Year_Before", "LONG",   None),
         ("Year_After",  "LONG",   None),
         ("Area_Before", "DOUBLE", None),
         ("Area_After",  "DOUBLE", None),
         ("Change_Pct",  "DOUBLE", None)],
    )

    elapsed = time.time() - t0
    mins, secs = divmod(int(elapsed), 60)
    log.info("")
    log.info("=== Summary ===")
    log.info("  Duplicate APN-Year  : %d combos", len(dup_rows))
    log.info("  Within-year overlaps: %d pairs", len(overlap_rows))
    log.info("  Area discontinuities: %d stable APNs", len(shift_rows))
    log.info("Done.  (%dm %02ds)", mins, secs)


if __name__ == "__main__":
    main()
