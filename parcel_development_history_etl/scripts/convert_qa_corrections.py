"""Convert the QA correction CSVs into a single joined long-form table for
publishing as Cumulative_Accounting layer 16 (QaCorrections).

Input: data/qa_data/qa_change_events.csv  (5,925 rows; one row per change event)
       data/qa_data/qa_correction_detail.csv  (5,925 rows; 1:1 with events via ChangeEventID)

The dashboard (qa-change-rationale.html) previously fetched both CSVs and
joined client-side. Publishing a single joined table simplifies the dashboard
load (one query + pagination) and gives the analyst a single SDE table to
inspect when adjudicating corrections.

Outputs:
    data/processed_data/qa_corrections.csv
    data/processed_data/qa_corrections.json
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT          = Path(__file__).resolve().parents[2]
EVENTS_CSV    = ROOT / 'data' / 'qa_data' / 'qa_change_events.csv'
DETAILS_CSV   = ROOT / 'data' / 'qa_data' / 'qa_correction_detail.csv'
OUT_CSV       = ROOT / 'data' / 'processed_data' / 'qa_corrections.csv'
OUT_JSON      = ROOT / 'data' / 'processed_data' / 'qa_corrections.json'


def main() -> int:
    if not EVENTS_CSV.exists():
        print(f'ERROR: events CSV not found: {EVENTS_CSV}', file=sys.stderr)
        return 1
    if not DETAILS_CSV.exists():
        print(f'ERROR: details CSV not found: {DETAILS_CSV}', file=sys.stderr)
        return 1

    ev = pd.read_csv(EVENTS_CSV)
    dt = pd.read_csv(DETAILS_CSV)
    print(f'events: {len(ev)} rows; details: {len(dt)} rows')

    # 1:1 join on ChangeEventID. Drop duplicate columns from details where they
    # collide with events (RawAPN appears in both).
    dt_for_join = dt.drop(columns=['RawAPN', 'QaCorrectionDetailID'], errors='ignore')
    df = ev.merge(dt_for_join, on='ChangeEventID', how='inner', suffixes=('', '_dt'))
    print(f'joined: {len(df)} rows; {len(df.columns)} columns')

    today = date.today().isoformat()
    df['LoadedDate'] = today

    # Write CSV with stable column order
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    print(f'Wrote {len(df)} rows to {OUT_CSV.relative_to(ROOT)}')

    # JSON for dashboard. Drop NaN values for cleaner payload.
    rows = []
    for _, r in df.iterrows():
        row = {k: (None if pd.isna(v) else (v.item() if hasattr(v, 'item') else v)) for k, v in r.items()}
        rows.append(row)
    payload = {
        'asOfDate': today,
        'rowCount': len(rows),
        'rows':     rows,
    }
    OUT_JSON.write_text(json.dumps(payload))
    print(f'Wrote {len(df)} rows to {OUT_JSON.relative_to(ROOT)}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
