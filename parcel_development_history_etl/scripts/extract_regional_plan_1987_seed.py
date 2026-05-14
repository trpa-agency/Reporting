"""
extract_regional_plan_1987_seed.py - Pull the frozen 1987 Regional Plan
baseline out of regional_plan_allocations.json into a clean, normalized,
long-format CSV.

Why this exists
---------------
The 1987-era figures are NOT in Corral / LT Info - they predate the
transaction-tracking system, so no live query can produce them. They have to
live as a hard-coded reference: the `RegionalPlanCapacity` seed described in
`erd/regional_plan_allocations_service.md`. This script produces that seed.

The 2012-era half is deliberately NOT here - it comes live from the LT Info
`GetDevelopmentRightPoolBalanceReport` web service.

Input:  data/processed_data/regional_plan_allocations.json
        (run convert_regional_plan_allocations.py first)
Output: data/processed_data/regional_plan_1987_baseline.csv

Output schema (long / tidy format)
----------------------------------
  commodity  RES / RBU / CFA / TAU
  area       jurisdiction or pool name
  plan_era   always "1987" (forward-compatible: 2012-era rows would append
             here with the same shape once the live source is wired)
  metric     regional_plan_maximum / not_assigned / assigned_to_projects
             Residential carries all three; RBU/CFA/TAU carry only the
             maximum - the analyst's source does not split their assigned /
             not-assigned status by plan era.
  value      integer

Run:
    PYTHONIOENCODING=utf-8 \\
    "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" \\
    parcel_development_history_etl/scripts/extract_regional_plan_1987_seed.py
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import REGIONAL_PLAN_ALLOCATIONS_JSON, REGIONAL_PLAN_1987_BASELINE_CSV
from utils import get_logger

log = get_logger("extract_regional_plan_1987_seed")

# json key -> short commodity code for the by_plan_era commodity sheets
COMMODITY_KEYS = {
    "residential_bonus_units":     "RBU",
    "commercial_floor_area":       "CFA",
    "tourist_accommodation_units": "TAU",
}
RES_METRICS = ("regional_plan_maximum", "not_assigned", "assigned_to_projects")


def main() -> None:
    src = Path(REGIONAL_PLAN_ALLOCATIONS_JSON)
    dst = Path(REGIONAL_PLAN_1987_BASELINE_CSV)
    if not src.exists():
        raise SystemExit(
            f"{src} not found - run convert_regional_plan_allocations.py first"
        )

    data = json.loads(src.read_text(encoding="utf-8"))
    rows = []  # (commodity, area, plan_era, metric, value)

    # Residential: the analyst's file carries the full status triple per
    # jurisdiction, split by plan era - take the plan_1987 slice.
    for j in data["residential"]["by_jurisdiction"]:
        era = j.get("plan_1987") or {}
        for metric in RES_METRICS:
            v = era.get(metric)
            if v is not None:
                rows.append(("RES", j["name"], "1987", metric, v))

    # RBU / CFA / TAU: the source only splits the *maximum* by plan era,
    # so only regional_plan_maximum has a 1987 value.
    for json_key, code in COMMODITY_KEYS.items():
        for pool in data[json_key]["by_plan_era"]["by_pool"]:
            v = pool.get("plan_1987")
            if v is not None:   # skip purely-2012 rows (e.g. "Unreleased CFA from 2012 Plan")
                rows.append((code, pool["name"], "1987", "regional_plan_maximum", v))

    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["commodity", "area", "plan_era", "metric", "value"])
        w.writerows(rows)

    log.info("Wrote %s (%d rows)", dst, len(rows))
    by_commodity = Counter(r[0] for r in rows)
    for code, n in sorted(by_commodity.items()):
        log.info("  %-4s %d rows", code, n)
    # quick cross-check: residential 1987 maxima should total 6,087
    res_max = sum(r[4] for r in rows
                  if r[0] == "RES" and r[3] == "regional_plan_maximum")
    log.info("  RES regional_plan_maximum total: %d (expect 6,087)", res_max)


if __name__ == "__main__":
    main()
