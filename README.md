# TRPA Reporting

Scripts, notebooks, and ETL pipelines for TRPA's annual reporting and
cumulative-accounting workflows. Source systems: Corral (LTinfo backend at
`sql24/Corral`), Accela, ArcGIS enterprise geodatabase, plus analyst
spreadsheets under `data/raw_data/`.

## Python environment

Canonical env: ArcGIS Pro's `arcgispro-py3`.

- Interpreter: `C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe`
- Jupyter kernel: `arcgispro-py3`
- Plain `python` / `python3` / `py` do **not** work from bash — use the full path above.
- `arcpy` ships with ArcGIS Pro; `requirements.txt` covers everything else.

To install additions, clone the env and pip-install into the clone:

```powershell
conda create --clone arcgispro-py3 --name arcgispro-py3-work
conda activate arcgispro-py3-work
pip install -r requirements.txt
```

## Folder map

| Path | Purpose |
|---|---|
| `data/raw_data/` | Canonical source spreadsheets + archival snapshots (see `Archive/`) |
| `data/permit_data/`, `data/processed_data/`, `data/qa_data/` | ETL inputs/outputs + QA exports |
| `development_rights_etl/` | Development-rights transfers analysis (single-script + notebook) |
| `parcel_development_history_etl/` | Full parcel-history pipeline: `main.py` + `steps/` + `scripts/` + `validation.py` |
| `notebooks/` | Reproducible Corral-vs-XLSX diff + the transition-table build (v1 staging) |
| `erd/` | Schema design docs + validators + Corral schema dump (published to GitHub Pages) |
| `general/` | Legacy pre-refactor scripts + notebooks (superseded by the two `*_etl/` folders) |
| `html/` | Static dashboards published to GitHub Pages |
| `resources/` | Lookup tables + reference spreadsheets |
| `utils.py` | Shared helpers imported by `general/`; also imported as local `utils` inside `parcel_development_history_etl/` (that folder has its own `utils.py`) |

## GitHub Pages

`.github/workflows/pages.yml` renders `erd/*.md` → `erd/*.html` on every push
to `master` and publishes the whole repo as the static site
(`.nojekyll` at root). Dashboards under `html/` and docs under `erd/` are the
public-facing artifacts.

## Where new work goes

- **Schema-design docs** → `erd/` (Markdown; HTML regenerates in CI).
- **Reproducible analyses** → `notebooks/` (Jupyter, `arcgispro-py3` kernel).
- **Production pipelines** → `development_rights_etl/` or
  `parcel_development_history_etl/` depending on domain.
- **Static dashboards** → `html/` (served by Pages).

## Data Sources

- `F:\Research and Analysis\Reporting\Annual Reports\...` — internal snapshots
- Corral at `sql24/Corral` — live read via `erd/db_corral.py` (Windows Auth, read-only)
- Accela permit workflow — via Corral's `AccelaCAPRecord` bridge

## Tasks (active)

### Cumulative Accounting of Residential Units, TAU, and CFA

See `erd/target_schema.md` for the v1+ design. `notebooks/` holds the v1
staging work (transition table from Ken's XLSX).

### Count of Permits by Category

Accela permits summarized by Reporting Category. Steps:
- Delete TMP files; establish Reporting Category from Record Type
- Filter out Plan Revision records (strip `-01` suffix, secondary lookup)
- Count files by Reporting Category for the current year

### Tree Permit Activity

Batch Engine workflow, filtered by year. Merge with main Accela permit CSV on
File Number. Metrics: tree removal applications by year, total trees approved
per permit, Tree Total by reason, `% applications with reason X checked`.
Exclude permits created by BBARR (Fire District on TRPA's behalf).

### Banked Development Rights Analysis

Banked rights by type, land capability, location, jurisdiction. Group by
High Capability / Low Capability / SEZ. Banked before and after 12/12/12.
IPES score: 0 = SEZ, 1–725 = Low Capability, ≥726 = High Capability.

### Inactive Parcels to Current APN

Genealogy-based APN resolution — see
`parcel_development_history_etl/GENEALOGY.md`.
