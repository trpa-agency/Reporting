# TRPA Dashboards

Single-file HTML pages for the TRPA Cumulative Accounting cycle. Open from a browser; no build step.

- **Base URL**: `https://trpa-agency.github.io/Reporting/html/<filename>`
- **Local preview**: from the repo root, `python -m http.server 8123` then `http://localhost:8123/html/<filename>`
- **Active dashboards**: 8 (★ marks the primary view in each track)

---

Organized by the four conceptual tracks (5/11/2026):

## 1 · Allocation tracking

> *Where every residential allocation sits.* Three pool states: **TRPA pool · Jurisdiction pool · Private development pool.**

| Dashboard | Audience | Data |
|---|---|---|
| [**allocation-tracking.html**](allocation-tracking.html) ★ | Staff · daily ops | `data/raw_data/residentialAllocationGridExport.csv` (one row per allocation, 2,600 total) |
| [pool-balance-cards.html](pool-balance-cards.html) | Staff · per-pool drilldown | the analyst's `Additional Development as of April2026.xlsx` + inlined trajectory |

## 2 · Source of rights

> *Where each year's added units came from.* Categories: Pre-1987 / 1987 RP / 2012 RP / Banked / Conversion.

| Dashboard | Audience | Data |
|---|---|---|
| [**residential-additions-by-source.html**](residential-additions-by-source.html) ★ | Leadership · public | the analyst's `FINAL RES SUMMARY 2012 to 2025.xlsx` Summary sheet |

## 3 · Total potential development

> *Constructed + Banked + Converted + still in pools.* The full pipeline.

*No standalone dashboard yet - coverage split across #1 and #4. Building out post-ESA collab in June.*

## 4 · Total development tracking

> *How much of each development right is assigned to projects.* Since-1987 totals, with by-jurisdiction and by-pool breakdowns.

| Dashboard | Audience | Data |
|---|---|---|
| [**regional-capacity-dial.html**](regional-capacity-dial.html) ★ | Executive · board | `regional_plan_allocations.json` |

The page (titled **Tahoe Development Tracker**) has three sections, stacked top to bottom:
- **4 since-1987 count gauges** (Residential / RBU / TBU / CFA) - allocations assigned to projects
- **Residential allocations by jurisdiction** - all 8,687, era toggle (Combined / 1987 Plan / 2012 Plan)
- **Bonus units, CFA & tourist allocations** - by pool, commodity toggle

## Companion views (broader development)

| Dashboard | What it shows | Data |
|---|---|---|
| [development_history.html](development_history.html) | Building footprints by era; year slider | Tahoe Buildings FeatureServer (live AGOL) |
| [development_history_units.html](development_history_units.html) | Residential units associated with buildings (sqft-weighted split) | Above + `data/processed_data/buildings_with_units.json` |
| [qa-change-rationale.html](qa-change-rationale.html) | Per-APN audit log of 2023/2026 QA corrections | `qa_change_events.csv` from `04_load_ca_changes.ipynb` |
| [genealogy_solver/](genealogy_solver/) | APN lineage lookup (single or batch CSV); full component walk + 2025 cross-reference | `apn_genealogy_tahoe.csv` + `PDH_2025_OriginalYrBuilt.csv` → `genealogy_solver.json` |

## Archived

Moved to [`_archive/`](_archive/) on 2026-05-11 - superseded by newer dashboards. Kept for reference / link-stability; not linked from the active set above.

| Dashboard | Superseded by |
|---|---|
| [`_archive/residential-allocations-dashboard.html`](_archive/residential-allocations-dashboard.html) | `allocation-tracking.html` |
| [`_archive/allocation_drawdown.html`](_archive/allocation_drawdown.html) | `allocation-tracking.html` (year slider) + `pool-balance-cards.html` |
| [`_archive/public-allocation-availability.html`](_archive/public-allocation-availability.html) | `pool-balance-cards.html` (explainer folded in) |

---

## Data sources

One row per data source. The endpoint + layer columns link to the REST resource and its specific layer ID; the upstream column links to the LT Info JSON web service for layers staged nightly via the ETL.

### Cumulative_Accounting REST service (`maps.trpa.org`, live)

| Source | Layer | Upstream (LT Info) | Schema (fields × rows) | Used by |
|---|---|---|---|---|
| Parcel Development History | [layer 0](https://maps.trpa.org/server/rest/services/Cumulative_Accounting/MapServer/0) | - (PDH ETL from Enterprise GDB) | ~30 × ~150k (parcel-year) | future dashboards |
| Tahoe APN Genealogy | [layer 1](https://maps.trpa.org/server/rest/services/Cumulative_Accounting/MapServer/1) | - (4-source ETL) | ~8 × ~25k edges | genealogy_solver (pre-joined) |
| Residential Unit Inventory | [layer 2](https://maps.trpa.org/server/rest/services/Cumulative_Accounting/MapServer/2) | - | ~15 × ~50k units | future dashboards |
| Allocations 1987 Regional Plan | [layer 3](https://maps.trpa.org/server/rest/services/Cumulative_Accounting/MapServer/3) | - | ~11 × 6,087 | combine view (planned) |
| Allocations 2012 Regional Plan | [layer 4](https://maps.trpa.org/server/rest/services/Cumulative_Accounting/MapServer/4) | - (CSV from analyst until LT Info exposes the grid) | ~11 × 2,600 | combine view (planned) |
| Development Right Pool Balance Report | [layer 5](https://maps.trpa.org/server/rest/services/Cumulative_Accounting/MapServer/5) | [GetDevelopmentRightPoolBalanceReport](https://www.laketahoeinfo.org/WebServices/GetDevelopmentRightPoolBalanceReport) (staged nightly) | 7 × ~50 (per-pool) | combine view consumer (planned) |
| Development Right Transactions | [layer 6](https://maps.trpa.org/server/rest/services/Cumulative_Accounting/MapServer/6) | [GetDevelopmentRightTransactions](https://www.laketahoeinfo.org/WebServices/GetDevelopmentRightTransactions) (staged nightly) | 25 × ~3,000 | downstream consumers (planned) |
| Banked Development Rights | [layer 7](https://maps.trpa.org/server/rest/services/Cumulative_Accounting/MapServer/7) | [GetBankedDevelopmentRights](https://www.laketahoeinfo.org/WebServices/GetBankedDevelopmentRights) (staged nightly) | 11 × ~1,500 | **allocation-tracking** (Banked tile) · **regional-capacity-dial** (banked sub-line) |
| Transacted and Banked Development Rights | [layer 8](https://maps.trpa.org/server/rest/services/Cumulative_Accounting/MapServer/8) | [GetTransactedAndBankedDevelopmentRights](https://www.laketahoeinfo.org/WebServices/GetTransactedAndBankedDevelopmentRights) (staged nightly) | 20 × ~3,000 | downstream consumers (planned) |

### External REST services

| Source | Endpoint | Schema | Used by |
|---|---|---|---|
| Tahoe Buildings (AGOL) | [Tahoe_Buildings FeatureServer / layer 0](https://services5.arcgis.com/fXXSUzHD5JjcOt1v/arcgis/rest/services/Tahoe_Buildings/FeatureServer/0) | ~20 × ~70k footprints | **development_history** · **development_history_units** |
| TRPA Parcels | [Parcels FeatureServer / layer 0](https://maps.trpa.org/server/rest/services/Parcels/FeatureServer/0) | ~15 × ~50k parcels | **allocation-tracking** (map tab) |
| AllParcels | [AllParcels MapServer](https://maps.trpa.org/server/rest/services/AllParcels/MapServer) | parcel polygons + APN | **genealogy_solver** (map) |

### Analyst-delivered files (xlsx → csv / json via converter scripts)

| Source | File | Schema | Used by |
|---|---|---|---|
| residentialAllocationGridExport | `data/raw_data/residentialAllocationGridExport.csv` | 11 × 2,600 (incl. Construction Status) | **allocation-tracking** (Overview / Charts / Table) |
| CFA / TAU allocations | `data/raw_data/CFA_TAU_allocations.csv` | ~8 × ~700 | **allocation-tracking** (CFA + TAU rows) |
| Regional Plan allocations summary | `data/processed_data/regional_plan_allocations.json` (from `All Regional Plan Allocations Summary.xlsx`; will be retired by combine view) | nested by commodity / pool / era | **regional-capacity-dial** · **pool-balance-cards** |
| FINAL RES SUMMARY 2012-2025 | `FINAL RES SUMMARY 2012 to 2025.xlsx` (inlined) | 13 years × 5 sources | **residential-additions-by-source** |
| Buildings + units join | `data/processed_data/buildings_with_units.json` | footprint OID ↔ unit count | **development_history_units** |
| QA change events + detail | `data/qa_data/qa_change_events.csv` + `qa_correction_detail.csv` (from `04_load_ca_changes.ipynb`) | per-APN audit events | **qa-change-rationale** |
| Genealogy solver pre-join | `html/genealogy_solver/data/genealogy_solver.json` (from `apn_genealogy_tahoe.csv` + `PDH_2025_OriginalYrBuilt.csv`) | graph + per-APN attrs | **genealogy_solver** |

### Refresh commands

When the analyst sends a refreshed xlsx, drop it in `data/raw_data/` and run the matching converter. All dashboards `fetch(..., {cache: 'no-cache'})` so reloads pick up new data immediately.

```bash
# Set up alias once
PY="C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe"

# Per-allocation grid → CSV (allocation-tracking)
PYTHONIOENCODING=utf-8 "$PY" parcel_development_history_etl/scripts/convert_allocation_grid.py

# Regional Plan allocations summary → JSON + 1987 baseline CSV
#   (regional-capacity-dial + pool-balance-cards)
PYTHONIOENCODING=utf-8 "$PY" parcel_development_history_etl/scripts/convert_regional_plan_allocations.py
PYTHONIOENCODING=utf-8 "$PY" parcel_development_history_etl/scripts/extract_regional_plan_1987_seed.py

# Buildings × units join → JSON (development_history_units)
PYTHONIOENCODING=utf-8 "$PY" parcel_development_history_etl/scripts/build_buildings_with_units.py

# Genealogy graph + 2025 cross-reference → JSON (genealogy_solver)
PYTHONIOENCODING=utf-8 "$PY" parcel_development_history_etl/scripts/build_genealogy_solver_data.py
```

The PDH ETL pipeline (`main.py`) is upstream of all of the above - re-run when SDE parcels or the analyst's residential CSVs change.

### Backend ETL (scheduled, not analyst-facing)

`stage_ltinfo_allocations.py` is a generic 4-pipeline runner that pulls each LT Info JSON service into a `Cumulative_Accounting` staging layer nightly via Task Scheduler:

- [`GetDevelopmentRightPoolBalanceReport`](https://www.laketahoeinfo.org/WebServices/GetDevelopmentRightPoolBalanceReport) → [layer 5](https://maps.trpa.org/server/rest/services/Cumulative_Accounting/MapServer/5) (pool balances)
- [`GetDevelopmentRightTransactions`](https://www.laketahoeinfo.org/WebServices/GetDevelopmentRightTransactions) → [layer 6](https://maps.trpa.org/server/rest/services/Cumulative_Accounting/MapServer/6) (transaction log, ~3,000 rows)
- [`GetBankedDevelopmentRights`](https://www.laketahoeinfo.org/WebServices/GetBankedDevelopmentRights) → [layer 7](https://maps.trpa.org/server/rest/services/Cumulative_Accounting/MapServer/7) (current bank state per APN)
- [`GetTransactedAndBankedDevelopmentRights`](https://www.laketahoeinfo.org/WebServices/GetTransactedAndBankedDevelopmentRights) → [layer 8](https://maps.trpa.org/server/rest/services/Cumulative_Accounting/MapServer/8) (APN-transaction junction)

The older `Development_Rights_Transacted_and_Banked` REST service is being deprecated as a tagged copy of the same Corral data. The dashboards still consume the hand-converted JSON for pool balances until the combine view + LT Info field-semantics confirmation land - see [`erd/system_of_record_roadmap.md`](../erd/system_of_record_roadmap.md).

```bash
# Nightly LT Info to Enterprise GDB staging ETL (Task Scheduler)
PYTHONIOENCODING=utf-8 "$PY" parcel_development_history_etl/scripts/stage_ltinfo_allocations.py
```

---

## Tech stack

- **Plotly.js** (charts) - load **before** ArcGIS; Dojo's AMD loader captures Plotly's UMD wrapper otherwise
- **ArcGIS Maps SDK 4.31** (maps, where needed)
- **AG Grid Community** (sortable/filterable tables)
- **Open Sans** + TRPA brand tokens (`--trpa-blue #0072CE`, `--trpa-navy #003B71`, `--trpa-orange #E87722`, `--trpa-forest #4A6118`)

See [`.claude/skills/trpa-brand`](../.claude/skills/trpa-brand) and [`.claude/skills/trpa-dashboard-stack`](../.claude/skills/trpa-dashboard-stack) for the agency conventions.

## Adding a dashboard

1. Single-file `.html` in this folder.
2. Mirror the structural pattern from `development_history.html` (navy header → KPI row → controls → split content).
3. Pre-compute heavy data into `data/processed_data/*.json` and fetch by relative path; reserve live FeatureServer queries for thin attribute pulls.
4. Add an entry above.
