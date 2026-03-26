"""
Development History ETL — main orchestrator.

Usage (ArcGIS Pro Python):
  cd C:\\Users\\mbindl\\Documents\\GitHub\\Reporting\\parcel_development_history_etl
  C:\\...\\arcgispro-py3\\python.exe main.py

Flags
-----
--skip-s01   Skip FC copy (use if output FC already exists and is current)
--skip-s05   Skip spatial attribute updates (slow; skip for unit-only runs)
--only-qa    Only run Step 6 QA (output FC must already exist and be updated)

Steps
-----
S1   Build output FC from All Parcels service (2012-2024) + SOURCE_FC (2025)
S1c  Populate COUNTY + JURISDICTION via spatial join (needed for El Dorado fix)
S2   Load residential CSV + El Dorado fix + genealogy (s02b)
S3   APN crosswalk (spatial join for missing APNs)
S4   Write Residential_Units
S4b  Write TouristAccommodation_Units + CommercialFloorArea_SqFt
S5   Spatial attribute updates (slow)
S6   QA tables
"""
import argparse
import sys
import time
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from utils import get_logger

log = get_logger("main")


def main(skip_s01: bool = False,
         skip_s05: bool = False,
         only_qa: bool  = False) -> None:

    log.info("=" * 60)
    log.info("Development History ETL — starting")
    log.info("=" * 60)

    t0 = time.time()

    if only_qa:
        log.info("--only-qa flag set: running Step 6 only")
        from steps import s02_load_csv as s02
        from steps import s06_qa       as s06
        df_csv, _ = s02.run()
        s06.run(df_csv)
        _finish(t0)
        return

    # Step 1 — Prepare output feature class
    if not skip_s01:
        from steps import s01_prepare_fc as s01
        s01.run()
    else:
        log.info("Skipping Step 1 (--skip-s01)")

    # Step 1c — Populate COUNTY + JURISDICTION via spatial join
    from steps import s01c_populate_jurisdiction as s01c
    s01c.run()

    # Step 2 — Load CSV + El Dorado fix  →  df_csv, csv_lookup
    from steps import s02_load_csv as s02
    df_csv, csv_lookup = s02.run()

    # Step 3 — APN crosswalk  →  extends csv_lookup
    from steps import s03_crosswalk as s03
    csv_lookup = s03.run(df_csv, csv_lookup)

    # Step 4 — Write Residential_Units to output FC
    from steps import s04_update_units as s04
    s04.run(csv_lookup)

    # Step 4b — Write TouristAccommodation_Units + CommercialFloorArea_SqFt
    from steps import s04b_update_tourist_commercial as s04b
    s04b.run()

    # Step 5 — Spatial attribute updates
    if not skip_s05:
        from steps import s05_spatial_attrs as s05
        s05.run()
    else:
        log.info("Skipping Step 5 (--skip-s05)")

    # Step 6 — QA → GDB tables
    from steps import s06_qa as s06
    s06.run(df_csv)

    _finish(t0)


def _finish(t0: float) -> None:
    elapsed = time.time() - t0
    mins, secs = divmod(int(elapsed), 60)
    log.info("=" * 60)
    log.info("ETL complete  (%dm %02ds)", mins, secs)
    log.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Residential Units ETL")
    parser.add_argument("--skip-s01", action="store_true",
                        help="Skip Step 1 (FC copy)")
    parser.add_argument("--skip-s05", action="store_true",
                        help="Skip Step 5 (spatial attributes)")
    parser.add_argument("--only-qa",  action="store_true",
                        help="Run Step 6 QA only")
    args = parser.parse_args()

    main(skip_s01=args.skip_s01,
         skip_s05=args.skip_s05,
         only_qa=args.only_qa)
