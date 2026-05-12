"""
build_buildings_inventory.py — One row per Buildings_2019 footprint, joined
to the PDH 2025 parcel it sits on.

Schema:
  Building_ID         — Buildings_2019 OBJECTID (stable, unique)
  APN                 — APN of the parcel with the LARGEST_OVERLAP
  APN_canon           — canonical form (for joins)
  Square_Feet         — planar footprint area in US sq ft (SHAPE@.getArea)
  Original_Year_Built — parcel-level COMBINED_YEAR_BUILT (from prior step)
  Feature             — Buildings_2019 'Feature' attr (building type)
  Surface             — Buildings_2019 'Surface' attr (material)
  Parcel_Acres        — parcel acres (context)
  Residential_Units   — units on the parent parcel in 2025
  Units_Assigned      — units assigned specifically to THIS building via
                        sqft-weighted Hamilton-largest-remainder split (read
                        from buildings_with_units.json; ≤ Residential_Units)
  COUNTY, JURISDICTION

Output: data/processed_data/buildings_inventory_2025.csv

NOTE: re-run `scripts/build_buildings_with_units.py` after the prior build
to refresh `Units_Assigned`.

Run with ArcGIS Pro Python:
    PYTHONIOENCODING=utf-8 \\
    "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" \\
    parcel_development_history_etl/scripts/build_buildings_inventory.py
"""
import sys
from pathlib import Path

# Make the parent package importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import arcpy
import pandas as pd

from config import (
    OUTPUT_FC,
    FC_APN, FC_YEAR,
    BUILDINGS_FC,
    PDH_2025_YRBUILT_CSV,
    BUILDINGS_INVENTORY_CSV,
    BUILDINGS_WITH_UNITS_JSON,
)
from utils import get_logger, canonical_apn

log = get_logger("build_buildings_inventory")

YEAR = 2025


def get_building_areas() -> dict:
    """Read Buildings_2019; return {OBJECTID: (area_sqft, Feature, Surface)}."""
    log.info("Reading Buildings_2019 attributes: %s", BUILDINGS_FC)
    if not arcpy.Exists(BUILDINGS_FC):
        raise SystemExit(f"Buildings FC not found: {BUILDINGS_FC}")

    out: dict[int, tuple[float, str, str]] = {}
    with arcpy.da.SearchCursor(
            BUILDINGS_FC, ["OID@", "SHAPE@", "Feature", "Surface"]) as cur:
        for oid, geom, feat, surf in cur:
            if geom is None:
                continue
            sqft = float(geom.getArea("PLANAR", "SquareFeetUS")) if geom else 0.0
            out[int(oid)] = (round(sqft, 2),
                             (feat or "").strip(),
                             (surf or "").strip())
    log.info("  %d buildings loaded", len(out))
    return out


def spatial_join_buildings_to_parcels() -> dict:
    """
    Spatial-join Buildings_2019 → PDH YEAR=2025 with LARGEST_OVERLAP.
    Returns {Building_OBJECTID: APN_raw_str} — pick the parcel with the
    most overlap for each building (or only) parcel it intersects.
    """
    log.info("Spatial-joining Buildings_2019 → PDH 2025 (LARGEST_OVERLAP)")

    pdh_lyr = "binv_pdh2025"
    bldg_lyr = "binv_bldg"
    join_out = "memory/binv_join"
    for m in [pdh_lyr, bldg_lyr, join_out]:
        if arcpy.Exists(m):
            arcpy.management.Delete(m)

    arcpy.management.MakeFeatureLayer(OUTPUT_FC, pdh_lyr,
                                      where_clause=f"{FC_YEAR} = {YEAR}")
    arcpy.management.MakeFeatureLayer(BUILDINGS_FC, bldg_lyr)

    # Project buildings to parcel SR if needed (avoids SpatialJoin SR errors)
    parcel_sr = arcpy.Describe(OUTPUT_FC).spatialReference
    bldg_sr   = arcpy.Describe(BUILDINGS_FC).spatialReference
    if parcel_sr.factoryCode != bldg_sr.factoryCode:
        mem_proj = "memory/binv_bldg_proj"
        if arcpy.Exists(mem_proj):
            arcpy.management.Delete(mem_proj)
        log.info("  Projecting buildings (%s → %s) ...", bldg_sr.name, parcel_sr.name)
        arcpy.management.Project(BUILDINGS_FC, mem_proj, parcel_sr)
        arcpy.management.Delete(bldg_lyr)
        arcpy.management.MakeFeatureLayer(mem_proj, bldg_lyr)

    arcpy.analysis.SpatialJoin(
        target_features=bldg_lyr,
        join_features=pdh_lyr,
        out_feature_class=join_out,
        join_operation="JOIN_ONE_TO_ONE",
        join_type="KEEP_ALL",
        match_option="LARGEST_OVERLAP",
    )

    # The join output preserves building OID under TARGET_FID and brings in
    # the parcel APN as a regular field.
    fields = [f.name for f in arcpy.ListFields(join_out)]
    if FC_APN not in fields:
        log.warning("  APN field missing from join output; fields=%s", fields)
        return {}

    bid_to_apn: dict[int, str] = {}
    with arcpy.da.SearchCursor(join_out, ["TARGET_FID", FC_APN]) as cur:
        for bid, apn in cur:
            if apn and bid is not None:
                bid_to_apn[int(bid)] = str(apn).strip()

    for m in [pdh_lyr, bldg_lyr, join_out]:
        if arcpy.Exists(m):
            arcpy.management.Delete(m)

    log.info("  %d / %d buildings matched to a 2025 parcel",
             len(bid_to_apn), int(arcpy.management.GetCount(BUILDINGS_FC).getOutput(0)))
    return bid_to_apn


def main() -> None:
    log.info("=" * 70)
    log.info("BUILD BUILDINGS INVENTORY (2025)")
    log.info("=" * 70)

    areas = get_building_areas()
    bid_to_apn = spatial_join_buildings_to_parcels()

    # Load parcel context from prior PDH 2025 + year-built output
    log.info("Loading PDH 2025 context: %s", PDH_2025_YRBUILT_CSV)
    pdh = pd.read_csv(PDH_2025_YRBUILT_CSV,
                      dtype={"APN": str, "APN_canon": str})
    pdh_lookup = {
        row.APN: {
            "APN_canon":            row.APN_canon,
            "Original_Year_Built":  row.COMBINED_YEAR_BUILT,
            "Parcel_Acres":         row.PARCEL_ACRES,
            "Residential_Units":    int(row.Residential_Units or 0),
            "COUNTY":               row.COUNTY,
            "JURISDICTION":         row.JURISDICTION,
        }
        for row in pdh.itertuples(index=False)
    }

    # Optional: per-building Units_Assigned (sqft-weighted split). Source is
    # buildings_with_units.json — built downstream from this CSV, so on a
    # cold first run this won't exist and Units_Assigned will be left null.
    # Re-run this script after build_buildings_with_units.py to backfill.
    units_assigned: dict[int, int] = {}
    bw_path = Path(BUILDINGS_WITH_UNITS_JSON)
    if bw_path.exists():
        import json as _json
        with open(bw_path, "r", encoding="utf-8") as f:
            bw = _json.load(f)
        for b in bw.get("buildings", []):
            bid = b.get("id")
            n   = b.get("units_assigned")
            if bid is not None and n is not None:
                units_assigned[int(bid)] = int(n)
        log.info("Loaded units_assigned from %s (%d buildings)",
                 BUILDINGS_WITH_UNITS_JSON, len(units_assigned))
    else:
        log.info("No %s yet — Units_Assigned will be null on first build. "
                 "Re-run after build_buildings_with_units.py.",
                 BUILDINGS_WITH_UNITS_JSON)

    rows = []
    for bid, (sqft, feat, surf) in areas.items():
        apn_raw = bid_to_apn.get(bid)
        ctx = pdh_lookup.get(apn_raw, {}) if apn_raw else {}
        rows.append({
            "Building_ID":         bid,
            "APN":                 apn_raw,
            "APN_canon":           ctx.get("APN_canon"),
            "Square_Feet":         sqft,
            "Original_Year_Built": ctx.get("Original_Year_Built"),
            "Feature":             feat,
            "Surface":             surf,
            "Parcel_Acres":        ctx.get("Parcel_Acres"),
            "Residential_Units":   ctx.get("Residential_Units"),
            "Units_Assigned":      units_assigned.get(bid),
            "COUNTY":              ctx.get("COUNTY"),
            "JURISDICTION":        ctx.get("JURISDICTION"),
        })

    df = pd.DataFrame(rows)
    df["Original_Year_Built"] = pd.to_numeric(df["Original_Year_Built"],
                                              errors="coerce").astype("Int64")
    df["Units_Assigned"]      = pd.to_numeric(df["Units_Assigned"],
                                              errors="coerce").astype("Int64")

    out_path = Path(BUILDINGS_INVENTORY_CSV)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)

    log.info("=" * 70)
    log.info("Wrote %d building rows -> %s", len(df), out_path)
    log.info("=" * 70)

    # Summary
    log.info("Summary:")
    log.info("  buildings with APN matched:           %d (%.1f%%)",
             int(df["APN"].notna().sum()), 100 * df["APN"].notna().mean())
    log.info("  buildings with Original_Year_Built:   %d (%.1f%%)",
             int(df["Original_Year_Built"].notna().sum()),
             100 * df["Original_Year_Built"].notna().mean())
    log.info("  buildings on residential parcels:     %d",
             int((df["Residential_Units"].fillna(0) > 0).sum()))
    log.info("  total footprint sqft (all buildings): %s",
             f"{df['Square_Feet'].sum():,.0f}")
    log.info("  mean footprint sqft:                  %.0f",
             df["Square_Feet"].mean())
    log.info("  Feature breakdown (top 5):")
    for k, v in df["Feature"].value_counts().head(5).items():
        log.info("    %-30s %d", k or "(empty)", v)


if __name__ == "__main__":
    main()
