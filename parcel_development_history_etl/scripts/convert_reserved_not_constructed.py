"""Convert the Tracker's section iii hardcoded values into a tidy CSV for
publishing as Cumulative_Accounting layer 14 (ReservedNotConstructed).

Section iii = "Reserved, not constructed" - allocations drawn to a parcel but
not yet built. The 3 values come from the analyst's 2026-05-15 tally; path-to-
true-derivation requires a Construction_Status field on Layer 3 (1987 RP) that
isn't published yet (Layer 4 has Construction_Status for 2012 RP residential
only, gives 151 of the 698 RES total). When layer 3 grows that field, this
converter retires in favor of a SQL view UNIONing layer 3 + layer 4
Construction_Status='Not Completed' counts per commodity.

Outputs:
    data/processed_data/reserved_not_constructed.csv
    data/processed_data/reserved_not_constructed.json
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path

ROOT     = Path(__file__).resolve().parents[2]
OUT_CSV  = ROOT / 'data' / 'processed_data' / 'reserved_not_constructed.csv'
OUT_JSON = ROOT / 'data' / 'processed_data' / 'reserved_not_constructed.json'

AS_OF_DATE = '2026-05-15'

# From the analyst's 2026-05-15 tally. Same commodity codes as layer 10.
RAW = [
    {'CommodityCode': 'RES', 'Commodity': 'Residential allocations',     'Units': 698,    'Unit': 'units'},
    {'CommodityCode': 'CFA', 'Commodity': 'Commercial floor area',       'Units': 46962,  'Unit': 'sq ft'},
    {'CommodityCode': 'TAU', 'Commodity': 'Tourist accommodation units', 'Units': 138,    'Unit': 'units'},
]


def main() -> int:
    today = date.today().isoformat()
    rows = [
        {**r, 'AsOfDate': AS_OF_DATE, 'LoadedDate': today, 'SourceNote': "analyst tally; path-to-live = layer 4 Construction_Status + 1987 RP equivalent"}
        for r in RAW
    ]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f'Wrote {len(rows)} rows to {OUT_CSV.relative_to(ROOT)}')

    payload = {
        'asOfDate': AS_OF_DATE,
        'rows':     [{k: v for k, v in r.items() if k != 'LoadedDate'} for r in rows],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2))
    print(f'Wrote {len(rows)} rows to {OUT_JSON.relative_to(ROOT)}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
