"""
Step 1c — Populate COUNTY and JURISDICTION in the output feature class.

Performs a spatial join of parcel centroids to the TRPA Jurisdictions service.
Results are written to OUTPUT_FC so that:
  - S02's El Dorado APN fix has correct COUNTY values
  - S06 QA and downstream use have correct jurisdiction attribution
  - S05 does not need to re-populate these fields

Approach:
  1. Read one geometry per unique APN from OUTPUT_FC.
  2. Build in-memory centroid point FC.
  3. Spatial join centroids to Jurisdictions service:
       Pass 1 — WITHIN
       Pass 2 — CLOSEST <= 100m for any unmatched
  4. Convert full county names to 2-char codes.
  5. UpdateCursor over all OUTPUT_FC rows to write COUNTY + JURISDICTION.
"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))

import arcpy

from config import (OUTPUT_FC, FC_APN, FC_YEAR, CLOSEST_MAX_METERS,
                    JURISDICTION_SVC, COUNTY_CODE_MAP, EL_PAD_YEAR)
from utils  import get_logger, el_pad, el_depad, _EL_2D, _EL_3D

log = get_logger("s01c_populate_jurisdiction")

SVC_JURISDICTION = "JURISDICTION"
SVC_COUNTY       = "COUNTY"

_MEM_CENTROIDS = "memory/s01c_centroids"
_MEM_JOIN      = "memory/s01c_join"


def _build_centroid_fc() -> set:
    """Build in-memory centroid point FC from OUTPUT_FC (one point per unique APN)."""
    log.info("  Building centroid FC from OUTPUT_FC ...")

    apn_geom: dict = {}
    with arcpy.da.SearchCursor(OUTPUT_FC, [FC_APN, FC_YEAR, "SHAPE@"]) as cur:
        for apn, yr, geom in cur:
            if not apn or not geom or geom.area <= 0:
                continue
            apn = str(apn).strip()
            yr  = int(yr) if yr else 9999
            if apn not in apn_geom or yr < apn_geom[apn][1]:
                apn_geom[apn] = (geom, yr)

    log.info("  Unique APNs with geometry: %d", len(apn_geom))

    sr = arcpy.Describe(OUTPUT_FC).spatialReference
    for mem in [_MEM_CENTROIDS, _MEM_JOIN]:
        if arcpy.Exists(mem):
            arcpy.management.Delete(mem)

    arcpy.management.CreateFeatureclass(
        "memory", "s01c_centroids", "POINT", spatial_reference=sr)
    arcpy.management.AddField(_MEM_CENTROIDS, "APN_KEY", "TEXT", field_length=50)

    with arcpy.da.InsertCursor(_MEM_CENTROIDS, ["SHAPE@", "APN_KEY"]) as ic:
        for apn, (geom, _) in apn_geom.items():
            c = geom.centroid
            ic.insertRow([arcpy.PointGeometry(c, sr), apn])

    n = int(arcpy.management.GetCount(_MEM_CENTROIDS).getOutput(0))
    log.info("  Centroid FC: %d points", n)
    return set(apn_geom.keys())


def _spatial_join(all_apns: set) -> dict:
    """
    Spatial join centroids to Jurisdictions service.
    Returns {APN: (JURISDICTION, COUNTY)} with 2-char county codes.
    """
    log.info("  Connecting to Jurisdictions service ...")
    jrsd_lyr = "s01c_jrsd_lyr"
    pt_lyr1  = "s01c_pt_lyr1"
    pt_lyr2  = "s01c_pt_lyr2"

    for lyr in [jrsd_lyr, pt_lyr1, pt_lyr2]:
        if arcpy.Exists(lyr): arcpy.management.Delete(lyr)

    arcpy.management.MakeFeatureLayer(JURISDICTION_SVC, jrsd_lyr)
    arcpy.management.MakeFeatureLayer(_MEM_CENTROIDS,   pt_lyr1)

    result: dict = {}

    # Pass 1 — WITHIN
    log.info("  Pass 1: WITHIN ...")
    if arcpy.Exists(_MEM_JOIN): arcpy.management.Delete(_MEM_JOIN)
    arcpy.analysis.SpatialJoin(
        pt_lyr1, jrsd_lyr, _MEM_JOIN,
        "JOIN_ONE_TO_ONE", "KEEP_ALL", match_option="WITHIN")

    with arcpy.da.SearchCursor(
            _MEM_JOIN, ["APN_KEY", SVC_JURISDICTION, SVC_COUNTY, "Join_Count"]) as cur:
        for apn, jrsd, county, jc in cur:
            if jc and jc > 0 and apn:
                result[str(apn).strip()] = (jrsd, county)

    log.info("  Pass 1 matched: %d APNs", len(result))
    if arcpy.Exists(_MEM_JOIN): arcpy.management.Delete(_MEM_JOIN)

    # Pass 2 — CLOSEST for unmatched
    still_missing = all_apns - set(result.keys())
    if still_missing:
        log.info("  Pass 2: CLOSEST (<=%dm) for %d unmatched ...",
                 CLOSEST_MAX_METERS, len(still_missing))
        p2 = 0
        batches = [list(still_missing)[i:i+500]
                   for i in range(0, len(still_missing), 500)]
        for batch in batches:
            filt = " OR ".join(f"APN_KEY = '{a}'" for a in batch)
            if arcpy.Exists(pt_lyr2): arcpy.management.Delete(pt_lyr2)
            arcpy.management.MakeFeatureLayer(_MEM_CENTROIDS, pt_lyr2, filt)
            if arcpy.Exists(_MEM_JOIN): arcpy.management.Delete(_MEM_JOIN)
            arcpy.analysis.SpatialJoin(
                pt_lyr2, jrsd_lyr, _MEM_JOIN,
                "JOIN_ONE_TO_ONE", "KEEP_ALL",
                match_option="CLOSEST",
                search_radius=f"{CLOSEST_MAX_METERS} Meters",
                distance_field_name="DISTANCE")
            with arcpy.da.SearchCursor(
                    _MEM_JOIN,
                    ["APN_KEY", SVC_JURISDICTION, SVC_COUNTY,
                     "Join_Count", "DISTANCE"]) as cur:
                for apn, jrsd, county, jc, dist in cur:
                    apn = str(apn).strip() if apn else ""
                    if jc and jc > 0 and apn and dist <= CLOSEST_MAX_METERS:
                        if apn not in result:
                            result[apn] = (jrsd, county)
                            p2 += 1
            for lyr in [pt_lyr2, _MEM_JOIN]:
                if arcpy.Exists(lyr): arcpy.management.Delete(lyr)
        log.info("  Pass 2 matched: %d additional APNs", p2)

    for lyr in [jrsd_lyr, pt_lyr1, _MEM_CENTROIDS]:
        if arcpy.Exists(lyr): arcpy.management.Delete(lyr)

    # Apply county code map
    coded = {}
    for apn, (jrsd, county) in result.items():
        county = COUNTY_CODE_MAP.get(county, county) if county else county
        jrsd   = COUNTY_CODE_MAP.get(jrsd,   jrsd)   if jrsd   else jrsd
        coded[apn] = (jrsd, county)

    unmatched = all_apns - set(coded.keys())
    log.info("  Total matched: %d / %d  (%d unmatched)",
             len(coded), len(all_apns), len(unmatched))
    if unmatched:
        log.warning("  %d APNs unmatched — COUNTY/JURISDICTION will be null", len(unmatched))

    return coded


def _write_to_fc(lookup: dict) -> None:
    """Write COUNTY and JURISDICTION to all rows in OUTPUT_FC."""
    updated = skipped = 0
    with arcpy.da.UpdateCursor(OUTPUT_FC, [FC_APN, "JURISDICTION", "COUNTY"]) as cur:
        for apn, _, _ in cur:
            apn = str(apn).strip() if apn else ""
            if apn in lookup:
                jrsd, county = lookup[apn]
                cur.updateRow([apn, jrsd, county])
                updated += 1
            else:
                skipped += 1
    log.info("  Written: %d rows updated, %d skipped", updated, skipped)


def _normalize_el_dorado_apns() -> None:
    """
    Normalize El Dorado APNs in OUTPUT_FC to match the format used in each era:
      - Pre-2018: 2-digit suffix (080-155-11)  — depad any 3-digit
      - 2018+:    3-digit suffix (080-155-011) — pad any 2-digit

    Only touches rows WHERE COUNTY = 'EL'. Washoe and other counties with
    similar APN patterns are left untouched.
    """
    log.info("  Normalizing El Dorado APNs ...")
    depadded = padded = 0
    with arcpy.da.UpdateCursor(
            OUTPUT_FC, [FC_APN, FC_YEAR, "COUNTY"],
            where_clause="COUNTY = 'EL'") as cur:
        for apn, yr, county in cur:
            if not apn or not yr:
                continue
            apn = str(apn).strip()
            yr  = int(yr)
            if yr < EL_PAD_YEAR and _EL_3D.match(apn):
                cur.updateRow([el_depad(apn), yr, county])
                depadded += 1
            elif yr >= EL_PAD_YEAR and _EL_2D.match(apn):
                cur.updateRow([el_pad(apn), yr, county])
                padded += 1
    log.info("    Depadded (pre-%d): %d rows", EL_PAD_YEAR, depadded)
    log.info("    Padded   (%d+):    %d rows", EL_PAD_YEAR, padded)


def run() -> None:
    log.info("=== Step 1c: Populate COUNTY and JURISDICTION ===")
    all_apns = _build_centroid_fc()
    lookup   = _spatial_join(all_apns)
    _write_to_fc(lookup)
    _normalize_el_dorado_apns()
    log.info("Step 1c complete.")
