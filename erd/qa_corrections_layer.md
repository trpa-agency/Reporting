# QaCorrections - new Cumulative_Accounting REST layer

Designed 2026-05-15. Pre-joined Events + Detail for the QA correction campaigns (2023 + 2026 + future rolling corrections). Closes 2 `REPO-CSV` data sources on the qa-change-rationale dashboard.

## Source

- **Inputs**:
  - `data/qa_data/qa_change_events.csv` (5,925 rows, 13 fields)
  - `data/qa_data/qa_correction_detail.csv` (5,925 rows, 10 fields)
  - Both are outputs of `notebooks/04_load_ca_changes.ipynb` (the upstream loader from the analyst's `CA Changes breakdown.xlsx`)
- **Converter**: `scripts/convert_qa_corrections.py` joins on `ChangeEventID` (1:1) and emits a single flat table.
- **Cadence**: irregular - new sweep campaigns add rows; rolling corrections add events outside the sweep cycles.

## Schema (joined)

```sql
CREATE TABLE dbo.QaCorrections (
    ObjectID                       INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    ChangeEventID                  INT          NOT NULL,
    RawAPN                         VARCHAR(15)  NOT NULL,
    CanonicalAPN                   VARCHAR(15)  NOT NULL,
    CommodityShortName             VARCHAR(40)  NOT NULL,
    Year                           INT          NULL,
    PreviousQuantity               FLOAT        NULL,
    NewQuantity                    FLOAT        NULL,
    Quantity_Delta                 INT          NULL,
    ChangeSource                   VARCHAR(40)  NULL,
    Rationale                      VARCHAR(500) NULL,
    EvidenceURL                    VARCHAR(500) NULL,
    RecordedBy                     VARCHAR(50)  NULL,
    RecordedAt                     VARCHAR(40)  NOT NULL,
    ReportingYear                  INT          NULL,
    SweepCampaign                  VARCHAR(40)  NULL,
    CorrectionCategory             VARCHAR(200) NULL,
    CorrectionCategoryCanonical    BIT          NULL,
    SummaryReason                  VARCHAR(500) NULL,
    SourceFileSnapshot             VARCHAR(120) NULL,
    LoadedDate                     DATE         NOT NULL,
    CONSTRAINT UQ_QaCorrections UNIQUE (ChangeEventID)
);
```

5,925 rows at 2026-05-15.

## Publishing path

1. Run converter
2. Load CSV into SDE
3. Publish as `Cumulative_Accounting/MapServer/16`. **Pagination required** - 5,925 rows exceeds the 2,000 maxRecordCount; the dashboard loader will need to handle paginated fetches (see Layer 4 / Layer 7 patterns).
4. Dashboard URL swap: change `QA_CORRECTIONS_URL` constant from local JSON to layer 16 REST endpoint. The current loader accepts both ESRI features and local `{rows: [...]}` shapes.

## Pagination implementation note

When repointing to layer 16 REST, replace the single-shot `loadQaCorrections()` with a paginated loop:
```javascript
async function loadQaCorrections() {
  const all = [];
  let offset = 0;
  while (true) {
    const r = await fetch(QA_CORRECTIONS_URL + '&resultOffset=' + offset + '&resultRecordCount=2000', { cache: 'no-cache' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const js = await r.json();
    const feats = js.features || [];
    if (!feats.length) break;
    all.push(...feats.map(f => f.attributes));
    offset += feats.length;
    if (feats.length < 2000) break;
  }
  allRows = all.map(...);
}
```

## Files

- Converter: `parcel_development_history_etl/scripts/convert_qa_corrections.py`
- Tidy CSV: `data/processed_data/qa_corrections.csv`
- Dashboard JSON: `data/processed_data/qa_corrections.json` (~3 MB)
- This memo: `erd/qa_corrections_layer.md`
