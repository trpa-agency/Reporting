# TRPA Dashboards

Single-file HTML pages for the TRPA Cumulative Accounting cycle. Open from a browser; no build step.

- **Base URL**: `https://trpa-agency.github.io/Reporting/html/<filename>`
- **Local preview**: from the repo root, `python -m http.server 8123` then `http://localhost:8123/html/<filename>`
- **Active dashboards**: 9 (★ marks the primary view in each track)

---

Organized by the four conceptual tracks (5/11/2026):

## 1 · Allocation tracking

> *Where every residential allocation sits.* Three pool states: **TRPA pool · Jurisdiction pool · Private development pool.**

| Dashboard | Audience | Data |
|---|---|---|
| [**allocation-tracking.html**](allocation-tracking.html) ★ | Staff · daily ops | `data/raw_data/residentialAllocationGridExport.csv` (one row per allocation, 2,600 total) |
| [pool-balance-cards.html](pool-balance-cards.html) | Staff · per-pool drilldown | the analyst's `Additional Development as of April2026.xlsx` + inlined trajectory |
| [public-allocation-availability.html](public-allocation-availability.html) | Public | Same as pool-balance-cards |

## 2 · Source of rights

> *Where each year's added units came from.* Categories: Pre-1987 / 1987 RP / 2012 RP / Banked / Conversion.

| Dashboard | Audience | Data |
|---|---|---|
| [**residential-additions-by-source.html**](residential-additions-by-source.html) ★ | Leadership · public | the analyst's `FINAL RES SUMMARY 2012 to 2025.xlsx` Summary sheet |

## 3 · Total potential development

> *Constructed + Banked + Converted + still in pools.* The full pipeline.

*No standalone dashboard yet - coverage split across #1 and #4. Building out post-ESA collab in June.*

## 4 · Total development tracking

> *How much of everything is actually built.* Headline caps + live state breakdown + source-of-rights mix + annual construction.

| Dashboard | Audience | Data |
|---|---|---|
| [**regional-capacity-dial.html**](regional-capacity-dial.html) ★ | Executive · board | the analyst's 2026 PPTX slide 8 (gauges) + `residentialAllocationGridExport.csv` (2012 Plan cards) |

Three sections, stacked top to bottom on the page:
- **4 since-1987 cumulative gauges** (Residential / RBU / TBU / CFA)
- **Capacity utilization horizontal stacked bar**
- **2012 Plan additional grid** - 4 cards (Constructed · Private dev pool · Jurisdiction pool · TRPA pool = 2,600)

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

---

## Data sources at a glance

| Source | Used by |
|---|---|
| `residentialAllocationGridExport_fromAnalyst.xlsx` → CSV (one row per allocation, 2,600 rows, 11 cols incl. Construction Status) | allocation-tracking · regional-capacity-dial (live cards) |
| `Additional Development as of April2026.xlsx` | pool-balance-cards · public-allocation-availability · regional-capacity-dial (gauges) |
| `FINAL RES SUMMARY 2012 to 2025.xlsx` | residential-additions-by-source |
| `CA Changes breakdown.xlsx` (via `04_load_ca_changes.ipynb`) | qa-change-rationale |
| `2025 Transactions and Allocations Details.xlsx` | residential_units_inventory (downstream of development_history_units) |
| Tahoe Buildings FeatureServer (AGOL) | development_history · development_history_units |
| TRPA ArcGIS REST | allocation-tracking (map tab) |

### Refresh commands

When the analyst sends a refreshed xlsx, drop it in `data/raw_data/` and run the matching converter. All dashboards `fetch(..., {cache: 'no-cache'})` so reloads pick up new data immediately.

```bash
# Set up alias once
PY="C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe"

# Per-allocation grid → CSV (allocation-tracking + regional-capacity-dial cards)
PYTHONIOENCODING=utf-8 "$PY" parcel_development_history_etl/scripts/convert_allocation_grid.py

# Buildings × units join → JSON (development_history_units)
PYTHONIOENCODING=utf-8 "$PY" parcel_development_history_etl/scripts/build_buildings_with_units.py

# Genealogy graph + 2025 cross-reference → JSON (genealogy_solver)
PYTHONIOENCODING=utf-8 "$PY" parcel_development_history_etl/scripts/build_genealogy_solver_data.py
```

The PDH ETL pipeline (`main.py`) is upstream of all of the above - re-run when SDE parcels or the analyst's residential CSVs change.

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
