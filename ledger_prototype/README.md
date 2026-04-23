# `/ledger_prototype` — CSV-only prototype of the development-rights ledger

Flat-file proof that the two-table ledger model from
[`erd/target_schema.md`](../erd/target_schema.md) (refined in the plan file)
actually reproduces TRPA's §16.8.2 cumulative accounting totals before we
commit to any SDE DDL.

## Files

| Path | Role |
|---|---|
| `build_ledger.ipynb` | The one notebook. Pulls from Corral + the notebooks/ transition table, writes every CSV below, runs validators. |
| `data/account.csv` | Chart of accounts. `(AccountScope, JurisdictionID or CommodityPoolID, CommodityID, BucketType) → AccountID`. Static reference. |
| `data/ledger_entry.csv` | The facts. Every bucket-to-bucket movement from Corral `TdrTransaction*` + banking + (future) GIS FC + manual. |
| `data/ledger_entry_annotation.csv` | Ken's XLSX-unique permit metadata, joined to the matching ledger entry via `TdrTransactionID`. |
| `data/conversion_ratio.csv` | `600 CFA = 2 TAU = 2 SFRUU = 3 MFRUU` lookup (12 rows, hardcoded). |
| `views/v_cumulative_accounting.csv` | `(Year, Jurisdiction, Commodity, BucketType) → Balance`. Pivoted to columns per bucket. |
| `views/v_pool_drawdown.csv` | `(Year, CommodityPoolID)` pivoted by MovementType. |

`data/*.csv` and `views/*.csv` are gitignored except for
`data/conversion_ratio.csv` (small, hardcoded, useful to diff).

## Run

Kernel: `arcgispro-py3`.

```powershell
& "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" -m jupyter notebook
```

Open `build_ledger.ipynb`, Restart & Run All. Expect ~30s end to end once
cells are stable.

## What this isn't

- **Not DDL.** No schema changes anywhere. The six CSVs stand in for the
  six tables; views are derived CSVs.
- **Not comprehensive.** `ParcelSpatialAttribute`, `ParcelGenealogyEventEnriched`,
  and `CrossSystemID` from the target ERD are not in this prototype —
  they're orthogonal to the ledger mechanics and will land with the SDE
  build.
- **Not the GIS side.** The GIS-FC reader branch (Phase 3 of the SDE plan)
  isn't in scope here. Ledger facts come from Corral TDR + banking + the
  transition table only.
- **Not validated end-to-end yet.** Five questions are outstanding in
  [`erd/email_to_ken_ledger_v1.md`](../erd/email_to_ken_ledger_v1.md);
  `MaxCapacity` stays null and the 2023-report-match check may fail until
  those answers land.

## What "good" looks like after tomorrow

1. Notebook runs cleanly on `arcgispro-py3`.
2. `ledger_entry.csv` ~2,800 rows.
3. `SUM(Quantity) GROUP BY EventID = 0` for all balanced MovementTypes.
4. `v_cumulative_accounting.csv` 2023 SFRUU totals land within ±50 units of
   the [public 2023 report](https://thresholds.laketahoeinfo.org/CumulativeAccounting/Index/2023).
5. Any deltas are captured as findings in the last cell of the notebook.
