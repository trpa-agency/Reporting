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

from config import OUTPUT_FC, FC_APN, FC_YEAR, CSV_YEARS, SPATIAL_SOURCES, BUILDINGS_FC
from utils  import get_logger

log = get_logger("s05_spatial_attrs")

_SCRATCH = "memory"

# Temp FC names
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


def _sj_transfer(polygon_fc: str, source_url: str,
                 source_fields: list, target_fields: list,
                 scope_lyr: str, label: str) -> int:
    """
    Spatial join polygon_fc → source_url using LARGEST_OVERLAP, transfer
    attribute values back to scope_lyr via APN join.

    LARGEST_OVERLAP assigns each parcel the join feature it overlaps most,
    so gaps between adjacent polygons in the join layer cannot produce nulls.
    """
    join_fc = _JOIN_PREFIX + label.replace(" ", "_")
    if arcpy.Exists(join_fc):
        arcpy.management.Delete(join_fc)

    arcpy.analysis.SpatialJoin(
        polygon_fc, source_url, join_fc,
        "JOIN_ONE_TO_ONE", "KEEP_ALL",
        match_option="LARGEST_OVERLAP")

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


def _sum_building_sqft(scope_lyr: str) -> int:
    """
    Intersect 2019 parcel polygons with Buildings_2019, sum building footprint
    area (sq ft) per APN, and write Building_SqFt for all years.

    Year 2019 parcels are used for the intersect to match the buildings vintage
    and to avoid double-counting the same footprint across multi-year rows.
    The resulting APN → sqft dict is then applied to all years.

    Returns number of rows updated.
    """
    if not arcpy.Exists(BUILDINGS_FC):
        log.warning("Buildings FC not found: %s — skipping Building_SqFt", BUILDINGS_FC)
        return 0

    # Ensure field exists; AddField is a no-op if it already exists but we check
    # to avoid the warning noise on every run.
    existing_fields = {f.name for f in arcpy.ListFields(OUTPUT_FC)}
    if "Building_SqFt" not in existing_fields:
        arcpy.management.AddField(OUTPUT_FC, "Building_SqFt", "DOUBLE")
        log.info("  Added field Building_SqFt to OUTPUT_FC")

    # Initialize all rows to 0 so parcels with no buildings get an explicit value
    with arcpy.da.UpdateCursor(scope_lyr, ["Building_SqFt"]) as cur:
        for row in cur:
            row[0] = 0.0
            cur.updateRow(row)

    # Intersect year-2019 parcels with Buildings_2019
    lyr_2019      = "s05_bldg_yr2019"
    mem_intersect = "memory/s05_bldg_intersect"
    for name in [lyr_2019, mem_intersect]:
        if arcpy.Exists(name):
            arcpy.management.Delete(name)

    arcpy.management.MakeFeatureLayer(OUTPUT_FC, lyr_2019, f"{FC_YEAR} = 2019")
    n_parcels = int(arcpy.management.GetCount(lyr_2019).getOutput(0))
    log.info("  2019 parcels for building intersect: %d", n_parcels)

    # ERROR 000599 ("Falls outside of output geometry domains") is caused by
    # invalid/corrupt geometries.  Repair both inputs before intersecting.
    arcpy.management.RepairGeometry(lyr_2019)
    arcpy.management.RepairGeometry(BUILDINGS_FC)

    arcpy.analysis.Intersect([lyr_2019, BUILDINGS_FC], mem_intersect, "ALL")
    n_intersect = int(arcpy.management.GetCount(mem_intersect).getOutput(0))
    log.info("  Building intersect features: %d", n_intersect)

    # Sum building footprint area per APN (sq ft, explicit unit conversion
    # so the result is correct regardless of the FC spatial reference)
    bldg_sums: dict = {}
    if n_intersect > 0:
        with arcpy.da.SearchCursor(mem_intersect, [FC_APN, "SHAPE@"]) as cur:
            for apn, geom in cur:
                if apn and geom:
                    apn  = str(apn).strip()
                    sqft = geom.getArea("PLANAR", "SquareFeetUS")
                    bldg_sums[apn] = bldg_sums.get(apn, 0.0) + sqft
    log.info("  APNs with buildings: %d", len(bldg_sums))

    # Write back to all year-rows by APN
    n = 0
    with arcpy.da.UpdateCursor(scope_lyr, [FC_APN, "Building_SqFt"]) as cur:
        for row in cur:
            apn = str(row[0]).strip() if row[0] else None
            if apn and apn in bldg_sums:
                row[1] = bldg_sums[apn]
                cur.updateRow(row)
                n += 1

    for name in [lyr_2019, mem_intersect]:
        if arcpy.Exists(name):
            arcpy.management.Delete(name)

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

    # -- Spatial joins (polygon → polygon, LARGEST_OVERLAP) ------------------
    # Using the parcel polygon layer directly instead of centroid points so that
    # gaps between adjacent join polygons cannot produce null results.
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
        n = _sj_transfer(scope_lyr, src_url, src_flds, tgt_flds, scope_lyr, label)
        log.info("  %s : %d rows updated", label, n)

    # -- Building footprint sum (Buildings_2019) -----------------------------
    log.info("Summing building footprint area (Building_SqFt) ...")
    n_bldg = _sum_building_sqft(scope_lyr)
    log.info("  Building_SqFt updated: %d rows", n_bldg)

    # -- Null out "Outside Town Center" in TOWN_CENTER -----------------------
    # The TownCenter service has a catch-all polygon named "Outside Town Center"
    # that covers all non-town-center areas.  Store null instead so TOWN_CENTER
    # only contains actual town center names; proximity is captured in
    # LOCATION_TO_TOWNCENTER.
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
    if arcpy.Exists(scope_lyr):  arcpy.management.Delete(scope_lyr)
    for fc in arcpy.ListFeatureClasses(_JOIN_PREFIX + "*", feature_dataset="memory") or []:
        arcpy.management.Delete(fc)

    log.info("Step 5 complete.")


if __name__ == "__main__":
    run()
