"""Convert the analyst's AllocationsBalances xlsx into a normalized tidy table.

Source xlsx structure (3 blocks x 4 commodities = 12 rows):
    Block 1: Grand Total            (1987 + 2012 RP combined)
    Block 2: Source: 1987 Regional Plan
    Block 3: Source: 2012 Regional Plan

Each block has the same 4 commodities and 5 metric columns:
    TotalAuthorized | AllocatedToPrivate | JurisdictionPool | TRPAPool | Unreleased
plus an aggregate TotalBalanceRemaining column (= Juris + TRPA + Unreleased).

The xlsx is treated as a snapshot deliverable - the analyst regenerates it on
their cumulative-accounting cycle. This script normalizes it to a long-form
tidy table that mirrors how it will be loaded into SDE and published as a
non-spatial table in the Cumulative_Accounting REST service.

Outputs:
    data/processed_data/allocations_balances.csv   (canonical tidy form)
    data/processed_data/allocations_balances.json  (same data, dashboard-friendly)

Identity check:
    AllocatedToPrivate == TotalAuthorized - TotalBalanceRemaining
all 12 rows pass at 2026-05-15.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

# Project paths
ROOT      = Path(__file__).resolve().parents[2]
SRC_XLSX  = ROOT / 'data' / 'from_analyst'    / 'AllocationsBalances_May2026.xlsx'
OUT_CSV   = ROOT / 'data' / 'processed_data'  / 'allocations_balances.csv'
OUT_JSON  = ROOT / 'data' / 'processed_data'  / 'allocations_balances.json'

# Block header row index (0-based) and source label
BLOCKS = [
    (1,  'Grand Total'),
    (8,  '1987 Regional Plan'),
    (15, '2012 Regional Plan'),
]

METRIC_COLS = [
    'TotalAuthorized',
    'AllocatedToPrivate',
    'JurisdictionPool',
    'TRPAPool',
    'Unreleased',
]

# Stable code keyed off the commodity name for tidy code-side matching.
COMMODITY_CODE = {
    'Residential allocations':  'RES',
    'Residential bonus units':  'RBU',
    'Commercial floor area':    'CFA',
    'Tourist accommodation':    'TAU',
}

# Capture the as-of date from the filename suffix (May2026 -> 2026-05-15
# as a stand-in for the analyst's cycle date). Update the constant when a
# refreshed xlsx lands with a different month tag.
AS_OF_DATE = '2026-05-15'


def main() -> int:
    if not SRC_XLSX.exists():
        print(f'ERROR: source xlsx not found: {SRC_XLSX}', file=sys.stderr)
        return 1

    raw = pd.read_excel(SRC_XLSX, sheet_name='Sheet1', header=None)

    rows: list[dict] = []
    for header_idx, source in BLOCKS:
        for offset in range(4):
            r = raw.iloc[header_idx + 1 + offset]
            commodity = r[0]
            if commodity not in COMMODITY_CODE:
                print(f'WARNING: skipping unrecognized commodity {commodity!r} at row {header_idx + 1 + offset}', file=sys.stderr)
                continue
            row = {
                'Source':        source,
                'Commodity':     commodity,
                'CommodityCode': COMMODITY_CODE[commodity],
            }
            for j, col in enumerate(METRIC_COLS, start=1):
                val = r[j]
                row[col] = int(val) if pd.notna(val) else 0
            # Sum identity: held + reserved totals.
            row['TotalBalanceRemaining'] = row['JurisdictionPool'] + row['TRPAPool'] + row['Unreleased']
            row['AsOfDate']   = AS_OF_DATE
            row['LoadedDate'] = date.today().isoformat()
            row['SourceFile'] = SRC_XLSX.name
            rows.append(row)

    df = pd.DataFrame(rows)

    # Identity sanity check (silent unless mismatch)
    df['_computed_allocated'] = df['TotalAuthorized'] - df['TotalBalanceRemaining']
    bad = df[df['_computed_allocated'] != df['AllocatedToPrivate']]
    if not bad.empty:
        print('WARNING: AllocatedToPrivate != TotalAuthorized - TotalBalanceRemaining for:', file=sys.stderr)
        print(bad[['Source', 'Commodity', 'TotalAuthorized', 'AllocatedToPrivate', '_computed_allocated']].to_string(index=False), file=sys.stderr)
    df = df.drop(columns=['_computed_allocated'])

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    print(f'Wrote {len(df)} rows to {OUT_CSV.relative_to(ROOT)}')

    # JSON form for dashboard consumption (no pandas dependency in browser).
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
