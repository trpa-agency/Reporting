# `/notebooks` — Corral vs 2025 XLSX diff + transition table

Reproducible, incremental entry point to the full ERD proposal in
[`erd/target_schema.md`](../erd/target_schema.md). Keeps v1 simple:

- **Find the gap** between Corral (live SQL Server backend at `sql24/Corral`)
  and Ken's `2025 Transactions and Allocations Details.xlsx`.
- **Stage that gap** in one flat transition table designed to fold back into
  Corral later (either as new columns on `dbo.TdrTransaction` / `dbo.ParcelPermit`
  or as the full-ERD tables like `PermitCompletion` / `CrossSystemID`).

Everything here is **read-only** against Corral. No `CREATE TABLE` runs.

## Files

| File | Purpose |
|---|---|
| `01_corral_vs_xlsx_diff.ipynb` | Row- and column-level diff. Writes `out/diff_report.{json,md}`. |
| `02_build_transition_table.ipynb` | Projects the XLSX-only columns into a transition-table shape. Writes `out/corral_transition_table.{csv,parquet}`. |
| `03_transition_table_schema.sql` | Proposed DDL — not executed. Team reviews before any schema change. |
| `out/` | Output artifacts (gitignored). |

## How to run

Kernel: `arcgispro-py3` (full path: `C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe`).

Corral connection via `erd/db_corral.py` — uses Windows Authentication;
expects `sql24/Corral` reachable. A `.env` in repo root can override
`CORRAL_SERVER` / `CORRAL_DATABASE`.

```powershell
# From repo root, launch Jupyter on arcgispro-py3
& "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" -m jupyter notebook
```

Then open `notebooks/01_corral_vs_xlsx_diff.ipynb` first.

## What the transition table holds

Single staging table keyed on `TdrTransactionID` (FK handle back to
`dbo.TdrTransaction`), carrying the 8 XLSX columns Corral doesn't source
plus linkage bookkeeping. See [`03_transition_table_schema.sql`](./03_transition_table_schema.sql)
for the full column list and the rationale for staying flat at this phase.

## How this folds back into Corral

When the TRPA dev team is ready, the transition table splits cleanly:

- `AllocationNumber`, `TransactionCreatedDate`, `TransactionAcknowledgedDate`
  → new columns on `dbo.ResidentialAllocation`.
- `YearBuilt`, `PmYearBuilt`, `DetailedDevelopmentType`, `SupplementalNotes`
  → `PermitCompletion` sidecar (see target_schema.md ERD — permit completion).
- `TrpaMouProjectNumber` → `CrossSystemID` rows with `IDType='trpa_mou'`.
- `SourceFile`, `SourceRowNumber`, `LinkageStatus` dropped at that point.
