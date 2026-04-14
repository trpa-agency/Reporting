"""
Step 1 — Build output feature class from authoritative sources.

For years 2012–2024: queries the All Parcels MapServer service layer for each
year and inserts all features with APN + Year + Shape into OUTPUT_FC.  This
gives a clean, gap-free geometry base directly from the canonical source.

For 2025: the All Parcels service does not yet have a 2025 layer.  Rows are
copied from SOURCE_FC WHERE YEAR = 2025 as a fallback.

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
    ALLPARCELS_URL, YEAR_LAYER,
    COUNTY_CODE_MAP,
)
from utils import get_logger

log = get_logger("s01_prepare_fc")

# Years to pull from All Parcels service (excludes years with no layer)
SERVICE_YEARS = [y for y in CSV_YEARS if y in YEAR_LAYER]
FALLBACK_YEARS = [y for y in CSV_YEARS if y not in YEAR_LAYER]


def _create_empty_fc() -> None:
    """Drop and create OUTPUT_FC using SOURCE_FC as schema template.

    Using SOURCE_FC as template copies all field definitions (types, lengths,
    aliases) so S04, S04b, and S05 can write to their expected fields without
    needing to add them first.  No data is copied.
    """
    if arcpy.Exists(OUTPUT_FC):
        log.info("Deleting existing OUTPUT_FC")
        arcpy.management.Delete(OUTPUT_FC)

    out_name = OUTPUT_FC.split("\\")[-1]

    arcpy.management.CreateFeatureclass(
        out_path      = GDB,
        out_name      = out_name,
        geometry_type = "POLYGON",
        template      = SOURCE_FC,
    )
    log.info("Created empty OUTPUT_FC (schema from SOURCE_FC): %s", OUTPUT_FC)


def _insert_from_service(year: int) -> int:
    """
    Query the All Parcels service layer for *year* and insert all features
    (Shape + APN + COUNTY + Year) into OUTPUT_FC.
    COUNTY is needed by S02's El Dorado APN fix before S05 runs.
    Returns number of rows inserted.
    """
    layer_idx = YEAR_LAYER[year]
    url       = f"{ALLPARCELS_URL}/{layer_idx}"
    lyr       = f"s01_svc_{year}"

    if arcpy.Exists(lyr):
        arcpy.management.Delete(lyr)

    try:
        arcpy.management.MakeFeatureLayer(url, lyr)
    except Exception as exc:
        log.error("  Year %d: cannot connect to service layer %d — %s", year, layer_idx, exc)
        return 0

    # Find APN and JURISDICTION fields (case-insensitive).
    # The All Parcels service uses JURISDICTION (full name) not COUNTY (code).
    # We map JURISDICTION -> COUNTY code via COUNTY_CODE_MAP.
    field_map        = {f.name.upper(): f.name for f in arcpy.ListFields(lyr)}
    apn_field        = field_map.get(FC_APN.upper())
    juris_field      = (field_map.get("JURISDICTION") or
                        next((v for k, v in field_map.items()
                              if "JURISDICTI" in k), None))

    if not apn_field:
        log.error("  Year %d: APN field not found in service layer.", year)
        arcpy.management.Delete(lyr)
        return 0

    if not juris_field:
        log.warning("  Year %d: JURISDICTION field not found in service layer — COUNTY will be null.", year)

    read_fields   = ["SHAPE@", apn_field] + ([juris_field] if juris_field else [])
    insert_fields = ["SHAPE@", FC_APN, FC_YEAR, "COUNTY"]

    count = 0
    with arcpy.da.SearchCursor(lyr, read_fields) as src, \
         arcpy.da.InsertCursor(OUTPUT_FC, insert_fields) as ins:
        for row in src:
            shape, apn = row[0], row[1]
            juris      = row[2] if juris_field else None
            county     = COUNTY_CODE_MAP.get(juris) if juris else None
            if apn:
                ins.insertRow([shape, str(apn).strip(), year, county])
                count += 1

    arcpy.management.Delete(lyr)
    return count


def _insert_from_source_fc(year: int) -> int:
    """
    Copy rows for *year* from SOURCE_FC into OUTPUT_FC.
    Used as fallback for years with no All Parcels service layer (currently 2025).
    Includes COUNTY so the El Dorado fix works correctly.
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
    log.info("Service years : %s", SERVICE_YEARS)
    log.info("Fallback years: %s (from SOURCE_FC)", FALLBACK_YEARS)

    _create_empty_fc()

    year_counts = {}

    # Pull from All Parcels service for years with a layer
    for year in SERVICE_YEARS:
        log.info("  Year %d (service layer %d) ...", year, YEAR_LAYER[year])
        n = _insert_from_service(year)
        year_counts[year] = n
        log.info("    %d rows inserted", n)

    # Copy from SOURCE_FC for years without a service layer
    for year in FALLBACK_YEARS:
        log.info("  Year %d (SOURCE_FC fallback) ...", year)
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
