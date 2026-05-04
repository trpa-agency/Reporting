# Track B — Allocation Tracking

> **Status: schema + 5 dashboards landed; A1 next; 14 open gaps in the trace doc.**
> **Audience: TRPA dev team, Dan, governing board, partner jurisdictions.**

One of three parallel tracks of work in this repo (the others are Track A — Genealogy → Current Parcel, and Track C — QA Corrections). Track B owns the **allocation accounting** layer: where do development allocations sit, where did they go, and how does pool drawdown progress against the Regional Plan caps. Most of the public-facing reporting comes out of this track.

## What this track does

Three layers, each with a canonical doc:

1. **Schema** — 8 physical tables + 2 views + 3 materialized snapshots in [`target_schema.md`](./target_schema.md). The big ones: `vCommodityLedger` (UNION of all `dbo.TdrTransaction*` + banking + manual QA), `PoolDrawdownYearly`, `CumulativeAccountingSnapshot`, `ParcelHistoryView`.
2. **Backward-engineering trace** — [`dashboards_to_schema_trace.md`](./dashboards_to_schema_trace.md) walks each built dashboard backwards through its view contract to the schema columns it needs. Surfaces 14 open gaps.
3. **Dashboards** — 5 built (`html/`), all TRPA-branded.

## Regional Plan caps (since-1987 cumulative max)

The headline numbers Track B reports against. From Ken's 2026 PPTX slide 8:

| Commodity | Max | Constructed (2025) | % built |
|---|---:|---:|---:|
| Residential Allocations | **8,687 units** | 6,731 | 78% |
| Residential Bonus Units | **2,000 units** | 736 | 37% |
| Tourist Bonus Units | **400 units** | 58 | 15% |
| Commercial Floor Area | **1,000,000 sq ft** | 464K | 46% |

The 2012 Regional Plan's *additional* Board authorization (adopted 2013) on top of unused 1987 allocations was **2,600 residential units** — a subset of the 8,687 cumulative since-1987 max.

## Built dashboards

All in [`html/`](../html/), TRPA-branded (Open Sans + full TRPA palette per `trpa-brand` skill):

| File | Cluster | What it shows |
|---|---|---|
| [`allocation_drawdown.html`](../html/allocation_drawdown.html) | (prototype) | Stacked area: pool × year → remaining balance. 2013–2026, 9 pools. The original anchor that proved the stack works. |
| [`allocation-tracking.html`](../html/allocation-tracking.html) | (prototype) | Sankey + bar chart + map + AG Grid table; type switcher RES/CFA/TAU; year slider; jurisdiction pills. |
| [`residential-allocations-dashboard.html`](../html/residential-allocations-dashboard.html) | (prototype) | Earlier prototype, jurisdiction-specific residential view. |
| [`residential-additions-by-source.html`](../html/residential-additions-by-source.html) | A4 | Multi-line by year: 5 sources of added residential units (Allocations / Bonus / Transfers / Conversions / Banked). 2024–25 bonus surge is the headline. |
| [`qa-change-rationale.html`](../html/qa-change-rationale.html) | E1 | (Track C) — listed for completeness; QA audit trail with AG Grid. |

## Data flow

```
                     ┌─────────────────────────────────┐
                     │  Corral (sql24/Corral)          │
                     │  dbo.TdrTransaction* (9 types)  │
                     │  dbo.ParcelPermitBanked...      │
                     │  dbo.ResidentialAllocation      │
                     │  dbo.CommodityPool, Parcel, ... │
                     └──────────────────┬──────────────┘
                                        │
                  [vCommodityLedger view + nightly materialization]
                                        │
                ┌───────────────────────┼───────────────────────┐
                ▼                       ▼                       ▼
   ┌────────────────────┐ ┌──────────────────────┐ ┌─────────────────────┐
   │ CumulativeAccount- │ │ PoolDrawdownYearly   │ │ ParcelHistoryView   │
   │ ingSnapshot        │ │ (annual per pool +   │ │ (per APN x year x   │
   │ (5-bucket per      │ │  movement-type cols) │ │  commodity)         │
   │  jur x commodity)  │ │                      │ │                     │
   └─────────┬──────────┘ └──────────┬───────────┘ └──────────┬──────────┘
             │                       │                        │
             ▼                       ▼                        ▼
   ┌────────────────────┐ ┌──────────────────────┐ ┌─────────────────────┐
   │ Cumulative         │ │ Allocation           │ │ Parcel History      │
   │ Accounting Report  │ │ Drawdown dashboard   │ │ Lookup (per-APN)    │
   │ (annual XLSX repl) │ │                      │ │                     │
   └────────────────────┘ └──────────────────────┘ └─────────────────────┘
```

Today the dashboards bypass the schema layer and fetch CSV exports from LT Info grid pages (manual export → committed to `data/raw_data/` → fetched via GitHub raw URL). Once `vCommodityLedger` lands as a real DB view + REST service, dashboards switch to direct query. See [`dashboards_to_schema_trace.md`](./dashboards_to_schema_trace.md) §"LT Info grid pages → Corral tables" for the data-source mapping.

## Cadence

- **Annual reporting** — cumulative accounting report published each year.
- **Nightly recompute** (proposed) — `CumulativeAccountingSnapshot` and `PoolDrawdownYearly` rebuild nightly from `vCommodityLedger`. See `target_schema.md` Q13.
- **Manual CSV refresh** — until the schema lands, LT Info grid CSVs in `data/raw_data/` are re-exported and committed when staff need fresh dashboard data.

## Open issues

The trace doc has 14 open gaps; the highest-leverage are:

- **G1.1** Rule for `BonusUnitsRemaining` derivation — currently zero rows in the prototype CSV.
- **G2.6** `Unbanking` movement type — 171 units / 13 yr is non-trivial; needs a real source.
- **G2.7** Unreleased pool category — 770 residential allocations TRPA hasn't released to jurisdictions.
- **G2.8** Bonus Units as a first-class movement type — 2024–25 bonus surge (Sugar Pine + LTCC = 155 units) makes this the most-asked-for clarification.
- **G3.5** `Project` entity — needed to make the "Major Completed Projects" narrative on dashboards query-driven instead of HTML-hardcoded.

Full list in [`dashboards_to_schema_trace.md`](./dashboards_to_schema_trace.md) §"Roll-up: gap delta against target_schema.md."

## Refresh workflow (until schema lands)

For the LT Info CSV-fed dashboards (`allocation-tracking.html`, the drawdowns):

1. Re-export the relevant LT Info grid as CSV.
2. Drop into [`data/raw_data/`](../data/raw_data/).
3. Commit + push to MTB-Edits. Dashboards fetch from `raw.githubusercontent.com/.../MTB-Edits/...` so they pick up automatically.

For the Ken-XLSX-fed dashboards (`residential-additions-by-source.html`):

1. Drop the new XLSX in [`from_ken/`](../from_ken/) (or `data/qa_data/`).
2. Re-extract the 5×13 categorical matrix and update the dashboard's inlined `SOURCES` array.
3. Commit + push.

## Where this fits in the broader 3-track plan

| Track | Relationship to Track B |
|---|---|
| **A — Genealogy** | substrate: Track B's parcel joins use `canonical_apn` from Track A's utils |
| **B — Allocations** *(this doc)* | the public-facing reporting layer |
| **C — QA Corrections** | feeds Track B's `vParcelHistory` / `ParcelHistoryView` once the DB load happens; surfaces in dashboard E1 |

Track B has the most surface area (5 dashboards, 8 schema tables, 14 open gaps). The plan stays terse; the trace doc carries the per-dashboard detail.

## Files reference

- **Catalog:** [`proposed_dashboards.md`](./proposed_dashboards.md) — 25+ candidates in clusters A–H, every entry buildability-marked
- **Trace:** [`dashboards_to_schema_trace.md`](./dashboards_to_schema_trace.md) — backward-engineering for built dashboards + LT Info grid → Corral mapping
- **Schema:** [`target_schema.md`](./target_schema.md) — full 8-table proposal
- **Built dashboards:** [`../html/`](../html/) (5 files listed above)
- **Realized view CSVs:** [`../ledger_prototype/views/v_pool_drawdown.csv`](../ledger_prototype/views/v_pool_drawdown.csv), [`../ledger_prototype/views/v_cumulative_accounting.csv`](../ledger_prototype/views/v_cumulative_accounting.csv)
- **Ledger prototype:** [`../ledger_prototype/build_ledger.ipynb`](../ledger_prototype/build_ledger.ipynb) — Python proof-of-concept for `vCommodityLedger`
- **Dashboard tech stack:** see `trpa-dashboard-stack` skill (Plotly + Calcite + ArcGIS Maps SDK + AG Grid)
