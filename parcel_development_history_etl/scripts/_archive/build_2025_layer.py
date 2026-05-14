"""
build_2025_layer.py -- One-off script to create a clean 2025 parcel development layer.

Uses SOURCE_FC (YEAR=2025) as the authoritative geometry source + 2025 CSV
data from coworker.  The crosswalk and genealogy are built against the 2025
shapes in SOURCE_FC.

Outputs: Parcel_Development_2025 in C:\\GIS\\Parcel_Development_2025.gdb.

Run with ArcGIS Pro Python:
  "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" build_2025_layer.py
"""
import math
import sys
import os
from pathlib import Path

# Ensure parent package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import arcpy
import pandas as pd

from config import (
    SOURCE_FC,
    FC_APN, FC_YEAR, FC_UNITS, FC_COUNTY,
    FC_TOURIST_UNITS, FC_COMMERCIAL_SQFT,
    CSV_PATH, TOURIST_UNITS_CSV, COMMERCIAL_SQFT_CSV,
    GENEALOGY_TAHOE,
    EL_PAD_YEAR,
    JURISDICTION_SVC, COUNTY_CODE_MAP,
    CLOSEST_MAX_METERS, ALL_PARCELS_CURRENT,
    SPATIAL_SOURCES,
)
from utils import get_logger, el_pad, el_depad, _EL_2D, _EL_3D, df_to_gdb_table

log = get_logger("build_2025_layer")

# ── Output paths ─────────────────────────────────────────────────────────────
OUT_GDB      = r"C:\GIS\Parcel_Development_2025.gdb"
OUTPUT_2025  = OUT_GDB + r"\Parcel_Development_2025"
QA_TABLE     = OUT_GDB + r"\QA_2025_Summary"
QA_LOST      = OUT_GDB + r"\QA_2025_Lost_APNs"
QA_XWALK     = OUT_GDB + r"\QA_2025_Crosswalk"
QA_GENEALOGY = OUT_GDB + r"\QA_2025_Genealogy"
APN_MAPPING  = OUT_GDB + r"\APN_Mapping"

YEAR = 2025

# Manual APN fixes from APN_Mapping (user-verified successors for retired parcels)
MANUAL_APN_FIXES = {
    "027-323-010": "027-323-019",
    "028-301-006": "028-301-068",
    "027-313-002": "027-313-016",
    "035-301-001": "035-301-009",
    "015-304-031": "015-304-034",
    "034-691-020": "034-691-022",
}

# NAD83 UTM Zone 10N — the actual coordinate system of SOURCE_FC (which has
# WKID 0 / undefined SR in its metadata, but the coordinates are UTM 10N).
OUTPUT_SR = arcpy.SpatialReference(26910)


# =============================================================================
# Step 1 -- Build output FC from SOURCE_FC geometry
# =============================================================================
def step1_build_fc():
    """Copy 2025 parcels from SOURCE_FC -> OUTPUT_2025."""
    log.info("=== Step 1: Build 2025 FC from SOURCE_FC (YEAR=2025) ===")

    if arcpy.Exists(OUTPUT_2025):
        log.info("Deleting existing OUTPUT_2025")
        arcpy.management.Delete(OUTPUT_2025)

    out_name = OUTPUT_2025.split("\\")[-1]
    # SOURCE_FC has WKID 0 (undefined SR), but coordinates are NAD83 UTM 10N.
    # Define it explicitly so the output FC has a proper coordinate system.
    arcpy.management.CreateFeatureclass(
        out_path=OUT_GDB, out_name=out_name,
        geometry_type="POLYGON", template=SOURCE_FC,
        spatial_reference=OUTPUT_SR,
    )
    log.info("Created empty FC: %s (SR: %s)", OUTPUT_2025, OUTPUT_SR.name)

    if not arcpy.Exists(SOURCE_FC):
        log.error("SOURCE_FC not found: %s", SOURCE_FC)
        return 0

    count = 0
    where = f"{FC_YEAR} = {YEAR}"
    with arcpy.da.SearchCursor(SOURCE_FC, ["SHAPE@", FC_APN, FC_YEAR, "COUNTY"], where) as src, \
         arcpy.da.InsertCursor(OUTPUT_2025, ["SHAPE@", FC_APN, FC_YEAR, "COUNTY"]) as ins:
        for shape, apn, yr, county in src:
            if apn:
                ins.insertRow([shape, str(apn).strip(), YEAR, county])
                count += 1

    log.info("Inserted %d rows from SOURCE_FC (YEAR=%d)", count, YEAR)

    # Dedup: keep largest polygon per APN
    log.info("Deduplicating by APN (keep largest polygon) ...")
    best = {}
    dup_oids = []
    with arcpy.da.SearchCursor(OUTPUT_2025, ["OID@", FC_APN, "SHAPE@AREA"]) as cur:
        for oid, apn, area in cur:
            if not apn:
                continue
            key = str(apn).strip()
            area = area or 0
            if key not in best:
                best[key] = (oid, area)
            else:
                prev_oid, prev_area = best[key]
                if area > prev_area:
                    dup_oids.append(prev_oid)
                    best[key] = (oid, area)
                else:
                    dup_oids.append(oid)

    if dup_oids:
        oid_field = arcpy.Describe(OUTPUT_2025).OIDFieldName
        batch = 500
        removed = 0
        for i in range(0, len(dup_oids), batch):
            chunk = dup_oids[i:i + batch]
            oid_list = ", ".join(str(o) for o in chunk)
            where = f"{oid_field} IN ({oid_list})"
            tmp_lyr = "dedup_lyr"
            if arcpy.Exists(tmp_lyr):
                arcpy.management.Delete(tmp_lyr)
            arcpy.management.MakeFeatureLayer(OUTPUT_2025, tmp_lyr, where)
            n = int(arcpy.management.GetCount(tmp_lyr).getOutput(0))
            if n > 0:
                arcpy.management.DeleteRows(tmp_lyr)
                removed += n
            arcpy.management.Delete(tmp_lyr)
        log.info("Dedup: removed %d duplicate rows", removed)

    final_count = int(arcpy.management.GetCount(OUTPUT_2025).getOutput(0))
    log.info("Step 1 complete: %d parcels in OUTPUT_2025", final_count)
    return final_count


# =============================================================================
# Step 2 -- Populate COUNTY and JURISDICTION via spatial join
# =============================================================================
def step2_jurisdiction():
    """Spatial join parcel centroids to TRPA Jurisdictions service."""
    log.info("=== Step 2: Populate COUNTY and JURISDICTION ===")

    # Build in-memory centroid point FC (one per unique APN)
    mem_pts = "memory/jurisdiction_pts"
    mem_join = "memory/jurisdiction_join"
    for m in [mem_pts, mem_join]:
        if arcpy.Exists(m):
            arcpy.management.Delete(m)

    sr = arcpy.Describe(OUTPUT_2025).spatialReference
    arcpy.management.CreateFeatureclass("memory", "jurisdiction_pts", "POINT",
                                        spatial_reference=sr)
    arcpy.management.AddField(mem_pts, "APN", "TEXT", field_length=50)

    seen = set()
    with arcpy.da.SearchCursor(OUTPUT_2025, [FC_APN, "SHAPE@"]) as src, \
         arcpy.da.InsertCursor(mem_pts, ["SHAPE@", "APN"]) as ins:
        for apn, shape in src:
            if apn and apn not in seen and shape:
                centroid = shape.centroid
                ins.insertRow([arcpy.PointGeometry(centroid, sr), str(apn).strip()])
                seen.add(apn)

    log.info("Built centroid FC: %d unique APNs", len(seen))

    # Spatial join to Jurisdictions service
    jur_lyr = "jur_svc_lyr"
    if arcpy.Exists(jur_lyr):
        arcpy.management.Delete(jur_lyr)
    arcpy.management.MakeFeatureLayer(JURISDICTION_SVC, jur_lyr)

    arcpy.analysis.SpatialJoin(
        mem_pts, jur_lyr, mem_join,
        "JOIN_ONE_TO_ONE", "KEEP_ALL", match_option="WITHIN")

    # Read results
    join_fields = [f.name for f in arcpy.ListFields(mem_join)]
    county_fld = next((f for f in join_fields if f.upper() == "COUNTY"), None)
    juris_fld = next((f for f in join_fields if "JURISDICTI" in f.upper()), None)

    apn_county = {}
    apn_juris = {}

    if county_fld:
        with arcpy.da.SearchCursor(mem_join, ["APN", county_fld] +
                                   ([juris_fld] if juris_fld else [])) as cur:
            for row in cur:
                apn = row[0]
                county_name = row[1]
                juris = row[2] if juris_fld else None
                if apn and county_name:
                    code = COUNTY_CODE_MAP.get(county_name, county_name)
                    apn_county[str(apn).strip()] = code
                    if juris:
                        apn_juris[str(apn).strip()] = juris

    # Pass 2: CLOSEST for unmatched
    matched = set(apn_county.keys())
    unmatched = seen - matched
    if unmatched:
        log.info("  %d APNs unmatched after WITHIN, trying CLOSEST ...", len(unmatched))
        mem_join2 = "memory/jurisdiction_join2"
        if arcpy.Exists(mem_join2):
            arcpy.management.Delete(mem_join2)
        apn_filter = " OR ".join(f"APN = '{a}'" for a in list(unmatched)[:500])
        pt_lyr = "jur_pt_lyr"
        if arcpy.Exists(pt_lyr):
            arcpy.management.Delete(pt_lyr)
        arcpy.management.MakeFeatureLayer(mem_pts, pt_lyr, apn_filter)
        arcpy.analysis.SpatialJoin(
            pt_lyr, jur_lyr, mem_join2,
            "JOIN_ONE_TO_ONE", "KEEP_ALL",
            match_option="CLOSEST", search_radius="100 Meters")
        if county_fld:
            with arcpy.da.SearchCursor(mem_join2, ["APN", county_fld] +
                                       ([juris_fld] if juris_fld else [])) as cur:
                for row in cur:
                    apn = row[0]
                    county_name = row[1]
                    juris = row[2] if juris_fld else None
                    if apn and county_name:
                        code = COUNTY_CODE_MAP.get(county_name, county_name)
                        apn_county[str(apn).strip()] = code
                        if juris:
                            apn_juris[str(apn).strip()] = juris
        for m in [mem_join2, pt_lyr]:
            if arcpy.Exists(m):
                arcpy.management.Delete(m)

    # Write back to OUTPUT_2025
    # Ensure JURISDICTION field exists
    existing_fields = {f.name for f in arcpy.ListFields(OUTPUT_2025)}
    if "JURISDICTION" not in existing_fields:
        arcpy.management.AddField(OUTPUT_2025, "JURISDICTION", "TEXT", field_length=50)

    updated = 0
    with arcpy.da.UpdateCursor(OUTPUT_2025, [FC_APN, "COUNTY", "JURISDICTION"]) as cur:
        for apn, county, juris in cur:
            if not apn:
                continue
            a = str(apn).strip()
            new_county = apn_county.get(a, county)
            new_juris = apn_juris.get(a, juris)
            if new_county != county or new_juris != juris:
                cur.updateRow([apn, new_county, new_juris])
                updated += 1

    # Normalize El Dorado APNs to 3-digit (2025 >= EL_PAD_YEAR)
    el_fixed = 0
    with arcpy.da.UpdateCursor(OUTPUT_2025, [FC_APN, "COUNTY"]) as cur:
        for apn, county in cur:
            if county == "EL" and apn and _EL_2D.match(str(apn).strip()):
                cur.updateRow([el_pad(str(apn).strip()), county])
                el_fixed += 1

    log.info("Jurisdiction populated: %d APNs updated", updated)
    log.info("El Dorado APNs padded to 3-digit: %d", el_fixed)
    log.info("County breakdown:")
    county_counts = {}
    with arcpy.da.SearchCursor(OUTPUT_2025, ["COUNTY"]) as cur:
        for (c,) in cur:
            county_counts[c or "NULL"] = county_counts.get(c or "NULL", 0) + 1
    for c in sorted(county_counts):
        log.info("  %-6s: %d", c, county_counts[c])

    for m in [mem_pts, mem_join, jur_lyr]:
        if arcpy.Exists(m):
            arcpy.management.Delete(m)

    log.info("Step 2 complete.")


# =============================================================================
# Step 3 -- Load CSVs, apply corrections, build lookups (2025 only)
# =============================================================================

def _build_el_dorado_sets():
    """Build El Dorado 2-digit and 3-digit APN sets from the output FC (COUNTY='EL').
    For 2025 the FC already has 3-digit APNs; we return both sets so we can
    pad any 2-digit CSV APNs whose padded form exists in the FC.
    """
    el_2d = set()
    el_3d = set()
    with arcpy.da.SearchCursor(OUTPUT_2025, [FC_APN],
                               where_clause="COUNTY = 'EL'") as cur:
        for (apn,) in cur:
            if apn:
                a = str(apn).strip()
                if _EL_3D.match(a):
                    el_3d.add(a)
                elif _EL_2D.match(a):
                    el_2d.add(a)
    return el_2d, el_3d


def _load_genealogy():
    """Load consolidated genealogy master table."""
    if not Path(GENEALOGY_TAHOE).exists():
        return pd.DataFrame()
    gen = pd.read_csv(GENEALOGY_TAHOE, dtype=str)
    gen.columns = gen.columns.str.strip()
    gen["is_primary"] = pd.to_numeric(gen.get("is_primary", pd.Series()), errors="coerce").fillna(0).astype(int)
    gen["in_fc_new"] = pd.to_numeric(gen.get("in_fc_new", pd.Series()), errors="coerce").fillna(0).astype(int)
    gen["source_priority"] = pd.to_numeric(gen.get("source_priority", pd.Series()), errors="coerce").fillna(4).astype(int)
    gen = gen[(gen["is_primary"] == 1) & (gen["in_fc_new"] == 1)].copy()
    gen["change_year"] = pd.to_numeric(gen["change_year"], errors="coerce")
    gen = gen.dropna(subset=["change_year"])
    gen["change_year"] = gen["change_year"].astype(int)
    return gen.sort_values(["source_priority", "change_year"])


def _apply_genealogy(df, gen, label=""):
    """Apply genealogy corrections to a long-format DataFrame with APN, Year, value columns."""
    if gen.empty:
        log.info("  No genealogy to apply for %s", label)
        return df, []

    qa_rows = []
    remapped = set()
    subs = 0
    for _, rec in gen.iterrows():
        old, new, cy = rec["apn_old"], rec["apn_new"], int(rec["change_year"])
        if old == new or old in remapped:
            continue
        # For 2025-only, change_year must be <= 2025
        if cy > YEAR:
            continue
        mask = (df["APN"] == old)
        if not mask.any():
            continue
        existing_new = set(df.loc[df["APN"] == new, "Year"]) if "Year" in df.columns else set()
        safe = mask & ~df["Year"].isin(existing_new)
        if safe.any():
            val_col = [c for c in df.columns if c not in ("APN", "Year", "APN_orig")][0]
            units_moved = df.loc[safe, val_col].sum()
            df.loc[safe, "APN"] = new
            remapped.add(old)
            subs += 1
            qa_rows.append({
                "Old_APN": old, "New_APN": new, "Change_Year": cy,
                "Source": str(rec.get("source", "")),
                "Units_Moved": int(units_moved),
            })

    log.info("  Genealogy: %d APN substitutions for %s", subs, label)
    return df, qa_rows


def _apply_el_dorado_fix(df, el_2d, el_3d):
    """Pad 2-digit El Dorado CSV APNs to 3-digit where the padded form exists in FC."""
    # Find CSV APNs in 2-digit format whose padded version is in the FC
    pad_map = {}
    for a in df["APN"].unique():
        if _EL_2D.match(str(a)):
            padded = el_pad(str(a))
            if padded in el_3d:
                pad_map[a] = padded

    before = df["APN"].copy()
    df["APN"] = df["APN"].map(lambda a: pad_map.get(a, a))
    changed = (df["APN"] != before).sum()
    log.info("  El Dorado fix: %d rows padded (%d unique APNs)", changed, len(pad_map))
    return df


def _strip_trailing_zero(df, fc_apns):
    """Strip trailing '-0' from CSV APNs that don't match the FC but would match without it.

    Only applies to APNs ending in '-0' whose stripped form exists in fc_apns
    and whose original form does NOT exist in fc_apns.
    """
    strip_map = {}
    for a in df["APN"].unique():
        a_str = str(a)
        if a_str.endswith("-0") and a_str not in fc_apns:
            stripped = a_str[:-2]  # remove trailing '-0'
            if stripped in fc_apns:
                strip_map[a] = stripped

    if not strip_map:
        log.info("  Trailing -0 fix: no APNs to strip")
        return df

    before = df["APN"].copy()
    df["APN"] = df["APN"].map(lambda a: strip_map.get(a, a))
    changed = (df["APN"] != before).sum()
    log.info("  Trailing -0 fix: %d rows stripped (%d unique APNs)", changed, len(strip_map))
    return df


def _load_residential_csv():
    """Load residential CSV, extract 2025 column, return long-format DataFrame."""
    log.info("Loading residential CSV ...")
    df_wide = pd.read_csv(CSV_PATH)
    col_2025 = [c for c in df_wide.columns if "2025" in c and "Final" in c]
    if not col_2025:
        log.error("No 2025 Final column found in residential CSV!")
        return pd.DataFrame()

    df = df_wide[["APN", col_2025[0]]].copy()
    df.columns = ["APN", "Units_CSV"]
    df["Year"] = YEAR
    df["Units_CSV"] = pd.to_numeric(df["Units_CSV"], errors="coerce").fillna(0).astype(int)
    df["APN"] = df["APN"].astype(str).str.strip()
    log.info("  %d parcels loaded from residential CSV", len(df))
    return df


def _load_wide_csv(csv_path, label, value_col_name):
    """Load a wide-format APN x CY<year> CSV, extract 2025 column."""
    if not Path(csv_path).exists():
        log.info("  %s CSV not found -- skipping", label)
        return pd.DataFrame()

    df_wide = pd.read_csv(csv_path, dtype=str)
    # Normalise APN column
    if "APN" not in df_wide.columns:
        first = df_wide.columns[0]
        df_wide = df_wide.rename(columns={first: "APN"})

    df_wide = df_wide.dropna(subset=["APN"])
    col_2025 = [c for c in df_wide.columns if "2025" in c]
    if not col_2025:
        log.warning("  %s CSV has no 2025 column -- skipping", label)
        return pd.DataFrame()

    df = df_wide[["APN", col_2025[0]]].copy()
    df.columns = ["APN", value_col_name]
    df["Year"] = YEAR
    df[value_col_name] = pd.to_numeric(df[value_col_name], errors="coerce").fillna(0)
    df["APN"] = df["APN"].astype(str).str.strip()
    log.info("  %s: %d parcels loaded", label, len(df))
    return df


def _load_fc_native_units():
    """Load FC native residential units from SOURCE_FC.

    Uses YEAR=2024 as comparison baseline (2025 has no native units in
    SOURCE_FC, but 2024 has ~42k parcels with values from prior team work).
    """
    NATIVE_YEAR = 2024
    native = {}
    if arcpy.Exists(SOURCE_FC):
        where = f"{FC_YEAR} = {NATIVE_YEAR} AND {FC_UNITS} > 0"
        with arcpy.da.SearchCursor(SOURCE_FC, [FC_APN, FC_UNITS], where) as cur:
            for apn, units in cur:
                if apn and units:
                    native[str(apn).strip()] = int(units)
    log.info("  FC native units from SOURCE_FC (YEAR=%d): %d APNs",
             NATIVE_YEAR, len(native))
    return native


def step3_load_and_correct():
    """Load all CSVs, apply El Dorado fix + genealogy, build lookups."""
    log.info("=== Step 3: Load CSVs and apply corrections ===")

    el_2d, el_3d = _build_el_dorado_sets()
    log.info("El Dorado APNs: %d 2-digit, %d 3-digit", len(el_2d), len(el_3d))

    # Build FC APN set for trailing-zero fix
    fc_apns = set()
    with arcpy.da.SearchCursor(OUTPUT_2025, [FC_APN]) as cur:
        for (apn,) in cur:
            if apn:
                fc_apns.add(str(apn).strip())

    gen = _load_genealogy()
    if not gen.empty:
        log.info("Genealogy master: %d apply-ready rows", len(gen))

    all_genealogy_qa = []

    # -- Apply manual APN fixes to any DataFrame ------------------------------
    def _apply_manual_fixes(df):
        """Remap APNs using MANUAL_APN_FIXES (user-verified successors)."""
        before = df["APN"].copy()
        df["APN"] = df["APN"].map(lambda a: MANUAL_APN_FIXES.get(a, a))
        changed = (df["APN"] != before).sum()
        if changed:
            log.info("  Manual APN fixes: %d rows remapped", changed)
        return df

    # -- Residential --------------------------------------------------------
    df_res = _load_residential_csv()
    df_res = _apply_el_dorado_fix(df_res, el_2d, el_3d)
    df_res, qa_res = _apply_genealogy(df_res, gen, "Residential")
    all_genealogy_qa.extend(qa_res)
    df_res = _strip_trailing_zero(df_res, fc_apns)
    df_res = _apply_manual_fixes(df_res)
    res_lookup = {str(row.APN).strip(): int(row.Units_CSV)
                  for row in df_res.itertuples(index=False)}
    log.info("Residential lookup: %d entries", len(res_lookup))

    # -- Tourist ------------------------------------------------------------
    df_tourist = _load_wide_csv(TOURIST_UNITS_CSV, "Tourist units", "TAU")
    if not df_tourist.empty:
        df_tourist = _apply_el_dorado_fix(df_tourist, el_2d, el_3d)
        df_tourist, qa_t = _apply_genealogy(df_tourist, gen, "Tourist")
        all_genealogy_qa.extend(qa_t)
        df_tourist = _strip_trailing_zero(df_tourist, fc_apns)
        df_tourist = _apply_manual_fixes(df_tourist)
    tourist_lookup = {str(row.APN).strip(): int(row.TAU)
                      for row in df_tourist.itertuples(index=False)
                      if row.TAU > 0} if not df_tourist.empty else {}
    log.info("Tourist lookup: %d non-zero entries", len(tourist_lookup))

    # -- Commercial ---------------------------------------------------------
    df_comm = _load_wide_csv(COMMERCIAL_SQFT_CSV, "Commercial sqft", "CFA")
    if not df_comm.empty:
        df_comm = _apply_el_dorado_fix(df_comm, el_2d, el_3d)
        df_comm, qa_c = _apply_genealogy(df_comm, gen, "Commercial")
        all_genealogy_qa.extend(qa_c)
        df_comm = _strip_trailing_zero(df_comm, fc_apns)
        df_comm = _apply_manual_fixes(df_comm)
    comm_lookup = {str(row.APN).strip(): float(row.CFA)
                   for row in df_comm.itertuples(index=False)
                   if row.CFA > 0} if not df_comm.empty else {}
    log.info("Commercial lookup: %d non-zero entries", len(comm_lookup))

    # -- FC native residential for Unit_Source reconciliation ----------------
    fc_native = _load_fc_native_units()

    # -- Write genealogy QA -------------------------------------------------
    if all_genealogy_qa:
        df_qa = pd.DataFrame(all_genealogy_qa)
        try:
            df_to_gdb_table(df_qa, QA_GENEALOGY,
                            text_lengths={"Old_APN": 50, "New_APN": 50, "Source": 20})
        except Exception as exc:
            log.warning("Could not write genealogy QA: %s", exc)

    # Capture raw CSV totals BEFORE crosswalk modifies the lookups
    csv_totals = {
        "res": sum(v for v in res_lookup.values() if v > 0),
        "tau": sum(v for v in tourist_lookup.values() if v > 0),
        "cfa": sum(v for v in comm_lookup.values() if v > 0),
    }
    log.info("Raw CSV totals: res=%d  tau=%d  cfa=%.0f",
             csv_totals["res"], csv_totals["tau"], csv_totals["cfa"])

    return res_lookup, tourist_lookup, comm_lookup, fc_native, df_res, csv_totals


# =============================================================================
# Step 4 -- Crosswalk: resolve CSV APNs missing from the FC
# =============================================================================
def step4_crosswalk(res_lookup, tourist_lookup, comm_lookup, df_res):
    """Resolve CSV APNs not in OUTPUT_2025 via centroid spatial join."""
    log.info("=== Step 4: APN Crosswalk ===")

    # Get FC APNs
    fc_apns = set()
    with arcpy.da.SearchCursor(OUTPUT_2025, [FC_APN]) as cur:
        for (apn,) in cur:
            if apn:
                fc_apns.add(str(apn).strip())

    # Find CSV APNs missing from FC
    csv_apns = set(res_lookup.keys()) | set(tourist_lookup.keys()) | set(comm_lookup.keys())
    missing_apns = csv_apns - fc_apns
    log.info("FC APNs: %d, CSV APNs: %d, Missing: %d", len(fc_apns), len(csv_apns), len(missing_apns))

    if not missing_apns:
        log.info("No missing APNs -- crosswalk not needed.")
        return res_lookup, tourist_lookup, comm_lookup, []

    # Get geometry for missing APNs -- SOURCE_FC first, then All Parcels service
    sr = arcpy.Describe(OUTPUT_2025).spatialReference
    mem_pts = "memory/xwalk_pts_2025"
    mem_join = "memory/xwalk_join_2025"
    for m in [mem_pts, mem_join]:
        if arcpy.Exists(m):
            arcpy.management.Delete(m)

    arcpy.management.CreateFeatureclass("memory", "xwalk_pts_2025", "POINT",
                                        spatial_reference=sr)
    arcpy.management.AddField(mem_pts, "CSV_APN", "TEXT", field_length=50)

    pts_built = 0
    found_in_src = set()

    # Build a reverse lookup: depadded El Dorado APN -> original CSV APN
    # e.g. '027-323-10' -> '027-323-010' so SOURCE_FC 2-digit hits resolve
    depad_to_csv = {}
    for a in missing_apns:
        dp = el_depad(a)
        if dp != a:
            depad_to_csv[dp] = a

    # Pass A: SOURCE_FC -- has geometry for most historic APNs (any year)
    if arcpy.Exists(SOURCE_FC):
        src_geom = {}  # CSV_APN -> SHAPE@ (keep largest)
        with arcpy.da.SearchCursor(SOURCE_FC, [FC_APN, "SHAPE@"]) as cur:
            for apn, geom in cur:
                if not apn or not geom:
                    continue
                a = str(apn).strip()
                # Direct match (CSV APN == SOURCE_FC APN)
                csv_key = None
                if a in missing_apns:
                    csv_key = a
                # Depadded match (SOURCE_FC has 2-digit, CSV has 3-digit)
                elif a in depad_to_csv:
                    csv_key = depad_to_csv[a]

                if csv_key:
                    area = geom.area or 0
                    if csv_key not in src_geom or area > src_geom[csv_key].area:
                        src_geom[csv_key] = geom
        with arcpy.da.InsertCursor(mem_pts, ["SHAPE@", "CSV_APN"]) as ins:
            for a, geom in src_geom.items():
                centroid = geom.centroid
                ins.insertRow([arcpy.PointGeometry(centroid, sr), a])
                pts_built += 1
                found_in_src.add(a)
        log.info("  SOURCE_FC geometry: %d centroids built (%d via El Dorado depad)",
                 len(found_in_src),
                 sum(1 for a in found_in_src if el_depad(a) != a))

    # Pass B: All Parcels service for anything still missing
    still_need = missing_apns - found_in_src
    if still_need:
        lyr = "allparcels_current_lyr"
        if arcpy.Exists(lyr):
            arcpy.management.Delete(lyr)
        try:
            arcpy.management.MakeFeatureLayer(ALL_PARCELS_CURRENT, lyr)
            apn_list = sorted(still_need)
            batch = 100
            for i in range(0, len(apn_list), batch):
                chunk = apn_list[i:i + batch]
                sql = " OR ".join(f"{FC_APN} = '{a}'" for a in chunk)
                arcpy.management.SelectLayerByAttribute(lyr, "NEW_SELECTION", sql)
                with arcpy.da.SearchCursor(lyr, [FC_APN, "SHAPE@"]) as cur:
                    for apn, geom in cur:
                        if apn and geom and geom.area > 0:
                            a = str(apn).strip()
                            centroid = geom.centroid
                            with arcpy.da.InsertCursor(mem_pts, ["SHAPE@", "CSV_APN"]) as ic:
                                ic.insertRow([arcpy.PointGeometry(centroid, sr), a])
                            pts_built += 1
        except Exception as exc:
            log.warning("All Parcels service query failed: %s", exc)
        finally:
            if arcpy.Exists(lyr):
                arcpy.management.Delete(lyr)

    log.info("Built %d total centroid points for %d missing APNs", pts_built, len(missing_apns))

    if pts_built == 0:
        log.info("No geometry found for missing APNs -- crosswalk skipped.")
        return res_lookup, tourist_lookup, comm_lookup, []

    # Spatial join: centroid -> OUTPUT_2025
    fc_lyr = "xwalk_fc_lyr"
    if arcpy.Exists(fc_lyr):
        arcpy.management.Delete(fc_lyr)
    arcpy.management.MakeFeatureLayer(OUTPUT_2025, fc_lyr)

    crosswalk_rows = []

    # Pass 1: INTERSECT
    if arcpy.Exists(mem_join):
        arcpy.management.Delete(mem_join)
    arcpy.analysis.SpatialJoin(
        mem_pts, fc_lyr, mem_join,
        "JOIN_ONE_TO_ONE", "KEEP_ALL", match_option="INTERSECT")
    with arcpy.da.SearchCursor(mem_join, ["CSV_APN", FC_APN, "Join_Count"]) as cur:
        for csv_apn, fc_apn, jc in cur:
            if jc and jc > 0 and fc_apn:
                crosswalk_rows.append({"CSV_APN": csv_apn, "FC_APN": fc_apn,
                                       "Match_Type": "intersect"})

    # Pass 2: CLOSEST for unmatched
    matched_p1 = {r["CSV_APN"] for r in crosswalk_rows}
    still_missing = missing_apns - matched_p1
    if still_missing and pts_built > 0:
        if arcpy.Exists(mem_join):
            arcpy.management.Delete(mem_join)
        pt_lyr2 = "xwalk_pt_lyr2"
        if arcpy.Exists(pt_lyr2):
            arcpy.management.Delete(pt_lyr2)
        still_list = list(still_missing)[:500]
        apn_filter = " OR ".join(f"CSV_APN = '{a}'" for a in still_list)
        arcpy.management.MakeFeatureLayer(mem_pts, pt_lyr2, apn_filter)
        arcpy.analysis.SpatialJoin(
            pt_lyr2, fc_lyr, mem_join,
            "JOIN_ONE_TO_ONE", "KEEP_ALL",
            match_option="CLOSEST",
            search_radius=f"{CLOSEST_MAX_METERS} Meters",
            distance_field_name="DISTANCE")
        with arcpy.da.SearchCursor(mem_join, ["CSV_APN", FC_APN, "Join_Count", "DISTANCE"]) as cur:
            for csv_apn, fc_apn, jc, dist in cur:
                if jc and jc > 0 and fc_apn and dist <= CLOSEST_MAX_METERS:
                    crosswalk_rows.append({"CSV_APN": csv_apn, "FC_APN": fc_apn,
                                           "Match_Type": f"closest_{dist:.1f}m"})
        if arcpy.Exists(pt_lyr2):
            arcpy.management.Delete(pt_lyr2)

    # Extend lookups — sum into target when FC APN already has a value,
    # because the CSV tracks retired parcels separately from their successors.
    added = 0
    summed = 0
    for r in crosswalk_rows:
        csv_apn = r["CSV_APN"]
        fc_apn = r["FC_APN"]
        # Residential
        if csv_apn in res_lookup:
            if fc_apn not in res_lookup:
                res_lookup[fc_apn] = res_lookup[csv_apn]
                added += 1
            else:
                res_lookup[fc_apn] += res_lookup[csv_apn]
                summed += 1
        # Tourist
        if csv_apn in tourist_lookup:
            if fc_apn not in tourist_lookup:
                tourist_lookup[fc_apn] = tourist_lookup[csv_apn]
            else:
                tourist_lookup[fc_apn] += tourist_lookup[csv_apn]
        # Commercial
        if csv_apn in comm_lookup:
            if fc_apn not in comm_lookup:
                comm_lookup[fc_apn] = comm_lookup[csv_apn]
            else:
                comm_lookup[fc_apn] += comm_lookup[csv_apn]

    log.info("Crosswalk: %d APNs resolved, %d residential added, %d summed into existing",
             len(crosswalk_rows), added, summed)

    # Write QA table
    if crosswalk_rows:
        df_xwalk = pd.DataFrame(crosswalk_rows)
        try:
            df_to_gdb_table(df_xwalk, QA_XWALK,
                            text_lengths={"CSV_APN": 50, "FC_APN": 50, "Match_Type": 50})
        except Exception as exc:
            log.warning("Could not write crosswalk QA: %s", exc)

    for m in [mem_pts, mem_join, fc_lyr]:
        if arcpy.Exists(m):
            arcpy.management.Delete(m)

    log.info("Step 4 complete.")
    return res_lookup, tourist_lookup, comm_lookup, crosswalk_rows


# =============================================================================
# Step 5 -- Write units to the FC
# =============================================================================
def _safe_int(val):
    if val is None:
        return 0
    try:
        if math.isnan(float(val)):
            return 0
    except (TypeError, ValueError):
        pass
    return int(val)


def step5_write_units(res_lookup, tourist_lookup, comm_lookup, fc_native):
    """Write Residential_Units, Tourist, Commercial + Unit_Source to FC."""
    log.info("=== Step 5: Write units to OUTPUT_2025 ===")

    # Ensure fields exist
    existing_fields = {f.name for f in arcpy.ListFields(OUTPUT_2025)}
    for fname, ftype, flen in [
        ("FC_Native_Units", "LONG", None),
        ("Unit_Source", "TEXT", 15),
    ]:
        if fname not in existing_fields:
            if flen:
                arcpy.management.AddField(OUTPUT_2025, fname, ftype, field_length=flen)
            else:
                arcpy.management.AddField(OUTPUT_2025, fname, ftype)
            log.info("Added field: %s", fname)

    counts = {"CSV": 0, "FC": 0, "BOTH": 0, "ZERO": 0}
    t_updated = c_updated = 0
    updated = 0

    with arcpy.da.UpdateCursor(
            OUTPUT_2025,
            [FC_APN, FC_UNITS, FC_TOURIST_UNITS, FC_COMMERCIAL_SQFT,
             "FC_Native_Units", "Unit_Source"]) as cur:

        for apn, res_raw, tau_raw, cfa_raw, _, _ in cur:
            if not apn:
                continue
            a = str(apn).strip()

            # Residential — CSV is sole authority; FC native kept for reference only
            csv_v = res_lookup.get(a)
            native_v = fc_native.get(a, 0)
            csv_int = _safe_int(csv_v) if csv_v is not None else 0

            if csv_int > 0 and native_v > 0:
                merged = csv_int
                source = "BOTH"
            elif csv_int > 0:
                merged = csv_int
                source = "CSV"
            else:
                merged = 0
                source = "CSV"

            if merged == 0 and source == "CSV":
                counts["ZERO"] += 1
            else:
                counts[source] += 1

            # Tourist
            t_val = tourist_lookup.get(a, 0)
            if t_val > 0:
                t_updated += 1

            # Commercial
            c_val = comm_lookup.get(a, 0)
            if c_val > 0:
                c_updated += 1

            cur.updateRow([apn, merged, int(t_val), float(c_val), native_v, source])
            updated += 1

    log.info("Rows updated: %d", updated)
    log.info("  BOTH (CSV + FC agree): %d", counts["BOTH"])
    log.info("  CSV only:              %d", counts["CSV"])
    log.info("  FC only:               %d", counts["FC"])
    log.info("  Zero units:            %d", counts["ZERO"])
    log.info("  Tourist non-zero:      %d", t_updated)
    log.info("  Commercial non-zero:   %d", c_updated)
    log.info("Step 5 complete.")


# =============================================================================
# Step 6 -- Spatial attribute: TAZ
# =============================================================================
def step6_taz():
    """Spatial join parcels to TAZ service layer.

    NOTE: We copy the TAZ service to an in-memory FC first to avoid
    service-backed field-transfer issues with spatial joins, and use
    INTERSECT (works reliably across all SR configurations).
    """
    log.info("=== Step 6: TAZ spatial join ===")

    # Ensure TAZ field exists (TEXT so we can store integer TAZ ids cleanly)
    existing_fields = {f.name for f in arcpy.ListFields(OUTPUT_2025)}
    if "TAZ" not in existing_fields:
        arcpy.management.AddField(OUTPUT_2025, "TAZ", "TEXT", field_length=20)

    # Copy TAZ service locally to avoid service-backed join issues
    taz_url = SPATIAL_SOURCES["TAZ"]
    mem_taz = "memory/taz_local"
    mem_join = "memory/taz_join_2025"
    fc_lyr = "taz_fc_lyr"
    for m in [mem_taz, mem_join, fc_lyr]:
        if arcpy.Exists(m):
            arcpy.management.Delete(m)

    arcpy.management.CopyFeatures(taz_url, mem_taz)
    log.info("Copied TAZ service to memory (%d features)",
             int(arcpy.management.GetCount(mem_taz).getOutput(0)))

    arcpy.management.MakeFeatureLayer(OUTPUT_2025, fc_lyr)

    # INTERSECT works reliably; LARGEST_OVERLAP can fail with some SR configs
    arcpy.analysis.SpatialJoin(
        fc_lyr, mem_taz, mem_join,
        "JOIN_ONE_TO_ONE", "KEEP_ALL",
        match_option="INTERSECT")

    # The join result has TAZ (from our FC, all null) and TAZ_1 (from service)
    join_fields = [f.name for f in arcpy.ListFields(mem_join)]
    taz_fld = "TAZ_1" if "TAZ_1" in join_fields else "TAZ"

    taz_map = {}
    with arcpy.da.SearchCursor(mem_join, [FC_APN, taz_fld]) as cur:
        for apn, taz_val in cur:
            if apn and taz_val is not None:
                taz_map[str(apn).strip()] = str(int(taz_val))

    # Write back
    updated = 0
    with arcpy.da.UpdateCursor(OUTPUT_2025, [FC_APN, "TAZ"]) as cur:
        for apn, taz in cur:
            if not apn:
                continue
            new_taz = taz_map.get(str(apn).strip())
            if new_taz:
                cur.updateRow([apn, new_taz])
                updated += 1

    log.info("TAZ populated: %d / %d parcels", updated,
             int(arcpy.management.GetCount(OUTPUT_2025).getOutput(0)))

    for m in [mem_taz, mem_join, fc_lyr]:
        if arcpy.Exists(m):
            arcpy.management.Delete(m)

    log.info("Step 6 complete.")


# =============================================================================
# Step 7 -- QA Summary
# =============================================================================
def step7_qa(res_lookup, tourist_lookup, comm_lookup, fc_native, df_res, xwalk_rows, csv_totals):
    """Generate QA summary tables + APN_Mapping table."""
    log.info("=== Step 7: QA Summary ===")

    # -- Overall stats -------------------------------------------------------
    total_parcels = int(arcpy.management.GetCount(OUTPUT_2025).getOutput(0))
    total_res = sum(1 for v in res_lookup.values() if v > 0)
    total_tau = len(tourist_lookup)
    total_cfa = len(comm_lookup)

    log.info("OUTPUT_2025 parcels: %d", total_parcels)
    log.info("Residential CSV non-zero APNs: %d", total_res)
    log.info("Tourist units in CSV (non-zero): %d", total_tau)
    log.info("Commercial sqft in CSV (non-zero): %d", total_cfa)

    # -- Read back from FC for verification ----------------------------------
    fc_data = {"res": 0, "tau": 0, "cfa": 0}
    source_counts = {}
    taz_null = 0
    fc_res_by_apn = {}
    fc_tau_by_apn = {}
    fc_cfa_by_apn = {}
    with arcpy.da.SearchCursor(
            OUTPUT_2025,
            [FC_APN, FC_UNITS, FC_TOURIST_UNITS, FC_COMMERCIAL_SQFT,
             "Unit_Source", "TAZ"]) as cur:
        for apn, res, tau, cfa, source, taz in cur:
            a = str(apn).strip() if apn else ""
            res = _safe_int(res)
            tau = _safe_int(tau)
            cfa_v = cfa or 0
            if res > 0:
                fc_data["res"] += 1
                fc_res_by_apn[a] = res
            if tau > 0:
                fc_data["tau"] += 1
                fc_tau_by_apn[a] = tau
            if cfa_v > 0:
                fc_data["cfa"] += 1
                fc_cfa_by_apn[a] = cfa_v
            s = source or "NONE"
            source_counts[s] = source_counts.get(s, 0) + 1
            if not taz:
                taz_null += 1

    log.info("")
    log.info("--- FC Verification ---")
    log.info("Parcels with Residential_Units > 0: %d", fc_data["res"])
    log.info("Parcels with TouristAccommodation_Units > 0: %d", fc_data["tau"])
    log.info("Parcels with CommercialFloorArea_SqFt > 0: %d", fc_data["cfa"])
    log.info("TAZ null count: %d / %d", taz_null, total_parcels)
    log.info("")
    log.info("Unit_Source breakdown:")
    for s in sorted(source_counts):
        log.info("  %-6s: %d", s, source_counts[s])

    # Use pre-crosswalk CSV totals (captured before crosswalk inflated the lookups)
    xwalk_csv_apns = {r["CSV_APN"] for r in (xwalk_rows or [])}
    csv_total_units = csv_totals["res"]
    csv_total_tau = csv_totals["tau"]
    csv_total_cfa = csv_totals["cfa"]

    fc_total_units = sum(fc_res_by_apn.values())
    fc_total_tau = sum(fc_tau_by_apn.values())
    fc_total_cfa = sum(fc_cfa_by_apn.values())
    fc_native_total = sum(v for v in fc_native.values() if v > 0)

    log.info("")
    log.info("--- Unit Totals (CSV vs FC Output) ---")
    log.info("Residential:  CSV=%d  FC_native=%d  FC_output=%d  diff=%d",
             csv_total_units, fc_native_total, fc_total_units,
             fc_total_units - csv_total_units)
    log.info("Tourist:      CSV=%d  FC_output=%d  diff=%d",
             csv_total_tau, fc_total_tau, fc_total_tau - csv_total_tau)
    log.info("Commercial:   CSV=%.0f  FC_output=%.0f  diff=%.0f",
             csv_total_cfa, fc_total_cfa, fc_total_cfa - csv_total_cfa)

    # -- Build FC APN set for lost-APN analysis ------------------------------
    fc_apns = set()
    with arcpy.da.SearchCursor(OUTPUT_2025, [FC_APN]) as cur:
        for (apn,) in cur:
            if apn:
                fc_apns.add(str(apn).strip())

    # -- Lost APNs: CSV has value > 0, APN not in FC, AND not crosswalked ---
    lost_rows = []
    for apn, units in res_lookup.items():
        if units > 0 and apn not in fc_apns and apn not in xwalk_csv_apns:
            lost_rows.append({"APN": apn, "Residential_Units": units,
                              "Tourist_Units": tourist_lookup.get(apn, 0),
                              "Commercial_SqFt": comm_lookup.get(apn, 0.0)})
    seen_lost = {r["APN"] for r in lost_rows}
    for apn, units in tourist_lookup.items():
        if units > 0 and apn not in fc_apns and apn not in seen_lost and apn not in xwalk_csv_apns:
            lost_rows.append({"APN": apn, "Residential_Units": 0,
                              "Tourist_Units": units,
                              "Commercial_SqFt": comm_lookup.get(apn, 0.0)})
            seen_lost.add(apn)
    for apn, sqft in comm_lookup.items():
        if sqft > 0 and apn not in fc_apns and apn not in seen_lost and apn not in xwalk_csv_apns:
            lost_rows.append({"APN": apn, "Residential_Units": 0,
                              "Tourist_Units": 0,
                              "Commercial_SqFt": sqft})

    lost_res = sum(1 for r in lost_rows if r["Residential_Units"] > 0)
    lost_tau = sum(1 for r in lost_rows if r["Tourist_Units"] > 0)
    lost_cfa = sum(1 for r in lost_rows if r["Commercial_SqFt"] > 0)
    lost_res_units = sum(r["Residential_Units"] for r in lost_rows)
    lost_tau_units = sum(r["Tourist_Units"] for r in lost_rows)
    lost_cfa_sqft = sum(r["Commercial_SqFt"] for r in lost_rows)

    log.info("")
    log.info("--- Lost APNs (CSV value > 0, not in FC) ---")
    log.info("Residential: %d APNs / %d units lost", lost_res, lost_res_units)
    log.info("Tourist:     %d APNs / %d TAUs lost", lost_tau, lost_tau_units)
    log.info("Commercial:  %d APNs / %.0f sqft lost", lost_cfa, lost_cfa_sqft)

    if lost_rows:
        df_lost = pd.DataFrame(lost_rows)
        df_lost = df_lost.sort_values("Residential_Units", ascending=False)
        try:
            df_to_gdb_table(df_lost, QA_LOST, text_lengths={"APN": 50})
        except Exception as exc:
            log.warning("Could not write lost APNs QA: %s", exc)

    # -- Joined-but-zero: APN is in FC but CSV value didn't write ------------
    joined_zero_rows = []
    for apn, units in res_lookup.items():
        if units > 0 and apn in fc_apns and apn not in fc_res_by_apn:
            joined_zero_rows.append({
                "APN": apn, "Type": "Residential", "CSV_Value": units,
                "FC_Value": 0, "Note": "APN in FC but residential units = 0"})
    for apn, units in tourist_lookup.items():
        if units > 0 and apn in fc_apns and apn not in fc_tau_by_apn:
            joined_zero_rows.append({
                "APN": apn, "Type": "Tourist", "CSV_Value": units,
                "FC_Value": 0, "Note": "APN in FC but tourist units = 0"})
    for apn, sqft in comm_lookup.items():
        if sqft > 0 and apn in fc_apns and apn not in fc_cfa_by_apn:
            joined_zero_rows.append({
                "APN": apn, "Type": "Commercial", "CSV_Value": sqft,
                "FC_Value": 0, "Note": "APN in FC but commercial sqft = 0"})

    if joined_zero_rows:
        log.info("")
        log.info("--- Joined But Zero (APN in FC, CSV > 0, FC = 0) ---")
        jz_res = sum(1 for r in joined_zero_rows if r["Type"] == "Residential")
        jz_tau = sum(1 for r in joined_zero_rows if r["Type"] == "Tourist")
        jz_cfa = sum(1 for r in joined_zero_rows if r["Type"] == "Commercial")
        log.info("Residential: %d APNs", jz_res)
        log.info("Tourist:     %d APNs", jz_tau)
        log.info("Commercial:  %d APNs", jz_cfa)

    # =====================================================================
    # APN_Mapping table: consolidated map of old/lost APNs -> valid FC APNs
    # Sources: genealogy corrections + crosswalk spatial matches
    # =====================================================================
    log.info("")
    log.info("--- Building APN_Mapping table ---")
    mapping_rows = []

    # 1) Genealogy substitutions
    if arcpy.Exists(QA_GENEALOGY):
        with arcpy.da.SearchCursor(QA_GENEALOGY,
                                   ["Old_APN", "New_APN", "Change_Year", "Source"]) as cur:
            for old, new, cy, src in cur:
                mapping_rows.append({
                    "Lost_APN": str(old).strip(),
                    "Valid_APN": str(new).strip(),
                    "Map_Source": f"genealogy_{src}" if src else "genealogy",
                    "Change_Year": int(cy) if cy else None,
                    "In_FC": "Yes" if str(new).strip() in fc_apns else "No",
                })

    # 2) Crosswalk spatial matches
    for r in (xwalk_rows or []):
        mapping_rows.append({
            "Lost_APN": str(r["CSV_APN"]).strip(),
            "Valid_APN": str(r["FC_APN"]).strip(),
            "Map_Source": f"crosswalk_{r['Match_Type']}",
            "Change_Year": None,
            "In_FC": "Yes",
        })

    # 3) Still-lost APNs with no mapping (visible for manual fix)
    mapped_lost = {r["Lost_APN"] for r in mapping_rows}
    for r in lost_rows:
        apn = r["APN"]
        if apn not in mapped_lost:
            mapping_rows.append({
                "Lost_APN": apn,
                "Valid_APN": None,
                "Map_Source": "UNRESOLVED",
                "Change_Year": None,
                "In_FC": "No",
                "Residential_Units": r["Residential_Units"],
                "Tourist_Units": r["Tourist_Units"],
                "Commercial_SqFt": r["Commercial_SqFt"],
            })

    n_resolved = 0
    n_unresolved = 0
    if mapping_rows:
        df_map = pd.DataFrame(mapping_rows)
        for col in ["Residential_Units", "Tourist_Units", "Commercial_SqFt"]:
            if col not in df_map.columns:
                df_map[col] = 0
            df_map[col] = df_map[col].fillna(0)
        # Look up CSV values for genealogy/crosswalk rows
        for idx, row in df_map.iterrows():
            if row["Map_Source"] != "UNRESOLVED" and row["Residential_Units"] == 0:
                lost = row["Lost_APN"]
                df_map.at[idx, "Residential_Units"] = res_lookup.get(lost, 0)
                df_map.at[idx, "Tourist_Units"] = tourist_lookup.get(lost, 0)
                df_map.at[idx, "Commercial_SqFt"] = comm_lookup.get(lost, 0.0)

        # Sort: unresolved first, then by residential units descending
        sort_key = df_map["Map_Source"].eq("UNRESOLVED").map({True: 0, False: 1})
        df_map = df_map.assign(_sort=sort_key).sort_values(
            ["_sort", "Residential_Units"], ascending=[True, False]).drop(columns="_sort")

        try:
            df_to_gdb_table(df_map, APN_MAPPING,
                            text_lengths={"Lost_APN": 50, "Valid_APN": 50,
                                          "Map_Source": 50, "In_FC": 5})
            log.info("Written %d rows -> %s", len(df_map), APN_MAPPING)
        except Exception as exc:
            log.warning("Could not write APN_Mapping: %s", exc)

        n_resolved = sum(1 for _, r in df_map.iterrows() if r["Map_Source"] != "UNRESOLVED")
        n_unresolved = len(df_map) - n_resolved
        log.info("  Resolved mappings: %d", n_resolved)
        log.info("  Unresolved (need manual fix): %d", n_unresolved)

    # -- Summary table -------------------------------------------------------
    summary_rows = [
        {"Metric": "Total parcels in FC", "Value": total_parcels},
        {"Metric": "Residential CSV non-zero APNs", "Value": total_res},
        {"Metric": "Tourist CSV non-zero APNs", "Value": total_tau},
        {"Metric": "Commercial CSV non-zero APNs", "Value": total_cfa},
        {"Metric": "FC parcels with Residential > 0", "Value": fc_data["res"]},
        {"Metric": "FC parcels with Tourist > 0", "Value": fc_data["tau"]},
        {"Metric": "FC parcels with Commercial > 0", "Value": fc_data["cfa"]},
        {"Metric": "CSV residential total units", "Value": csv_total_units},
        {"Metric": "CSV tourist total TAUs", "Value": csv_total_tau},
        {"Metric": "CSV commercial total sqft", "Value": int(csv_total_cfa)},
        {"Metric": "FC output residential total units", "Value": fc_total_units},
        {"Metric": "FC output tourist total TAUs", "Value": fc_total_tau},
        {"Metric": "FC output commercial total sqft", "Value": int(fc_total_cfa)},
        {"Metric": "FC native residential total units", "Value": fc_native_total},
        {"Metric": "Residential diff (FC - CSV)", "Value": fc_total_units - csv_total_units},
        {"Metric": "Tourist diff (FC - CSV)", "Value": fc_total_tau - csv_total_tau},
        {"Metric": "Commercial diff (FC - CSV)", "Value": int(fc_total_cfa - csv_total_cfa)},
        {"Metric": "TAZ null count", "Value": taz_null},
        {"Metric": "Unit_Source = BOTH", "Value": source_counts.get("BOTH", 0)},
        {"Metric": "Unit_Source = CSV", "Value": source_counts.get("CSV", 0)},
        {"Metric": "Unit_Source = FC", "Value": source_counts.get("FC", 0)},
        {"Metric": "Lost APNs (residential)", "Value": lost_res},
        {"Metric": "Lost units (residential)", "Value": lost_res_units},
        {"Metric": "Lost APNs (tourist)", "Value": lost_tau},
        {"Metric": "Lost TAUs (tourist)", "Value": lost_tau_units},
        {"Metric": "Lost APNs (commercial)", "Value": lost_cfa},
        {"Metric": "Lost sqft (commercial)", "Value": int(lost_cfa_sqft)},
        {"Metric": "APN mappings resolved", "Value": n_resolved},
        {"Metric": "APN mappings unresolved", "Value": n_unresolved},
    ]
    df_summary = pd.DataFrame(summary_rows)
    try:
        df_to_gdb_table(df_summary, QA_TABLE,
                        text_lengths={"Metric": 100})
        log.info("Written -> %s", QA_TABLE)
    except Exception as exc:
        log.warning("Could not write summary QA: %s", exc)

    log.info("Step 7 complete.")


# =============================================================================
# Main
# =============================================================================
def main():
    log.info("=" * 70)
    log.info("BUILD 2025 PARCEL DEVELOPMENT LAYER")
    log.info("Output GDB: %s", OUT_GDB)
    log.info("=" * 70)

    # Create output GDB if it doesn't exist
    if not arcpy.Exists(OUT_GDB):
        gdb_folder = os.path.dirname(OUT_GDB)
        gdb_name = os.path.basename(OUT_GDB)
        arcpy.management.CreateFileGDB(gdb_folder, gdb_name)
        log.info("Created output GDB: %s", OUT_GDB)

    step1_build_fc()
    step2_jurisdiction()
    res_lookup, tourist_lookup, comm_lookup, fc_native, df_res, csv_totals = step3_load_and_correct()
    res_lookup, tourist_lookup, comm_lookup, xwalk_rows = step4_crosswalk(
        res_lookup, tourist_lookup, comm_lookup, df_res)
    step5_write_units(res_lookup, tourist_lookup, comm_lookup, fc_native)
    step6_taz()
    step7_qa(res_lookup, tourist_lookup, comm_lookup, fc_native, df_res, xwalk_rows, csv_totals)

    log.info("=" * 70)
    log.info("DONE -- Output: %s", OUTPUT_2025)
    log.info("=" * 70)


if __name__ == "__main__":
    main()
