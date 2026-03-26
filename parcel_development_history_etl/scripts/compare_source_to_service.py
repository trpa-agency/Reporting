"""
compare_source_to_service.py — Compare Parcel_History_Attributed against
the All Parcels MapServer service layers, one per year in scope.

READ-ONLY — this script never modifies SOURCE_FC or any feature class.
Results are written to a GDB QA table for analyst review.

For each year the script reports:

  FC_ONLY       APN present in SOURCE_FC for year Y, absent from the
                year-Y service layer.  Review candidates — may be rows
                incorrectly assigned to this year during a FC refresh,
                carried-forward retired parcels, or geometry artifacts.

  SERVICE_ONLY  APN present in the year-Y service layer, absent from
                SOURCE_FC.  Gaps that the ETL crosswalk (s03) must
                resolve; reported here for visibility.

El Dorado note
--------------
El Dorado County changed APN suffix padding in 2018 (2-digit → 3-digit).
Pre-2018 rows with 3-digit El Dorado APNs would appear as false FC_ONLY
against the service's 2-digit form.  Suffixes are normalised before
comparison to suppress these.

Run:
  python compare_source_to_service.py

Writes:
  QA_Source_vs_Service  columns: Year, APN, Category (FC_ONLY | SERVICE_ONLY), OID
"""

import sys
import re
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import arcpy

from config import (
    SOURCE_FC, FC_APN, FC_YEAR, CSV_YEARS, GDB,
    ALLPARCELS_URL, YEAR_LAYER,
    QA_SOURCE_VS_SERVICE,
)

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("compare_source_to_service")


# ── El Dorado APN normalisation ───────────────────────────────────────────────

_EL_RE = re.compile(r'^(\d{3}-\d{3}-)0(\d{2})$')


def _norm(apn: str) -> str:
    """Strip leading zero from El Dorado 3-digit suffix so 083-030-022 == 083-030-22."""
    m = _EL_RE.match(apn)
    return f"{m.group(1)}{m.group(2)}" if m else apn


# ── Service layer reader ──────────────────────────────────────────────────────

def _service_apns(year: int) -> set[str]:
    """
    Fetch normalised APN set from the All Parcels MapServer layer for *year*.
    Returns empty set if the layer is unavailable.
    """
    layer_idx = YEAR_LAYER.get(year)
    if layer_idx is None:
        log.warning("No YEAR_LAYER entry for %d — skipping service query", year)
        return set()

    url = f"{ALLPARCELS_URL}/{layer_idx}"
    lyr = f"svc_{year}"
    if arcpy.Exists(lyr):
        arcpy.management.Delete(lyr)

    try:
        arcpy.management.MakeFeatureLayer(url, lyr)
    except Exception as exc:
        log.error("Cannot connect to service layer for %d: %s", year, exc)
        return set()

    field_map = {f.name.upper(): f.name for f in arcpy.ListFields(lyr)}
    apn_fld   = field_map.get(FC_APN.upper())
    if not apn_fld:
        log.error("APN field '%s' not found in year-%d service layer. "
                  "Available: %s", FC_APN, year, sorted(field_map.values()))
        arcpy.management.Delete(lyr)
        return set()

    apns = set()
    with arcpy.da.SearchCursor(lyr, [apn_fld]) as cur:
        for (apn,) in cur:
            if apn:
                apns.add(_norm(str(apn).strip()))

    arcpy.management.Delete(lyr)
    return apns


# ── Source FC reader ──────────────────────────────────────────────────────────

def _source_apns(year: int) -> dict[str, list[int]]:
    """Return {normalised_APN: [OID, ...]} for all SOURCE_FC rows for *year*."""
    result: dict[str, list[int]] = defaultdict(list)
    where = f"{FC_YEAR} = {year}"
    with arcpy.da.SearchCursor(SOURCE_FC, ["OID@", FC_APN], where) as cur:
        for oid, apn in cur:
            if apn:
                result[_norm(str(apn).strip())].append(oid)
    return dict(result)


# ── Year-by-year comparison ───────────────────────────────────────────────────

def compare_all_years(years: list[int]) -> list[dict]:
    """
    Returns combined list of {Year, APN, OID, Category} rows.
    FC_ONLY rows include OIDs; SERVICE_ONLY rows have OID=None.
    """
    all_rows: list[dict] = []

    for year in years:
        t_yr    = time.time()
        log.info("  Year %d ...", year)

        svc_set = _service_apns(year)
        src_map = _source_apns(year)
        src_set = set(src_map.keys())

        in_fc_only      = src_set - svc_set
        in_service_only = svc_set - src_set

        for apn in sorted(in_fc_only):
            for oid in src_map[apn]:
                all_rows.append({
                    "Year"    : year,
                    "APN"     : apn,
                    "OID"     : oid,
                    "Category": "FC_ONLY",
                })

        for apn in sorted(in_service_only):
            all_rows.append({
                "Year"    : year,
                "APN"     : apn,
                "OID"     : None,
                "Category": "SERVICE_ONLY",
            })

        log.info("    FC_ONLY: %4d  |  SERVICE_ONLY: %4d  |  Matched: %d  (%.1fs)",
                 len(in_fc_only), len(in_service_only),
                 len(src_set & svc_set),
                 time.time() - t_yr)

    return all_rows


# ── QA table writer ───────────────────────────────────────────────────────────

def _write_qa_table(rows: list[dict]) -> None:
    if arcpy.Exists(QA_SOURCE_VS_SERVICE):
        arcpy.management.Delete(QA_SOURCE_VS_SERVICE)
    tname = QA_SOURCE_VS_SERVICE.split("\\")[-1]
    arcpy.management.CreateTable(GDB, tname)
    arcpy.management.AddField(QA_SOURCE_VS_SERVICE, "Year",     "LONG")
    arcpy.management.AddField(QA_SOURCE_VS_SERVICE, "APN",      "TEXT", field_length=50)
    arcpy.management.AddField(QA_SOURCE_VS_SERVICE, "Category", "TEXT", field_length=15)
    arcpy.management.AddField(QA_SOURCE_VS_SERVICE, "OID",      "LONG")

    with arcpy.da.InsertCursor(
            QA_SOURCE_VS_SERVICE, ["Year", "APN", "Category", "OID"]) as ic:
        for r in rows:
            ic.insertRow([r["Year"], r["APN"], r["Category"], r.get("OID")])

    log.info("Written %d rows → %s", len(rows), QA_SOURCE_VS_SERVICE)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    t0    = time.time()
    years = sorted(CSV_YEARS)

    log.info("=== compare_source_to_service.py (diagnostic only) ===")
    log.info("Source FC : %s", SOURCE_FC)
    log.info("Service   : %s", ALLPARCELS_URL)
    log.info("Years     : %d – %d  (%d years)", years[0], years[-1], len(years))
    log.info("")

    all_rows = compare_all_years(years)

    fc_only      = [r for r in all_rows if r["Category"] == "FC_ONLY"]
    service_only = [r for r in all_rows if r["Category"] == "SERVICE_ONLY"]

    log.info("")
    log.info("=== Summary ===")
    log.info("  FC_ONLY      : %d rows (%d unique APNs) — review QA_Source_vs_Service",
             len(fc_only), len({r["APN"] for r in fc_only}))
    log.info("  SERVICE_ONLY : %d rows (%d unique APNs)",
             len(service_only), len({r["APN"] for r in service_only}))

    _write_qa_table(all_rows)

    elapsed = time.time() - t0
    mins, secs = divmod(int(elapsed), 60)
    log.info("Done.  (%dm %02ds)", mins, secs)


if __name__ == "__main__":
    main()
