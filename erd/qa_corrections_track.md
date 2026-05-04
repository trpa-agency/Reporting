# Track C — QA Corrections

> **Status: prototype landed (loader + reconciliation + schema sidecar). Dashboard E1 next.**
> **Audience: Ken, Dan, anyone reading or extending the QA tracking pipeline.**

One of three parallel tracks of work in this repo (the others are Track A — Genealogy → Current Parcel, and Track B — Allocation Tracking). Track C captures every QA adjustment to existing-development quantities with rationale, so Ken's Excel-only audit trail becomes a queryable structured store.

## What this track does

Ken's master record of QA corrections lives at [`data/qa_data/CA Changes breakdown.xlsx`](../data/qa_data/CA Changes breakdown.xlsx) (and its committed copy at [`from_ken/CA Changes breakdown.xlsx`](../from_ken/CA Changes breakdown.xlsx)). It carries 44,371 row-cycles of per-APN change rationale across the **2023 and 2026 big-sweep campaigns**. Track C does three things with it:

1. **Schema** — `target_schema.md` defines `QaCorrectionDetail` as a sidecar (1:0..1) to `ParcelDevelopmentChangeEvent` when `ChangeSource='qa_correction'`, plus a `RawAPN` audit column.
2. **Loader** — `notebooks/04_load_ca_changes.ipynb` reads the XLSX and emits normalized CSVs matching the proposed schema shape.
3. **Reconciliation bridge** — `notebooks/05_qa_reconciliation.ipynb` joins the loader's events against the 8 reconciliation reports `s06_qa.py` already writes, so every automated detection gets labeled `addressed_2023`, `addressed_2026`, `addressed_both`, or `pending`.

## Reporting cadence

- **Annual** cumulative accounting reports — every year, includes corrections trickled in since the last report.
- **Periodic big sweeps** — TRPA ran one in 2023, another in 2026, more in the future. These produce the volume of corrections in Ken's XLSX. The schema's `SweepCampaign` column flags rows from these specifically (`'2023_big_sweep'`, `'2026_big_sweep'`, etc.); rolling-correction years populate `SweepCampaign=NULL`.

## Data flow

```
                 ┌─────────────────────────────────────────────┐
                 │  Ken's XLSX (data/qa_data/CA Changes.xlsx)  │
                 │  44,371 rows × {APN, 2023 delta + reason,   │
                 │                  2026 delta + reason}       │
                 └──────────────────────┬──────────────────────┘
                                        │
                       [04_load_ca_changes.ipynb]
                                        │
                                        ▼
       ┌──────────────────────────┐    ┌─────────────────────────────┐
       │  qa_change_events.csv    │    │  qa_correction_detail.csv   │
       │  5,925 rows (parent)     │◄───┤  5,925 rows (sidecar)       │
       └────────────┬─────────────┘    └─────────────────────────────┘
                    │
                    │              ┌──────────────────────────────┐
                    │              │  s06_qa.py outputs (3 CSVs)  │
                    │              │  QA_Lost_APNs (698)          │
                    │              │  QA_FC_Units_Not_In_CSV (158K)│
                    │              │  QA_Unit_Reconciliation (60K) │
                    │              └──────────────┬───────────────┘
                    │                             │
                    └──────────[05_qa_reconciliation.ipynb]──────┐
                                                                  ▼
                                         ┌────────────────────────────────────┐
                                         │  qa_reconciliation_status.csv      │
                                         │  218,192 rows (one per s06 finding)│
                                         │  Status ∈ {addressed_*, pending}   │
                                         └────────────────────────────────────┘
                                         ┌────────────────────────────────────┐
                                         │  qa_ken_only_corrections.csv       │
                                         │  1,035 rows (Ken corrected, s06    │
                                         │  didn't flag)                      │
                                         └────────────────────────────────────┘
                                                                  │
                                                                  ▼
                                              [Future: dashboard E1, AG Grid table
                                               filterable by Status / Year / Source]
```

## Outputs reference

All in [`data/qa_data/`](../data/qa_data/):

| File | Rows | What it is |
|---|---:|---|
| `qa_change_events.csv` | 5,925 | Parent rows: subset of proposed `ParcelDevelopmentChangeEvent` columns. One per `(APN, ReportingYear)` cycle with non-zero delta. |
| `qa_correction_detail.csv` | 5,925 | Sidecar rows mirroring proposed `QaCorrectionDetail`. Carries `ReportingYear`, `SweepCampaign`, `CorrectionCategory`, `SummaryReason`, `RawAPN`, `SourceFileSnapshot`. |
| `qa_load_orphans.csv` | 4,137 | Validation issues from the loader. Mostly noncanonical category labels (Ken's wording paraphrases Sheet2's controlled vocab) — informational, not blocking. |
| `qa_reconciliation_status.csv` | 218,192 | One row per s06 finding, labeled by Ken's address status. Sourced from 3 s06 CSVs (`QA_Lost_APNs`, `QA_FC_Units_Not_In_CSV`, `QA_Unit_Reconciliation`). |
| `qa_ken_only_corrections.csv` | 1,035 | Ken's events with no matching s06 finding — pre-detection corrections, s06 false negatives, or out-of-scope work. |

## Headline numbers (latest run)

**Loader:** 5,925 events emitted (3,864 from 2023 sweep, 2,061 from 2026 sweep). **30.2% of category labels match Sheet2's canonical vocab** — Ken's Sheet1 wording paraphrases Sheet2.

**Reconciliation:** 218,192 s06 findings labeled.

| Status | Count | % |
|---|---:|---:|
| `addressed_2023` | 5,575 | 2.6% |
| `addressed_2026` | 11,051 | 5.1% |
| `addressed_both` | 8,659 | 4.0% |
| `pending` | 192,907 | **88.4%** |

By s06 source — % addressed gives QA throughput per detection type:

| Source | Total | Addressed | % |
|---|---:|---:|---:|
| `QA_Lost_APNs` | 698 | 480 | **69%** |
| `QA_Unit_Reconciliation` | 59,674 | 15,805 | 26% |
| `QA_FC_Units_Not_In_CSV` | 157,820 | 9,000 | **6%** |

**Biggest remaining QA pile:** `QA_FC_Units_Not_In_CSV` at 149K untouched detections. That's where the next sweep campaign will spend most of its time.

## Refresh workflow

When Ken sends a new XLSX (or after a future sweep):

1. Drop the new file at `from_ken/CA Changes breakdown.xlsx` (canonical, committed) or `data/qa_data/CA Changes breakdown.xlsx` (working).
2. Re-run `notebooks/04_load_ca_changes.ipynb` end-to-end (target ~30 sec for ~44K rows).
3. Re-run `notebooks/05_qa_reconciliation.ipynb` (~2 min, joins 218K s06 rows).
4. Diff the new `qa_reconciliation_status.csv` against the prior version to see "what got addressed since last run".
5. Commit the new outputs.

The loader is **idempotent on `SourceFileSnapshot`** (a string of the form `CA Changes breakdown.xlsx@2026-04-30` derived from the file's mtime). The eventual DB load will UPSERT on `(RawAPN, ReportingYear, SourceFileSnapshot)`.

## Open issues

### O1. 30% canonical-vocab match rate — needs Ken's input

Only 30.2% of Ken's Sheet1 category labels match Sheet2's controlled vocabulary exactly. The other 70% are paraphrases. Two ways to fix:

- **Option A: expand Sheet2 vocab** — add the variant labels Ken actually uses to the Sheet2 list. Loader's `VOCAB_2023` / `VOCAB_2026` sets pick them up automatically.
- **Option B: build a Sheet1→Sheet2 mapping table** — preserve Sheet2's tight 9+5 vocab; map each Sheet1 variant to its canonical equivalent in a new lookup CSV (`qa_data/correction_category_mapping.csv`).

Top noncanonical labels for Ken to triage (each has 500+ rows):

```
Corrections - Units Removed Based on County Data                                        890
Unit(s) not previously counted. Constructed in or before 2012. Verified with County.    733
Correction Based on County Data                                                         696
Mobile Home Park Corrections                                                            582
Over-Correction                                                                         349
```

Recommend **Option B** — preserves Sheet2 as the authoritative list and avoids vocabulary drift; the mapping table is easy to extend per future sweep.

### O2. Year-aware reconciliation matching

Current reconciliation matches by APN only. Refinement: a Ken cycle-Y correction can only address an s06 finding for Year X if X ≤ Y (a 2023 correction can't fix a 2024 detection). Update tightens the "addressed" count and reveals more `pending` rows for follow-up.

### O3. Compute Previous/New quantities

Ken's XLSX carries deltas only. To populate `PreviousQuantity` / `NewQuantity` on `ParcelDevelopmentChangeEvent` (per the schema), join to `from_ken/FINAL RES SUMMARY 2012 to 2025.xlsx` Residential sheet by canonical APN. Deferred from the prototype.

### O4. Resolve commodity per row

Loader currently writes `CommodityShortName='SFRUU_or_MFRUU_TBD'` because Ken's data is residential but doesn't split SFRUU/MFRUU/ADU. Once the schema lands, look up per parcel from `dbo.ParcelCommodityInventory` or the existing-development snapshot.

### O5. Promote to production script

Once stable, fold both notebooks into `parcel_development_history_etl/steps/s07_load_and_reconcile_ca_changes.py` so they run as part of the standard ETL.

## Where this fits in the broader 3-track plan

| Track | Owner concept | Status |
|---|---|---|
| **A. Genealogy → Current Parcel** | Never let an APN lose track | Existing infra (`apn_genealogy_*.csv`, `s02b_genealogy.py`); not yet swept |
| **B. Allocation Tracking** | Where allocations sit + pool drawdown | Mostly done — dashboards live (`html/allocation_drawdown.html`, `html/allocation-tracking.html`, `html/residential-additions-by-source.html`) |
| **C. QA Corrections** *(this doc)* | Track every adjustment with rationale | Schema + loader + reconciliation landed; dashboard E1 next |

Track C uses Track A's APN canonicalization (currently inlined in the loader; will switch to `parcel_development_history_etl/utils.py:el_pad` once Track A consolidates). Track C feeds Track B's per-parcel history view (`vParcelHistory` / `ParcelHistoryView`) once the DB load happens.

## Files reference

- **Schema:** [`target_schema.md`](./target_schema.md) §"ERD — QA corrections sidecar (Track C)"
- **Loader notebook:** [`../notebooks/04_load_ca_changes.ipynb`](../notebooks/04_load_ca_changes.ipynb)
- **Reconciliation notebook:** [`../notebooks/05_qa_reconciliation.ipynb`](../notebooks/05_qa_reconciliation.ipynb)
- **Trace doc:** [`dashboards_to_schema_trace.md`](./dashboards_to_schema_trace.md) §Trace 3 (Parcel History Lookup) and §G3.x gap markers
- **s06 reference:** [`../parcel_development_history_etl/steps/s06_qa.py`](../parcel_development_history_etl/steps/s06_qa.py)
- **Related skill:** [`trpa-data-engineering`](../README.md) for ETL conventions
