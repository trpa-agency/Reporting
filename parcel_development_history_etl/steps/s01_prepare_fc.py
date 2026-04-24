"""
Step 1 — Build output feature class from SOURCE_FC.

All CSV_YEARS (2012–2025) are copied from SOURCE_FC, which already mirrors
the All Parcels canonical layers and crucially has valid geometry for every
year.  The All Parcels REST service was previously used for 2013–2024 but
returned features with null SHAPE@ through arcpy's SearchCursor — breaking
the per-year spatial crosswalk in S03 and producing large unit shortfalls
(2021+ most affected).

Spatial attributes (County, Jurisdiction, Zoning, etc.) are populated later
by Step 5.  Unit fields are populated by Steps 4 and 4b.

Drops and recreates OUTPUT_FC on every run so results are always fresh.
"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))

import arcpy

from config import (
    SOURCE_FC, OUTPUT_FC, GDB,
    FC_APN, FC_YEAR, CSV_YEARS,
)
from utils import get_logger

log = get_logger("s01_prepare_fc")


def _create_empty_fc() -> None:
    """Drop and create OUTPUT_FC using SOURCE_FC as schema template.

    Using SOURCE_FC as template copies all field definitions (types, lengths,
    aliases) so S04, S04b, and S05 can write to their expected fields without
    needing to add them first.  No data is copied.

    `template` only copies field schema — spatial reference must be passed
    explicitly via `spatial_reference=`, otherwise the new FC gets SR=Unknown
    and InsertCursor silently drops geometry from sources whose SR differs
    (e.g. Web Mercator from AllParcels REST).
    """
    if arcpy.Exists(OUTPUT_FC):
        log.info("Deleting existing OUTPUT_FC")
        arcpy.management.Delete(OUTPUT_FC)

    out_name = OUTPUT_FC.split("\\")[-1]
    src_sr   = arcpy.Describe(SOURCE_FC).spatialReference

    arcpy.management.CreateFeatureclass(
        out_path          = GDB,
        out_name          = out_name,
        geometry_type     = "POLYGON",
        template          = SOURCE_FC,
        spatial_reference = src_sr,
    )
    log.info("Created empty OUTPUT_FC (schema + SR %s): %s", src_sr.name, OUTPUT_FC)


def _insert_from_source_fc(year: int) -> int:
    """
    Copy rows for *year* from SOURCE_FC into OUTPUT_FC (Shape + APN + COUNTY).
    COUNTY is needed by S02's El Dorado APN fix before S05 runs.
    Returns number of rows inserted.
    """
    if not arcpy.Exists(SOURCE_FC):
        log.error("  SOURCE_FC not found: %s", SOURCE_FC)
        return 0

    count = 0
    where = f"{FC_YEAR} = {year}"
    with arcpy.da.SearchCursor(SOURCE_FC, ["SHAPE@", FC_APN, FC_YEAR, "COUNTY"], where) as src, \
         arcpy.da.InsertCursor(OUTPUT_FC, ["SHAPE@", FC_APN, FC_YEAR, "COUNTY"]) as ins:
        for shape, apn, yr, county in src:
            if apn:
                ins.insertRow([shape, str(apn).strip(), yr, county])
                count += 1

    return count


def _dedup_fc() -> int:
    """Remove duplicate APN x Year rows, keeping the one with the largest area.

    Service layers can return multiple polygons per APN (condos, common areas).
    We keep one row per (APN, Year) — the largest polygon — and delete the rest.
    Returns number of rows removed.
    """
    log.info("Dedup: scanning for duplicate APN x Year rows ...")

    # Pass 1 — identify which OIDs to keep (largest area per APN x Year)
    best: dict = {}  # (apn, year) -> (oid, area)
    dup_oids: list = []

    with arcpy.da.SearchCursor(
            OUTPUT_FC, ["OID@", FC_APN, FC_YEAR, "SHAPE@AREA"]) as cur:
        for oid, apn, yr, area in cur:
            if not apn:
                continue
            key = (str(apn).strip(), int(yr) if yr else 0)
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

    if not dup_oids:
        log.info("Dedup: no duplicates found.")
        return 0

    log.info("Dedup: %d duplicate rows to remove ...", len(dup_oids))

    # Pass 2 — delete duplicate OIDs in batches
    oid_field = arcpy.Describe(OUTPUT_FC).OIDFieldName
    batch = 500
    removed = 0
    for i in range(0, len(dup_oids), batch):
        chunk = dup_oids[i:i + batch]
        oid_list = ", ".join(str(o) for o in chunk)
        where = f"{oid_field} IN ({oid_list})"
        lyr = "s01_dedup_lyr"
        if arcpy.Exists(lyr):
            arcpy.management.Delete(lyr)
        arcpy.management.MakeFeatureLayer(OUTPUT_FC, lyr, where)
        n = int(arcpy.management.GetCount(lyr).getOutput(0))
        if n > 0:
            arcpy.management.DeleteRows(lyr)
            removed += n
        arcpy.management.Delete(lyr)

    log.info("Dedup: removed %d rows.", removed)
    return removed


def run() -> None:
    log.info("=== Step 1: Build output feature class ===")
    log.info("All years sourced from SOURCE_FC: %s", SOURCE_FC)

    _create_empty_fc()

    year_counts = {}
    for year in CSV_YEARS:
        log.info("  Year %d (from SOURCE_FC) ...", year)
        n = _insert_from_source_fc(year)
        year_counts[year] = n
        log.info("    %d rows inserted", n)

    total = sum(year_counts.values())
    log.info("Output FC: %d total rows across %d years", total, len(year_counts))
    log.info("Rows per year:")
    for yr in sorted(year_counts):
        log.info("  %d : %6d rows", yr, year_counts[yr])

    removed = _dedup_fc()
    if removed:
        log.info("Output FC after dedup: %d rows",
                 int(arcpy.management.GetCount(OUTPUT_FC).getOutput(0)))

    log.info("Step 1 complete.")


if __name__ == "__main__":
    run()
