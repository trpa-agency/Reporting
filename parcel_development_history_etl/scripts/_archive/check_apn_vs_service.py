"""
check_apn_vs_service.py — Standalone preliminary QA script.

For each year (2012–2025), compares the APN set in Parcel_History_Attributed
against the corresponding AllParcels MapServer year layer.  Reports two error types:

  IN_FC_NOT_IN_SERVICE  — APN present in the source FC for that year but missing
                          from the AllParcels service layer for that year.
                          Suggests a phantom row in the FC (wrong year attribution,
                          retired parcel still in the dataset, or FC copy error).

  IN_SERVICE_NOT_IN_FC  — APN present in the AllParcels service for that year but
                          absent from the source FC.
                          Suggests the FC is missing parcels for that year
                          (source dataset not fully refreshed).

Output: GDB table QA_APN_Vs_Service with columns:
  APN, YEAR, ERROR_TYPE

Run from ArcGIS Pro Python:
  & "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" `
    "C:/Users/mbindl/Documents/GitHub/Reporting/parcel_development_history_etl/check_apn_vs_service.py"
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import arcpy

from config import (
    SOURCE_FC, GDB,
    FC_APN, FC_YEAR,
    ALLPARCELS_URL, YEAR_LAYER, CSV_YEARS,
)

# ── Config ────────────────────────────────────────────────────────────────────
# Field name for APN in the AllParcels service layers
# (assumed same as FC_APN — change here if the service uses a different field)
SVC_APN_FIELD  = "APN"
OUTPUT_TABLE   = GDB + r"\QA_APN_Vs_Service"

# ── Logging ───────────────────────────────────────────────────────────────────
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("check_apn_vs_service")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_fc_apns_by_year() -> dict[int, set]:
    """
    Read Parcel_History_Attributed and return {year: set(APN)} for all years
    in CSV_YEARS.  One full pass over the source FC.
    """
    log.info("Reading APNs from source FC (%s) ...", SOURCE_FC)
    result: dict[int, set] = {yr: set() for yr in CSV_YEARS}
    yr_set = set(CSV_YEARS)

    with arcpy.da.SearchCursor(SOURCE_FC, [FC_APN, FC_YEAR]) as cur:
        for apn, yr in cur:
            if yr and int(yr) in yr_set and apn:
                result[int(yr)].add(str(apn).strip())

    for yr in CSV_YEARS:
        log.info("  FC %d : %d APNs", yr, len(result[yr]))
    return result


def _read_service_apns(year: int, layer_idx: int) -> set:
    """
    Fetch all APNs from the AllParcels MapServer layer for the given year.
    Returns a set of APN strings.
    """
    url = f"{ALLPARCELS_URL}/{layer_idx}"
    lyr = f"apn_check_lyr_{year}"
    if arcpy.Exists(lyr):
        arcpy.management.Delete(lyr)

    apns = set()
    try:
        arcpy.management.MakeFeatureLayer(url, lyr)
        with arcpy.da.SearchCursor(lyr, [SVC_APN_FIELD]) as cur:
            for (apn,) in cur:
                if apn:
                    apns.add(str(apn).strip())
    except Exception as exc:
        log.error("  Failed to read service layer %d (year %d): %s",
                  layer_idx, year, exc)
    finally:
        if arcpy.Exists(lyr):
            arcpy.management.Delete(lyr)

    return apns


def _write_output(rows: list[dict]) -> None:
    """Write error rows to the output GDB table."""
    if arcpy.Exists(OUTPUT_TABLE):
        arcpy.management.Delete(OUTPUT_TABLE)

    arcpy.management.CreateTable(GDB, "QA_APN_Vs_Service")
    arcpy.management.AddField(OUTPUT_TABLE, "APN",        "TEXT", field_length=50)
    arcpy.management.AddField(OUTPUT_TABLE, "YEAR",       "LONG")
    arcpy.management.AddField(OUTPUT_TABLE, "ERROR_TYPE", "TEXT", field_length=30)

    with arcpy.da.InsertCursor(OUTPUT_TABLE, ["APN", "YEAR", "ERROR_TYPE"]) as ic:
        for r in rows:
            ic.insertRow([r["APN"], r["YEAR"], r["ERROR_TYPE"]])

    log.info("Written %d rows → %s", len(rows), OUTPUT_TABLE)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    log.info("=== check_apn_vs_service.py ===")
    log.info("Source FC : %s", SOURCE_FC)
    log.info("Service   : %s", ALLPARCELS_URL)
    log.info("Years     : %s", CSV_YEARS)

    fc_by_year = _read_fc_apns_by_year()

    all_errors: list[dict] = []

    summary_rows = []

    for year in sorted(CSV_YEARS):
        layer_idx = YEAR_LAYER.get(year)
        if layer_idx is None:
            log.warning("No YEAR_LAYER entry for %d — skipping", year)
            continue

        log.info("Year %d  (layer %d) ...", year, layer_idx)
        svc_apns = _read_service_apns(year, layer_idx)
        fc_apns  = fc_by_year[year]

        log.info("  Service APNs : %d", len(svc_apns))
        log.info("  FC APNs      : %d", len(fc_apns))

        if len(svc_apns) == 0:
            log.warning("  Service returned 0 APNs for %d — layer may not exist yet. Skipping.", year)
            continue

        in_fc_not_svc = fc_apns  - svc_apns
        in_svc_not_fc = svc_apns - fc_apns

        log.info("  IN_FC_NOT_IN_SERVICE : %d", len(in_fc_not_svc))
        log.info("  IN_SERVICE_NOT_IN_FC : %d", len(in_svc_not_fc))

        for apn in sorted(in_fc_not_svc):
            all_errors.append({"APN": apn, "YEAR": year,
                                "ERROR_TYPE": "IN_FC_NOT_IN_SERVICE"})
        for apn in sorted(in_svc_not_fc):
            all_errors.append({"APN": apn, "YEAR": year,
                                "ERROR_TYPE": "IN_SERVICE_NOT_IN_FC"})

        summary_rows.append({
            "year": year,
            "fc": len(fc_apns),
            "svc": len(svc_apns),
            "in_fc_not_svc": len(in_fc_not_svc),
            "in_svc_not_fc": len(in_svc_not_fc),
        })

    # ── Summary ───────────────────────────────────────────────────────────────
    log.info("")
    log.info("=== Summary ===")
    log.info("  %-6s  %-8s  %-8s  %-20s  %-20s",
             "Year", "FC_APNs", "Svc_APNs",
             "In_FC_Not_Service", "In_Service_Not_FC")
    for r in summary_rows:
        log.info("  %-6d  %-8d  %-8d  %-20d  %-20d",
                 r["year"], r["fc"], r["svc"],
                 r["in_fc_not_svc"], r["in_svc_not_fc"])

    total_fc_only  = sum(r["in_fc_not_svc"] for r in summary_rows)
    total_svc_only = sum(r["in_svc_not_fc"] for r in summary_rows)
    log.info("")
    log.info("  Total IN_FC_NOT_IN_SERVICE : %d rows", total_fc_only)
    log.info("  Total IN_SERVICE_NOT_IN_FC : %d rows", total_svc_only)
    log.info("  Total error rows           : %d", len(all_errors))

    _write_output(all_errors)

    elapsed = time.time() - t0
    mins, secs = divmod(int(elapsed), 60)
    log.info("Done.  (%dm %02ds)", mins, secs)


if __name__ == "__main__":
    main()
