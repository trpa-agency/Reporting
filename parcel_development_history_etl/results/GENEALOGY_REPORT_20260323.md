# Parcel Genealogy Master CSV - Build Report
**Date:** March 23, 2026
**Analyst:** M. Bindl
**Script:** `build_genealogy_master.py`
**Output:** `data/raw_data/apn_genealogy_master.csv`

---

## 1. Purpose

This report documents the first build of `apn_genealogy_master.csv`, a structured parcel genealogy lookup table used by the Residential Units ETL (Step 2b) to correct historical APN references in the stacked CSV before joining to the parcel history feature class.

The master CSV maps retired CSV APNs to their current successor APNs on a per-year basis, allowing the ETL to correctly match residential unit counts to the right parcel geometry for each year. Explicit genealogy corrections applied in Step 2b take priority over the spatial crosswalk fallback in Step 3.

---

## 2. Input Sources

| Source | Rows | Notes Column |
|---|---|---|
| `parcel_geneology_notes.csv` | ~130 APNs | `ParcelTrackerNotes` - detailed multi-step histories |
| `parcel_geneology_notes_2.csv` | ~42,000 APNs | `ParcelNotes` - full CSV population, simpler format |
| `Residential_Parcels_History` FC | 855,552 rows | Queried for first/last year each APN appears |

When an APN appeared in both notes files, the longer note was retained.

---

## 3. Parsing Method

Free-text notes were parsed using two regex patterns:

- **`New APN(s): X`** - captures all APN patterns up to the first parenthesis (which typically contains context about source parcels, not successors)
- **`Portions of this parcel are now part of APNs X, Y, Z`** - captures bulk-split succession

APN formats matched:
- Standard 3-segment: `\d{3}-\d{3}-\d{2,3}` (e.g., `123-032-01`)
- Extended 4-segment: `\d{4}-\d{2}-\d{3}-\d{3}` (e.g., `1418-34-110-039`)

---

## 4. Output Summary

| Metric | Count |
|---|---|
| Total rows in master CSV | **1,848** |
| Unique old APNs | **1,416** |
| Rename rows (1:1 succession) | **1,111** |
| Split rows - primary successor | **305** |
| Split rows - secondary successors (reference only) | **432** |

---

## 5. Change Year Detection

For each genealogy record, change year was assigned in priority order:

| Method | Count | Description |
|---|---|---|
| `old_apn_last+1` | **465** | Last year old APN appears in FC + 1 (most reliable) |
| `new_apn_first` | **1,142** | First year new APN appears in FC (used when old APN not in FC) |
| `unknown` | **241** | Neither old nor new APN found in FC - needs manual fill |

The large `new_apn_first` count (1,142) indicates many parcels in the notes changed before 2012 - their old APN never appears in the parcel history FC, but their successor APN does. Since the FC scope starts at 2012, these were assigned `change_year = 2012`, meaning the substitution applies across all 14 years in scope.

### Change Year Distribution (Primary Rows Only)

| Year | Rows |
|---|---|
| 2012 | 868 |
| 2013 | 10 |
| 2014 | 33 |
| 2015 | 41 |
| 2016 | 22 |
| 2017 | 95 |
| 2018 | 99 |
| 2019 | 7 |
| 2021 | 19 |
| 2022 | 12 |
| 2023 | 13 |
| 2024 | 12 |
| 2025 | 4 |
| 2026 | 18 |

The 2012 spike (868 rows) represents pre-2012 changes that are correctly applied across the full ETL scope. The 2026 rows (18) represent APNs whose `fc_last_year = 2025` - the old APN is still active in the current FC and the transition hasn't occurred within the 2012–2025 window.

---

## 6. Issues Requiring Manual Review

### Issue 1 - 241 Rows with Unknown Change Year

Neither the old APN nor the new APN was found in the parcel history FC. These rows have `year_source = unknown` and `change_year` is blank. Step 2b will skip these until `change_year` is filled in manually.

**To fix:** Filter `apn_genealogy_master.csv` to `year_source = unknown` in Excel. For each:
1. Look up the old APN in the AllParcels service or county assessor records to find when it was retired
2. Enter the year of the change in `change_year`
3. If the change predates 2012, enter `2012`

A sample of unknown rows:

| old_apn | new_apn | Notes excerpt |
|---|---|---|
| `126-271-15` | `126-271-19` | Previous APNs were merged and split |
| `090-172-031` | `090-172-034` | New APNs with lot groupings |
| `097-060-012` | `097-060-022` | Portions combined with other parcels |
| `123-044-10` | `123-044-09` | Combined to form common area + condos |
| Various `005-xxx` / `007-xxx` | `1318-xx-xxx-xxx` | Pre-2012 Washoe/Douglas renumbering |

### Issue 2 - 43 Self-Reference Rows (old_apn = new_apn)

These rows were misparsed. The note mentions the APN in a context that the regex interpreted as a new successor (e.g., "Previous APN: X (parcel was split into **090-066-024** and ...)"). The APN appears in the note text but is not actually a successor - it IS the row's APN.

**To fix:** These rows are harmless in Step 2b (they would substitute an APN with itself, which `s02b_genealogy.py` skips via `if old_apn == new_apn: continue`). However, they add noise. On next script run these could be suppressed, or you can manually delete them from the master CSV now.

Sample self-references:
- `130-312-28 → 130-312-28`
- `097-083-013 → 097-083-013`
- `093-042-016 → 093-042-016` (note just says "New APN: 093-042-016")
- `089-124-013 → 089-124-013`, `089-093-010 → 089-093-010` (same pattern)

### Issue 3 - 39 Rows with change_year = 2026 (Outside ETL Scope)

These parcels still appeared in the FC through 2025 (`fc_last_year = 2025`), meaning the transition hasn't occurred within the 2012–2025 window. The notes describe a future or very recent event.

**Impact:** Step 2b will write `change_year = 2026` into `csv_lookup` substitutions. Since the CSV only covers 2012–2025, the condition `Year >= 2026` will never be true and no substitution will be applied. These rows are effectively inert for the current ETL run. No action required unless the CSV is extended to 2026.

### Issue 4 - Complex Multi-Step Chain APNs

Several genealogy chains span 3+ steps (e.g., `001-070-06 → 001-070-20 → 1418-10-701-001`). Each intermediate step is captured as its own row in the master CSV, and Step 2b applies them in sequence via the corrected `df_csv`. However, if an intermediate APN is not in the original CSV (it existed only briefly between two renaming events and was never assigned residential units), the chain may not resolve completely.

These cases are rare and would appear in `QA_Lost_APNs` after the next ETL run with diminished but non-zero counts.

---

## 7. Source Attribution

| Source File | Rows in Master |
|---|---|
| `parcel_geneology_notes_2.csv` (full population) | 1,793 |
| `parcel_geneology_notes.csv` (detailed tracker notes) | 55 |

The detailed tracker notes file (notes_1) contributed 55 rows that had more detailed or corrected notes than the corresponding entries in notes_2. These include complex multi-parcel histories for known project areas and condo conversions.

---

## 8. Next Steps

### Priority 1 - Fill Unknown Change Years (241 rows)

Filter master CSV to `year_source = unknown`, fill in `change_year` for each. Most of these are Washoe County `005-xxx` / `007-xxx` → `1318-xx-xxx-xxx` renumbering events that predate 2012 (enter `2012` for all such cases).

### Priority 2 - Validate Split Primaries

For `change_type = split` rows with `is_primary = 1`, confirm the first-listed successor is the unit-bearing parcel. The parser picks the first APN mentioned after "New APN:" as primary, which may not always match where the residential unit ended up.

Focus on splits with high unit counts - these are most impactful on the deficit. Use the `QA_Lost_APNs` table from the current ETL run (before genealogy) to identify which split APNs had the most units.

### Priority 3 - Run ETL with Genealogy Applied

Once unknown change years are filled in (or even before - the 1,175 rows with known change years will already improve the match rate):

```powershell
& "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" "C:/Users/mbindl/Documents/GitHub/Reporting/parcel_development_history_etl/main.py" --skip-s01 --skip-s05
```

Then compare `QA_Units_By_Year` (CSV vs. FC deficit) against the baseline from `REPORT_20260321.md` to measure improvement.

### Priority 4 - Annual Maintenance

When the residential CSV is updated for a new year:
1. Re-run `build_genealogy_master.py` to pick up any new genealogy notes added to the source CSVs
2. Review any new `year_source = unknown` rows added
3. The master CSV is append-safe - existing rows with manually filled `change_year` values will be overwritten on re-run, so keep a backup of manual edits or consider moving manually corrected rows to a separate `apn_genealogy_manual.csv` that gets merged in `build_genealogy_master.py`

---

## 9. Output File Location

| File | Path |
|---|---|
| Master genealogy CSV | `data/raw_data/apn_genealogy_master.csv` |
| Builder script | `parcel_development_history_etl/build_genealogy_master.py` |
| ETL application step | `parcel_development_history_etl/steps/s02b_genealogy.py` |
| QA output (after ETL run) | `C:\GIS\ParcelHistory.gdb\QA_Genealogy_Applied` |
