"""Convert regional_plan_allocations.json into a tidy long-form pool balances
table for publishing as a new Cumulative_Accounting REST layer.

The source JSON (produced by convert_regional_plan_allocations.py from the
analyst's All Regional Plan Allocations Summary xlsx) carries nested
per-jurisdiction / per-pool breakdowns. The pool-balance-cards dashboard
currently fetches the JSON directly; this converter pivots it into a flat
long-form table that fits SDE + REST publishing.

Schema: one row per (Commodity, Pool/Jurisdiction), Combined plan-era only -
this matches what pool-balance-cards renders today. The 1987 / 2012 plan-era
splits stay in the source JSON (they're available via the existing converter
output) but aren't surfaced in any dashboard so don't ship in layer 12 yet.

Outputs:
    data/processed_data/pool_balances.csv
    data/processed_data/pool_balances.json
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT      = Path(__file__).resolve().parents[2]
SRC_JSON  = ROOT / 'data' / 'processed_data' / 'regional_plan_allocations.json'
OUT_CSV   = ROOT / 'data' / 'processed_data' / 'pool_balances.csv'
OUT_JSON  = ROOT / 'data' / 'processed_data' / 'pool_balances.json'

# Map source JSON key -> (commodity display name, short code)
COMMODITY_META = {
    'residential':                 ('Residential Allocations', 'RES'),
    'residential_bonus_units':     ('Residential Bonus Units', 'RBU'),
    'commercial_floor_area':       ('Commercial Floor Area',   'CFA'),
    'tourist_accommodation_units': ('Tourist Accommodation Units', 'TAU'),
}


def emit_row(rows: list, *, commodity: str, code: str, pool: str, group: str | None,
             max_: int | None, assigned: int | None, not_assigned: int | None,
             as_of: str) -> None:
    rows.append({
        'Commodity':            commodity,
        'CommodityCode':        code,
        'Plan':                 'Combined',
        'Pool':                 pool,
        'Group':                group or '',
        'RegionalPlanMaximum':  int(max_)         if max_         is not None else 0,
        'AssignedToProjects':   int(assigned)     if assigned     is not None else 0,
        'NotAssigned':          int(not_assigned) if not_assigned is not None else 0,
        'AsOfDate':             as_of,
    })


def main() -> int:
    if not SRC_JSON.exists():
        print(f'ERROR: source JSON not found: {SRC_JSON}', file=sys.stderr)
        return 1

    src = json.loads(SRC_JSON.read_text())
    meta = src.get('meta', {})
    # The xlsx's "As of {date}" string - keep as-is in the AsOfDate field. The
    # converter for layer 10 / 11 standardizes to ISO; this one preserves the
    # source string for now since the JSON only carries the formatted form.
    as_of = meta.get('as_of', '')

    rows: list[dict] = []

    # Residential: by_jurisdiction has the per-jurisdiction breakdown.
    # Each entry has combined/plan_1987/plan_2012 with regional_plan_maximum /
    # not_assigned / assigned_to_projects. We emit Combined only.
    res_name, res_code = COMMODITY_META['residential']
    for j in src.get('residential', {}).get('by_jurisdiction', []):
        c = j.get('combined', {})
        # Group is implicit by jurisdiction; "TRPA Allocation Incentive Pool"
        # rows belong to a TRPA group, "Unreleased" to its own.
        name = j.get('name', '')
        if 'TRPA' in name:
            group = 'TRPA pools'
        elif 'Unreleased' in name:
            group = 'Unreleased'
        else:
            group = 'Jurisdiction'
        emit_row(rows, commodity=res_name, code=res_code, pool=name, group=group,
                 max_=c.get('regional_plan_maximum'),
                 assigned=c.get('assigned_to_projects'),
                 not_assigned=c.get('not_assigned'),
                 as_of=as_of)

    # RBU / CFA / TAU: status.by_pool has the per-pool breakdown (combined).
    for skey, (name_disp, code) in COMMODITY_META.items():
        if skey == 'residential':
            continue
        for p in src.get(skey, {}).get('status', {}).get('by_pool', []):
            emit_row(rows, commodity=name_disp, code=code,
                     pool=p.get('name', ''),
                     group=p.get('group'),
                     max_=p.get('regional_plan_maximum'),
                     assigned=p.get('assigned_to_projects'),
                     not_assigned=p.get('not_assigned'),
                     as_of=as_of)

    # Add LoadedDate + SourceFile for provenance
    today = date.today().isoformat()
    for r in rows:
        r['LoadedDate'] = today
        r['SourceFile'] = SRC_JSON.name

    # Sanity check: RegionalPlanMaximum should approximately equal Assigned + NotAssigned
    bad = []
    for r in rows:
        s = r['AssignedToProjects'] + r['NotAssigned']
        if r['RegionalPlanMaximum'] and s != r['RegionalPlanMaximum']:
            bad.append((r['Commodity'], r['Pool'], r['RegionalPlanMaximum'], s))
    if bad:
        print('WARNING: RegionalPlanMaximum != Assigned + NotAssigned for:', file=sys.stderr)
        for c, p, m, s in bad:
            print(f'  [{c}] {p}: max={m}, assigned+notassigned={s}', file=sys.stderr)
    else:
        print(f'OK: identity Max = Assigned + NotAssigned holds for all {len(rows)} rows')

    # Write CSV
    import csv
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open('w', newline='', encoding='utf-8') as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print(f'Wrote {len(rows)} rows to {OUT_CSV.relative_to(ROOT)}')

    # Write JSON (dashboard-friendly, mirrors layer 10/11 shape)
    payload = {
        'asOfDate':   as_of,
        'sourceFile': SRC_JSON.name,
        'rows':       [{k: v for k, v in r.items() if k not in ('LoadedDate', 'SourceFile')} for r in rows],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2))
    print(f'Wrote {len(rows)} rows to {OUT_JSON.relative_to(ROOT)}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
