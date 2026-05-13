# Tracks status

> **Three parallel work streams for the cumulative-accounting platform.**
> **Audience: TRPA dev team, leadership, the analyst, anyone reading or extending the pipeline.**

This doc consolidates per-track status from the three originally separate files (`genealogy_track.md`, `allocation_track.md`, `qa_corrections_track.md`). Each track is independently scoped but shares the same parcel substrate (Track A) and the same proposed schema in [`target_schema.md`](./target_schema.md).

| Track | Owner concept | Status |
|---|---|---|
| **A. Genealogy → Current Parcel** | Never let an APN lose track | Existing infra in place; canonical resolver pending consolidation |
| **B. Allocation Tracking** | Where allocations sit + pool drawdown | Schema + 8 dashboards landed (5 in `html/`, 3 added in 2026 cycle); 14 open gaps in [`dashboards_to_schema_trace.md`](./dashboards_to_schema_trace.md) |
| **C. QA Corrections** | Track every adjustment with rationale | Prototype landed (loader + reconciliation + schema sidecar); dashboard E1 next |

---

## Track A - Genealogy → Current Parcel

**Status: existing infra in place; canonical resolver pending consolidation.**

Track A's job is **never lose track of an APN** as parcels split, merge, get renamed, or shift format (the 2018 leading-zero reformat that affected multiple counties). Every other track joins on parcel; Track A is the substrate that makes those joins reliable.

### Responsibilities

1. **APN canonicalization** - turn any raw APN string into a single canonical form. Implemented in [`parcel_development_history_etl/utils.py`](../parcel_development_history_etl/utils.py) as `canonical_apn(raw)` (broad - pads any standard `NNN-NNN-NN(N)` to 3-digit third segment) plus `el_pad`/`el_depad` for El-Dorado-specific cases.
2. **Genealogy event sourcing** - collect parcel split/merge/rename events from 4 distinct source systems into per-source CSVs, plus a consolidated master.
3. **APN resolution at query time** - given an APN and an as-of date, walk the genealogy chain to return the canonical parcel ID at that date. Schema target: `fn_resolve_apn(@apn, @as_of)` (proposed in `target_schema.md`).

### Source systems (4 lineages → 1 consolidated)

Each genealogy CSV in [`data/qa_data/`](../data/qa_data/):

| File | Source | Rows |
|---|---|---:|
| `apn_genealogy_master.csv` | Manual master (manually curated) | ~5K |
| `apn_genealogy_accela.csv` | Accela permit system parent/child links | ~30K |
| `apn_genealogy_ltinfo.csv` | LT Info parcel records | ~3K |
| `apn_genealogy_spatial.csv` | Spatial overlap detection (geometric) | ~1K |
| `apn_genealogy_tahoe.csv` | **Consolidated** (single source of truth, input to ETL) | ~37K |

[`s02b_genealogy.py`](../parcel_development_history_etl/steps/s02b_genealogy.py) reads only `apn_genealogy_tahoe.csv`. Re-run [`scripts/build_genealogy_tahoe.py`](../parcel_development_history_etl/scripts/build_genealogy_tahoe.py) whenever any of the 4 upstream sources changes.

### Key utilities (use these, don't reinvent)

```python
from parcel_development_history_etl.utils import canonical_apn, el_pad, el_depad
```

- `canonical_apn(raw)` - broad. Pads any `NNN-NNN-NN(N)` to 3-digit third segment. Returns `None` for empty/NaN. Other formats (Douglas long-form) pass through.
- `el_pad(apn)` / `el_depad(apn)` - El Dorado-specific year-aware variants.

### Open issues

- **A.O1** - Consolidate the 4 source CSVs into one canonical SQL resolver `fn_resolve_apn(@apn, @as_of)`.
- **A.O2** - Schema land - `ParcelGenealogyEventEnriched` (10+ columns vs Corral's 3-column `dbo.ParcelGenealogy`).
- **A.O3** - Genealogy-restatement change events - when an old→new mapping affects historical rows, rewrite in place or emit `ChangeSource='genealogy_restatement'`?
- **A.O4** - Track C's loader currently calls `canonical_apn` directly instead of going through `s02b_genealogy.py`. After A.O1 lands, switch to the resolver.
- **A.O5** - CSV-vs-DB resolver contract test once SQL function lands.

---

## Track B - Allocation Tracking

**Status: schema + 8 dashboards landed; 14 open gaps in the trace doc.**

Track B owns the **allocation accounting** layer: where do development allocations sit, where did they go, and how does pool drawdown progress against the Regional Plan caps. Most of the public-facing reporting comes out of this track.

### Regional Plan caps (since-1987 cumulative max)

From the analyst's 2026 PPTX slide 8:

| Commodity | Max | Constructed (2025) | % built |
|---|---:|---:|---:|
| Residential Allocations | **8,687 units** | 6,731 | 78% |
| Residential Bonus Units | **2,000 units** | 736 | 37% |
| Tourist Bonus Units | **400 units** | 58 | 15% |
| Commercial Floor Area | **1,000,000 sq ft** | 464K | 46% |

The 2012 Regional Plan's *additional* Board authorization (adopted 2013) on top of unused 1987 allocations was **2,600 residential units** - a subset of the 8,687 cumulative since-1987 max.

### Built dashboards (8 active in `html/`)

Per the framing (5/11/2026), organized by track:

| Track | Primary ★ | Supporting |
|---|---|---|
| #1 Allocation tracking | `allocation-tracking.html` | `pool-balance-cards.html`, `public-allocation-availability.html` |
| #2 Source of rights | `residential-additions-by-source.html` | - |
| #4 Total development | `regional-capacity-dial.html` | - |

Plus three "companion" views (parcel-development history side): `development_history.html`, `development_history_units.html`, `qa-change-rationale.html`.

See [`../html/index.md`](../html/index.md) for the live catalog with per-dashboard data sources.

### Data flow

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
       CumulativeAccountingSnapshot   PoolDrawdownYearly      ParcelHistoryView
                │                       │                       │
                ▼                       ▼                       ▼
       Cumulative Accounting Report   Allocation Drawdown    Parcel History
       (annual XLSX replacement)      dashboard              Lookup (per-APN)
```

Today the dashboards bypass the schema layer and read CSV / JSON exports from the analyst's xlsx files (via converter scripts in `parcel_development_history_etl/scripts/`). Once `vCommodityLedger` lands as a real DB view, dashboards switch to direct query.

### Open issues (highest-leverage from the trace doc)

- **B.G1.1** - Rule for `BonusUnitsRemaining` derivation.
- **B.G2.6** - `Unbanking` movement type (171 units / 13 yr).
- **B.G2.7** - Unreleased pool category (770 residential allocations TRPA hasn't released to jurisdictions). *Surfaced in the 2026 cycle via the residentialAllocationGridExport CSV.*
- **B.G2.8** - Bonus Units as first-class movement type - 2024–25 surge (Sugar Pine + LTCC = 155 units) is the most-asked-for clarification.
- **B.G3.5** - `Project` entity for the "Major Completed Projects" narrative on dashboards.

Full list in [`dashboards_to_schema_trace.md`](./dashboards_to_schema_trace.md).

### Refresh workflow (until schema lands)

When the analyst sends a refreshed xlsx, drop in `data/raw_data/` and run the matching converter (see `html/index.md` for commands).

---

## Track C - QA Corrections

**Status: prototype landed (loader + reconciliation + schema sidecar). Dashboard E1 next.**

Track C captures every QA adjustment to existing-development quantities with rationale, so the analyst's Excel-only audit trail becomes a queryable structured store.

### What this track does

the analyst's master record lives at [`data/qa_data/CA Changes breakdown.xlsx`](../data/qa_data/) - 44,371 row-cycles of per-APN change rationale across the **2023 and 2026 big-sweep campaigns**. Track C does three things:

1. **Schema** - `target_schema.md` defines `QaCorrectionDetail` as a sidecar (1:0..1) to `ParcelDevelopmentChangeEvent` when `ChangeSource='qa_correction'`, plus a `RawAPN` audit column.
2. **Loader** - [`notebooks/04_load_ca_changes.ipynb`](../notebooks/04_load_ca_changes.ipynb) reads the XLSX and emits normalized CSVs matching the proposed schema shape.
3. **Reconciliation bridge** - [`notebooks/05_qa_reconciliation.ipynb`](../notebooks/05_qa_reconciliation.ipynb) joins the loader's events against the 8 reconciliation reports `s06_qa.py` already writes, labeling every automated detection as `addressed_2023` / `addressed_2026` / `addressed_both` / `pending`.

### Outputs (in `data/qa_data/`)

| File | Rows | What it is |
|---|---:|---|
| `qa_change_events.csv` | 5,925 | Parent rows mirroring `ParcelDevelopmentChangeEvent`. One per `(APN, ReportingYear)` cycle with non-zero delta. |
| `qa_correction_detail.csv` | 5,925 | Sidecar mirroring `QaCorrectionDetail`. Carries `ReportingYear`, `SweepCampaign`, `CorrectionCategory`, `SummaryReason`, `RawAPN`, `SourceFileSnapshot`. |
| `qa_load_orphans.csv` | 4,137 | Validation issues from the loader - mostly noncanonical category labels (informational, not blocking). |
| `qa_reconciliation_status.csv` | 218,192 | One row per s06 finding, labeled by the analyst's address status. |
| `qa_analyst_only_corrections.csv` | 1,035 | the analyst's events with no matching s06 finding - pre-detection corrections, s06 false negatives, or out-of-scope. |

### Headline reconciliation numbers (latest run)

| Status | Count | % |
|---|---:|---:|
| `addressed_2023` | 5,575 | 2.6% |
| `addressed_2026` | 11,051 | 5.1% |
| `addressed_both` | 8,659 | 4.0% |
| `pending` | 192,907 | **88.4%** |

By s06 source - % addressed gives QA throughput per detection type:

| Source | Total | Addressed | % |
|---|---:|---:|---:|
| `QA_Lost_APNs` | 698 | 480 | **69%** |
| `QA_Unit_Reconciliation` | 59,674 | 15,805 | 26% |
| `QA_FC_Units_Not_In_CSV` | 157,820 | 9,000 | **6%** |

**Biggest remaining pile**: `QA_FC_Units_Not_In_CSV` at 149K untouched detections - where the next sweep will spend most of its time.

### Refresh workflow

When the analyst sends a new XLSX (or after a future sweep):

1. Drop the new file at `from_analyst/CA Changes breakdown.xlsx` (canonical) or `data/qa_data/CA Changes breakdown.xlsx` (working).
2. Re-run `notebooks/04_load_ca_changes.ipynb` (~30 sec for ~44K rows).
3. Re-run `notebooks/05_qa_reconciliation.ipynb` (~2 min, joins 218K s06 rows).
4. Diff the new `qa_reconciliation_status.csv` against prior to see "what got addressed since last run".

The loader is **idempotent on `SourceFileSnapshot`** (a string of the form `CA Changes breakdown.xlsx@2026-04-30`).

### Open issues

- **C.O1** - 30% canonical-vocab match rate. Recommend a `qa_data/correction_category_mapping.csv` to preserve Sheet2 as authoritative while mapping the analyst's Sheet1 paraphrases.
- **C.O2** - Year-aware reconciliation matching: a the analyst cycle-Y correction can only address an s06 finding for Year X if X ≤ Y.
- **C.O3** - Compute `PreviousQuantity` / `NewQuantity` (the analyst's XLSX carries deltas only). Join to `FINAL RES SUMMARY 2012 to 2025.xlsx` Residential sheet by canonical APN.
- **C.O4** - Resolve commodity per row (currently `SFRUU_or_MFRUU_TBD` because the analyst's data doesn't split SFRUU/MFRUU/ADU).
- **C.O5** - Promote both notebooks to `parcel_development_history_etl/steps/s07_load_and_reconcile_ca_changes.py`.

---

## Cross-track files reference

- **Schema**: [`target_schema.md`](./target_schema.md)
- **Validation findings**: [`validation_findings.md`](./validation_findings.md)
- **Dashboard catalog**: [`../html/index.md`](../html/index.md)
- **Corral table inventory**: [`corral_tables.md`](./corral_tables.md)
- **Inventory tables ERD** (recent): [`inventory_tables_erd.md`](./inventory_tables_erd.md)
- **Ledger prototype**: [`../ledger_prototype/build_ledger.ipynb`](../ledger_prototype/build_ledger.ipynb) - CSV proof-of-concept for `vCommodityLedger`
