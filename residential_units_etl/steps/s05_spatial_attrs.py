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
"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))

import arcpy

from config import OUTPUT_FC, FC_YEAR, CSV_YEARS, SPATIAL_SOURCES
from utils  import get_logger

log = get_logger("s05_spatial_attrs")

_SCRATCH = "memory"

# Temp FC names
_PARCEL_PT   = _SCRATCH + "/s05_parcel_centroids"
_JOIN_PREFIX = _SCRATCH + "/s05_join_"


def _make_scope_layer(lyr_name: str) -> None:
    """Make a feature layer of all output FC rows in CSV_YEARS."""
    if arcpy.Exists(lyr_name):
        arcpy.management.Delete(lyr_name)
    yr_list = ", ".join(str(y) for y in CSV_YEARS)
    arcpy.management.MakeFeatureLayer(
        OUTPUT_FC, lyr_name, f"{FC_YEAR} IN ({yr_list})")


def _flag_within(scope_lyr: str, source_fc: str, field: str) -> int:
    """Set *field* = 0 for all rows, then 1 for rows that intersect *source_fc*."""
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


_SYSTEM_FIELDS = {
    "OBJECTID", "Shape", "Shape_Length", "Shape_Area",
    "Join_Count", "TARGET_FID",
}
_NUMERIC_TYPES = {"SmallInteger", "Integer", "Single", "Double"}


def _sj_transfer(centroid_fc: str, source_url: str,
                 source_fields: list, target_fields: list,
                 scope_lyr: str, label: str) -> int:
    """
    Spatial join centroid_fc → source_url, transfer attribute values
    back to scope_lyr via APN join.
    """
    join_fc = _JOIN_PREFIX + label.replace(" ", "_")
    if arcpy.Exists(join_fc):
        arcpy.management.Delete(join_fc)

    arcpy.analysis.SpatialJoin(
        centroid_fc, source_url, join_fc,
        "JOIN_ONE_TO_ONE", "KEEP_ALL",
        match_option="HAVE_THEIR_CENTER_IN")

    # Check which source fields actually exist in the join output
    join_field_names = {f.name for f in arcpy.ListFields(join_fc)}
    missing_fields   = [f for f in source_fields if f not in join_field_names]
    if missing_fields:
        avail = sorted(f for f in join_field_names if f not in _SYSTEM_FIELDS)
        log.warning("  [%s] fields not found in join output: %s", label, missing_fields)
        log.warning("  [%s] available fields: %s", label, avail)
        source_fields = [f for f in source_fields if f in join_field_names]
        target_fields = target_fields[:len(source_fields)]

    if not source_fields:
        arcpy.management.Delete(join_fc)
        return 0

    # Build type map for target fields so we can cast correctly
    tgt_field_types = {f.name: f.type for f in arcpy.ListFields(scope_lyr)
                       if f.name in target_fields}

    join_dict = {}
    with arcpy.da.SearchCursor(join_fc, ["APN"] + source_fields) as cur:
        for row in cur:
            apn = row[0]
            if apn:
                join_dict[str(apn).strip()] = row[1:]

    n = 0
    with arcpy.da.UpdateCursor(scope_lyr, ["APN"] + target_fields) as cur:
        for row in cur:
            apn = str(row[0]).strip() if row[0] else None
            if apn and apn in join_dict:
                vals = join_dict[apn]
                for i, v in enumerate(vals):
                    ftype = tgt_field_types.get(target_fields[i], "String")
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

    if arcpy.Exists(join_fc):
        arcpy.management.Delete(join_fc)
    return n


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

    # -- WITHIN flags --------------------------------------------------------
    log.info("Flagging WITHIN_TRPA_BNDY ...")
    n1 = _flag_within(scope_lyr, SPATIAL_SOURCES["TRPA_bdy"], "WITHIN_TRPA_BNDY")
    log.info("  WITHIN_TRPA_BNDY = 1 : %d rows", n1)

    log.info("Flagging WITHIN_BONUSUNIT_BNDY ...")
    n2 = _flag_within(scope_lyr, SPATIAL_SOURCES["BonusUnit"], "WITHIN_BONUSUNIT_BNDY")
    log.info("  WITHIN_BONUSUNIT_BNDY = 1 : %d rows", n2)

    # -- Centroid points (built once, reused for all joins) ------------------
    log.info("Building centroid points ...")
    if arcpy.Exists(_PARCEL_PT): arcpy.management.Delete(_PARCEL_PT)
    arcpy.management.FeatureToPoint(scope_lyr, _PARCEL_PT, "INSIDE")
    n_pts = int(arcpy.management.GetCount(_PARCEL_PT).getOutput(0))
    log.info("  %d centroid points", n_pts)

    # -- Spatial joins -------------------------------------------------------
    joins = [
        (SPATIAL_SOURCES["TownCenter"],        ["Name"],
         ["TOWN_CENTER"],                       "TownCenter"),
        (SPATIAL_SOURCES["LocationToTownCtr"], ["LOCATION_TO_TOWNCENTER"],
         ["LOCATION_TO_TOWNCENTER"],             "LocToTC"),
        (SPATIAL_SOURCES["TAZ"],               ["TAZ"],
         ["TAZ"],                               "TAZ"),
        (SPATIAL_SOURCES["LocalPlan"],         ["PLAN_ID","PLAN_NAME"],
         ["PLAN_ID","PLAN_NAME"],               "LocalPlan"),
        (SPATIAL_SOURCES["Zoning"],            ["ZONING_ID","ZONING_DESCRIPTION"],
         ["ZONING_ID","ZONING_DESCRIPTION"],    "Zoning"),
        (SPATIAL_SOURCES["RegionalLandUse"],   ["REGIONAL_LANDUSE"],
         ["REGIONAL_LANDUSE"],                  "RLU"),
    ]

    for src_url, src_flds, tgt_flds, label in joins:
        log.info("Spatial join: %s ...", label)
        n = _sj_transfer(_PARCEL_PT, src_url, src_flds, tgt_flds, scope_lyr, label)
        log.info("  %s : %d rows updated", label, n)

    # -- Cleanup -------------------------------------------------------------
    if arcpy.Exists(_PARCEL_PT): arcpy.management.Delete(_PARCEL_PT)
    if arcpy.Exists(scope_lyr):  arcpy.management.Delete(scope_lyr)
    for fc in arcpy.ListFeatureClasses(_JOIN_PREFIX + "*", feature_dataset="memory") or []:
        arcpy.management.Delete(fc)

    log.info("Step 5 complete.")


if __name__ == "__main__":
    run()
