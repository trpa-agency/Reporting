# TRPA Dashboards — Index

> Single-file HTML dashboards for the TRPA Cumulative Accounting cycle and parcel-development history. Each page loads its libraries from CDN; no build step required. Drop the file into a browser or open the GitHub Pages link below.

**Base URL** (all pages): `https://trpa-agency.github.io/Reporting/html/<filename>`

**Local preview** — from the repo root:

```bash
PYTHONIOENCODING=utf-8 "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" -m http.server 8123
# then open http://localhost:8123/html/<filename>
```

The `.claude/launch.json` config wires this up for the Claude Code preview MCP — call `preview_start` with name `html-static`.

---

## Cumulative-accounting headline views

### [Regional Plan Capacity Dial](https://trpa-agency.github.io/Reporting/html/regional-capacity-dial.html)

> Local: [`regional-capacity-dial.html`](regional-capacity-dial.html)

Where the Tahoe Region sits against its since-1987 cumulative capacity caps. One gauge per commodity (residential allocations, residential bonus units, tourist bonus units, commercial floor area) showing constructed vs Regional Plan maximum.

- **Data:** inlined from `from_ken/Cumulative Accounting 2026 Report.pptx` slide 8 and `from_ken/Additional Development as of April2026.xlsx`
- **Target SDE table:** `CumulativeAccountingSnapshot` aggregated to Regional totals (see [`erd/dashboards_to_schema_trace.md`](../erd/dashboards_to_schema_trace.md) Trace 1; Cluster A1)
- **Audience:** executive / board level — headline numbers

### [Residential Additions by Source](https://trpa-agency.github.io/Reporting/html/residential-additions-by-source.html)

> Local: [`residential-additions-by-source.html`](residential-additions-by-source.html)

Where the 1,573 added residential units came from each year, 2013–2025. Lines / stacked area / stacked percent toggle. Net growth of 1,469 after 110 removals (banked or converted out).

- **Data:** compiled from `from_ken/FINAL RES SUMMARY 2012 to 2025.xlsx` — Summary sheet's "Added Residential Units from {Allocations, Bonus Units, Transfers, Conversions, Banked}" rows + per-year "Major Completed Projects" column
- **Ultimate source:** `dbo.TdrTransaction` + `dbo.ParcelPermitBankedDevelopmentRight` + `dbo.ResidentialBonusUnit*` in Corral; once `vCommodityLedger` exists it reads directly
- **Audience:** analysts, leadership, public — the story of new construction by mechanism

---

## Allocation tracking & drawdown

### [Allocation Tracking](https://trpa-agency.github.io/Reporting/html/allocation-tracking.html)

> Local: [`allocation-tracking.html`](allocation-tracking.html)

Comprehensive operational dashboard: 2,600 authorized 2012 Regional Plan additional · of 8,687 since-1987 max. Tabs for charts / map / data table; filters by type, jurisdiction, year. AG Grid with CSV export.

- **Data:** live from TRPA ArcGIS REST services + permit system
- **Audience:** allocation staff (daily ops); the most feature-complete page
- **Stack:** Plotly + Calcite + ArcGIS Maps SDK + AG Grid — the reference implementation called out in [`trpa-dashboard-stack`](../.claude/skills/trpa-dashboard-stack/SKILL.md)

### [Residential Allocation Drawdown](https://trpa-agency.github.io/Reporting/html/allocation_drawdown.html)

> Local: [`allocation_drawdown.html`](allocation_drawdown.html)

Stacked area chart of residential allocation drawdown by pool × year. Shows how each jurisdiction's pool has been used down from its original capacity.

- **Data:** Ken's *LT Info Pool Balance Report* snapshot (with TRPA Pool 144→154 correction applied)
- **Target SDE table:** `PoolDrawdownYearly` (see Trace 2)

### [Pool Balance Cards](https://trpa-agency.github.io/Reporting/html/pool-balance-cards.html)

> Local: [`pool-balance-cards.html`](pool-balance-cards.html)

Daily-use staff view. One card per residential allocation pool with current remaining count, percent of original capacity drawn down, and trajectory since 2013. Click any card for per-year detail.

- **Data:** remaining counts inlined from `from_ken/Additional Development as of April2026.xlsx` LT Info Pools Balances sheet (with the TRPA Pool 144→154 correction). Per-year trajectory inlined from `allocation_drawdown.html`'s embedded series.
- **Target SDE table:** `PoolDrawdownYearly` (Trace 2 / G2.1)
- **Audience:** allocation staff

### [Residential Allocation Availability](https://trpa-agency.github.io/Reporting/html/public-allocation-availability.html)

> Local: [`public-allocation-availability.html`](public-allocation-availability.html)

Public-facing slice of the pool-balance dashboard. How many residential allocations remain in each Lake Tahoe Basin jurisdiction — county / city searchable.

- **Data:** `from_ken/Additional Development as of April2026.xlsx` LT Info Pools Balances sheet (TRPA Pool 144→154 correction applied)
- **Audience:** public — simplified version of the staff `pool-balance-cards.html` (Cluster G1)

### [Tahoe Residential Allocations](https://trpa-agency.github.io/Reporting/html/residential-allocations-dashboard.html)

> Local: [`residential-allocations-dashboard.html`](residential-allocations-dashboard.html)

Detailed allocations table with AG Grid filters/exports. The largest dashboard in the folder — likely a v1 staff workspace before the more focused B1/G1 splits were built.

- **Data:** allocations registry (in-page)
- **Audience:** staff — granular per-allocation lookup

---

## Development history (new)

### [Development History — Buildings](https://trpa-agency.github.io/Reporting/html/development_history.html)

> Local: [`development_history.html`](development_history.html)

Map of every building footprint in the Lake Tahoe Basin, colored by Regional Plan era of construction. Drag the year slider (1900–2025) to play back development. Two charts on the right: stacked-area cumulative buildings, per-year construction histogram.

- **Map source:** live [Tahoe Buildings FeatureServer](https://services5.arcgis.com/fXXSUzHD5JjcOt1v/arcgis/rest/services/Tahoe_Buildings/FeatureServer/0) (Esri AGOL mirror of `Buildings_2019` GDB)
- **Chart source:** statistics query on the same FeatureServer (count of buildings grouped by `YEAR_BUILT`)
- **Era classification:** `≤1987` Pre-1987 Plan / `1988–2011` 1987 Plan / `≥2012` 2012 Plan
- **Audience:** planners, analysts; great for spotting development booms and the post-1987 slow-down

### [Development History — Residential Units](https://trpa-agency.github.io/Reporting/html/development_history_units.html)

> Local: [`development_history_units.html`](development_history_units.html)

Companion to the buildings dashboard, pivoted to **residential units**. Each parcel's units are split across its building footprints in proportion to `Square_Feet` (Hamilton's largest-remainder method). KPI cards show residential buildings vs multifamily; charts show cumulative units and the units-per-building distribution. Map filter toggle: All buildings / Residential / Multifamily.

- **Pre-computed source:** [`data/processed_data/buildings_with_units.json`](../data/processed_data/buildings_with_units.json) — 44,739 buildings each tagged with `units_assigned`, `era`, `year_built`
- **Built by:** [`parcel_development_history_etl/scripts/build_buildings_with_units.py`](../parcel_development_history_etl/scripts/build_buildings_with_units.py) — joins `residential_units_inventory_2025.csv` × `buildings_inventory_2025.csv`
- **Map layer:** Tahoe Buildings FeatureServer (same as the buildings dashboard); the filter toggle uses an `OBJECTID IN (…)` definitionExpression built from the JSON
- **Audience:** housing analysts. Caveats (ADUs, post-2019 construction without footprints) called out in the in-page footnote.

---

## QA / audit

### [QA Change Rationale Audit Trail](https://trpa-agency.github.io/Reporting/html/qa-change-rationale.html)

> Local: [`qa-change-rationale.html`](qa-change-rationale.html)

Per-APN audit log of QA corrections to existing residential development. Captures the 2023 and 2026 big-sweep correction campaigns out of Ken's `CA Changes breakdown.xlsx`. Searchable by APN, change type, year.

- **Data:** `qa_change_events.csv` + `qa_correction_detail.csv` — outputs of `notebooks/04_load_ca_changes.ipynb`. Joined client-side on `ChangeEventID`.
- **Refresh:** re-run the notebook when Ken sends a new XLSX
- **Track docs:** [`erd/qa_corrections_track.md`](../erd/qa_corrections_track.md) (Track C)

---

## Data sources at a glance

| Source | What's in it | Used by |
|---|---|---|
| `from_ken/Additional Development as of April2026.xlsx` | LT Info pool balances · banked development · headline balances | `pool-balance-cards`, `public-allocation-availability`, `regional-capacity-dial` |
| `from_ken/FINAL RES SUMMARY 2012 to 2025.xlsx` | Per-APN 14-year residential history + per-year added/removed totals | `residential-additions-by-source` (raw also drives the PDH ETL) |
| `from_ken/CA Changes breakdown.xlsx` | Per-APN audit log of 2023 + 2026 QA correction campaigns | `qa-change-rationale` |
| `from_ken/Cumulative Accounting 2026 Report.pptx` slide 8 | Headline Regional Plan caps + constructed counts | `regional-capacity-dial` |
| `from_ken/2025 Transactions and Allocations Details.xlsx` | Per-APN TransactionID, Development Right, Allocation Number, TRPA/Local Permit # | `residential_units_inventory_2025.csv` Source/Pool/Permit columns (consumed by the units dashboard) |
| `from_ken/OriginalYrBuilt.xlsx` → `data/raw_data/original_year_built.csv` | Per-APN original year built, 284K rows | `PDH_2025_OriginalYrBuilt.csv` derivation |
| Tahoe Buildings FeatureServer (AGOL) | Live building footprints; YEAR_BUILT, BUILDING_SQFT, APN | both `development_history*` pages |
| Parcels FeatureServer (`maps.trpa.org`) | Live parcel attributes incl. APO_ADDRESS, YEAR_BUILT | `residential_units_inventory` (addresses, county-source year built filler) |
| `C:\GIS\ParcelHistory.gdb\Parcel_Development_History` | Authoritative per-parcel-per-year unit history; 2012–2025 | upstream of every residential dashboard |
| TRPA ArcGIS REST | Live allocations + permit data | `allocation-tracking`, `residential-allocations-dashboard` |
| Corral (`sql24`, Feb-2024 snapshot) | The LTinfo backend — `dbo.TdrTransaction`, `dbo.ParcelPermitBankedDevelopmentRight`, etc. | Ultimate source for `residential-additions-by-source`; not queried live yet |

For the full ERD / proposed-schema work see [`../erd/`](../erd/) — start with [`erd/README.md`](../erd/README.md).

---

## Tech stack (consistent across all pages)

- **Plotly.js** (charts) — load **before** ArcGIS, otherwise Dojo's AMD loader captures Plotly's UMD wrapper and `window.Plotly` is never set
- **ArcGIS Maps SDK 4.31** (maps) — only on pages that need a map
- **AG Grid Community** (tables) — `allocation-tracking`, `residential-allocations-dashboard`, `qa-change-rationale`
- **Calcite Design System** — used on `allocation-tracking`; the rest use a lightweight custom CSS with the TRPA palette
- **Open Sans** from Google Fonts
- All CSS variables defined per [`trpa-brand`](../.claude/skills/trpa-brand/SKILL.md): `--trpa-blue #0072CE` / `--trpa-navy #003B71` / `--trpa-orange #E87722` / `--trpa-forest #4A6118`

## Adding a new dashboard

1. Drop a new `.html` file in this folder. Single-file is the rule — no `node_modules/`, no build step.
2. Use the structural pattern from [`development_history.html`](development_history.html) (header → KPI row → toggle/slider bar → split content). Mirror brand tokens.
3. If you need server-side data, prefer pre-computing into `data/processed_data/*.json` and `fetch('../data/processed_data/<file>')` — keeps the page snappy. Live FeatureServer queries are fine for thin attribute pulls.
4. Add an entry here.
5. Commit. GitHub Pages picks it up automatically.
