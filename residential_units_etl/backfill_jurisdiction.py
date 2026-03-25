"""
backfill_jurisdiction.py — One-off script to populate JURISDICTION and COUNTY
fields in Parcel_History_Attributed via spatial join to the TRPA Jurisdictions
service (Boundaries/FeatureServer/10).

Approach:
  1. Read one geometry per unique APN from the source FC (earliest year).
  2. Build parcel centroid points (in memory).
  3. Spatial join centroids to the Jurisdictions service (WITHIN, then CLOSEST ≤ 100m).
  4. Build lookup {APN: (JURISDICTION, COUNTY)}.
  5. UpdateCursor over ALL rows in source FC to fill both fields.

Run from ArcGIS Pro Python:
  & "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" `
    "C:/Users/mbindl/Documents/GitHub/Reporting/residential_units_etl/backfill_jurisdiction.py"

Fields updated in:
  C:\\GIS\\ParcelHistory.gdb\\Parcel_History_Attributed
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import arcpy

# ── Config ────────────────────────────────────────────────────────────────────
SOURCE_FC          = r"C:\GIS\ParcelHistory.gdb\Parcel_History_Attributed"
JURISDICTION_SVC   = "https://maps.trpa.org/server/rest/services/Boundaries/FeatureServer/10"
FC_APN             = "APN"
FC_YEAR            = "YEAR"
SVC_JURISDICTION   = "JURISDICTION"   # field name in service
SVC_COUNTY         = "COUNTY"         # field name in service
OUT_JURISDICTION   = "JURISDICTION"   # field name to write in source FC
OUT_COUNTY         = "COUNTY"         # field name to write in source FC
CLOSEST_MAX_METERS = 100

# County name → 2-char code (matches COUNTY codes used throughout the ETL)
COUNTY_CODE_MAP = {
    "Washoe"                 : "WA",
    "El Dorado"              : "EL",
    "Placer"                 : "PL",
    "Douglas"                : "DG",
    "Carson City"            : "CC",
    "City of South Lake Tahoe": "CSLT",
}

_MEM_CENTROIDS = "memory/jrsd_centroids"
_MEM_JOIN      = "memory/jrsd_join"

# ── Logging ───────────────────────────────────────────────────────────────────
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("backfill_jurisdiction")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_fields():
    """
    Ensure JURISDICTION (length 100) and COUNTY (length 10) exist in source FC.
    If a field already exists but is too short, delete and recreate it.
    """
    existing = {f.name: f for f in arcpy.ListFields(SOURCE_FC)}

    targets = [(OUT_JURISDICTION, 100), (OUT_COUNTY, 20)]
    for fname, required_len in targets:
        if fname in existing:
            current_len = existing[fname].length or 0
            if current_len < required_len:
                log.info("Field %s exists but length %d < %d — recreating ...",
                         fname, current_len, required_len)
                arcpy.management.DeleteField(SOURCE_FC, fname)
                arcpy.management.AddField(SOURCE_FC, fname, "TEXT",
                                          field_length=required_len)
                log.info("  Recreated: %s (length %d)", fname, required_len)
            else:
                log.info("Field %s OK (length %d)", fname, current_len)
        else:
            arcpy.management.AddField(SOURCE_FC, fname, "TEXT",
                                      field_length=required_len)
            log.info("Added field: %s (length %d)", fname, required_len)


def _build_centroid_fc() -> dict:
    """
    Read one geometry per unique APN (earliest year) from source FC.
    Build an in-memory centroid point FC.
    Returns {APN: centroid_point_geometry} for reference.
    """
    log.info("Reading geometries from source FC (one per unique APN) ...")
    apn_geom = {}   # {apn: (geom, year)}

    with arcpy.da.SearchCursor(SOURCE_FC, [FC_APN, FC_YEAR, "SHAPE@"]) as cur:
        for apn, yr, geom in cur:
            if not apn or not geom or geom.area <= 0:
                continue
            apn = str(apn).strip()
            yr  = int(yr) if yr else 9999
            if apn not in apn_geom or yr < apn_geom[apn][1]:
                apn_geom[apn] = (geom, yr)

    log.info("  Unique APNs with geometry: %d", len(apn_geom))

    sr = arcpy.Describe(SOURCE_FC).spatialReference
    for mem in [_MEM_CENTROIDS, _MEM_JOIN]:
        if arcpy.Exists(mem):
            arcpy.management.Delete(mem)

    arcpy.management.CreateFeatureclass(
        "memory", "jrsd_centroids", "POINT", spatial_reference=sr)
    arcpy.management.AddField(_MEM_CENTROIDS, "APN_KEY", "TEXT", field_length=50)

    with arcpy.da.InsertCursor(_MEM_CENTROIDS, ["SHAPE@", "APN_KEY"]) as ic:
        for apn, (geom, _) in apn_geom.items():
            centroid = geom.centroid
            ic.insertRow([arcpy.PointGeometry(centroid, sr), apn])

    n = int(arcpy.management.GetCount(_MEM_CENTROIDS).getOutput(0))
    log.info("  Centroid FC built: %d points", n)
    return apn_geom


def _spatial_join_to_service() -> dict:
    """
    Spatial join centroid FC to Jurisdictions service.
    Pass 1: WITHIN.  Pass 2: CLOSEST ≤ CLOSEST_MAX_METERS for unmatched.
    Returns {APN: (JURISDICTION, COUNTY)}.
    """
    log.info("Connecting to Jurisdictions service ...")
    jrsd_lyr = "jrsd_service_lyr"
    pt_lyr1  = "jrsd_pt_lyr1"
    pt_lyr2  = "jrsd_pt_lyr2"

    for lyr in [jrsd_lyr, pt_lyr1, pt_lyr2, _MEM_JOIN]:
        if arcpy.Exists(lyr):
            arcpy.management.Delete(lyr)

    arcpy.management.MakeFeatureLayer(JURISDICTION_SVC, jrsd_lyr)
    arcpy.management.MakeFeatureLayer(_MEM_CENTROIDS,   pt_lyr1)

    result = {}   # {apn: (jurisdiction, county)}

    # ── Pass 1: WITHIN ────────────────────────────────────────────────────────
    log.info("Pass 1: WITHIN join ...")
    arcpy.analysis.SpatialJoin(
        pt_lyr1, jrsd_lyr, _MEM_JOIN,
        "JOIN_ONE_TO_ONE", "KEEP_ALL",
        match_option="WITHIN")

    with arcpy.da.SearchCursor(
            _MEM_JOIN,
            ["APN_KEY", SVC_JURISDICTION, SVC_COUNTY, "Join_Count"]) as cur:
        for apn, jrsd, county, jc in cur:
            if jc and jc > 0 and apn:
                result[str(apn).strip()] = (jrsd, county)

    p1 = len(result)
    log.info("  Pass 1 matched: %d APNs", p1)
    if arcpy.Exists(_MEM_JOIN):
        arcpy.management.Delete(_MEM_JOIN)

    # ── Pass 2: CLOSEST for unmatched ─────────────────────────────────────────
    matched_p1 = set(result.keys())
    all_apns   = set()
    with arcpy.da.SearchCursor(_MEM_CENTROIDS, ["APN_KEY"]) as cur:
        for (apn,) in cur:
            if apn:
                all_apns.add(str(apn).strip())
    still_missing = all_apns - matched_p1

    if still_missing:
        log.info("Pass 2: CLOSEST (≤%dm) for %d unmatched APNs ...",
                 CLOSEST_MAX_METERS, len(still_missing))

        apn_filter = " OR ".join(f"APN_KEY = '{a}'" for a in list(still_missing)[:500])
        # Process in batches of 500 to avoid overly long SQL
        batches = [list(still_missing)[i:i+500]
                   for i in range(0, len(still_missing), 500)]
        p2 = 0
        for batch in batches:
            filt = " OR ".join(f"APN_KEY = '{a}'" for a in batch)
            if arcpy.Exists(pt_lyr2):
                arcpy.management.Delete(pt_lyr2)
            arcpy.management.MakeFeatureLayer(_MEM_CENTROIDS, pt_lyr2, filt)
            if arcpy.Exists(_MEM_JOIN):
                arcpy.management.Delete(_MEM_JOIN)
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
            if arcpy.Exists(pt_lyr2):
                arcpy.management.Delete(pt_lyr2)
            if arcpy.Exists(_MEM_JOIN):
                arcpy.management.Delete(_MEM_JOIN)

        log.info("  Pass 2 matched: %d additional APNs", p2)

    for lyr in [jrsd_lyr, pt_lyr1, _MEM_CENTROIDS]:
        if arcpy.Exists(lyr):
            arcpy.management.Delete(lyr)

    no_match = all_apns - set(result.keys())
    log.info("Total matched: %d / %d APNs  (%d unmatched)",
             len(result), len(all_apns), len(no_match))
    if no_match:
        log.warning("  Unmatched APNs (no jurisdiction found): %d", len(no_match))
        for apn in sorted(no_match)[:20]:
            log.warning("    %s", apn)
        if len(no_match) > 20:
            log.warning("    ... and %d more", len(no_match) - 20)

    return result


def _update_source_fc(lookup: dict) -> None:
    """
    UpdateCursor over all rows in source FC to write JURISDICTION and COUNTY.
    """
    log.info("Updating source FC (%s) ...", SOURCE_FC)
    fields = [FC_APN, OUT_JURISDICTION, OUT_COUNTY]

    updated = skipped = 0
    with arcpy.da.UpdateCursor(SOURCE_FC, fields) as cur:
        for apn, *_ in cur:
            apn = str(apn).strip() if apn else ""
            if apn in lookup:
                jrsd, county = lookup[apn]
                # Convert full county names to 2-char codes
                county = COUNTY_CODE_MAP.get(county, county) if county else county
                # For JURISDICTION, also apply county code map when value is a
                # bare county name (unincorporated areas); city names pass through
                jrsd = COUNTY_CODE_MAP.get(jrsd, jrsd) if jrsd else jrsd
                cur.updateRow([apn, jrsd, county])
                updated += 1
            else:
                skipped += 1

    log.info("  Updated : %d rows", updated)
    log.info("  Skipped : %d rows (APN not in lookup — set to null)", skipped)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    log.info("=== backfill_jurisdiction.py ===")
    log.info("Source FC : %s", SOURCE_FC)
    log.info("Service   : %s", JURISDICTION_SVC)

    _ensure_fields()
    _build_centroid_fc()
    lookup = _spatial_join_to_service()
    _update_source_fc(lookup)

    elapsed = time.time() - t0
    mins, secs = divmod(int(elapsed), 60)
    log.info("Done.  (%dm %02ds)", mins, secs)


if __name__ == "__main__":
    main()
