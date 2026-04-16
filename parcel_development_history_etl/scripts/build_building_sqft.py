"""
Standalone script: populate Building_SqFt on the output FC.

Intersects 2019 parcel polygons with Buildings_2019, sums building footprint
area (sq ft) per APN, and writes Building_SqFt for all year-rows.

Year 2019 parcels are used for the intersect to match the buildings vintage
and to avoid double-counting the same footprint across multi-year rows.
The resulting APN → sqft dict is then applied to all years.

Run this independently of the main ETL for validation or ad-hoc updates:

    C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe \\
        parcel_development_history_etl/scripts/build_building_sqft.py
"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))

import arcpy

from config import OUTPUT_FC, FC_APN, FC_YEAR, CSV_YEARS, BUILDINGS_FC
from utils  import get_logger

log = get_logger("build_building_sqft")


def run() -> None:
    log.info("=== Building footprint area (Building_SqFt) ===")

    if not arcpy.Exists(BUILDINGS_FC):
        log.error("Buildings FC not found: %s", BUILDINGS_FC)
        sys.exit(1)

    if not arcpy.Exists(OUTPUT_FC):
        log.error("Output FC not found: %s", OUTPUT_FC)
        sys.exit(1)

    # Ensure field exists
    existing_fields = {f.name for f in arcpy.ListFields(OUTPUT_FC)}
    if "Building_SqFt" not in existing_fields:
        arcpy.management.AddField(OUTPUT_FC, "Building_SqFt", "DOUBLE")
        log.info("Added field Building_SqFt to OUTPUT_FC")

    # Scope layer: all years in CSV_YEARS
    scope_lyr = "bldgsqft_scope"
    if arcpy.Exists(scope_lyr):
        arcpy.management.Delete(scope_lyr)
    yr_list = ", ".join(str(y) for y in CSV_YEARS)
    arcpy.management.MakeFeatureLayer(OUTPUT_FC, scope_lyr, f"{FC_YEAR} IN ({yr_list})")
    n_scope = int(arcpy.management.GetCount(scope_lyr).getOutput(0))
    log.info("Rows in scope: %d", n_scope)

    # Initialize all rows to 0
    with arcpy.da.UpdateCursor(scope_lyr, ["Building_SqFt"]) as cur:
        for row in cur:
            row[0] = 0.0
            cur.updateRow(row)

    # Intersect year-2019 parcels with Buildings_2019
    lyr_2019      = "bldgsqft_yr2019"
    mem_intersect = "memory/bldgsqft_intersect"
    mem_bldg      = "memory/bldgsqft_projected"
    for name in [lyr_2019, mem_intersect, mem_bldg]:
        if arcpy.Exists(name):
            arcpy.management.Delete(name)

    arcpy.management.MakeFeatureLayer(OUTPUT_FC, lyr_2019, f"{FC_YEAR} = 2019")
    n_parcels = int(arcpy.management.GetCount(lyr_2019).getOutput(0))
    log.info("2019 parcels for building intersect: %d", n_parcels)

    # Project Buildings_2019 into the parcel FC's SR if they differ.
    # Intersect uses the first input's SR as the output SR; coordinates from
    # the second input that fall outside that domain trigger ERROR 000599.
    parcel_sr = arcpy.Describe(OUTPUT_FC).spatialReference
    bldg_sr   = arcpy.Describe(BUILDINGS_FC).spatialReference

    if parcel_sr.factoryCode != bldg_sr.factoryCode:
        log.info("Projecting Buildings_2019 (%s → %s) ...",
                 bldg_sr.name, parcel_sr.name)
        arcpy.management.Project(BUILDINGS_FC, mem_bldg, parcel_sr)
        bldg_input = mem_bldg
    else:
        bldg_input = BUILDINGS_FC

    arcpy.analysis.Intersect([lyr_2019, bldg_input], mem_intersect, "ALL")
    n_intersect = int(arcpy.management.GetCount(mem_intersect).getOutput(0))
    log.info("Building intersect features: %d", n_intersect)

    # Sum footprint area per APN (explicit unit conversion)
    bldg_sums: dict = {}
    if n_intersect > 0:
        with arcpy.da.SearchCursor(mem_intersect, [FC_APN, "SHAPE@"]) as cur:
            for apn, geom in cur:
                if apn and geom:
                    apn  = str(apn).strip()
                    sqft = geom.getArea("PLANAR", "SquareFeetUS")
                    bldg_sums[apn] = bldg_sums.get(apn, 0.0) + sqft
    log.info("APNs with buildings: %d", len(bldg_sums))

    # Write back to all year-rows by APN
    n = 0
    with arcpy.da.UpdateCursor(scope_lyr, [FC_APN, "Building_SqFt"]) as cur:
        for row in cur:
            apn = str(row[0]).strip() if row[0] else None
            if apn and apn in bldg_sums:
                row[1] = bldg_sums[apn]
                cur.updateRow(row)
                n += 1
    log.info("Building_SqFt updated: %d rows", n)

    # Cleanup
    for name in [scope_lyr, lyr_2019, mem_intersect, mem_bldg]:
        if arcpy.Exists(name):
            arcpy.management.Delete(name)

    log.info("Done.")


if __name__ == "__main__":
    run()
