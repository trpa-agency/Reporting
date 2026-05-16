# ReservedNotConstructed - new Cumulative_Accounting REST layer

Designed 2026-05-15. Codifies the analyst's "Reserved, not constructed" tally that drives Tahoe Development Tracker section iii. Closes one `HARDCODED` data source on the active dashboard set.

## Source

- **File**: none (analyst email 2026-05-15; values transcribed into the converter)
- **Converter**: `scripts/convert_reserved_not_constructed.py` carries the source-of-truth values; re-run when the analyst sends a refreshed tally.
- **Cadence**: yearly (typically). 3 values per cycle (one per commodity).
- **Path to true derivation**: when Layer 3 (1987 RP) grows a `Construction_Status` field, this snapshot retires in favor of a SQL view = `Layer 3 Construction_Status='Not Completed'` + `Layer 4 Construction_Status='Not Completed'` per commodity. Today Layer 4 covers 2012 RP residential only (151 of the 698 RES); 1987 RP residential + all CFA + TAU need the field added on Layer 3 / a corresponding 1987 RP residential / CFA / TAU breakdown.

## Schema

```sql
CREATE TABLE dbo.ReservedNotConstructed (
    ObjectID       INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    CommodityCode  VARCHAR(4)   NOT NULL,   -- 'RES' | 'CFA' | 'TAU'
    Commodity      VARCHAR(50)  NOT NULL,
    Units          INT          NOT NULL,
    Unit           VARCHAR(10)  NOT NULL,   -- 'units' | 'sq ft'
    SourceNote     VARCHAR(200) NOT NULL,
    AsOfDate       DATE         NOT NULL,
    LoadedDate     DATE         NOT NULL
);
```

3 rows at 2026-05-15: RES 698 / CFA 46,962 / TAU 138.

## Publishing path

1. Run converter
2. Load CSV into SDE
3. Publish as `Cumulative_Accounting/MapServer/14`
4. Dashboard URL swap: change `RESERVED_NOT_CONSTRUCTED_URL` from local JSON to layer 14 REST endpoint

## Files

- Converter: `parcel_development_history_etl/scripts/convert_reserved_not_constructed.py`
- Tidy CSV: `data/processed_data/reserved_not_constructed.csv`
- Dashboard JSON: `data/processed_data/reserved_not_constructed.json`
- This memo: `erd/reserved_not_constructed_layer.md`
