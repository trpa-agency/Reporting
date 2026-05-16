# PoolBalances - new Cumulative_Accounting REST layer

Designed 2026-05-15. Normalization of the analyst's `All Regional Plan Allocations Summary.xlsx` Combined-plan-era summary into a flat long-form table. Path-to-REST for the cards rendered by `pool-balance-cards.html`.

## Source

- **File**: `data/from_analyst/All Regional Plan Allocations Summary.xlsx`
- **Intermediate JSON**: `data/processed_data/regional_plan_allocations.json` (produced by `convert_regional_plan_allocations.py` from the raw xlsx)
- **This converter**: `scripts/convert_pool_balances.py` reads the intermediate JSON (not the raw xlsx) and pivots the per-jurisdiction / per-pool nested structure into 26 flat rows.
- **Cadence**: snapshot. Re-run when the analyst sends a refreshed Allocations Summary xlsx.
- **As-of date**: pulled from the xlsx meta block (currently `May 12, 2026`); normalize to ISO before loading to SDE.

## Identity preserved

For every row:
```
RegionalPlanMaximum = AssignedToProjects + NotAssigned
```
All 26 rows pass at 2026-05-15. The converter checks and warns on mismatch.

## Normalized schema (proposed SDE table)

```sql
CREATE TABLE dbo.PoolBalances (
    ObjectID              INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    Commodity             VARCHAR(40)  NOT NULL,  -- 'Residential Allocations' | 'Residential Bonus Units' | 'Commercial Floor Area' | 'Tourist Accommodation Units'
    CommodityCode         VARCHAR(4)   NOT NULL,  -- 'RES' | 'RBU' | 'CFA' | 'TAU'
    Plan                  VARCHAR(15)  NOT NULL,  -- 'Combined' (1987 + 2012 splits stay in source JSON for now)
    Pool                  VARCHAR(80)  NOT NULL,  -- jurisdiction OR TRPA pool name OR 'Unreleased'
    "Group"               VARCHAR(80)  NOT NULL,  -- 'Jurisdiction' | 'TRPA pools' | 'Unreleased' | etc.
    RegionalPlanMaximum   INT          NOT NULL,
    AssignedToProjects    INT          NOT NULL,
    NotAssigned           INT          NOT NULL,
    AsOfDate              DATE         NOT NULL,
    LoadedDate            DATE         NOT NULL,
    SourceFile            VARCHAR(120) NOT NULL,
    CONSTRAINT UQ_PoolBalances UNIQUE (CommodityCode, Pool, Plan, AsOfDate)
);
```

`Group` is quoted because it's a SQL reserved word in some contexts.

### Why Combined only

The pool-balance-cards dashboard renders the Combined view (1987 + 2012 totals). The 1987 / 2012 splits are interesting but no dashboard surfaces them yet; keeping the layer scoped to Combined keeps the row count at 26 and avoids publishing unused data. When a future dashboard wants the era splits, add a second pass that pulls from `residential.by_jurisdiction[i].plan_1987` and `plan_2012` (and the analogous nested keys for RBU/CFA/TAU).

### Why this is a separate layer from Layer 10

Layer 10 ("AllocationsBalances") carries commodity-total rows (12 rows = 3 Sources x 4 Commodities). It doesn't break out per-jurisdiction / per-pool. Layer 12 ("PoolBalances") adds that pool-grain detail. They could be UNION-able views over a common base table if we ever want to consolidate; today they ship as separate tables.

## Publishing path

1. **Run converter** (already wired - run after `convert_regional_plan_allocations.py`):
   ```bash
   PYTHONIOENCODING=utf-8 \
     "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" \
     parcel_development_history_etl/scripts/convert_pool_balances.py
   ```
   Emits `data/processed_data/pool_balances.csv` (26 rows) + `.json`.

2. **Load to SDE**:
   - Normalize AsOfDate to ISO (`2026-05-12` instead of `May 12, 2026`)
   - Create the empty table per the DDL above
   - Bulk insert from the CSV
   - Refresh-load pattern: delete rows matching the new AsOfDate, then re-insert

3. **Publish to REST**:
   - Add the table to the Cumulative_Accounting MapServer source mxd/aprx (no spatial join; standalone table)
   - Republish the service
   - Resulting endpoint: `https://maps.trpa.org/server/rest/services/Cumulative_Accounting/MapServer/12`
   - Smoke test:
     ```
     /12/query?where=CommodityCode%3D%27RES%27&outFields=*&f=json
     ```
     Should return 7 rows for residential.

4. **Update `index.html`** Data Sources table - add a row for layer 12.

5. **Repoint dashboard**: `pool-balance-cards.html` currently reads `regional_plan_allocations.json` directly. After this layer lands, swap the URL constant from the local JSON to layer 12. The dashboard already has a `loadPoolBalances()` shim (added on the intermediate repoint step) that accepts both ESRI features form and the local JSON form, so the swap is a single URL change.

## Per-year residential metering (NOT in this layer)

The pool-balance-cards detail panel shows a per-year released-vs-assigned metering chart when a residential pool is selected. That data lives in `regional_plan_allocations.json` `residential.by_year.released` + `assigned`. It needs a temporal dimension Layer 12 lacks (Layer 12 is current-state per pool, not time-series). Options:

- **Layer 13 PoolBalancesMeteringByYear** (deferred): schema `(Commodity, Pool, Year, Direction, Units)` with ~600 rows. Same converter pattern. Defer until we've decided whether other commodities (RBU/CFA/TAU) want per-year metering too - currently the analyst only publishes it for residential.
- **Keep the JSON for metering only**: dashboard loads layer 12 for cards + KPIs, layer 13 (or the JSON) for the metering chart. Acceptable interim.

## Files

- Source xlsx: `data/from_analyst/All Regional Plan Allocations Summary.xlsx`
- Intermediate JSON: `data/processed_data/regional_plan_allocations.json` (existing converter)
- New flat converter: `parcel_development_history_etl/scripts/convert_pool_balances.py`
- Tidy CSV: `data/processed_data/pool_balances.csv`
- Dashboard JSON: `data/processed_data/pool_balances.json`
- This memo: `erd/pool_balances_layer.md`
