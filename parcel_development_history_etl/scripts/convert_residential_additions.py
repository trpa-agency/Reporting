"""Convert FINAL RES SUMMARY 2012 to 2025.xlsx Summary sheet into a tidy
year-by-source matrix for publishing as a new Cumulative_Accounting REST layer.

Source xlsx layout (Summary sheet, year x metric grid):
    Row  3: Total Residential Units                 (cumulative built per year)
    Row  6: Net Change Residential Units            (= Added - Removed)
    Row  9: Added Residential Units                 (Added total per year)
    Row 10: Added from Residential Allocations
    Row 11: Added from Residential Bonus Unit
    Row 12: Added from Transfers
    Row 13: Added from Conversions
    Row 14: Added from Banked
    Row 16: Removed Residential Units               (Removed total per year)
    Row 17: Banked (outflow)
    Row 18: Converted (outflow)

Output is long-form: one row per (Year, Direction, Source) with signed Units
(positive for additions, negative for removals). Net Change + Total are
derivable from these rows; we DON'T publish them (let downstream sum) so the
layer stays normalized.

Outputs:
    data/processed_data/residential_additions.csv
    data/processed_data/residential_additions.json
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT      = Path(__file__).resolve().parents[2]
SRC_XLSX  = ROOT / 'data' / 'from_analyst'    / 'FINAL RES SUMMARY 2012 to 2025.xlsx'
OUT_CSV   = ROOT / 'data' / 'processed_data'  / 'residential_additions.csv'
OUT_JSON  = ROOT / 'data' / 'processed_data'  / 'residential_additions.json'

YEARS = list(range(2012, 2026))   # cols 1..14 in Summary (col 0 is the row label)

# Row index -> (direction, source) mapping. Skip Net Change + Total rows -
# downstream consumers can derive those from these atomic rows.
ROW_MAP = {
    10: ('Added',   'Allocations'),
    11: ('Added',   'Bonus Units'),
    12: ('Added',   'Transfers'),
    13: ('Added',   'Conversions'),
    14: ('Added',   'Banked'),
    17: ('Removed', 'Banked'),       # rows banked out (returned to bank)
    18: ('Removed', 'Converted'),    # rows converted out
}

AS_OF_DATE = '2026-05-15'


def main() -> int:
    if not SRC_XLSX.exists():
        print(f'ERROR: source xlsx not found: {SRC_XLSX}', file=sys.stderr)
        return 1

    raw = pd.read_excel(SRC_XLSX, sheet_name='Summary', header=None)

    rows: list[dict] = []
    for row_idx, (direction, source) in ROW_MAP.items():
        r = raw.iloc[row_idx]
        # Validate the row label matches our expectation (defensive)
        label = str(r[0])
        for j, year in enumerate(YEARS, start=1):
            val = r[j]
            if pd.isna(val):
                units = 0
            else:
                units = int(val)
            # Sign convention: removed rows already negative in xlsx; flip if not
            if direction == 'Removed' and units > 0:
                units = -units
            rows.append({
                'Year':       year,
                'Direction':  direction,
                'Source':     source,
                'Units':      units,
                'SourceRow':  label,   # provenance: which xlsx row this came from
                'AsOfDate':   AS_OF_DATE,
                'LoadedDate': date.today().isoformat(),
                'SourceFile': SRC_XLSX.name,
            })

    df = pd.DataFrame(rows)

    # Derive sanity checks (silent unless mismatch with xlsx Net Change row).
    added_by_year   = df[df.Direction == 'Added'  ].groupby('Year')['Units'].sum()
    removed_by_year = df[df.Direction == 'Removed'].groupby('Year')['Units'].sum()
    net_derived     = added_by_year + removed_by_year   # removed is negative

    xlsx_net = {}
    for j, year in enumerate(YEARS, start=1):
        v = raw.iloc[6, j]
        if pd.notna(v):
            xlsx_net[year] = int(v)
    mismatches = []
    for year in YEARS:
        if year in xlsx_net and year in net_derived.index:
            if net_derived[year] != xlsx_net[year]:
                mismatches.append((year, int(net_derived[year]), xlsx_net[year]))
    if mismatches:
        print('WARNING: derived Net Change != xlsx Net Change for:', file=sys.stderr)
        for year, derived, xlsx in mismatches:
            print(f'  {year}: derived={derived}, xlsx={xlsx}', file=sys.stderr)
    else:
        print('OK: derived Net Change matches xlsx Net Change for all years')

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    print(f'Wrote {len(df)} rows to {OUT_CSV.relative_to(ROOT)}')

    payload = {
        'asOfDate':   AS_OF_DATE,
        'sourceFile': SRC_XLSX.name,
        'rows':       df.drop(columns=['LoadedDate', 'SourceFile']).to_dict(orient='records'),
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2))
    print(f'Wrote {len(df)} rows to {OUT_JSON.relative_to(ROOT)}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
