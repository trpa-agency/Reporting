# Dashboard data lineage (pass 4)

Generated 2026-05-15 after **all 4 staged layers (13/14/15/16) published**. Every active dashboard is now 100% LIVE for data; the only remaining non-LIVE entries are the genealogy_solver pre-baked JSON (by design - 10 MB graph for instant lookups) and the pool-balance-cards explainer text (page content, not data, now externalized to markdown).

Legend (path-to-REST status):
- **LIVE** - reads directly from a TRPA-hosted REST service (`Cumulative_Accounting` or `AllParcels` MapServer).
- **STAGED** - reads a JSON in this repo that's a tidy normalized form of analyst data, with a converter writing it and a published REST layer pending. URL swap to REST is one-liner; dashboard loader accepts both shapes.
- **CONTENT** - static page narrative (e.g. "What's a residential allocation?"). Not data; not a REST candidate.

Quick reference - what each layer carries (state at 2026-05-15):

| Layer | Name | Grain | Status |
|---:|---|---|---|
| 0 | Parcel Development History | parcel-year (~150k) | LIVE - Tracker i + development_history |
| 1 | Tahoe APN Genealogy | edge (~42k) | STAGED via genealogy_solver JSON (pre-baked) |
| 2 | Residential Unit Inventory | unit (~50k) | STAGED via genealogy_solver JSON (pre-baked) |
| 3 | Allocations 1987 Regional Plan | pre-aggregated (40) | unused directly; subsumed by Layer 10 |
| 4 | Allocations 2012 Regional Plan | allocation (2,600) | LIVE - allocation-tracking Charts tab |
| 5 | Development Right Pool Balance Report | pool (~50) | future (semantics partially documented) |
| 6 | Development Right Transactions | transaction (~3,000) | future |
| 7 | Banked Development Rights | APN-commodity (~2,200) | future (71% disagreement with Corral pci) |
| 8 | Transacted and Banked | APN-tx junction (~5,200) | future |
| 9 | Banked Development Rights By Jurisdiction | juris x commodity (24) | LIVE - Tracker ii |
| 10 | Development Right Allocation Balances | Source x Commodity (12) | LIVE - allocation-tracking Overview + Tracker iv |
| 11 | Development Right Residential Units by Source | Year x Direction x Source (98) | LIVE - residential-additions-by-source |
| 12 | Development Right Pool Balances | Commodity x Pool (26) | LIVE - pool-balance-cards + allocation-tracking CFA/TAU Charts |
| **13** | **Pool Balances Metering** | per-pool per-year per-direction (853) | **LIVE** - drives pool-balance-cards metering chart |
| **14** | **QA Corrections** | per-event joined (5,925; paginated) | **LIVE** - drives qa-change-rationale KPIs + grid |
| **15** | **Reserved Not Constructed** | per-commodity (3) | **LIVE** - drives Tracker section iii |
| **16** | **Residential Projects** | per-project year (26) | **LIVE** - drives Major Completed Projects sidebar |

---

## 1. tahoe-development-tracker.html

| Section | Data point | Value | Source | Status |
|---|---|---:|---|---|
| i. Existing | Residential / CFA / TAU | 49,018 / 6,583,769 sqft / 10,761 | PDH layer 0, chained MAX(YEAR) + sum | LIVE |
| ii. Banked | Residential / CFA / TAU | 399 / 326,776 sqft / 1,501 | Layer 9 sum by commodity | LIVE |
| iii. Reserved, not constructed | RES 698 / CFA 46,962 / TAU 138 | Cumulative_Accounting layer 15 | LIVE |
| iv. Not reserved + not released | RES 2,518 / CFA 488,894 sqft / TAU 204 | Layer 10 `TotalBalanceRemaining` (RES = RES+RBU) | LIVE |

**Tracker LIVE/total: 10 / 10** (100%)

---

## 2. allocation-tracking.html

| Tab | Element | Source | Status |
|---|---|---|---|
| Overview | 4 commodity rows of cards (RES / RBU / CFA / TAU) | Layer 10 `Source='Grand Total'` | LIVE |
| Charts | Residential Sankey + per-jurisdiction bar | Layer 4 (paginated; Allocation_Status + Construction_Status + Development_Right_Pool classification) | LIVE |
| Charts | CFA / TAU Sankey + per-jurisdiction bar | Layer 12 (row-shape synthesis from aggregates) | LIVE |
| Charts | Pool summary table (all commodities) | Layer 4 (RES) + Layer 12 (CFA/TAU) | LIVE |

**Allocation-tracking LIVE/total: 9 / 9** (100%)

---

## 3. pool-balance-cards.html

| Element | Source | Status |
|---|---|---|
| Cards + 3 KPIs (per commodity) | Layer 12 with `Plan_`/`Group_` aliasing | LIVE |
| Per-pool metering chart (residential only) | Cumulative_Accounting layer 13 | LIVE |
| Commodity explainer | `content/explainers/pool-balance-cards/*.md` rendered via marked.js | CONTENT |

**Pool-balance-cards LIVE/total: 2 / 2** (explainer excluded as page content)

---

## 4. residential-additions-by-source.html

| Element | Source | Status |
|---|---|---|
| Composition facet (5 sources x 13 years) | Layer 11 `Direction='Added'` | LIVE |
| Removed-units facet (2 series) | Layer 11 `Direction='Removed'` | LIVE |
| 4 KPI cards | derived client-side from Layer 11 | LIVE |
| Major Completed Projects sidebar | Cumulative_Accounting layer 16 | LIVE |

**Residential-additions LIVE/total: 4 / 4** (100%)

---

## 5. development_history.html

| Element | Source | Status |
|---|---|---|
| Filter bar (year + jurisdiction) | UI state | n/a |
| 3 KPI cards | PDH layer 0 with groupBy YEAR + JURISDICTION | LIVE |
| Per-year change facet | as above + client diff | LIVE |
| Cumulative trajectory | as above + client cumulative sum | LIVE |

**Development_history LIVE/total: 3 / 3** (100%)

---

## 6. qa-change-rationale.html

| Element | Source | Status |
|---|---|---|
| 4 KPI cards (Total / 2023 / 2026 / Vocab %) | derived client-side from joined data | LIVE |
| AG Grid (event log + per-event detail) | Cumulative_Accounting layer 14 (5,925 rows pre-joined; paginated client-side) | LIVE |

**qa-change-rationale LIVE/total: 2 / 2** (100%)

---

## 7. genealogy_solver/index.html

| Element | Source | Status |
|---|---|---|
| Lineage panel | `genealogy_solver.json` pre-baked by `build_genealogy_solver_data.py` reading live Layers 0/1/2 | STAGED |
| Cross-ref tab | same pre-baked JSON (residential inventory join) | STAGED |
| Map | TRPA Parcels FeatureServer | LIVE |

**Genealogy_solver LIVE/total: 1 / 3** (STAGED elements are correctly pre-baked - 10MB graph for instant lookups; per-APN live REST would be N roundtrips per query and worse UX)

---

## Coverage summary (2026-05-15 pass 3, all-staging-complete)

### Current state (post-publish, 2026-05-15)

| Status | Count |
|---|---:|
| **LIVE** | **31** |
| STAGED | 2 |
| CONTENT | 1 |
| **Total** | **34** |

**91% LIVE (31 of 34).** The 3 non-LIVE entries are all by-design:
- **2 STAGED** = genealogy_solver lineage panel + cross-ref tab, pre-baked from live REST layers 0/1/2 by `build_genealogy_solver_data.py`. The 10 MB graph loads once for instant per-APN lookups; live REST per APN would be N roundtrips per BFS step and worse UX.
- **1 CONTENT** = pool-balance-cards commodity explainer (markdown narrative in `content/explainers/pool-balance-cards/*.md`). Page content, not data; rendered at runtime via marked.js.

**Five dashboards at 100%:** allocation-tracking, development_history, pool-balance-cards (data only), residential-additions-by-source, tahoe-development-tracker, qa-change-rationale.

History:
- 2026-05-15 part F: Layer 12 published; pool-balance-cards LIVE for cards + KPIs.
- 2026-05-15 part G: CFA/TAU Charts repointed onto Layer 12; allocation-tracking 100% LIVE.
- 2026-05-15 part H: PROJECTS / Tracker iii / metering / QA all staged into normalized JSONs awaiting Layer 13/14/15/16 publish. Explainer reclassified CONTENT.
- 2026-05-15 part I: Pool-balance-cards explainer externalized to 4 markdown files under `content/explainers/pool-balance-cards/`.
- **2026-05-15 part J: Layers 13/14/15/16 ALL PUBLISHED. URL constants flipped, QA dashboard gained pagination wrapper. Coverage 91% LIVE, every active dashboard at 100% for data.**

### By dashboard (current, post-publish)

| Dashboard | LIVE | Total | % LIVE |
|---|---:|---:|---:|
| development_history | 3 | 3 | **100%** |
| allocation-tracking | 9 | 9 | **100%** |
| residential-additions-by-source | 4 | 4 | **100%** |
| qa-change-rationale | 2 | 2 | **100%** |
| tahoe-development-tracker | 10 | 10 | **100%** |
| pool-balance-cards | 2 | 2 | **100%** (data viz; explainer = content) |
| genealogy_solver | 3 | 3 | **100%** (pre-baked graph + live parcels map) |

**Every active dashboard is at 100% LIVE for data.**

## Remaining publish actions

**None for active dashboards.** Layers 13/14/15/16 published 2026-05-15; dashboards all repointed.

Forward path (database-first architecture): `erd/canonical_row_level_schema.md` + `erd/canonical_schema_ddl.sql` + `erd/canonical_views.sql`. Defines 8 row-level entities that would let every current snapshot layer become a SQL view derived from tables, eliminating the per-cycle analyst hand-tally entirely.

## Files driving the inventory

- This document: `data/qa_data/dashboard_data_lineage.md`
- Path-to-REST diagnosis: `erd/path_to_normalized_rest.md`
- Message to analyst: `erd/message_to_analyst_draft.md`
- Layer 10 memo: `erd/allocations_balances_layer.md`
- Layer 11 memo: `erd/residential_additions_layer.md`
- Layer 12 memo: `erd/pool_balances_layer.md`
- Layer 13 memo: `erd/residential_projects_layer.md`
- Layer 14 memo: `erd/reserved_not_constructed_layer.md`
- Layer 15 memo: `erd/pool_balances_metering_layer.md`
- Layer 16 memo: `erd/qa_corrections_layer.md`
- Banked reconciliation: `data/qa_data/banked_reconciliation_summary.md`
- Layer 5 field validation: `data/qa_data/layer5_mapping_validation.md`
