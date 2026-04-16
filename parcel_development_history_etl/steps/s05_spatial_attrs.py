"""
Step 5 — Update spatial attributes via service spatial joins.

Fields updated:
  PARCEL_ACRES, PARCEL_SQFT         from SHAPE@ geometry
  WITHIN_TRPA_BNDY                  SelectLayerByLocation vs TRPA boundary
  WITHIN_BONUSUNIT_BNDY             SelectLayerByLocation vs Bonus Unit boundary
  TOWN_CENTER                       centroid → TownCenter polygons
  LOCATION_TO_TOWNCENTER            centroid → LocationToTownCenter polygons
  TAZ                               centroid → TAZ polygons
  PLAN_ID, PLAN_NAME                centroid → LocalPlan polygons
  ZONING_ID, ZONING_DESCRIPTION     centroid → Zoning polygons
  REGIONAL_LANDUSE                  centroid → RegionalLandUse polygons

Approach
--------
1. Cache every service layer to memory before any spatial operations.
   Joining directly against a live service URL silently truncates at the
   service's max record count (often 1000–2000).

2. Build one polygon per APN (most recent year) then derive centroid points.
   Zone membership joins use centroid INTERSECT, not polygon LARGEST_OVERLAP.
   LARGEST_OVERLAP always finds *something* — even for out-of-basin parcels
   with no real zone assignment — producing silently wrong values.  A centroid
   that falls outside all zone polygons correctly returns NULL.

3. Collect results into {APN: values} dicts, then write back to all year-rows
   in a single cursor pass per field group.

4. Each service join is wrapped in try/except so a single failing service
   does not abort the remaining joins.
"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))

import arcpy

from config import OUTPUT_FC, FC_APN, FC_YEAR, CSV_YEARS, SPATIAL_SOURCES
from utils  import get_logger

log = get_logger("s05_spatial_attrs")

_MEM = "memory"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_scope_layer(lyr_name: str) -> None:
    """Feature layer of all output FC rows in CSV_YEARS."""
    if arcpy.Exists(lyr_name):
        arcpy.management.Delete(lyr_name)
    yr_list = ", ".join(str(y) for y in CSV_YEARS)
    arcpy.management.MakeFeatureLayer(
        OUTPUT_FC, lyr_name, f"{FC_YEAR} IN ({yr_list})")


def _make_dedup_fc() -> str:
    """
    Build an in-memory FC with one polygon per APN (most recent year).
    Zone membership doesn't change year-to-year for a stable APN, so joining
    against all 14 year-rows is redundant and slow.
    """
    mem_fc = f"{_MEM}/s05_dedup"
    if arcpy.Exists(mem_fc):
        arcpy.management.Delete(mem_fc)

    best: dict[str, tuple[int, object]] = {}
    yr_list = ", ".join(str(y) for y in CSV_YEARS)
    with arcpy.da.SearchCursor(
            OUTPUT_FC, [FC_APN, FC_YEAR, "SHAPE@"],
            where_clause=f"{FC_YEAR} IN ({yr_list})") as cur:
        for apn, year, geom in cur:
            if apn and geom:
                a = str(apn).strip()
                if a not in best or year > best[a][0]:
                    best[a] = (year, geom)

    sr = arcpy.Describe(OUTPUT_FC).spatialReference
    arcpy.management.CreateFeatureclass(_MEM, "s05_dedup", "POLYGON",
                                        spatial_reference=sr)
    arcpy.management.AddField(mem_fc, FC_APN, "TEXT", field_length=50)

    with arcpy.da.InsertCursor(mem_fc, [FC_APN, "SHAPE@"]) as ic:
        for apn, (_, geom) in best.items():
            ic.insertRow([apn, geom])

    n = int(arcpy.management.GetCount(mem_fc).getOutput(0))
    log.info("  Dedup layer: %d unique APNs", n)
    return mem_fc


def _make_centroids(dedup_fc: str) -> str:
    """
    Generate one centroid point per APN from dedup_fc using INSIDE
    (guaranteed to land inside the polygon even for irregular shapes).
    """
    mem_fc = f"{_MEM}/s05_centroids"
    if arcpy.Exists(mem_fc):
        arcpy.management.Delete(mem_fc)
    arcpy.management.FeatureToPoint(dedup_fc, mem_fc, "INSIDE")
    n = int(arcpy.management.GetCount(mem_fc).getOutput(0))
    log.info("  Centroid layer: %d points", n)
    return mem_fc


def _cache_service(url: str, tag: str) -> str | None:
    """
    Download a service layer to memory and return its path.
    Returns None on failure so callers can skip gracefully.
    """
    mem_fc = f"{_MEM}/s05_svc_{tag}"
    if arcpy.Exists(mem_fc):
        arcpy.management.Delete(mem_fc)
    try:
        arcpy.management.CopyFeatures(url, mem_fc)
        n = int(arcpy.management.GetCount(mem_fc).getOutput(0))
        if n == 0:
            log.warning("  Cached %s but got 0 features — skipping", tag)
            arcpy.management.Delete(mem_fc)
            return None
        log.info("  Cached %-20s  %d features", tag, n)
        return mem_fc
    except Exception as exc:
        log.error("  Failed to cache %s: %s", tag, exc)
        return None


def _flag_within(scope_lyr: str, source_fc: str, field: str) -> int:
    """Set field = 0 for all rows, then 1 for rows that intersect source_fc."""
    with arcpy.da.UpdateCursor(scope_lyr, [field]) as cur:
        for row in cur:
            row[0] = 0
            cur.updateRow(row)
    sel = arcpy.management.SelectLayerByLocation(scope_lyr, "INTERSECT", source_fc)
    n = 0
    with arcpy.da.UpdateCursor(sel, [field]) as cur:
        for row in cur:
            row[0] = 1
            cur.updateRow(row)
            n += 1
    arcpy.management.SelectLayerByAttribute(scope_lyr, "CLEAR_SELECTION")
    return n


_SYSTEM_FIELDS = {"OBJECTID", "Shape", "Shape_Length", "Shape_Area",
                  "Join_Count", "TARGET_FID"}
_NUMERIC_TYPES = {"SmallInteger", "Integer", "Single", "Double"}


def _resolve_fields(join_fc: str, requested: list[str]) -> dict[str, str]:
    """
    Map requested field names to their actual names in the join output FC.

    SpatialJoin appends _1 to any field from the join layer whose name
    conflicts with the target layer.  Since our centroid FC only has APN,
    OBJECTID, and Shape, conflicts are rare but possible (e.g. if the service
    has its own APN field).

    Returns {requested_name: actual_name}.  Fields that cannot be resolved
    are logged as warnings and excluded from the result.
    """
    available = {f.name for f in arcpy.ListFields(join_fc)}
    mapping   = {}
    for req in requested:
        if req in available:
            mapping[req] = req
        elif f"{req}_1" in available:
            mapping[req] = f"{req}_1"
            log.debug("    %s resolved to %s_1 in join output", req, req)
        else:
            avail_str = sorted(f for f in available if f not in _SYSTEM_FIELDS)
            log.warning("    Field '%s' not found in join output. Available: %s",
                        req, avail_str)
    return mapping


def _sj_collect(centroid_fc: str, cached_fc: str,
                source_fields: list[str], label: str) -> dict[str, tuple]:
    """
    Spatial join centroid_fc → cached_fc using INTERSECT.

    Returns {apn: (val, ...)} only for APNs whose centroid falls inside a
    zone polygon (Join_Count > 0).  APNs outside all zones are absent from
    the dict and will remain NULL in the output FC — which is correct.

    INTERSECT on centroid points (vs LARGEST_OVERLAP on polygons) means no
    parcel is silently matched to a wrong zone due to a sliver overlap.
    """
    join_fc = f"{_MEM}/s05_join_{label}"
    if arcpy.Exists(join_fc):
        arcpy.management.Delete(join_fc)

    arcpy.analysis.SpatialJoin(
        centroid_fc, cached_fc, join_fc,
        "JOIN_ONE_TO_ONE", "KEEP_ALL",
        match_option="INTERSECT")

    field_map = _resolve_fields(join_fc, source_fields)
    if not field_map:
        if arcpy.Exists(join_fc):
            arcpy.management.Delete(join_fc)
        return {}

    actual_fields = [field_map[r] for r in source_fields if r in field_map]

    results: dict[str, tuple] = {}
    with arcpy.da.SearchCursor(
            join_fc, [FC_APN, "Join_Count"] + actual_fields) as cur:
        for row in cur:
            apn        = row[0]
            join_count = row[1]
            if apn and join_count and join_count > 0:
                results[str(apn).strip()] = row[2:]

    if arcpy.Exists(join_fc):
        arcpy.management.Delete(join_fc)

    return results


def _write_back(scope_lyr: str, apn_dict: dict[str, tuple],
                target_fields: list[str]) -> int:
    """
    Write apn_dict values to all year-rows in scope_lyr matched by APN.
    APNs absent from apn_dict are left unchanged (NULL stays NULL).
    Returns number of row-years written.
    """
    tgt_types = {f.name: f.type for f in arcpy.ListFields(scope_lyr)
                 if f.name in target_fields}
    n = 0
    with arcpy.da.UpdateCursor(scope_lyr, [FC_APN] + target_fields) as cur:
        for row in cur:
            apn = str(row[0]).strip() if row[0] else None
            if not apn or apn not in apn_dict:
                continue
            vals = apn_dict[apn]
            for i, v in enumerate(vals[:len(target_fields)]):
                ftype = tgt_types.get(target_fields[i], "String")
                if v is None:
                    row[i + 1] = None
                elif ftype in _NUMERIC_TYPES:
                    try:
                        row[i + 1] = (int(v) if ftype in {"SmallInteger", "Integer"}
                                      else float(v))
                    except (ValueError, TypeError):
                        row[i + 1] = None
                else:
                    row[i + 1] = str(v)
            cur.updateRow(row)
            n += 1
    return n


# ── Main step ─────────────────────────────────────────────────────────────────

def run() -> None:
    log.info("=== Step 5: Spatial attribute updates ===")

    scope_lyr = "s05_scope"
    _make_scope_layer(scope_lyr)
    n_scope = int(arcpy.management.GetCount(scope_lyr).getOutput(0))
    log.info("Rows in scope: %d", n_scope)

    # -- PARCEL_ACRES / PARCEL_SQFT ------------------------------------------
    log.info("Calculating PARCEL_ACRES / PARCEL_SQFT ...")
    n = 0
    with arcpy.da.UpdateCursor(
            scope_lyr, ["PARCEL_ACRES", "PARCEL_SQFT", "SHAPE@"]) as cur:
        for row in cur:
            if row[2] and row[2].area > 0:
                row[0] = row[2].getArea("PLANAR", "ACRES")
                row[1] = row[2].getArea("PLANAR", "SquareFeetUS")
                cur.updateRow(row)
                n += 1
    log.info("  %d rows updated", n)

    # -- Cache all service layers to memory ----------------------------------
    log.info("Caching service layers ...")
    cached = {}
    for key, url in SPATIAL_SOURCES.items():
        cached[key] = _cache_service(url, key)

    # -- WITHIN flags (SelectLayerByLocation — unaffected by join logic) -----
    for svc_key, field in [("TRPA_bdy",  "WITHIN_TRPA_BNDY"),
                            ("BonusUnit", "WITHIN_BONUSUNIT_BNDY")]:
        log.info("Flagging %s ...", field)
        if cached.get(svc_key):
            try:
                cnt = _flag_within(scope_lyr, cached[svc_key], field)
                log.info("  %s = 1 : %d rows", field, cnt)
            except Exception as exc:
                log.error("  %s failed: %s", field, exc)
        else:
            log.warning("  Skipping %s — service not cached", field)

    # -- One polygon per APN → centroid points for zone joins ----------------
    log.info("Building deduplicated APN layer ...")
    dedup_fc = _make_dedup_fc()
    n_dedup  = int(arcpy.management.GetCount(dedup_fc).getOutput(0))

    log.info("Generating centroid points ...")
    centroid_fc = _make_centroids(dedup_fc)

    # -- Zone membership joins -----------------------------------------------
    # centroid INTERSECT: a centroid outside all zone polygons → JOIN_COUNT=0
    # → stays NULL.  No parcel is silently matched to the wrong zone.
    joins = [
        ("TownCenter",        ["Name"],
         ["TOWN_CENTER"]),
        ("LocationToTownCtr", ["BUFFER_NAME"],
         ["LOCATION_TO_TOWNCENTER"]),
        ("TAZ",               ["TAZ"],
         ["TAZ"]),
        ("LocalPlan",         ["PLAN_ID", "PLAN_NAME"],
         ["PLAN_ID", "PLAN_NAME"]),
        ("Zoning",            ["ZONING_ID", "ZONING_DESCRIPTION"],
         ["ZONING_ID", "ZONING_DESCRIPTION"]),
        ("RegionalLandUse",   ["REGIONAL_LAND_USE"],
         ["REGIONAL_LANDUSE"]),
    ]

    for svc_key, src_flds, tgt_flds in joins:
        log.info("Spatial join: %s ...", svc_key)
        if not cached.get(svc_key):
            log.warning("  Skipping %s — service not cached", svc_key)
            continue
        try:
            apn_dict = _sj_collect(centroid_fc, cached[svc_key], src_flds, svc_key)
            pct      = 100.0 * len(apn_dict) / n_dedup if n_dedup else 0
            log.info("  [%s] %d / %d APNs matched (%.1f%%)",
                     svc_key, len(apn_dict), n_dedup, pct)
            n_written = _write_back(scope_lyr, apn_dict, tgt_flds)
            log.info("  [%s] %d row-years written", svc_key, n_written)
        except Exception as exc:
            log.error("  [%s] failed: %s", svc_key, exc)

    # -- Null out "Outside Town Center" catch-all ----------------------------
    log.info("Nulling TOWN_CENTER = 'Outside Town Center' ...")
    n_outside = 0
    with arcpy.da.UpdateCursor(
            scope_lyr, ["TOWN_CENTER"],
            "TOWN_CENTER = 'Outside Town Center'") as cur:
        for row in cur:
            row[0] = None
            cur.updateRow(row)
            n_outside += 1
    log.info("  Cleared %d rows", n_outside)

    # -- Cleanup -------------------------------------------------------------
    for name in [scope_lyr, dedup_fc, centroid_fc]:
        if arcpy.Exists(name):
            arcpy.management.Delete(name)
    for fc_path in [f"{_MEM}/s05_svc_{k}" for k in SPATIAL_SOURCES]:
        if arcpy.Exists(fc_path):
            arcpy.management.Delete(fc_path)

    log.info("Step 5 complete.")


if __name__ == "__main__":
    run()
