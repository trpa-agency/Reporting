"""Convert the inline PROJECTS array in residential-additions-by-source.html
into a tidy CSV ready for SDE + REST publishing as layer 13.

The source is the analyst's PPTX slide 4 + xlsx "Major Completed Projects"
row. There's no consolidated xlsx for this; values were transcribed inline.
This converter codifies them as structured data with project name, total
units, and a Description field that preserves the original phrasing
(including affordability notes like "47 affordable, 1 moderate").

Once layer 13 publishes, the residential-additions-by-source dashboard
swaps its inline PROJECTS array for a layer 13 fetch.

Outputs:
    data/processed_data/residential_projects.csv
    data/processed_data/residential_projects.json
"""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT     = Path(__file__).resolve().parents[2]
OUT_CSV  = ROOT / 'data' / 'processed_data' / 'residential_projects.csv'
OUT_JSON = ROOT / 'data' / 'processed_data' / 'residential_projects.json'

AS_OF_DATE = '2026-05-15'

# Source: dashboard inline array, transcribed from analyst PPTX slide 4 +
# xlsx narrative. (Year, full description string per project.)
RAW = [
    (2014, 'Aspens: 48 units (47 affordable, 1 moderate)'),
    (2016, 'Peak 10: 10 units'),
    (2018, 'Sierra Colina: 1 unit'),
    (2019, 'Tahoe City Marina: 10 units'),
    (2019, 'Sierra Colina: 4 units'),
    (2020, 'Beach Club: 25 units'),
    (2020, 'Wildwood Commons: 23 units'),
    (2020, 'Gondola Vista: 20 units'),
    (2020, 'Sierra Colina: 5 units'),
    (2021, 'Beach Club: 21 units'),
    (2021, 'Sierra Colina: 6 units'),
    (2021, 'WoodVista: 6 units'),
    (2021, 'Tahoe Cedars: 4 units'),
    (2022, 'Emerald Bay Cabins: 6 units'),
    (2022, 'Sierra Colina: 3 units'),
    (2023, 'Beach Club: 24 units'),
    (2023, 'Sierra Colina: 6 units'),
    (2024, 'Sugar Pine: 69 units (67 affordable)'),
    (2024, 'Birds Nest: 21 MF units (affordable)'),
    (2024, '395 N Lake: 12 MF units'),
    (2024, 'Sierra Colina: 11 units'),
    (2024, 'Beach Club: 8 units'),
    (2025, 'Sugar Pine: 60 units (59 affordable)'),
    (2025, 'LTCC Dorms: 41 units (19 affordable / 1 achievable)'),
    (2025, 'Beach Club: 16 units'),
    (2025, 'Sierra Colina: 8 units'),
]

# Match "<Name>: <N> [MF] unit(s) [(<notes>)]"
PATTERN = re.compile(r'^(?P<name>[^:]+):\s+(?P<units>\d+)\s+(?:MF\s+)?units?(?:\s+\((?P<notes>.+)\))?\s*$')


def parse(desc: str) -> tuple[str, int, str]:
    m = PATTERN.match(desc)
    if not m:
        print(f'WARNING: could not parse {desc!r}', file=sys.stderr)
        return desc, 0, ''
    return m.group('name').strip(), int(m.group('units')), (m.group('notes') or '').strip()


def main() -> int:
    rows: list[dict] = []
    today = date.today().isoformat()
    for year, desc in RAW:
        name, units, notes = parse(desc)
        rows.append({
            'Year':        year,
            'ProjectName': name,
            'Units':       units,
            'Notes':       notes,
            'Description': desc,
            'AsOfDate':    AS_OF_DATE,
            'LoadedDate':  today,
        })

    # Sanity: aggregate by year, see how many units accounted for
    from collections import defaultdict
    by_year = defaultdict(int)
    for r in rows:
        by_year[r['Year']] += r['Units']
    print('Units per year (from projects):')
    for y in sorted(by_year):
        print(f'  {y}: {by_year[y]:>4}')

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
