"""
Diagnostic: classify every PARCEL_NEW APN from QA_Lost_APNs.

For each APN the CSV knows about but that was never found in the FC,
determine which scenario explains the balanced totals:

  A — Genealogy absorbed it:
      The APN appears as a *successor* in the genealogy master. Its units
      were written to the predecessor's row. The "new" APN never gets its
      own FC row because the ETL only creates rows for APNs that have
      geometry. But units are counted via the predecessor.

  B — Row exists in FC, null geometry:
      An FC row exists for this APN but SHAPE@ is None. Units are in the
      totals (FC_Total still matches CSV_Total) but the parcel can't be
      spatially attributed. Spatially invisible in all geographic breakdowns.

  C — Row exists in FC, has geometry, has units:
      The QA_Lost_APNs detection had a false positive (e.g. APN format
      difference between the CSV and FC that genealogy resolved but the
      QA table didn't account for).

  D — Row missing from FC entirely:
      No row in OUTPUT_FC at all. If totals still balance, units must be
      carried by a predecessor under genealogy. If totals DON'T balance
      for that year, this is a true data gap.

Output: printed table + CSV written to QA_DATA_DIR.

Usage
-----
    & "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" `
        parcel_development_history_etl/scripts/diagnose_parcel_new.py
"""
import csv
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))

import arcpy

from config import (
    OUTPUT_FC, FC_APN, FC_YEAR, FC_UNITS,
    QA_DATA_DIR, QA_LOST_APNS,
    GENEALOGY_TAHOE, CSV_YEARS,
)
from utils import get_logger

log = get_logger("diagnose_parcel_new")


def _load_parcel_new() -> list[dict]:
    """Read PARCEL_NEW rows from QA_Lost_APNs GDB table."""
    rows = []
    with arcpy.da.SearchCursor(
            QA_LOST_APNS,
            [FC_APN, 'Years_Lost', 'Total_Units_CSV', 'Issue_Category']) as cur:
        for apn, years_lost, units, cat in cur:
            if cat == 'PARCEL_NEW':
                rows.append({
                    'APN': str(apn).strip(),
                    'Years_Lost': years_lost,
                    'CSV_Units': int(units) if units else 0,
                })
    rows.sort(key=lambda r: -r['CSV_Units'])
    log.info("PARCEL_NEW APNs to diagnose: %d", len(rows))
    return rows


def _load_genealogy_successors() -> set[str]:
    """Return the set of APNs that appear as *successors* in the genealogy table."""
    import pathlib, csv as csv_mod
    p = pathlib.Path(GENEALOGY_TAHOE)
    if not p.exists():
        log.warning("Genealogy file not found: %s", p)
        return set()
    successors = set()
    with open(p, newline='', encoding='utf-8-sig') as f:
        for row in csv_mod.DictReader(f):
            val = row.get('apn_new', '').strip()
            if val:
                successors.add(val)
    log.info("Genealogy successors loaded: %d", len(successors))
    return successors


def _scan_fc(apns: set[str]) -> dict[str, dict]:
    """
    For each APN in apns, collect all FC rows:
      has_row        — bool, any row found
      has_geom       — bool, at least one row has non-null geometry
      fc_units_total — sum of Residential_Units across all years
      years_in_fc    — sorted list of years present
    """
    result = {apn: {'has_row': False, 'has_geom': False,
                    'fc_units_total': 0, 'years_in_fc': []}
              for apn in apns}

    yr_list = ', '.join(str(y) for y in CSV_YEARS)
    with arcpy.da.SearchCursor(
            OUTPUT_FC, [FC_APN, FC_YEAR, FC_UNITS, 'SHAPE@'],
            f"{FC_YEAR} IN ({yr_list})") as cur:
        for apn_raw, year, units, shape in cur:
            apn = str(apn_raw).strip() if apn_raw else None
            if apn not in result:
                continue
            r = result[apn]
            r['has_row'] = True
            if shape is not None:
                r['has_geom'] = True
            r['fc_units_total'] += int(units) if units else 0
            r['years_in_fc'].append(year)

    return result


def classify(has_row, has_geom, fc_units, csv_units, is_successor) -> tuple[str, str]:
    """Return (scenario_code, explanation)."""
    if has_row and has_geom and fc_units > 0:
        return 'C', 'Row in FC with geometry and units — QA false positive (format mismatch resolved by genealogy?)'
    if has_row and not has_geom:
        return 'B', 'Row in FC but null geometry — units in totals but spatially invisible'
    if has_row and has_geom and fc_units == 0:
        return 'B*', 'Row in FC with geometry but 0 units — check ETL unit-write logic'
    # no row
    if is_successor:
        return 'A', 'No FC row; APN appears as genealogy successor — units carried by predecessor APN'
    return 'D', 'No FC row and not in genealogy — true data gap; verify CSV APN format and AllParcels service'


def run() -> None:
    log.info("=== diagnose_parcel_new ===")

    pn_rows   = _load_parcel_new()
    pn_apns   = {r['APN'] for r in pn_rows}
    successors = _load_genealogy_successors()
    fc_data   = _scan_fc(pn_apns)

    results = []
    counts = {'A': 0, 'B': 0, 'B*': 0, 'C': 0, 'D': 0}

    for r in pn_rows:
        apn      = r['APN']
        fd       = fc_data[apn]
        is_succ  = apn in successors
        scenario, explanation = classify(
            fd['has_row'], fd['has_geom'], fd['fc_units_total'],
            r['CSV_Units'], is_succ)
        counts[scenario] = counts.get(scenario, 0) + 1
        results.append({
            'APN':           apn,
            'CSV_Units':     r['CSV_Units'],
            'Scenario':      scenario,
            'Has_FC_Row':    fd['has_row'],
            'Has_Geometry':  fd['has_geom'],
            'FC_Units':      fd['fc_units_total'],
            'In_Genealogy':  is_succ,
            'Explanation':   explanation,
        })

    # ── Print summary ──────────────────────────────────────────────────────
    print()
    print('=' * 72)
    print('  PARCEL_NEW DIAGNOSTIC RESULTS')
    print('=' * 72)
    print(f'  {"Scenario":<6}  {"Count":>5}  Description')
    print(f'  {"-"*6}  {"-"*5}  {"-"*50}')
    descs = {
        'A':  'Genealogy absorbed — units in totals under predecessor APN',
        'B':  'Null geometry — units in totals but spatially invisible',
        'B*': 'Has geometry but 0 units — ETL logic issue',
        'C':  'QA false positive — APN is in FC with units',
        'D':  'True gap — no FC row, not in genealogy',
    }
    for sc, desc in descs.items():
        if counts.get(sc, 0):
            print(f'  {sc:<6}  {counts[sc]:>5}  {desc}')
    print()

    print(f'  {"APN":<25} {"CSV_U":>5}  {"FC_U":>5}  {"Scen":<4}  Explanation')
    print(f'  {"-"*25} {"-"*5}  {"-"*5}  {"-"*4}  {"-"*50}')
    for row in results:
        print(f'  {row["APN"]:<25} {row["CSV_Units"]:>5}  {row["FC_Units"]:>5}  '
              f'{row["Scenario"]:<4}  {row["Explanation"]}')

    # ── Write CSV ──────────────────────────────────────────────────────────
    import pathlib
    out_path = pathlib.Path(QA_DATA_DIR) / 'diagnose_parcel_new.csv'
    with open(out_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    log.info("CSV written: %s", out_path)
    print(f'\n  CSV: {out_path}')


if __name__ == '__main__':
    run()
