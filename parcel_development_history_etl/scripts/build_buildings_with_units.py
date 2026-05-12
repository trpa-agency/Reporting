"""
build_buildings_with_units.py — Associate residential units with individual
building footprints by splitting each parcel's units across its buildings,
weighted by building square footage.

Inputs (both already produced by earlier scripts):
  - buildings_inventory_2025.csv      (one row per Buildings_2019 footprint)
  - residential_units_inventory_2025.csv (one row per current residential unit)

Output: data/processed_data/buildings_with_units.json
  {
    "meta": {
      "total_buildings": N,
      "buildings_with_units": N,
      "total_units_assigned": N,
      "single_unit_buildings": N,
      "multi_unit_buildings": N,
      "max_units_on_one_building": N,
      "generated_at": "..."
    },
    "buildings": [
      {
        "id": <int OBJECTID>,
        "apn": "<canonical>",
        "year": <int>,            // year_built (may be null)
        "sqft": <float>,          // Square_Feet
        "era": "Pre-1987 Plan" | "1987 Plan" | "2012 Plan" | "Unknown",
        "units_assigned": <int>   // sqft-weighted split of parcel units
      },
      ...
    ],
    "by_year_era": [              // cumulative + per-year additions
      { "year": 1900, "n_pre87": 0, "n_p87": 0, "n_p12": 0,
                       "cum_pre87": 0, "cum_p87": 0, "cum_p12": 0,
                       "buildings_pre87": 0, "buildings_p87": 0,
                       "buildings_p12": 0,
                       "cum_buildings_pre87": 0, ... },
      ...
    ]
  }

Splitting logic
---------------
For each parcel with units U and buildings B (with sqft s_1..s_B):
  - If only 1 building: it gets all U units.
  - If multiple buildings: distribute U units in proportion to sqft, rounded
    to integers via the largest-remainder method so the sum stays exactly U.
  - Edge case: if a building has 0 sqft, it gets 0 units unless that's the
    only building on the parcel.

Era follows the residential units inventory: parcel-level Era based on
Original_Year_Built (Pre-1987 / 1987 Plan / 2012 Plan / Unknown). Buildings
on parcels with no residential units get era from their OWN Original_Year_Built
in the buildings inventory (these have units_assigned=0).

Run with ArcGIS Pro Python:
    PYTHONIOENCODING=utf-8 \\
    "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" \\
    parcel_development_history_etl/scripts/build_buildings_with_units.py
"""
import json
import math
import sys
import datetime as _dt
from pathlib import Path

# Make the parent package importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from config import (
    BUILDINGS_INVENTORY_CSV,
    BUILDINGS_WITH_UNITS_JSON,
)
from utils import get_logger

log = get_logger("build_buildings_with_units")

MIN_YEAR = 1900
MAX_YEAR = 2025


def era_from_year(y) -> str:
    if pd.isna(y):
        return "Unknown"
    try:
        y = int(y)
    except (TypeError, ValueError):
        return "Unknown"
    if y <= 1987:
        return "Pre-1987 Plan"
    if y <= 2011:
        return "1987 Plan"
    return "2012 Plan"


def largest_remainder_split(total: int, weights: list[float]) -> list[int]:
    """
    Distribute *total* integer units across len(weights) buckets in proportion
    to *weights*, ensuring the sum equals *total* exactly. Uses Hamilton's
    largest-remainder method.
    """
    if total <= 0 or not weights:
        return [0] * len(weights)
    s = sum(weights)
    if s <= 0:
        # No sqft anywhere — fall back to even split
        even = [total // len(weights)] * len(weights)
        for i in range(total - sum(even)):
            even[i] += 1
        return even
    raw = [total * (w / s) for w in weights]
    floor = [math.floor(r) for r in raw]
    remainders = [r - f for r, f in zip(raw, floor)]
    leftover = total - sum(floor)
    # Hand the leftover to the largest remainders
    order = sorted(range(len(weights)), key=lambda i: -remainders[i])
    for i in order[:leftover]:
        floor[i] += 1
    return floor


def main() -> None:
    log.info("=" * 70)
    log.info("BUILD BUILDINGS_WITH_UNITS")
    log.info("=" * 70)

    # Single source: the buildings inventory. It already carries the parcel's
    # Residential_Units total (from PDH) and Original_Year_Built (from
    # COMBINED_YEAR_BUILT), so we don't need the units inventory here.
    # Avoids a circular dependency where the units inventory consumes this
    # script's JSON output for its Building_ID assignment.
    log.info("Loading buildings: %s", BUILDINGS_INVENTORY_CSV)
    bldgs = pd.read_csv(BUILDINGS_INVENTORY_CSV,
                        dtype={"APN": str, "APN_canon": str})
    bldgs["Square_Feet"] = pd.to_numeric(bldgs["Square_Feet"],
                                         errors="coerce").fillna(0)
    bldgs["Original_Year_Built"] = pd.to_numeric(
        bldgs["Original_Year_Built"], errors="coerce").astype("Int64")
    bldgs["Residential_Units"] = pd.to_numeric(
        bldgs["Residential_Units"], errors="coerce").fillna(0).astype(int)
    log.info("  %d buildings loaded", len(bldgs))

    # Derive per-APN aggregates from the buildings inventory: parcel unit
    # total, parcel-level year built, era.
    apn_units: dict = {}
    for apn_canon, g in bldgs.groupby("APN_canon", sort=False):
        first = g.iloc[0]
        n_units = int(first["Residential_Units"])
        if n_units <= 0:
            continue
        year = first["Original_Year_Built"]
        apn_units[apn_canon] = {
            "n_units":    n_units,
            "year_built": year if pd.notna(year) else None,
            "era":        era_from_year(year),
        }
    log.info("  %d residential parcels with at least one building footprint", len(apn_units))

    # For each parcel with units, split across its buildings by sqft
    # We need buildings grouped by APN_canon
    bldgs_by_apn = bldgs.groupby("APN_canon", sort=False)
    bldg_units: dict[int, int] = {}  # Building_ID → units assigned

    for apn_canon, group in bldgs_by_apn:
        if apn_canon not in apn_units:
            continue
        u = int(apn_units[apn_canon]["n_units"])
        sqfts = group["Square_Feet"].fillna(0).tolist()
        bids = group["Building_ID"].tolist()
        split = largest_remainder_split(u, sqfts)
        for bid, units_for_this_bldg in zip(bids, split):
            bldg_units[int(bid)] = units_for_this_bldg

    log.info("  %d buildings assigned at least 1 unit",
             sum(1 for v in bldg_units.values() if v > 0))

    # Build the per-building list
    buildings_out = []
    for r in bldgs.itertuples(index=False):
        bid = int(r.Building_ID)
        # Year: prefer parcel's year if parcel has units, else building's own
        parcel_info = apn_units.get(r.APN_canon)
        if parcel_info and pd.notna(parcel_info["year_built"]):
            year = int(parcel_info["year_built"])
            era = parcel_info["era"]
        elif pd.notna(r.Original_Year_Built):
            year = int(r.Original_Year_Built)
            era = era_from_year(year)
        else:
            year = None
            era = "Unknown"
        buildings_out.append({
            "id":             bid,
            "apn":            r.APN_canon if isinstance(r.APN_canon, str) else None,
            "year":           year,
            "sqft":           round(float(r.Square_Feet or 0), 1),
            "era":            era,
            "units_assigned": int(bldg_units.get(bid, 0)),
        })

    # Aggregate per-year time series across buildings
    # We track:
    #   - buildings_in_year_era: count of buildings built in year Y in era E
    #   - units_in_year_era:     sum of units_assigned for buildings built in year Y in era E
    # Plus cumulative running totals.
    years = list(range(MIN_YEAR, MAX_YEAR + 1))
    year_idx = {y: i for i, y in enumerate(years)}

    add_b = {"pre87": [0]*len(years), "p87": [0]*len(years), "p12": [0]*len(years)}
    add_u = {"pre87": [0]*len(years), "p87": [0]*len(years), "p12": [0]*len(years)}

    era_key = {
        "Pre-1987 Plan": "pre87",
        "1987 Plan":     "p87",
        "2012 Plan":     "p12",
    }
    for b in buildings_out:
        y = b["year"]
        e = era_key.get(b["era"])
        if y is None or e is None: continue
        if y < MIN_YEAR or y > MAX_YEAR: continue
        i = year_idx[y]
        add_b[e][i] += 1
        add_u[e][i] += b["units_assigned"]

    # Cumulative
    cum_b = {k: [] for k in add_b}
    cum_u = {k: [] for k in add_u}
    for k in add_b:
        running_b = running_u = 0
        for i, _ in enumerate(years):
            running_b += add_b[k][i]
            running_u += add_u[k][i]
            cum_b[k].append(running_b)
            cum_u[k].append(running_u)

    by_year_era = []
    for i, y in enumerate(years):
        by_year_era.append({
            "year": y,
            "buildings_pre87": add_b["pre87"][i],
            "buildings_p87":   add_b["p87"][i],
            "buildings_p12":   add_b["p12"][i],
            "units_pre87":     add_u["pre87"][i],
            "units_p87":       add_u["p87"][i],
            "units_p12":       add_u["p12"][i],
            "cum_buildings_pre87": cum_b["pre87"][i],
            "cum_buildings_p87":   cum_b["p87"][i],
            "cum_buildings_p12":   cum_b["p12"][i],
            "cum_units_pre87":     cum_u["pre87"][i],
            "cum_units_p87":       cum_u["p87"][i],
            "cum_units_p12":       cum_u["p12"][i],
        })

    # Meta / stats
    total_buildings        = len(buildings_out)
    buildings_with_units   = sum(1 for b in buildings_out if b["units_assigned"] > 0)
    total_units_assigned   = sum(b["units_assigned"] for b in buildings_out)
    single_unit_buildings  = sum(1 for b in buildings_out if b["units_assigned"] == 1)
    multi_unit_buildings   = sum(1 for b in buildings_out if b["units_assigned"] >= 2)
    max_units_on_one_bldg  = max((b["units_assigned"] for b in buildings_out), default=0)

    meta = {
        "total_buildings":         total_buildings,
        "buildings_with_units":    buildings_with_units,
        "total_units_assigned":    total_units_assigned,
        "single_unit_buildings":   single_unit_buildings,
        "multi_unit_buildings":    multi_unit_buildings,
        "max_units_on_one_bldg":   max_units_on_one_bldg,
        "min_year":                MIN_YEAR,
        "max_year":                MAX_YEAR,
        "generated_at":            _dt.datetime.now().isoformat(timespec="seconds"),
    }

    out = {
        "meta":         meta,
        "buildings":    buildings_out,
        "by_year_era":  by_year_era,
    }

    out_path = Path(BUILDINGS_WITH_UNITS_JSON)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Compact JSON to keep file size small
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))

    log.info("=" * 70)
    log.info("Wrote -> %s (%.1f KB)", out_path, out_path.stat().st_size / 1024)
    log.info("=" * 70)
    log.info("Meta:")
    for k, v in meta.items():
        log.info("  %-26s %s", k, v)


if __name__ == "__main__":
    main()
