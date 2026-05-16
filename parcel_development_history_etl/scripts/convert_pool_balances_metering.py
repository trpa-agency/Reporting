"""Convert the residential per-year metering blocks from
regional_plan_allocations.json into a tidy long-form table for publishing as
Cumulative_Accounting layer 15 (PoolBalancesMetering).

Source data: `residential.by_year.{released, assigned, not_assigned, unreleased}`
- each block is {years: [Y1..YN], rows: [{name, values: [...]}, ...]}

The pool-balance-cards detail panel uses 2 of these: `released` (vertical bar)
and `assigned` (line+markers) when a residential pool is selected. The
`not_assigned` and `unreleased` blocks aren't surfaced today but are included
in the layer for completeness (they're per-year balances that show pool draw-
down over time).

Outputs:
    data/processed_data/pool_balances_metering.csv
    data/processed_data/pool_balances_metering.json
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path

ROOT     = Path(__file__).resolve().parents[2]
SRC_JSON = ROOT / 'data' / 'processed_data' / 'regional_plan_allocations.json'
OUT_CSV  = ROOT / 'data' / 'processed_data' / 'pool_balances_metering.csv'
OUT_JSON = ROOT / 'data' / 'processed_data' / 'pool_balances_metering.json'

BLOCK_KEYS = {
    'released':     'Released',
    'assigned':     'Assigned',
    'not_assigned': 'NotAssigned',
    'unreleased':   'Unreleased',
}


def main() -> int:
    if not SRC_JSON.exists():
        print(f'ERROR: source JSON not found: {SRC_JSON}', file=sys.stderr)
        return 1

    src = json.loads(SRC_JSON.read_text())
    as_of = src.get('meta', {}).get('as_of', '')
    rows: list[dict] = []
    today = date.today().isoformat()

    by_year = src.get('residential', {}).get('by_year', {})
    for src_key, direction in BLOCK_KEYS.items():
        block = by_year.get(src_key, {})
        years = block.get('years', [])
        for row in block.get('rows', []):
            name   = row.get('name', '')
            values = row.get('values', [])
            for year, val in zip(years, values):
                if val is None:
                    continue
                rows.append({
                    'Commodity':     'Residential allocations',
                    'CommodityCode': 'RES',
                    'Pool':          name,
                    'Year':          int(year),
                    'Direction':     direction,
                    'Units':         int(val) if val is not None else 0,
                    'AsOfDate':      as_of,
                    'LoadedDate':    today,
                })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open('w', newline='', encoding='utf-8') as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print(f'Wrote {len(rows)} rows to {OUT_CSV.relative_to(ROOT)}')

    payload = {
        'asOfDate': as_of,
        'rows':     [{k: v for k, v in r.items() if k != 'LoadedDate'} for r in rows],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2))
    print(f'Wrote {len(rows)} rows to {OUT_JSON.relative_to(ROOT)}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
