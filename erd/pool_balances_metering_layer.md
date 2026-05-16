# PoolBalancesMetering - new Cumulative_Accounting REST layer

Designed 2026-05-15. Long-form per-year per-pool metering for residential allocations, normalized from the analyst's `regional_plan_allocations.json` `residential.by_year` blocks. Drives the metering chart on the pool-balance-cards detail panel.

## Source

- **File**: `data/processed_data/regional_plan_allocations.json` (intermediate, produced by `convert_regional_plan_allocations.py` from the analyst's `All Regional Plan Allocations Summary.xlsx`)
- **Converter**: `scripts/convert_pool_balances_metering.py` reads the nested `residential.by_year.{released, assigned, not_assigned, unreleased}` blocks and pivots to long form.
- **Cadence**: yearly. Re-run when the analyst sends a refreshed Allocations Summary xlsx.

## Schema

```sql
CREATE TABLE dbo.PoolBalancesMetering (
    ObjectID       INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    Commodity      VARCHAR(40)  NOT NULL,       -- 'Residential allocations' (only commodity with metering today)
    CommodityCode  VARCHAR(4)   NOT NULL,       -- 'RES'
    Pool           VARCHAR(80)  NOT NULL,       -- 'Placer County', 'TRPA Allocation Incentive Pool', etc.
    Year           INT          NOT NULL,
    Direction      VARCHAR(15)  NOT NULL,       -- 'Released' | 'Assigned' | 'NotAssigned' | 'Unreleased'
    Units          INT          NOT NULL,
    AsOfDate       VARCHAR(20)  NOT NULL,       -- source xlsx string (preserve as-is until ISO normalization)
    LoadedDate     DATE         NOT NULL,
    CONSTRAINT UQ_PoolBalancesMetering UNIQUE (CommodityCode, Pool, Year, Direction, AsOfDate)
);
```

853 rows at 2026-05-15: 4 Directions x 7 pools (mostly) x 41 years (1986-2026).

## Publishing path

1. Run `convert_regional_plan_allocations.py` (if xlsx is fresh) then `convert_pool_balances_metering.py`
2. Load CSV into SDE
3. Publish as `Cumulative_Accounting/MapServer/15`
4. Dashboard URL swap: change `METERING_URL` in `pool-balance-cards.html` from local JSON to layer 15 REST endpoint

## Files

- Converter: `parcel_development_history_etl/scripts/convert_pool_balances_metering.py`
- Tidy CSV: `data/processed_data/pool_balances_metering.csv`
- Dashboard JSON: `data/processed_data/pool_balances_metering.json`
- This memo: `erd/pool_balances_metering_layer.md`
