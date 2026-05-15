"""
build_buildings_inventory_fc.py - Build the Buildings Inventory feature class
into the staging GDB, ready to upload and publish as a Cumulative_Accounting
service layer.

One polygon row per building footprint:
  - footprints  : Impervious_Surface_2019/MapServer/0 WHERE Feature = 'Building'
                  (pulled via the REST /query endpoint - arcpy.MakeFeatureLayer
                  cannot open a MapServer layer URL)
  - parcel link : spatial-joined (LARGEST_OVERLAP) to PDH 2025 parcels
                  (OUTPUT_FC, YEAR=2025) - the Impervious layer has no APN field
  - attributes  : Residential_Units / TouristAccommodation_Units /
                  CommercialFloorArea_SqFt / COUNTY / JURISDICTION /
                  PARCEL_ACRES / YEAR_BUILT  from PDH 2025;
                  Original_Year_Built (min per APN) from the Residential Unit
                  Inventory; Square_Feet computed from the footprint geometry.

Output: STAGING_GDB \\ Buildings_Inventory  (polygon feature class)

This is a NEW script - the older build_buildings_inventory.py still produces
the interim local CSV that build_buildings_with_units.py consumes; that chain
moves to the service later.

Run with ArcGIS Pro Python:
    PYTHONIOENCODING=utf-8 \\
    "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" \\
    parcel_development_history_etl/scripts/build_buildings_inventory_fc.py
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# Make the parent package importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import arcpy
import pandas as pd

from config import (
    OUTPUT_FC, FC_YEAR, FC_APN,
    IMPERVIOUS_2019_URL,
    STAGING_GDB,
    RESIDENTIAL_UNITS_INVENTORY_CSV,
)
from utils import get_logger, canonical_apn

log = get_logger("build_buildings_inventory_fc")

YEAR = 2025
OUT_FC = str(Path(STAGING_GDB) / "Buildings_Inventory")

# PDH 2025 parcel fields carried onto each building (the spatial join brings
# them in; the `have` filter below drops any that are not actually present).
PDH_FIELDS = ["Residential_Units", "TouristAccommodation_Units",
              "CommercialFloorArea_SqFt", "COUNTY", "JURISDICTION",
              "PARCEL_ACRES", "YEAR_BUILT"]

# Scratch intermediates in the staging GDB (deleted at the end / on re-run).
_TMP_FOOTPRINTS = str(Path(STAGING_GDB) / "bi_footprints_tmp")
_TMP_PROJECTED  = str(Path(STAGING_GDB) / "bi_footprints_proj")
_TMP_JOIN       = str(Path(STAGING_GDB) / "bi_spatialjoin_tmp")
_LYR_PDH        = "bi_pdh2025"


def _cleanup(*items):
    for it in items:
        if it and arcpy.Exists(it):
            arcpy.management.Delete(it)


def _int(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _float(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def extract_building_footprints(out_fc: str) -> int:
    """Page through the Impervious_Surface_2019 REST /query endpoint for
    Feature = 'Building' and write the footprints (geometry + Surface) to
    out_fc. arcpy.MakeFeatureLayer cannot open a MapServer layer URL, so this
    queries the service directly - the proven pattern used elsewhere in the
    repo. Writes incrementally to keep memory flat for a large layer."""
    base = f"{IMPERVIOUS_2019_URL}/query"
    common = {
        "where": "Feature = 'Building'",
        "outFields": "Surface",
        "returnGeometry": "true",
        "orderByFields": "OBJECTID ASC",
        "f": "json",
    }
    ins = None
    n = n_bad = 0
    offset, page = 0, 2000
    try:
        while True:
            params = {**common, "resultOffset": offset, "resultRecordCount": page}
            url = f"{base}?{urllib.parse.urlencode(params)}"
            with urllib.request.urlopen(url, timeout=180) as resp:
                data = json.loads(resp.read())
            if "error" in data:
                raise SystemExit(f"REST error from Impervious: {data['error']}")
            batch = data.get("features", [])
            if not batch:
                break
            if ins is None:
                sr = data.get("spatialReference", {})
                wkid = sr.get("latestWkid") or sr.get("wkid")
                if not wkid:
                    raise SystemExit("Impervious query returned no spatialReference")
                arcpy.management.CreateFeatureclass(
                    str(Path(out_fc).parent), Path(out_fc).name, "POLYGON",
                    spatial_reference=arcpy.SpatialReference(wkid))
                arcpy.management.AddField(out_fc, "Surface", "TEXT", field_length=16)
                ins = arcpy.da.InsertCursor(out_fc, ["SHAPE@", "Surface"])
            for f in batch:
                g = f.get("geometry")
                if not g:
                    n_bad += 1
                    continue
                try:
                    shp = arcpy.AsShape(g, True)
                except Exception:
                    n_bad += 1
                    continue
                surf = (f.get("attributes", {}).get("Surface") or "").strip() or None
                ins.insertRow([shp, surf])
                n += 1
            log.info("  offset=%d: +%d (total %d)", offset, len(batch), n)
            if not data.get("exceededTransferLimit") and len(batch) < page:
                break
            offset += page
    finally:
        if ins is not None:
            del ins
    if n_bad:
        log.warning("  skipped %d footprints with missing/invalid geometry", n_bad)
    if n == 0:
        raise SystemExit("No building footprints returned - check the service / filter")
    log.info("  wrote %d footprints to %s", n, out_fc)
    return n


def load_original_year_built() -> dict:
    """APN_canon -> min Original_Year_Built, from the Residential Unit Inventory."""
    log.info("Loading Original_Year_Built: %s", RESIDENTIAL_UNITS_INVENTORY_CSV)
    df = pd.read_csv(RESIDENTIAL_UNITS_INVENTORY_CSV,
                     dtype={"APN": str, "APN_canon": str}, low_memory=False)
    if "Original_Year_Built" not in df.columns or "APN_canon" not in df.columns:
        log.warning("  unit inventory missing expected columns; got %s",
                    list(df.columns))
        return {}
    df["Original_Year_Built"] = pd.to_numeric(df["Original_Year_Built"],
                                              errors="coerce")
    df = df.dropna(subset=["APN_canon", "Original_Year_Built"])
    lookup = (df.groupby("APN_canon")["Original_Year_Built"]
                .min().astype(int).to_dict())
    log.info("  %d APNs with an Original_Year_Built", len(lookup))
    return lookup


def main() -> None:
    log.info("=" * 70)
    log.info("BUILD BUILDINGS INVENTORY FC -> %s", OUT_FC)
    log.info("=" * 70)
    arcpy.env.overwriteOutput = True

    if not arcpy.Exists(STAGING_GDB):
        raise SystemExit(f"Staging GDB not found: {STAGING_GDB}")
    if not arcpy.Exists(OUTPUT_FC):
        raise SystemExit(f"PDH OUTPUT_FC not found: {OUTPUT_FC}")
    _cleanup(OUT_FC, _TMP_FOOTPRINTS, _TMP_PROJECTED, _TMP_JOIN, _LYR_PDH)

    # 1. Building footprints from Impervious_Surface_2019 (Feature = 'Building')
    log.info("Extracting building footprints: %s", IMPERVIOUS_2019_URL)
    n_footprints = extract_building_footprints(_TMP_FOOTPRINTS)

    # 2. Project footprints to the PDH spatial reference if they differ
    pdh_sr  = arcpy.Describe(OUTPUT_FC).spatialReference
    foot_sr = arcpy.Describe(_TMP_FOOTPRINTS).spatialReference
    if foot_sr.factoryCode != pdh_sr.factoryCode:
        log.info("  projecting footprints %s -> %s", foot_sr.name, pdh_sr.name)
        arcpy.management.Project(_TMP_FOOTPRINTS, _TMP_PROJECTED, pdh_sr)
        footprints = _TMP_PROJECTED
    else:
        footprints = _TMP_FOOTPRINTS

    # 3. Spatial-join footprints -> PDH 2025 parcels (LARGEST_OVERLAP)
    log.info("Spatial-joining footprints -> PDH %d parcels (LARGEST_OVERLAP)", YEAR)
    arcpy.management.MakeFeatureLayer(
        OUTPUT_FC, _LYR_PDH, where_clause=f"{FC_YEAR} = {YEAR}")
    arcpy.analysis.SpatialJoin(
        target_features=footprints, join_features=_LYR_PDH,
        out_feature_class=_TMP_JOIN, join_operation="JOIN_ONE_TO_ONE",
        join_type="KEEP_ALL", match_option="LARGEST_OVERLAP")

    # footprint OID (TARGET_FID) -> parcel attributes
    join_fields = ["TARGET_FID", FC_APN] + PDH_FIELDS
    have = {f.name for f in arcpy.ListFields(_TMP_JOIN)}
    join_fields = [f for f in join_fields if f in have]
    log.info("  join carried: %s", join_fields)
    parcel_by_oid: dict[int, dict] = {}
    with arcpy.da.SearchCursor(_TMP_JOIN, join_fields) as cur:
        for row in cur:
            d = dict(zip(join_fields, row))
            parcel_by_oid[int(d["TARGET_FID"])] = d
    n_matched = sum(1 for d in parcel_by_oid.values() if d.get(FC_APN))
    log.info("  %d / %d footprints matched a 2025 parcel", n_matched, n_footprints)

    # 4. Original_Year_Built lookup from the Residential Unit Inventory
    oyb_by_apn = load_original_year_built()

    # 5. Create the output FC and its schema
    log.info("Creating %s", OUT_FC)
    arcpy.management.CreateFeatureclass(
        STAGING_GDB, "Buildings_Inventory", "POLYGON", spatial_reference=pdh_sr)
    schema = [
        ("Building_ID",                "LONG",   None),
        ("Surface",                    "TEXT",   16),
        ("Square_Feet",                "DOUBLE", None),
        ("APN",                        "TEXT",   30),
        ("APN_canon",                  "TEXT",   30),
        ("Residential_Units",          "LONG",   None),
        ("TouristAccommodation_Units", "LONG",   None),
        ("CommercialFloorArea_SqFt",   "DOUBLE", None),
        ("Original_Year_Built",        "LONG",   None),
        ("YEAR_BUILT",                 "TEXT",   10),
        ("PARCEL_ACRES",               "DOUBLE", None),
        ("COUNTY",                     "TEXT",   20),
        ("JURISDICTION",               "TEXT",   100),
    ]
    for name, ftype, flen in schema:
        if flen:
            arcpy.management.AddField(OUT_FC, name, ftype, field_length=flen)
        else:
            arcpy.management.AddField(OUT_FC, name, ftype)

    # 6. Populate: one row per footprint, geometry + joined attributes
    out_fields = ["SHAPE@", "Building_ID", "Surface", "Square_Feet",
                  "APN", "APN_canon", "Residential_Units",
                  "TouristAccommodation_Units", "CommercialFloorArea_SqFt",
                  "Original_Year_Built", "YEAR_BUILT", "PARCEL_ACRES",
                  "COUNTY", "JURISDICTION"]
    n_written = n_oyb = 0
    with arcpy.da.SearchCursor(footprints, ["OID@", "SHAPE@", "Surface"]) as src, \
         arcpy.da.InsertCursor(OUT_FC, out_fields) as ins:
        for oid, geom, surface in src:
            p = parcel_by_oid.get(int(oid), {})
            apn = p.get(FC_APN)
            apn_c = canonical_apn(apn) if apn else None
            oyb = oyb_by_apn.get(apn_c) if apn_c else None
            if oyb is not None:
                n_oyb += 1
            sqft = geom.getArea("PLANAR", "SquareFeetUS") if geom else None
            yb = p.get("YEAR_BUILT")
            ins.insertRow([
                geom,
                int(oid),
                (surface or "").strip() or None,
                round(sqft, 2) if sqft is not None else None,
                str(apn).strip() if apn else None,
                apn_c,
                _int(p.get("Residential_Units")),
                _int(p.get("TouristAccommodation_Units")),
                _float(p.get("CommercialFloorArea_SqFt")),
                oyb,
                str(yb).strip() if yb not in (None, "") else None,
                _float(p.get("PARCEL_ACRES")),
                (p.get("COUNTY") or None),
                (p.get("JURISDICTION") or None),
            ])
            n_written += 1

    # 7. Clean up scratch intermediates
    _cleanup(_TMP_FOOTPRINTS, _TMP_PROJECTED, _TMP_JOIN, _LYR_PDH)

    # 8. Summary
    log.info("=" * 70)
    log.info("Buildings_Inventory: %d rows -> %s", n_written, OUT_FC)
    log.info("  matched to a 2025 parcel:   %d (%.1f%%)",
             n_matched, 100 * n_matched / max(n_written, 1))
    log.info("  with Original_Year_Built:   %d (%.1f%%)",
             n_oyb, 100 * n_oyb / max(n_written, 1))
    log.info("=" * 70)
    log.info("Ready to upload and publish as a Cumulative_Accounting layer.")


if __name__ == "__main__":
    main()
