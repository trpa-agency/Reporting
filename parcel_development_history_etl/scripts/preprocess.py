"""
Residential Units ETL — Pre-processing orchestrator.

Runs source-FC diagnostics and correction before the main ETL, in order:

  Step P0 — Service comparison           (compare_source_to_service)
              Diagnose: APNs in SOURCE_FC but absent from the year-specific
              All Parcels service layer (FC_ONLY = review candidates) and
              APNs in the service but missing from the FC (SERVICE_ONLY).
              READ-ONLY — results flagged in QA_Source_vs_Service for review.
              Writes: QA_Source_vs_Service

  ── Working copy ──────────────────────────────────────────────────
              SOURCE_FC is copied → WORKING_FC after P0.
              All subsequent steps (P1–P3) operate on WORKING_FC only.
              SOURCE_FC (Parcel_History_Attributed) is never modified.

  Step P1 — Topology / integrity check  (check_parcel_topology)
              Diagnose: duplicate APN-Year rows, within-year parcel overlaps,
              area discontinuities for stable APNs.
              Writes: QA_Topo_DuplicateAPN, QA_Topo_Overlap, QA_Topo_AreaShift

  Step P2 — Deduplicate source FC        (deduplicate_source_fc)
              Fix: remove duplicate APN × Year rows identified in P1.
              Writes: QA_Duplicates_Removed

  Step P3 — Spatial genealogy            (build_spatial_genealogy)
              Build: year-over-year Identity analysis → apn_genealogy_spatial.csv
              Also detects: multi-hop chains, split area conservation issues.
              Writes: QA_Spatial_Genealogy, apn_genealogy_spatial.csv

Run from ArcGIS Pro Python:
  cd C:\\Users\\mbindl\\Documents\\GitHub\\Reporting\\parcel_development_history_etl
  C:\\...\\arcgispro-py3\\python.exe preprocess.py

Flags
-----
  --skip-p0        Skip service comparison (P0)
  --skip-p1        Skip topology check (P1)
  --skip-p2        Skip deduplication (P2)
  --skip-p3        Skip spatial genealogy build (P3)
  --only-p0        Run service comparison only (flag, no edits anywhere)
  --only-p1        Run topology check only (requires working copy to exist)
  --only-diagnose  Run P0 + P1 diagnostic steps only, no copy created
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))  # package root (config, utils)
sys.path.insert(0, str(Path(__file__).parent))      # scripts/ (sibling modules)

from utils import get_logger

log = get_logger("preprocess")


def _create_working_copy() -> None:
    """Copy SOURCE_FC → WORKING_FC.  Drops and recreates on every call."""
    import arcpy
    from config import SOURCE_FC, WORKING_FC, GDB
    log.info("-" * 60)
    log.info("Creating working copy of source FC ...")
    log.info("-" * 60)

    if arcpy.Exists(WORKING_FC):
        arcpy.management.Delete(WORKING_FC)

    # Compact GDB before copying — cleans up orphaned data from any prior
    # failed write operations that would otherwise corrupt the new copy.
    log.info("Compacting GDB ...")
    arcpy.management.Compact(GDB)

    out_name = WORKING_FC.split("\\")[-1]
    arcpy.conversion.FeatureClassToFeatureClass(SOURCE_FC, GDB, out_name)

    # Verify row count matches source exactly
    src_count  = int(arcpy.management.GetCount(SOURCE_FC).getOutput(0))
    copy_count = int(arcpy.management.GetCount(WORKING_FC).getOutput(0))
    if copy_count != src_count:
        arcpy.management.Delete(WORKING_FC)
        raise RuntimeError(
            f"Working copy row count mismatch: SOURCE_FC={src_count}, "
            f"WORKING_FC={copy_count}. Copy aborted — GDB may need manual repair."
        )
    log.info("Working copy verified: %s  (%d rows)", WORKING_FC, copy_count)


def _run_p0() -> None:
    log.info("-" * 60)
    log.info("Step P0 — Compare source FC to All Parcels service")
    log.info("-" * 60)
    import compare_source_to_service as p0
    p0.main()


def _run_p1() -> None:
    log.info("-" * 60)
    log.info("Step P1 — Topology / integrity check")
    log.info("-" * 60)
    import check_parcel_topology as p1
    p1.main()


def _run_p2() -> None:
    log.info("-" * 60)
    log.info("Step P2 — Deduplicate source FC")
    log.info("-" * 60)
    import deduplicate_source_fc as p2
    p2.main()


def _run_p3() -> None:
    log.info("-" * 60)
    log.info("Step P3 — Build spatial genealogy")
    log.info("-" * 60)
    import build_spatial_genealogy as p3
    p3.main()


def main(skip_p0: bool = False,
         skip_p1: bool = False,
         skip_p2: bool = False,
         skip_p3: bool = False,
         only_p0: bool = False,
         only_p1: bool = False,
         only_diagnose: bool = False) -> None:

    log.info("=" * 60)
    log.info("Residential Units ETL — Pre-processing")
    log.info("=" * 60)

    t0 = time.time()

    # ── Diagnostic-only shortcuts (no working copy created) ───────────────────
    if only_p0:
        log.info("--only-p0: service comparison only (no edits)")
        _run_p0()
        _finish(t0)
        return

    if only_diagnose:
        log.info("--only-diagnose: P0 + P1 flag-only (no working copy created)")
        _run_p0()
        _run_p1()
        _finish(t0)
        return

    # ── Full pre-processing sequence ──────────────────────────────────────────

    # P0 — compare original against service (flag only, no edits)
    if not skip_p0:
        _run_p0()
    else:
        log.info("Skipping Step P0 (--skip-p0)")

    # Working copy — created after P0 so comparison runs on the raw original
    _create_working_copy()

    # P1 — topology check on working copy
    if not skip_p1:
        _run_p1()
    else:
        log.info("Skipping Step P1 (--skip-p1)")

    # P2 — dedup working copy
    if not skip_p2:
        _run_p2()
    else:
        log.info("Skipping Step P2 (--skip-p2)")

    # P3 — spatial genealogy from working copy
    if not skip_p3:
        _run_p3()
    else:
        log.info("Skipping Step P3 (--skip-p3)")

    _finish(t0)


def _finish(t0: float) -> None:
    elapsed = time.time() - t0
    mins, secs = divmod(int(elapsed), 60)
    log.info("=" * 60)
    log.info("Pre-processing complete  (%dm %02ds)", mins, secs)
    log.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Residential Units ETL — Pre-processing")
    parser.add_argument("--skip-p0", action="store_true",
                        help="Skip Step P0 (service comparison)")
    parser.add_argument("--skip-p1", action="store_true",
                        help="Skip Step P1 (topology check)")
    parser.add_argument("--skip-p2", action="store_true",
                        help="Skip Step P2 (deduplicate source FC)")
    parser.add_argument("--skip-p3", action="store_true",
                        help="Skip Step P3 (spatial genealogy build)")
    parser.add_argument("--only-p0", action="store_true",
                        help="Run service comparison only")
    parser.add_argument("--only-p1", action="store_true",
                        help="Run topology check only (no edits to source FC)")
    parser.add_argument("--only-diagnose", action="store_true",
                        help="Run P0 + P1 diagnostics only (no edits to source FC)")
    args = parser.parse_args()

    main(skip_p0=args.skip_p0,
         skip_p1=args.skip_p1,
         skip_p2=args.skip_p2,
         skip_p3=args.skip_p3,
         only_p0=args.only_p0,
         only_p1=args.only_p1,
         only_diagnose=args.only_diagnose)
