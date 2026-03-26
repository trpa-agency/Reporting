"""
Step 3 — Build APN crosswalk.

For CSV APNs that don't exist in the output FC for a given year
(parcel renames, historical splits), find the correct FC APN via
centroid spatial join:
  Pass 1 — INTERSECT
  Pass 2 — CLOSEST (≤ CLOSEST_MAX_METERS)

Extends csv_lookup with (FC_APN, Year) → units entries.
Writes QA_APN_Crosswalk table to GDB.
"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))

import arcpy
import pandas as pd

from config import (OUTPUT_FC, FC_APN, FC_YEAR, CSV_YEARS,
                    CLOSEST_MAX_METERS, QA_APN_CROSSWALK, ALL_PARCELS_CURRENT)
from utils  import get_logger, df_to_gdb_table

log = get_logger("s03_crosswalk")

_MEM_CENTROIDS = "memory/xwalk_centroids"
_MEM_JOIN      = "memory/xwalk_join"


def _get_fc_apn_years() -> set:
    """Return the set of (APN, Year) tuples present in the output FC."""
    result = set()
    with arcpy.da.SearchCursor(OUTPUT_FC, [FC_APN, FC_YEAR]) as cur:
        for apn, yr in cur:
            if apn and yr:
                result.add((str(apn).strip(), int(yr)))
    return result


def _get_apn_geometry(apns: set) -> dict:
    """
    For each APN in *apns*, return its geometry from the FC.
    Uses the earliest year the APN appears (most likely to have full polygon).
    Returns {apn: (geometry, source_year)}.
    """
    result = {}
    # Build SQL in batches to avoid overly long WHERE clauses
    apn_list = list(apns)
    batch    = 500
    for i in range(0, len(apn_list), batch):
        chunk = apn_list[i:i+batch]
        q = " OR ".join(f"{FC_APN} = {chr(39)}{a}{chr(39)}" for a in chunk)
        with arcpy.da.SearchCursor(OUTPUT_FC, [FC_APN, FC_YEAR, "SHAPE@"], q) as cur:
            for apn, yr, geom in cur:
                if apn in apns and geom and geom.area > 0:
                    apn = str(apn).strip()
                    if apn not in result or yr < result[apn][1]:
                        result[apn] = (geom, int(yr))
    return result


def _get_geometry_from_allparcels(apns: set, sr) -> dict:
    """
    Fetch parcel geometry from the All Parcels current service for APNs that
    have no geometry in the historical FC.  Returns {apn: (geometry, 9999)}.
    9999 is a sentinel source_year meaning "current / service layer".

    The All Parcels service APN field is assumed to be the same FC_APN constant.
    If the service uses a different field name, update FC_APN in config or adjust
    the SQL here.
    """
    result = {}
    if not apns:
        return result

    lyr = "all_parcels_current_lyr"
    try:
        if arcpy.Exists(lyr):
            arcpy.management.Delete(lyr)
        arcpy.management.MakeFeatureLayer(ALL_PARCELS_CURRENT, lyr)

        apn_list = list(apns)
        batch    = 100  # smaller batches for service queries
        for i in range(0, len(apn_list), batch):
            chunk = apn_list[i : i + batch]
            sql   = " OR ".join(f"{FC_APN} = '{a}'" for a in chunk)
            arcpy.management.SelectLayerByAttribute(lyr, "NEW_SELECTION", sql)
            with arcpy.da.SearchCursor(lyr, [FC_APN, "SHAPE@"]) as cur:
                for apn, geom in cur:
                    if apn and geom and geom.area > 0:
                        apn = str(apn).strip()
                        if apn not in result:
                            # Project geometry to match output FC spatial reference
                            if geom.spatialReference.factoryCode != sr.factoryCode:
                                geom = geom.projectAs(sr)
                            result[apn] = (geom, 9999)

    except Exception as exc:
        log.warning("All Parcels service query failed: %s", exc)
        log.warning("  APNs without geometry from service will be left unresolved.")
    finally:
        if arcpy.Exists(lyr):
            arcpy.management.Delete(lyr)

    return result


def run(df_csv: pd.DataFrame, csv_lookup: dict) -> dict:
    log.info("=== Step 3: Build APN crosswalk ===")

    # -- Find missing APN x Year combos --------------------------------------
    fc_apn_years  = _get_fc_apn_years()
    csv_apn_years = set(zip(df_csv["APN"], df_csv["Year"]))
    missing       = csv_apn_years - fc_apn_years

    missing_apns  = {apn for apn, _ in missing}
    log.info("CSV APN x Year combos   : %d", len(csv_apn_years))
    log.info("FC  APN x Year combos   : %d", len(fc_apn_years))
    log.info("Missing combos          : %d  (%d unique APNs)", len(missing), len(missing_apns))

    if not missing:
        log.info("No missing APN x Year — crosswalk not needed.")
        return csv_lookup

    # -- Get geometry for missing APNs ----------------------------------------
    log.info("Fetching geometries for %d APNs ...", len(missing_apns))
    apn_geom = _get_apn_geometry(missing_apns)
    has_geom = set(apn_geom.keys())
    no_geom  = missing_apns - has_geom
    log.info("  With geometry (FC)  : %d", len(has_geom))
    log.info("  Without geometry    : %d  (not in FC any year)", len(no_geom))

    # -- Fallback: fetch geometry from All Parcels current service ------------
    if no_geom:
        log.info("Trying All Parcels service for %d APNs with no FC geometry ...",
                 len(no_geom))
        sr          = arcpy.Describe(OUTPUT_FC).spatialReference
        svc_geom    = _get_geometry_from_allparcels(no_geom, sr)
        log.info("  Found in All Parcels service: %d", len(svc_geom))
        apn_geom.update(svc_geom)
        has_geom = set(apn_geom.keys())
        no_geom  = missing_apns - has_geom
        log.info("  Still without geometry: %d", len(no_geom))

    # -- Build centroid point FC in memory ------------------------------------
    if arcpy.Exists(_MEM_CENTROIDS): arcpy.management.Delete(_MEM_CENTROIDS)
    sr = arcpy.Describe(OUTPUT_FC).spatialReference
    arcpy.management.CreateFeatureclass(
        "memory", "xwalk_centroids", "POINT", spatial_reference=sr)
    arcpy.management.AddField(_MEM_CENTROIDS, "CSV_APN",  "TEXT", field_length=50)
    arcpy.management.AddField(_MEM_CENTROIDS, "SRC_YEAR", "LONG")

    with arcpy.da.InsertCursor(_MEM_CENTROIDS, ["SHAPE@", "CSV_APN", "SRC_YEAR"]) as ic:
        for apn, (geom, src_yr) in apn_geom.items():
            centroid = geom.centroid
            pt = arcpy.PointGeometry(centroid, sr)
            ic.insertRow([pt, apn, src_yr])
    log.info("Centroid FC: %d points",
             int(arcpy.management.GetCount(_MEM_CENTROIDS).getOutput(0)))

    # -- Spatial join per year ------------------------------------------------
    crosswalk_rows = []

    _BATCH = 500  # max APNs per SQL WHERE clause

    for year in sorted(CSV_YEARS):
        # APNs missing in this year that have geometry
        yr_missing = {apn for apn, yr in missing if yr == year and apn in has_geom}
        if not yr_missing:
            continue

        fc_lyr  = "xwalk_fc_lyr"
        pt_lyr  = "xwalk_pt_lyr"
        pt_lyr2 = "xwalk_pt_lyr2"
        for lyr in [fc_lyr, pt_lyr, pt_lyr2, _MEM_JOIN]:
            if arcpy.Exists(lyr): arcpy.management.Delete(lyr)

        sql_yr = f"{FC_YEAR} = {year}"
        arcpy.management.MakeFeatureLayer(OUTPUT_FC, fc_lyr, sql_yr)

        p1 = p2 = 0

        # Pass 1: INTERSECT — batched to avoid SQL expression length limits
        yr_list = sorted(yr_missing)
        for i in range(0, len(yr_list), _BATCH):
            batch = yr_list[i:i + _BATCH]
            apn_filter = " OR ".join(
                f"CSV_APN = {chr(39)}{a}{chr(39)}" for a in batch)
            if arcpy.Exists(pt_lyr): arcpy.management.Delete(pt_lyr)
            arcpy.management.MakeFeatureLayer(_MEM_CENTROIDS, pt_lyr, apn_filter)
            if arcpy.Exists(_MEM_JOIN): arcpy.management.Delete(_MEM_JOIN)
            arcpy.analysis.SpatialJoin(
                pt_lyr, fc_lyr, _MEM_JOIN,
                "JOIN_ONE_TO_ONE", "KEEP_ALL",
                match_option="INTERSECT")
            with arcpy.da.SearchCursor(
                    _MEM_JOIN, ["CSV_APN", FC_APN, "Join_Count"]) as cur:
                for csv_apn, fc_apn, jc in cur:
                    if jc and jc > 0 and fc_apn:
                        crosswalk_rows.append({
                            "CSV_APN": csv_apn, "FC_APN": fc_apn,
                            "Year": year, "Match_Type": "intersect"})
                        p1 += 1
        for lyr in [pt_lyr, _MEM_JOIN]:
            if arcpy.Exists(lyr): arcpy.management.Delete(lyr)

        # Pass 2: CLOSEST for still-unmatched — also batched
        matched_p1 = {r["CSV_APN"] for r in crosswalk_rows if r["Year"] == year}
        still_missing = sorted(yr_missing - matched_p1)
        for i in range(0, len(still_missing), _BATCH):
            batch = still_missing[i:i + _BATCH]
            apn_filter2 = " OR ".join(
                f"CSV_APN = {chr(39)}{a}{chr(39)}" for a in batch)
            if arcpy.Exists(pt_lyr2): arcpy.management.Delete(pt_lyr2)
            arcpy.management.MakeFeatureLayer(_MEM_CENTROIDS, pt_lyr2, apn_filter2)
            if arcpy.Exists(_MEM_JOIN): arcpy.management.Delete(_MEM_JOIN)
            arcpy.analysis.SpatialJoin(
                pt_lyr2, fc_lyr, _MEM_JOIN,
                "JOIN_ONE_TO_ONE", "KEEP_ALL",
                match_option="CLOSEST",
                search_radius=f"{CLOSEST_MAX_METERS} Meters",
                distance_field_name="DISTANCE")
            with arcpy.da.SearchCursor(
                    _MEM_JOIN, ["CSV_APN", FC_APN, "Join_Count", "DISTANCE"]) as cur:
                for csv_apn, fc_apn, jc, dist in cur:
                    if jc and jc > 0 and fc_apn and dist <= CLOSEST_MAX_METERS:
                        crosswalk_rows.append({
                            "CSV_APN": csv_apn, "FC_APN": fc_apn,
                            "Year": year, "Match_Type": f"closest_{dist:.1f}m"})
                        p2 += 1
        for lyr in [pt_lyr2, _MEM_JOIN]:
            if arcpy.Exists(lyr): arcpy.management.Delete(lyr)

        if arcpy.Exists(fc_lyr): arcpy.management.Delete(fc_lyr)

        log.info("  %d : %d within + %d closest", year, p1, p2)

    if arcpy.Exists(_MEM_CENTROIDS): arcpy.management.Delete(_MEM_CENTROIDS)

    # -- Extend csv_lookup ----------------------------------------------------
    df_xwalk = pd.DataFrame(crosswalk_rows) if crosswalk_rows else pd.DataFrame(
        columns=["CSV_APN", "FC_APN", "Year", "Match_Type"])
    df_xwalk["APN_Changed"] = df_xwalk["CSV_APN"] != df_xwalk["FC_APN"]

    added = 0
    for _, row in df_xwalk.iterrows():
        fc_apn  = row["FC_APN"]
        csv_apn = row["CSV_APN"]
        year    = int(row["Year"])
        val     = csv_lookup.get((csv_apn, year))
        if val is not None and (fc_apn, year) not in csv_lookup:
            csv_lookup[(fc_apn, year)] = val
            added += 1

    log.info("Crosswalk rows      : %d", len(df_xwalk))
    log.info("csv_lookup entries added: %d", added)

    # -- Write GDB table ------------------------------------------------------
    if len(df_xwalk):
        df_to_gdb_table(df_xwalk, QA_APN_CROSSWALK,
                        text_lengths={"CSV_APN": 50, "FC_APN": 50, "Match_Type": 50})
        log.info("Written → %s", QA_APN_CROSSWALK)

    log.info("Step 3 complete.")
    return csv_lookup


if __name__ == "__main__":
    import s02_load_csv as s02
    df_csv, lu = s02.run()
    run(df_csv, lu)
