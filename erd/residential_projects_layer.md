# ResidentialProjects - new Cumulative_Accounting REST layer

Designed 2026-05-15. Codifies the inline PROJECTS array on `residential-additions-by-source.html` as a structured REST layer. Closes the last `INLINE` data source on the active dashboard set.

## Source

- **File**: none (analyst PPTX slide 4 + xlsx Summary "Major Completed Projects" row; transcribed manually into the converter)
- **Converter**: `scripts/convert_residential_projects.py` carries the source-of-truth tuples; re-run when the analyst sends new projects.
- **Cadence**: yearly (typically). 25-30 projects per cycle.

## Schema

```sql
CREATE TABLE dbo.ResidentialProjects (
    ObjectID      INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    Year          INT          NOT NULL,
    ProjectName   VARCHAR(80)  NOT NULL,
    Units         INT          NOT NULL,
    Notes         VARCHAR(120) NOT NULL DEFAULT '',  -- affordability detail, e.g. "47 affordable, 1 moderate"
    Description   VARCHAR(200) NOT NULL,             -- original phrasing for backward compatibility
    AsOfDate      DATE         NOT NULL,
    LoadedDate    DATE         NOT NULL
);
```

26 rows at 2026-05-15 snapshot, totaling 468 units across 10 years (2014-2025).

## Publishing path

1. Run converter (one-time + on refresh)
2. Load CSV into SDE
3. Publish as `Cumulative_Accounting/MapServer/13`
4. Dashboard URL swap: change `RESIDENTIAL_PROJECTS_URL` constant from local JSON to layer 13 REST

## Files

- Converter: `parcel_development_history_etl/scripts/convert_residential_projects.py`
- Tidy CSV: `data/processed_data/residential_projects.csv`
- Dashboard JSON: `data/processed_data/residential_projects.json`
- This memo: `erd/residential_projects_layer.md`
