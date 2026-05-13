# Development History ETL - Methods

**Project:** Tahoe Development History by Parcel (2012–2025)
**Package:** `parcel_development_history_etl/`
**Output:** `C:\GIS\ParcelHistory.gdb\Parcel_Development_History`
**Python:** ArcGIS Pro - `C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe`

---

## Purpose

This ETL builds a parcel-level development history feature class covering the Lake Tahoe Basin from 2012 to 2025. For each parcel × year combination it records:

- **Residential_Units** - existing residential dwelling units
- **TouristAccommodation_Units** - tourist accommodation units (TAUs)
- **CommercialFloorArea_SqFt** - commercial floor area in square feet
- **Building_SqFt** - total footprint area of buildings on the parcel (from 2019 buildings layer)
- Spatial attributes: jurisdiction, county, zoning, regional land use, TAZ, town center proximity, TRPA boundary membership

---

## Authoritative Data Sources

The ETL treats two upstream systems as authoritative and generates QA output that recommends fixes to each one rather than patching around their issues.

| Source | Authority | Maintained by |
|--------|-----------|---------------|
| **All Parcels MapServer** | Parcel geometry and APNs for each year | TRPA GIS - individual year feature classes managed directly |
| **Development attribute CSVs** | Residential units, TAUs, commercial sq ft | TRPA analyst (coworker) |

**All Parcels MapServer layers:**

| Path | Description |
|------|-------------|
| `https://maps.trpa.org/server/rest/services/AllParcels/MapServer` | One layer per year (2013–2024); see `YEAR_LAYER` in `config.py` for layer indices |

> **Note:** 2012 is intentionally excluded from `YEAR_LAYER`. Parcel geometry for 2012 is sourced directly from `SOURCE_FC` (`Parcel_History_Attributed`) rather than the map service, because the service geometry for that year was found to be incomplete or inconsistent with the GDB-maintained record.

**Development attribute CSVs:**

| File | Contents |
|------|----------|
| `data/raw_data/ExistingResidential_2012_2025_unstacked.csv` | APN × Year = residential units (wide format) |
| `data/raw_data/TouristUnits_2012to2025.csv` | APN × CY2012..CY2025 = TAUs (wide format) |
| `data/raw_data/CommercialFloorArea_2012to2025.csv` | APN × CY2012..CY2025 = sq ft (wide format) |

> **CSV omission error is an open QA area.** The CSV was carefully constructed from permit, allocation, and county assessor data and its unit values are generally trusted. The primary concern is *omission* - parcels with units that were never captured in the CSV - rather than incorrect values for parcels that are present. Comparison against `Parcel_History_Attributed` (SOURCE_FC) reveals this directly: as of April 2026, 5,888 APN×Year pairs where SOURCE_FC has a non-zero unit value have no corresponding CSV entry (`FC_NATIVE` rows). Identifying and filling these gaps is the key validation task.

**Supporting sources:**

| File | Description |
|------|-------------|
| `C:\GIS\ParcelHistory.gdb\Parcel_History_Attributed` | SOURCE_FC - 2012 geometry + 2025 fallback; also provides native unit values for comparison |
| `C:\GIS\Buildings.gdb\Buildings_2019` | Building footprints (2019 vintage); used to compute `Building_SqFt` via spatial intersection |
| `data/raw_data/apn_genealogy_tahoe.csv` | Consolidated parcel genealogy - APN renames, splits, merges (see Genealogy section) |

**New genealogy reference files (not yet integrated - for QA use):**

| File | Description |
|------|-------------|
| `data/raw_data/Accela genealogy from addresses.xlsx` | ~23,600 old→new APN pairs from Accela address records; lacks `change_year` |
| `data/raw_data/Parcel Genealogy Lookups KK.xlsx` | ~47,600 old→new APN pairs from analyst research; includes format normalization pairs |

These files have not been ingested into `apn_genealogy_tahoe.csv` because they lack `change_year`, which the ETL requires to know which years to remap. Use `scripts/qa_lost_apns_vs_new_genealogy.py` to cross-reference them against the current lost-APN list and identify pairs worth investigating.

---

## Architecture

```
main.py
  ├── S01   s01_prepare_fc.py               Build OUTPUT_FC from All Parcels service (2013–2024)
  │                                         + SOURCE_FC for 2012 and 2025 fallback
  ├── S01c  s01c_populate_jurisdiction.py   Spatial join → populate COUNTY + JURISDICTION
  ├── S02   s02_load_csv.py                 Load residential CSV, El Dorado fix, build lookup
  │     └── S02b  s02b_genealogy.py         Apply genealogy APN corrections
  ├── S03   s03_crosswalk.py                Spatial join: resolve remaining unmatched APNs
  ├── S04   s04_update_units.py             Write Residential_Units
  ├── S04b  s04b_update_tourist_commercial.py  Write TAUs + CommercialFloorArea_SqFt
  ├── S05   s05_spatial_attrs.py            Spatial join: Zoning, RLU, TAZ, town center, Building_SqFt, etc.
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
| `scripts/qa_lost_apns_vs_new_genealogy.py` | Post-ETL QA: cross-reference lost APNs against Accela and KK genealogy files to find candidate mappings |
| `scripts/detect_change_years.py` | **New (Apr 2026)** - For NEEDS_CHANGE_YEAR pairs from `qa_lost_vs_new_genealogy.csv`, queries OUTPUT_FC and SOURCE_FC to determine when the old APN last appears and the new APN first appears. Recommends `change_year` with confidence ratings. Outputs `data/raw_data/change_year_candidates.csv` pre-formatted for direct copy into `apn_genealogy_master.csv`. |

---

## ETL Steps in Detail

### S01 - Build Output Feature Class
Creates a fresh output FC by querying the All Parcels MapServer service for each year. Each service layer is the canonical, gap-free source of parcel geometry and APNs for that year. Only Shape, APN, and Year are written here - all other attributes are filled by subsequent steps.

- **2013–2024**: queries the corresponding All Parcels service layer (indices in `YEAR_LAYER` in `config.py`)
- **2012**: copied from `SOURCE_FC` (`Parcel_History_Attributed`), not the service; the service geometry for 2012 was found to be less reliable than the GDB record
- **2025**: no service layer yet - rows are copied from `SOURCE_FC` as a fallback

Uses `SOURCE_FC` as schema template so all downstream fields exist at creation. Drops and recreates OUTPUT_FC on every run.

### S01c - Populate COUNTY and JURISDICTION
Performs a centroid spatial join of all unique parcels in OUTPUT_FC against the TRPA Jurisdictions service (`Boundaries/FeatureServer/10`). Two passes: WITHIN first, then CLOSEST ≤ 100m for any unmatched. Converts full county names to 2-character codes (e.g. `El Dorado` → `EL`).

This step runs before S02 so that COUNTY is populated when the El Dorado APN fix runs.

### S02 - Load Residential CSV
1. Reads wide-format CSV (APN × 2012–2025), melts to long format (~593K rows)
2. **El Dorado APN fix**: El Dorado County changed APN suffix formatting in 2018 (2-digit → 3-digit, e.g. `080-155-11` → `080-155-011`). `build_el_dorado_fix()` queries the FC for COUNTY=EL APNs and builds a `pad_map` (2-digit → 3-digit) and `depad_map` (3-digit → 2-digit). Two cases are handled:
   - **Case 1 - Parcel spans 2018:** Both 2-digit (pre-2018 FC rows) and 3-digit (2018+ FC rows) exist in the FC. The 2-digit form is found by the FC query and enters `pad_map` directly.
   - **Case 2 - Parcel born at or after 2018:** Only the 3-digit form ever exists in the FC. The 2-digit form is never in the FC, so a straight query misses it. `build_el_dorado_fix()` also collects 3-digit APNs and adds their de-padded 2-digit form → 3-digit form to `pad_map`. This allows CSV entries using the 2-digit form (entered before the parcel existed in the county system) to be padded correctly. Example: `015-370-30 → 015-370-030` (FC has 3-digit form only, starting 2021).
3. **El Dorado split-format dedup**: Some APNs appear in the CSV in both 2-digit and 3-digit forms (one row per format). After the El Dorado fix normalizes both to the same key, duplicates are resolved by keeping the max unit count for each `(APN, Year)` pair.
4. **S02b - Apply Genealogy** (see below)
5. **Post-genealogy dedup**: Genealogy substitution can create duplicate `(APN, Year)` rows when the target APN has a zero-unit placeholder row for that year (zeros don't trigger conflict-skip). Since `csv_lookup` is built as a dict (last-write-wins), a zero-unit duplicate row can silently overwrite a valid non-zero substitution. A second groupby-max dedup after genealogy prevents this.
6. Builds `csv_lookup`: `{(APN, Year): units}` passed to S04.

**S02b - Apply Genealogy** (called from within S02)
Applies parcel event corrections to the long-format CSV before the lookup is built. For each record where `is_primary=1`, `in_fc_new=1`, and `change_year` is set: rows where `APN == apn_old AND Year >= change_year` have their APN replaced with `apn_new`.

**Conflict-skip logic:** A substitution is blocked only if the target APN already has a *non-zero* unit value for that year. Zero-value rows are treated as placeholders and do not block remapping - this prevents historical units from being silently dropped for split-parcel successors that have a zero placeholder row in early years. Applied in source-priority × change_year order (MANUAL → ACCELA → SPATIAL). Results written to `QA_Genealogy_Applied`.

### S03 - APN Crosswalk
For CSV APNs that still have no match in OUTPUT_FC after S02b, resolves them via spatial join to find the correct current APN.

**Resolution order:**
1. **SOURCE_FC fallback** - queries `Parcel_History_Attributed` directly using the APN (with El Dorado 2-digit/3-digit variant awareness). Used when the All Parcels service is unavailable or has gaps.
2. **All Parcels service** - centroid spatial join against the current service layer.

**El Dorado format expansion in geometry lookup:** S03's `_get_apn_geometry()` handles two cases:
- **Case A (3-digit in crosswalk list):** Also searches for the 2-digit form so pre-2018 FC rows contribute geometry. Results mapped back to the canonical 3-digit key.
- **Case B (2-digit APN that only exists in FC in 3-digit form):** Parcels born at or after the 2018 format change never have a 2-digit row in the FC. S03 also searches for the padded 3-digit form so its geometry can be used for the centroid spatial join.

**Sum-on-collision:** If a CSV APN resolves to an FC APN that already has a value in `csv_lookup`, the values are summed rather than skipped. This handles cases where multiple historical APNs map to the same current parcel (e.g. after a merge event). Results written to `QA_APN_Crosswalk`.

### S04 - Write Residential Units
Writes `Residential_Units` from `csv_lookup` to OUTPUT_FC.

**Merge strategy:**

| Condition | `Residential_Units` written | `Unit_Source` |
|-----------|----------------------------|---------------|
| CSV has a value, SOURCE_FC native = 0/null | CSV value | `CSV` |
| CSV and SOURCE_FC agree | CSV value | `BOTH_AGREE` |
| CSV and SOURCE_FC differ (both non-zero) | CSV value | `DISAGREE` |
| SOURCE_FC has value, CSV has none | 0 | `FC_NATIVE` |
| Neither has a value | 0 | `CSV` |

**CSV is sole authority for `Residential_Units`.** Even when SOURCE_FC has a native value that CSV lacks, the merged output writes 0 and tags the row `FC_NATIVE`. The native value is preserved in `FC_Native_Units` for analyst review via `QA_Unit_Reconciliation`. This ensures the ETL does not silently introduce SOURCE_FC values that may be stale carryovers or otherwise unvetted.

SOURCE_FC native values are loaded via `_load_source_fc_natives()` for `FC_NATIVE_YEARS` (2012 and 2018–2025). Adds `FC_Native_Units` (LONG) and `Unit_Source` (TEXT) fields to OUTPUT_FC.

### S04b - Write Tourist & Commercial Attributes
Loads `TouristUnits_2012to2025.csv` and `CommercialFloorArea_2012to2025.csv`. For each: melts to long format, applies El Dorado APN fix, applies genealogy, writes non-zero values to `TouristAccommodation_Units` and `CommercialFloorArea_SqFt`.

### S05 - Spatial Attribute Updates *(slow - ~15 min; skippable)*
Spatial joins against reference layers to populate:

- `PARCEL_ACRES`, `PARCEL_SQFT`
- `WITHIN_TRPA_BNDY`, `WITHIN_BONUSUNIT_BNDY`
- `TOWN_CENTER`, `LOCATION_TO_TOWNCENTER`
- `TAZ`, `PLAN_ID`/`PLAN_NAME`
- `ZONING_ID`/`ZONING_DESCRIPTION`
- `REGIONAL_LANDUSE`
- **`Building_SqFt`** - intersects year=2019 parcels against `Buildings_2019` (`C:\GIS\Buildings.gdb\Buildings_2019`), sums building footprint area per APN in US square feet, and propagates the value to all year-rows for that APN. This provides a coarse indicator for parcels that have units in the CSV but no physical buildings present.

Skip with `--skip-s05` during iterative unit QA runs.

### S06 - QA Tables
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
- `is_primary` - 1 = apply this remap, 0 = secondary/skip
- `in_fc_new` - new APN exists in the FC (application filter)
- `source_priority` - 1=MANUAL, 2=ACCELA, 3=LTINFO, 4=SPATIAL
- `change_year` - year the event occurred

**Application filter:** `is_primary=1 AND in_fc_new=1 AND change_year set` → ~32,500 records per run.

Rebuild whenever source files change:
```powershell
& "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" `
  parcel_development_history_etl/build_genealogy_tahoe.py
```

### New Genealogy Files (not yet integrated)

Two additional files were received that contain candidate APN mappings not yet in the master table:

| File | Pairs | Issue |
|------|-------|-------|
| `Accela genealogy from addresses.xlsx` (Sheet3) | ~23,600 new | No `change_year` |
| `Parcel Genealogy Lookups KK.xlsx` (Sheet1) | ~47,600 new | No `change_year`; many are format-only normalizations |

These cannot be added directly to `apn_genealogy_tahoe.csv` without `change_year`. Use the QA script below to identify which ones match currently-lost APNs and prioritize those for manual date research.

---

## QA Outputs and Fix Recommendations

QA is framed around two questions: **what should be fixed in the CSVs** and **what should be fixed in the All Parcels service layers**. All QA tables are written to `ParcelHistory.gdb` and open directly in ArcGIS Pro.

### Fix recommendations → CSV maintainer

| Table | Contents | Action |
|-------|---------|--------|
| `QA_CSV_APN_Fixes` | APNs in the residential/tourist/commercial CSVs that couldn't be matched to any parcel in the service after genealogy and crosswalk. Categorized by likely cause (PARCEL_SPLIT, PARCEL_NEW, UNKNOWN). | Coworker should update the APN in their spreadsheet to the current parcel identifier |
| `QA_Genealogy_Applied` | Every APN substitution applied in S02b: old APN, new APN, source, change year, years updated, units moved. | Where genealogy is doing the remapping, the coworker may want to update the CSV to use the current APN directly so the remap is no longer needed |
| `QA_Units_By_Year` | Total units in CSV vs FC per year, difference, and status flag. Large discrepancies indicate missing or incorrect rows in the CSV. | Review years with large gaps |

> **Open QA area - CSV omission error:** The tables above flag structural issues (APN mismatches, unresolved parcels) but the more important gap is *omission* - parcels with units that are present in SOURCE_FC but absent from the CSV entirely. The `QA_Unit_Reconciliation` table (filtered to `FC_NATIVE`) is the starting point: it lists every APN×Year where SOURCE_FC has a non-zero unit count that the CSV does not have. These are candidate omissions to review with the CSV maintainer.

### Fix recommendations → All Parcels service team

| Table | Contents | Action |
|-------|---------|--------|
| `QA_Service_APN_Fixes` | APNs in the output FC with null COUNTY or JURISDICTION after S01c - centroid fell outside all jurisdiction polygons. Likely a geometry issue in the service layer (sliver, misaligned boundary parcel). | Fix geometry in the source year feature class |
| `QA_Duplicate_APN_Year` | Duplicate APN × Year rows in OUTPUT_FC - indicates duplicate features in the All Parcels service layer for that year. | Remove duplicate from source year feature class |

### Audit and reference tables

| Table | Contents |
|-------|---------|
| `QA_APN_Crosswalk` | APNs resolved via spatial join in S03 (CSV APN had no direct FC match - resolved by geometry) |
| `QA_Unit_Reconciliation` | Full parcel × year reconciliation: CSV value, FC native value, merged value, source label |
| `QA_Spatial_Completeness` | Null spatial attribute counts per year for parcels within TRPA boundary (post-S05) |
| `QA_Source_vs_Service` | Output of `compare_source_to_service.py` - FC_ONLY and SERVICE_ONLY APNs per year |
| `QA_Lost_APNs` | APNs from the CSV that could not be placed after genealogy + crosswalk; categorized (PARCEL_SPLIT, PARCEL_NEW, UNKNOWN) with unit counts |

### Post-ETL QA script - Lost APNs vs new genealogy files

```powershell
cd parcel_development_history_etl
& "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" `
  scripts/qa_lost_apns_vs_new_genealogy.py
```

Reads `QA_Lost_APNs` from the GDB, cross-references each lost APN against the Accela and KK genealogy files, and writes `data/raw_data/qa_lost_vs_new_genealogy.csv`.

**Action categories in the output:**

| Action | Meaning |
|--------|---------|
| `NEEDS_CHANGE_YEAR` | Lost APN has a candidate mapping in Accela or KK that is an actual rename. Verify in ArcGIS Pro and add `change_year` to promote to master genealogy. |
| `review_format_only` | Mapping appears to be a pure APN format normalization (same parcel, different padding) or a segment-count change of uncertain cause. May be resolved as a county-wide lookup rather than a genealogy entry. |
| `already_in_tahoe` | Pair is already in `apn_genealogy_tahoe.csv` - lost APN was not resolved because the target APN is not in the FC or `change_year` is missing. |
| `no_candidate` | No match found in either new file. Requires manual spatial investigation in ArcGIS Pro. |

---

## Logging

Every ETL run writes log output to two places simultaneously:

**Console** - INFO level and above, visible while the script runs.

**Log file** - DEBUG level (more verbose), written to `logs/etl_YYYYMMDD.log`. One file per calendar day; multiple runs on the same day append to the same file. Log files are retained indefinitely and provide a full audit trail of every substitution, match, and warning.

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

Reports are not auto-generated - they are written manually after reviewing the QA tables and log output. They serve as a human-readable record of the state of the data at each run and the decisions made.

---

## Running the ETL

**Before any run:** close ArcGIS Pro (or disconnect from the GDB) to release locks on `ParcelHistory.gdb`.

### First run - build FC from service (~10–15 min without S05)
```powershell
& "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" `
  parcel_development_history_etl/main.py --skip-s05
```

### Iterative runs - skip service rebuild, skip spatial joins (~5 min)
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
- [ ] `apn_genealogy_tahoe.csv` is current - rebuild with `build_genealogy_tahoe.py` if any genealogy source was updated
- [ ] ArcGIS Pro is closed / GDB is not locked
- [ ] Running on ArcGIS Pro Python (`arcgispro-py3`)

---

## Known Limitations

**2025 parcels:** No All Parcels service layer for 2025 yet. S01 falls back to `SOURCE_FC` for 2025 geometry. When the 2025 layer is published, add its index to `YEAR_LAYER` in `config.py`.

**LTinfo genealogy:** ~3,533 records have no `change_year` and are skipped. These cover pre-2021 parcel events. Rebuild `apn_genealogy_tahoe.csv` when dates are filled in.

**New genealogy files (Accela + KK):** ~23,600 and ~47,600 new pairs respectively lack `change_year` and cannot be applied until dates are researched. Use `qa_lost_apns_vs_new_genealogy.py` to prioritize which pairs to investigate first.

**Lost APNs:** As of the April 15, 2026 final run, 709 APNs from the residential CSV cannot be directly placed in the output FC (515 PARCEL_SPLIT / 6,281 units; 131 UNKNOWN / 826 units; 63 PARCEL_NEW / 661 units). All are recovered by the S03 spatial crosswalk (5,434 entries). Zero APNs remain unresolved - deficit is 0 across all years. (The El Dorado Case 2 fix - see above - resolved the final three APNs that previously had no geometry.)

**Building_SqFt:** Based on 2019 building footprints only. Does not reflect demolitions or new construction after 2019. Intended as a QA indicator (zero buildings + non-zero units flags a parcel for review), not a precise current measurement.

**CSV omission error:** The CSV was carefully built from permit, allocation, and county assessor data and its values are generally trusted. The primary risk is omission - parcels with real units that were never captured in the CSV. As of April 2026, SOURCE_FC has non-zero unit values for 5,888 APN×Year pairs that have no corresponding CSV entry (`FC_NATIVE` rows). These are the primary candidates for omission review. See `QA_Unit_Reconciliation` filtered to `FC_NATIVE`.

**Service layer quality:** The output FC is only as good as the All Parcels service layers. Use `compare_source_to_service.py` periodically and work with the GIS team to correct gaps or duplicate features in the source year feature classes.

---

## Next Steps (as of April 15, 2026)

Current data state from the April 15, 2026 final run (Run 2):

| Check | Value |
|---|---|
| Annual deficit | **0/yr, all 14 years (2012–2025)** |
| Total deficit | 0 units |
| Lost APNs (QA category) | 709 - all recovered by S03 spatial crosswalk |
| Truly unresolvable | 0 |
| Genealogy substitutions | 523 APN subs / 8,803 unit-years remapped per run |
| Genealogy rows skipped (no change_year) | 2,397 |
| Duplicate APN×Year in FC | 0 - clean |
| Genealogy master | 1,958 rows |
| BOTH_AGREE rows | 324,099 |
| DISAGREE rows | 9,625 (CSV used in all cases) |
| FC_NATIVE rows | 5,867 (SOURCE_FC has units CSV lacks - not written to output) |

### 1. ~~Resolve the 3 previously "permanently lost" APNs~~ - RESOLVED

**Fixed April 15, 2026 (Run 2):** `015-370-30`, `016-300-64`, `018-320-18` were El Dorado parcels born at/after 2018 that only exist in the FC in 3-digit form. Extended `build_el_dorado_fix()` (Case 2) and S03's geometry lookup (Case B) to handle this. Zero deficit achieved - see REPORT_20260415b.md.

### 2. Continue NEEDS_CHANGE_YEAR genealogy work

Run `detect_change_years.py` against the current `qa_lost_vs_new_genealogy.csv` to find more promotable pairs. 2,397 genealogy rows are still skipped each run for lack of `change_year`. Each batch of promoted pairs further reduces the lost-APN QA list (even if the actual deficit is already close to irreducible, the genealogy record is worth completing).

### 3. Investigate 9,611 DISAGREE pairs

`QA_Unit_Reconciliation` filtered to `Category = DISAGREE` shows 9,611 APN×Year pairs where SOURCE_FC and CSV both have non-zero units but differ. The ETL uses CSV in all cases. Worth spot-checking to see if differences are systematic (concentrated in a county or year) or isolated noise.

### 4. Run full S05 spatial joins

All recent runs used `--skip-s05`. `TOWN_CENTER`, `TAZ`, `ZONING`, `REGIONAL_LANDUSE`, and `Building_SqFt` are from the previous full run. Once unit QA is satisfactory, run:
```powershell
& "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" `
  parcel_development_history_etl/main.py --skip-s01
```

### 5. Review 5,874 FC_NATIVE rows

These are APN×Year pairs where SOURCE_FC has a non-zero unit value the CSV lacks. Not written to the output (CSV is sole authority), but they are candidates for CSV omission. Review `QA_Unit_Reconciliation` filtered to `FC_NATIVE` with the CSV maintainer.

---

## Key Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `APN` | Text | Assessor Parcel Number - primary join key |
| `YEAR` | Long | Calendar year of the parcel record |
| `Residential_Units` | Long | Existing residential dwelling units (CSV sole authority) |
| `TouristAccommodation_Units` | Long | Tourist accommodation units |
| `CommercialFloorArea_SqFt` | Double | Commercial floor area in square feet |
| `Building_SqFt` | Double | Building footprint area in US sq ft (from Buildings_2019; populated by S05) |
| `FC_Native_Units` | Long | Unit value from SOURCE_FC before ETL (stored for reference; not written to Residential_Units) |
| `Unit_Source` | Text | CSV / FC_NATIVE / BOTH_AGREE / DISAGREE - merge outcome for this row |
| `COUNTY` | Text | 2-char county code: EL, PL, WA, DG, CC, CSLT |
| `JURISDICTION` | Text | Jurisdiction name or code |
| `WITHIN_TRPA_BNDY` | SmallInt | 1 = within TRPA boundary |
| `WITHIN_BONUSUNIT_BNDY` | SmallInt | 1 = within bonus unit boundary |

---
