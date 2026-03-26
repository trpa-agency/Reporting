# Development History ETL — Methods

**Project:** Tahoe Development History by Parcel (2012–2025)
**Package:** `parcel_development_history_etl/`
**Output:** `C:\GIS\ParcelHistory.gdb\Parcel_Development_History`
**Python:** ArcGIS Pro — `C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe`

---

## Purpose

This ETL builds a parcel-level development history feature class covering the Lake Tahoe Basin from 2012 to 2025. For each parcel × year combination it records:

- **Residential_Units** — existing residential dwelling units
- **TouristAccommodation_Units** — tourist accommodation units (TAUs)
- **CommercialFloorArea_SqFt** — commercial floor area in square feet
- Spatial attributes: jurisdiction, county, zoning, regional land use, TAZ, town center proximity, TRPA boundary membership

---

## Authoritative Data Sources

The ETL treats two upstream systems as authoritative and generates QA output that recommends fixes to each one rather than patching around their issues.

| Source | Authority | Maintained by |
|--------|-----------|---------------|
| **All Parcels MapServer** | Parcel geometry and APNs for each year | TRPA GIS — individual year feature classes managed directly |
| **Development attribute CSVs** | Residential units, TAUs, commercial sq ft | TRPA analyst (coworker) |

**All Parcels MapServer layers:**

| Path | Description |
|------|-------------|
| `https://maps.trpa.org/server/rest/services/AllParcels/MapServer` | One layer per year (2012–2024); see `YEAR_LAYER` in `config.py` for layer indices |

**Development attribute CSVs:**

| File | Contents |
|------|----------|
| `data/raw_data/ExistingResidential_2012_2025_unstacked.csv` | APN × Year = residential units (wide format) |
| `data/raw_data/TouristUnits_2012to2025.csv` | APN × CY2012..CY2025 = TAUs (wide format) |
| `data/raw_data/CommercialFloorArea_2012to2025.csv` | APN × CY2012..CY2025 = sq ft (wide format) |

**Supporting sources:**

| File | Description |
|------|-------------|
| `C:\GIS\ParcelHistory.gdb\Parcel_History_Attributed` | SOURCE_FC — 2025 geometry fallback (no service layer yet) |
| `data/raw_data/apn_genealogy_tahoe.csv` | Consolidated parcel genealogy — APN renames, splits, merges (see Genealogy section) |

---

## Architecture

```
main.py
  ├── S01   s01_prepare_fc.py               Build OUTPUT_FC from All Parcels service (2012–2024)
  │                                         + SOURCE_FC fallback for 2025
  ├── S01c  s01c_populate_jurisdiction.py   Spatial join → populate COUNTY + JURISDICTION
  ├── S02   s02_load_csv.py                 Load residential CSV, El Dorado fix, build lookup
  │     └── S02b  s02b_genealogy.py         Apply genealogy APN corrections
  ├── S03   s03_crosswalk.py                Spatial join: resolve remaining unmatched APNs
  ├── S04   s04_update_units.py             Write Residential_Units
  ├── S04b  s04b_update_tourist_commercial.py  Write TAUs + CommercialFloorArea_SqFt
  ├── S05   s05_spatial_attrs.py            Spatial join: Zoning, RLU, TAZ, town center, etc.
  └── S06   s06_qa.py                       Write QA tables to GDB
```

**Utility / setup scripts** (run manually as needed, not part of main.py):

| Script | Purpose |
|--------|---------|
| `build_genealogy_master.py` | Parse raw genealogy notes CSVs → `apn_genealogy_master.csv` |
| `parse_genealogy_sources.py` | Parse Accela + LTinfo Excel files → `apn_genealogy_accela.csv`, `apn_genealogy_ltinfo.csv` |
| `build_genealogy_tahoe.py` | Merge all genealogy sources → `apn_genealogy_tahoe.csv` |
| `build_spatial_genealogy.py` | Detect parcel events spatially → `apn_genealogy_spatial.csv` |
| `compare_source_to_service.py` | Compare OUTPUT_FC against All Parcels service layers year-by-year. Produces `apn_fc_only.csv` and `apn_service_only.csv` as fix recommendations for the service layer team. |
| `deduplicate_source_fc.py` | Deduplicate SOURCE_FC (run if duplicate APN×Year rows are found) |
| `check_parcel_topology.py` | Topology QA: overlapping/duplicate geometry |

---

## ETL Steps in Detail

### S01 — Build Output Feature Class
Creates a fresh output FC by querying the All Parcels MapServer service directly for each year. Each service layer is the canonical, gap-free source of parcel geometry and APNs for that year. Only Shape, APN, and Year are written here — all other attributes are filled by subsequent steps.

- **2012–2024**: queries the corresponding All Parcels service layer (indices in `YEAR_LAYER` in `config.py`)
- **2025**: no service layer yet — rows are copied from `SOURCE_FC` as a fallback

Uses `SOURCE_FC` as schema template so all downstream fields exist at creation. Drops and recreates OUTPUT_FC on every run.

### S01c — Populate COUNTY and JURISDICTION
Performs a centroid spatial join of all unique parcels in OUTPUT_FC against the TRPA Jurisdictions service (`Boundaries/FeatureServer/10`). Two passes: WITHIN first, then CLOSEST ≤ 100m for any unmatched. Converts full county names to 2-character codes (e.g. `El Dorado` → `EL`).

This step runs before S02 so that COUNTY is populated when the El Dorado APN fix runs.

### S02 — Load Residential CSV
1. Reads wide-format CSV (APN × 2012–2025), melts to long format (~593K rows)
2. **El Dorado APN fix**: El Dorado County changed APN suffix formatting in 2018 (2-digit → 3-digit, e.g. `080-155-11` → `080-155-011`). Uses COUNTY from OUTPUT_FC (populated by S01c) to identify El Dorado parcels and apply the correct format per year.
3. Builds `csv_lookup`: `{(APN, Year): units}` passed to S04.

**S02b — Apply Genealogy** (called from within S02)
Applies parcel event corrections to the long-format CSV before the lookup is built. For each record where `is_primary=1`, `in_fc_new=1`, and `change_year` is set: rows where `APN == apn_old AND Year >= change_year` have their APN replaced with `apn_new`. Conflict-skip prevents double-counting. Applied in source-priority × change_year order (MANUAL → ACCELA → SPATIAL). Results written to `QA_Genealogy_Applied`.

### S03 — APN Crosswalk
For CSV APNs that still have no match in OUTPUT_FC after S02b, performs a centroid spatial join against the current All Parcels layer to find the correct current APN. Extends `csv_lookup`. Results written to `QA_APN_Crosswalk`.

### S04 — Write Residential Units
Writes `Residential_Units` from `csv_lookup` to OUTPUT_FC. Since OUTPUT_FC is rebuilt fresh from the service each run, there are no pre-existing native unit values for 2012–2024 — CSV is always the source. For 2025 (copied from SOURCE_FC), FC-native values may exist and are recorded in `FC_Native_Units` for reference. Adds `FC_Native_Units` and `Unit_Source` fields.

### S04b — Write Tourist & Commercial Attributes
Loads `TouristUnits_2012to2025.csv` and `CommercialFloorArea_2012to2025.csv`. For each: melts to long format, applies El Dorado APN fix, applies genealogy, writes non-zero values to `TouristAccommodation_Units` and `CommercialFloorArea_SqFt`.

### S05 — Spatial Attribute Updates *(slow — ~15 min; skippable)*
Spatial joins against 7 reference layers to populate: `PARCEL_ACRES`, `PARCEL_SQFT`, `WITHIN_TRPA_BNDY`, `WITHIN_BONUSUNIT_BNDY`, `TOWN_CENTER`, `LOCATION_TO_TOWNCENTER`, `TAZ`, `PLAN_ID`/`PLAN_NAME`, `ZONING_ID`/`ZONING_DESCRIPTION`, `REGIONAL_LANDUSE`.

Skip with `--skip-s05` during iterative unit QA runs.

### S06 — QA Tables
Writes QA tables to `ParcelHistory.gdb` for review in ArcGIS Pro. Tables are grouped by the upstream system they recommend fixes to. See [QA section](#qa-outputs-and-fix-recommendations) below.

---

## Genealogy System

Parcel events (splits, merges, renames) cause APN mismatches between the CSVs (which may use historical APNs) and the output FC (which uses current APNs from the service). The genealogy system tracks these events and remaps CSV APNs to their current equivalents before any FC join.

### Sources (in priority order)

| File | Source | Records | Notes |
|------|--------|---------|-------|
| `apn_genealogy_master.csv` | Analyst-curated | ~1,250 | Hand-reviewed; authoritative |
| `apn_genealogy_accela.csv` | Accela permit system | ~37,000 | 2021–2025 events; parsed from `Accela_Genealogy_March2026.xlsx` |
| `apn_genealogy_ltinfo.csv` | LTinfo parcel system | ~3,500 | Parent→child pairs; most lack `change_year` and are skipped until dates are filled in |
| `apn_genealogy_spatial.csv` | Spatial overlap analysis | ~700 | Auto-detected from FC geometry |

### Consolidated Master (`apn_genealogy_tahoe.csv`)
Built by `build_genealogy_tahoe.py`. Merges all sources, canonicalizes APN formats, deduplicates, and flags each pair:
- `is_primary` — 1 = apply this remap, 0 = secondary/skip
- `in_fc_new` — new APN exists in the FC (application filter)
- `source_priority` — 1=MANUAL, 2=ACCELA, 3=LTINFO, 4=SPATIAL
- `change_year` — year the event occurred

**Application filter:** `is_primary=1 AND in_fc_new=1 AND change_year set` → ~32,500 records per run.

Rebuild whenever source files change:
```powershell
& "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" `
  parcel_development_history_etl/build_genealogy_tahoe.py
```

---

## QA Outputs and Fix Recommendations

QA is framed around two questions: **what should be fixed in the CSVs** and **what should be fixed in the All Parcels service layers**. All QA tables are written to `ParcelHistory.gdb` and open directly in ArcGIS Pro.

### Fix recommendations → CSV maintainer

| Table | Contents | Action |
|-------|---------|--------|
| `QA_CSV_APN_Fixes` | APNs in the residential/tourist/commercial CSVs that couldn't be matched to any parcel in the service after genealogy and crosswalk. Categorized by likely cause (PARCEL_SPLIT, PARCEL_NEW, UNKNOWN). | Coworker should update the APN in their spreadsheet to the current parcel identifier |
| `QA_Genealogy_Applied` | Every APN substitution applied in S02b: old APN, new APN, source, change year, years updated, units moved. | Where genealogy is doing the remapping, the coworker may want to update the CSV to use the current APN directly so the remap is no longer needed |
| `QA_Units_By_Year` | Total units in CSV vs FC per year, difference, and status flag. Large discrepancies indicate missing or incorrect rows in the CSV. | Review years with large gaps |

### Fix recommendations → All Parcels service team

| Table | Contents | Action |
|-------|---------|--------|
| `QA_Service_APN_Fixes` | APNs in the output FC with null COUNTY or JURISDICTION after S01c — centroid fell outside all jurisdiction polygons. Likely a geometry issue in the service layer (sliver, misaligned boundary parcel). | Fix geometry in the source year feature class |
| `QA_Duplicate_APN_Year` | Duplicate APN × Year rows in OUTPUT_FC — indicates duplicate features in the All Parcels service layer for that year. | Remove duplicate from source year feature class |

### Audit and reference tables

| Table | Contents |
|-------|---------|
| `QA_APN_Crosswalk` | APNs resolved via spatial join in S03 (CSV APN had no direct FC match — resolved by geometry) |
| `QA_Unit_Reconciliation` | Full parcel × year reconciliation: CSV value, FC value, merged value, source label |
| `QA_Spatial_Completeness` | Null spatial attribute counts per year for parcels within TRPA boundary (post-S05) |
| `QA_Source_vs_Service` | Output of `compare_source_to_service.py` — FC_ONLY and SERVICE_ONLY APNs per year |

---

## Logging

Every ETL run writes log output to two places simultaneously:

**Console** — INFO level and above, visible while the script runs.

**Log file** — DEBUG level (more verbose), written to `logs/etl_YYYYMMDD.log`. One file per calendar day; multiple runs on the same day append to the same file. Log files are retained indefinitely and provide a full audit trail of every substitution, match, and warning.

Log format:
```
2026-03-25 14:12:32  INFO      s02b_genealogy  Accela: 24070 APN substitutions / 145297 unit-years remapped
```

Fields: `timestamp  level  step_name  message`

To review a past run:
```powershell
Get-Content parcel_development_history_etl\logs\etl_20260325.log | Select-String "ERROR|WARNING"
```

---

## Run Reports

After each significant run, a Markdown report is written to `results/` documenting what changed, key QA numbers, and any issues to follow up on. Reports are named `REPORT_YYYYMMDD.md` (or `REPORT_YYYYMMDDb.md` for multiple runs on the same day).

Reports are not auto-generated — they are written manually after reviewing the QA tables and log output. They serve as a human-readable record of the state of the data at each run and the decisions made.

---

## Running the ETL

**Before any run:** close ArcGIS Pro (or disconnect from the GDB) to release locks on `ParcelHistory.gdb`.

### First run — build FC from service (~10–15 min without S05)
```powershell
& "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" `
  parcel_development_history_etl/main.py --skip-s05
```

### Iterative runs — skip service rebuild, skip spatial joins (~5 min)
```powershell
& "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" `
  parcel_development_history_etl/main.py --skip-s01 --skip-s05
```

### Full run with spatial joins (~20–25 min)
```powershell
& "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" `
  parcel_development_history_etl/main.py --skip-s01
```

### QA tables only
```powershell
& "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" `
  parcel_development_history_etl/main.py --only-qa
```

---

## Pre-Run Checklist

- [ ] `ExistingResidential_2012_2025_unstacked.csv` is current
- [ ] `TouristUnits_2012to2025.csv` is current
- [ ] `CommercialFloorArea_2012to2025.csv` is current
- [ ] `apn_genealogy_tahoe.csv` is current — rebuild with `build_genealogy_tahoe.py` if any genealogy source was updated
- [ ] ArcGIS Pro is closed / GDB is not locked
- [ ] Running on ArcGIS Pro Python (`arcgispro-py3`)

---

## Known Limitations

**2025 parcels:** No All Parcels service layer for 2025 yet. S01 falls back to `SOURCE_FC` for 2025 geometry. When the 2025 layer is published, add its index to `YEAR_LAYER` in `config.py`.

**LTinfo genealogy:** ~3,533 records have no `change_year` and are skipped. These cover pre-2021 parcel events. Rebuild `apn_genealogy_tahoe.csv` when dates are filled in.

**Service layer quality:** The output FC is only as good as the All Parcels service layers. Use `compare_source_to_service.py` periodically and work with the GIS team to correct gaps or duplicate features in the source year feature classes.

---

## Key Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `APN` | Text | Assessor Parcel Number — primary join key |
| `YEAR` | Long | Calendar year of the parcel record |
| `Residential_Units` | Long | Existing residential dwelling units |
| `TouristAccommodation_Units` | Long | Tourist accommodation units |
| `CommercialFloorArea_SqFt` | Double | Commercial floor area in square feet |
| `FC_Native_Units` | Long | Pre-ETL unit value (2025 only; null for 2012–2024) |
| `Unit_Source` | Text | CSV / FC_NATIVE / BOTH_AGREE / DISAGREE |
| `COUNTY` | Text | 2-char county code: EL, PL, WA, DG, CC, CSLT |
| `JURISDICTION` | Text | Jurisdiction name or code |
| `WITHIN_TRPA_BNDY` | SmallInt | 1 = within TRPA boundary |
| `WITHIN_BONUSUNIT_BNDY` | SmallInt | 1 = within bonus unit boundary |

---
