"""
Compare SOURCE_FC vs All Parcels service for 2012.

Produces a feature class with parcels missing from either source:
  SOURCE_ONLY  — in SOURCE_FC but not in service
  SERVICE_ONLY — in service but not in SOURCE_FC

Output: C:\GIS\ParcelHistory.gdb\QA_2012_Source_Comparison
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import arcpy

from config import (SOURCE_FC, GDB, FC_APN, FC_YEAR,
                    ALLPARCELS_URL, YEAR_LAYER, EL_PAD_YEAR)
from utils import get_logger, el_pad, el_depad, _EL_2D, _EL_3D

log = print  # simple print logging for one-off script

OUT_FC = GDB + r"\QA_2012_Source_Comparison"
YEAR = 2012
SVC_URL = f"{ALLPARCELS_URL}/{YEAR_LAYER[YEAR]}"


def _read_source_fc():
    """Read 2012 APNs + shapes from SOURCE_FC."""
    apns = {}  # apn -> shape
    where = f"{FC_YEAR} = {YEAR}"
    with arcpy.da.SearchCursor(SOURCE_FC, ["SHAPE@", FC_APN], where) as cur:
        for shape, apn in cur:
            if apn:
                a = str(apn).strip()
                apns[a] = shape
    return apns


def _read_service():
    """Read 2012 APNs + shapes from All Parcels service."""
    lyr = "compare_svc_2012"
    if arcpy.Exists(lyr):
        arcpy.management.Delete(lyr)

    log(f"Connecting to service: {SVC_URL}")
    arcpy.management.MakeFeatureLayer(SVC_URL, lyr)

    # Find APN field
    field_map = {f.name.upper(): f.name for f in arcpy.ListFields(lyr)}
    apn_field = field_map.get(FC_APN.upper())
    if not apn_field:
        raise ValueError("APN field not found in service layer")

    apns = {}  # apn -> shape
    with arcpy.da.SearchCursor(lyr, ["SHAPE@", apn_field]) as cur:
        for shape, apn in cur:
            if apn:
                a = str(apn).strip()
                if a not in apns:  # keep first if duplicates
                    apns[a] = shape

    arcpy.management.Delete(lyr)
    return apns


def _normalize_for_compare(apns_dict, label):
    """Build a normalized APN lookup (depad 3-digit EL APNs for comparison)."""
    normalized = {}
    for apn, shape in apns_dict.items():
        # Normalize: depad 3-digit to 2-digit for matching purposes
        norm = el_depad(apn) if _EL_3D.match(apn) else apn
        normalized[norm] = (apn, shape)  # keep original APN + shape
    return normalized


def run():
    log("=== Compare 2012: SOURCE_FC vs All Parcels Service ===")

    # Read both sources
    log("Reading SOURCE_FC for 2012 ...")
    source_apns = _read_source_fc()
    log(f"  SOURCE_FC: {len(source_apns)} APNs")

    log("Reading All Parcels service for 2012 ...")
    service_apns = _read_service()
    log(f"  Service:   {len(service_apns)} APNs")

    # Normalize both for comparison (depad EL 3-digit)
    source_norm = _normalize_for_compare(source_apns, "SOURCE")
    service_norm = _normalize_for_compare(service_apns, "SERVICE")

    source_only_keys = set(source_norm.keys()) - set(service_norm.keys())
    service_only_keys = set(service_norm.keys()) - set(source_norm.keys())
    both_keys = set(source_norm.keys()) & set(service_norm.keys())

    log(f"\n  Both:         {len(both_keys)}")
    log(f"  SOURCE_ONLY:  {len(source_only_keys)}")
    log(f"  SERVICE_ONLY: {len(service_only_keys)}")

    # Create output FC
    if arcpy.Exists(OUT_FC):
        arcpy.management.Delete(OUT_FC)

    out_name = OUT_FC.split("\\")[-1]
    arcpy.management.CreateFeatureclass(
        out_path=GDB,
        out_name=out_name,
        geometry_type="POLYGON",
        spatial_reference=arcpy.Describe(SOURCE_FC).spatialReference,
    )

    # Add fields
    arcpy.management.AddField(OUT_FC, "APN", "TEXT", field_length=30)
    arcpy.management.AddField(OUT_FC, "APN_Original", "TEXT", field_length=30)
    arcpy.management.AddField(OUT_FC, "Missing_From", "TEXT", field_length=15)

    insert_fields = ["SHAPE@", "APN", "APN_Original", "Missing_From"]

    source_count = 0
    service_count = 0

    with arcpy.da.InsertCursor(OUT_FC, insert_fields) as ins:
        # SOURCE_ONLY — missing from service
        for norm_apn in source_only_keys:
            orig_apn, shape = source_norm[norm_apn]
            ins.insertRow([shape, norm_apn, orig_apn, "SERVICE"])
            source_count += 1

        # SERVICE_ONLY — missing from SOURCE_FC
        for norm_apn in service_only_keys:
            orig_apn, shape = service_norm[norm_apn]
            ins.insertRow([shape, norm_apn, orig_apn, "SOURCE_FC"])
            service_count += 1

    log(f"\nOutput FC: {OUT_FC}")
    log(f"  Missing from SERVICE: {source_count} parcels (in SOURCE_FC only)")
    log(f"  Missing from SOURCE_FC: {service_count} parcels (in service only)")
    log(f"  Total: {source_count + service_count}")
    log("Done. Open in ArcGIS Pro and symbolize by Missing_From field.")


if __name__ == "__main__":
    run()
