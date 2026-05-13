# Parcel Genealogy - Methods and Maintenance

**Project:** Tahoe Development History by Parcel (2012–2025)
**Last updated:** April 15, 2026

---

## What Is the Genealogy System?

Parcel boundaries change over time. When a parcel is subdivided, merged, or renumbered by the county assessor, the APN changes. The development attribute CSVs reference APNs that may no longer exist in the current parcel database. Without correction, units under retired APNs are silently lost from the output.

The **genealogy system** tracks APN transitions - old APN → new APN, and the year the change occurred - and remaps historical CSV entries to their current parcel identifiers before any spatial join. The goal is a **comprehensive genealogy covering all parcel events in the Tahoe Basin from 2012 to 2025**.

---

## How It Works in the ETL

Step S02b reads `apn_genealogy_tahoe.csv` and modifies the long-format CSV dataframe in place before the lookup dictionary is built. For each qualifying record:

> For all rows in df_csv where `APN == old_apn AND Year >= change_year`, replace APN with `new_apn`.

This redirects historical CSV units to the current parcel APN, so they match the FC.

**Application filter:** `is_primary = 1 AND in_fc_new = 1 AND change_year IS NOT NULL`  
As of April 15, 2026: **32,529 apply-ready rows**, producing **522 substitutions / 8,803 unit-years remapped** per run.

**Conflict-skip:** If the new APN already has a non-zero unit count for a given year, the substitution is skipped for that year. Those units stay under the old APN and are resolved by the S03 spatial crosswalk instead.

**Post-genealogy dedup:** Genealogy substitution can create duplicate `(APN, Year)` rows when the target APN has a zero-unit placeholder row (zeros don't trigger conflict-skip). A groupby-max dedup immediately after S02b prevents the zero row from clobbering the real value in the csv_lookup dict. This run removed 90 such duplicate rows.

---

## Genealogy Sources

Four sources feed the consolidated genealogy. Each is maintained separately and merged by `build_genealogy_tahoe.py`.

### 1. Manual Master (`apn_genealogy_master.csv`)
**1,958 rows | Priority 1 (highest)**

Hand-curated entries, each verified against the FC or in ArcGIS Pro. This is the most reliable source. Entries here override all others.

**Schema:**

| Field | Description |
|-------|-------------|
| `old_apn` | Retired APN |
| `new_apn` | Successor APN |
| `change_year` | First year to use new APN |
| `change_type` | `rename`, `split`, `merge` |
| `is_primary` | 1 = apply in ETL; 0 = record only (e.g. coworker already handled in CSV) |
| `year_source` | How change_year was determined (`fc_last_old+1`, `fc_first_new`, `manual`) |
| `notes_excerpt` | Brief rationale |
| `source` | Where the pair came from |
| `fc_last_year` | Last year old APN appears in FC |
| `fc_new_first` | First year new APN appears in FC |

**When to add here:** After verifying a pair in ArcGIS Pro - old APN disappears, new APN appears at the same location.

**How to add:** Edit `apn_genealogy_master.csv` directly (UTF-8 encoding), then rebuild:
```
"C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" parcel_development_history_etl/scripts/build_genealogy_tahoe.py
```

### 2. Accela (`apn_genealogy_accela.csv`)
**~37,000 rows | Priority 2**

Parsed from Accela permit system data. Covers 2021–2025 events reliably. Parsed by `parse_genealogy_sources.py` from `data/raw_data/Accela_Genealogy_March2026.xlsx`.

### 3. LTinfo (`apn_genealogy_ltinfo.csv`)
**~3,500 rows | Priority 3**

Parent→child pairs from the LTinfo parcel system. Most lack `change_year` and are currently skipped. Coverage improves as dates are filled in.

### 4. Spatial (`apn_genealogy_spatial.csv`)
**~700 rows | Priority 4**

Auto-detected from spatial overlap between consecutive year layers. Lower confidence - supplement, not primary source.

---

## Consolidated File (`apn_genealogy_tahoe.csv`)

Built by `build_genealogy_tahoe.py`. This is what the ETL reads.

**Current state (April 15, 2026):**

| Metric | Value |
|--------|-------|
| Total pairs | 42,159 |
| With change_year | 39,370 |
| Without change_year (skipped each run) | 2,789 |
| READY (is_primary=1, in_fc_new=1, change_year set) | 806 |
| El Dorado pairs | 31,563 |
| Manual source pairs | 1,909 |
| Accela source pairs | 37,331 |

Rebuild whenever any source file changes:
```
"C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" parcel_development_history_etl/scripts/build_genealogy_tahoe.py
```

---

## Finding and Adding New Genealogy Pairs

### Step 1 - Identify Lost APNs

After each ETL run, `QA_Lost_APNs` lists APNs from the CSV with units that couldn't be placed in the FC. Cross-reference against known genealogy sources:

```
"C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" parcel_development_history_etl/scripts/qa_lost_apns_vs_new_genealogy.py
```

Output: `data/raw_data/qa_lost_vs_new_genealogy.csv`

| Action | Meaning |
|--------|---------|
| `NEEDS_CHANGE_YEAR` | Candidate new APN found in Accela or KK data; needs a verified change_year |
| `already_in_tahoe` | Pair exists in genealogy but still lost - `in_fc_new=0` or `change_year` missing |
| `no_candidate` | No match found; needs manual spatial investigation in ArcGIS Pro |
| `ALREADY_HANDLED` | Coworker already applied correct units in CSV; add as `is_primary=0` for record completeness |

### Step 2 - Auto-Detect `change_year`

For `NEEDS_CHANGE_YEAR` pairs, run:

```
"C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" parcel_development_history_etl/scripts/detect_change_years.py
```

Output: `data/raw_data/change_year_candidates.csv`

This queries OUTPUT_FC and SOURCE_FC to find:

| Column | Description |
|--------|-------------|
| `FC_Last_Year_Old` | Last year the old APN appears in FC |
| `FC_First_Year_New` | First year the new APN appears in FC |
| `Suggested_Change_Year` | `last_year_old + 1` (or `first_new` if old not found) |
| `Confidence` | HIGH, MEDIUM_OFFBYONE, MEDIUM_GAP, MEDIUM_NEW_ONLY, LOW |
| `Promote_Ready` | YES for HIGH/MEDIUM_OFFBYONE pairs where new APN is in FC |

The output is pre-formatted with columns matching `apn_genealogy_master.csv` schema. **Promote_Ready = YES** pairs can be copied directly into the master.

### Step 3 - Verify in ArcGIS Pro

For MEDIUM_GAP or uncertain pairs, verify manually:
1. Select the old APN in its last known year → confirm geometry
2. Select the new APN in its first known year → confirm same location
3. Confirm the transition makes geographic sense (split → multiple successors; rename → same polygon, new APN)

### Step 4 - Add to Master and Rebuild

Add verified rows to `apn_genealogy_master.csv` (save as UTF-8), rebuild `apn_genealogy_tahoe.csv`, re-run ETL with `--skip-s01 --skip-s05`.

---

## Special Cases

### El Dorado APN Format Change (2018)

El Dorado County switched suffixes from 2-digit to 3-digit in 2018 (e.g. `080-155-11` → `080-155-011`). This is handled by the ETL's El Dorado fix in S02 - **not** by the genealogy system.

**Do not add El Dorado format-only pairs to genealogy.** The `detect_change_years.py` script filters these automatically via `_is_el_format_pair()`.

Exception: if the format change coincides with a genuine rename (different parcel, not just different padding), that IS a genealogy record.

### CSV and the El Dorado Transition

The residential CSV should have **one row per APN**. The ETL normalizes El Dorado format by year. If a coworker manually entered both the 2-digit and 3-digit form of the same APN in separate CSV rows, the ETL's El Dorado split-format dedup resolves it (keeps max value), but the CSV is harder to maintain. The correct practice: one row per APN, let the ETL handle the format.

### `is_primary = 0` Records

Genealogy records that exist for documentation only - the ETL will not apply the substitution. Use when:
- The coworker has already correctly attributed units to the new APN in the CSV
- Both old and new APN have units in overlapping years (ALREADY_HANDLED)

Units are correct in the output; the record exists so the full succession history is captured.

### Conflict Skips

When genealogy substitution is skipped (target APN has non-zero units for that year), the old APN stays in df_csv and flows to S03 spatial crosswalk. This is normal. Review `QA_Genealogy_Applied` → `Years_Conflicted` column to see where this occurred.

---

## Maintenance Workflow

```
1. Run ETL
        ↓
2. Review QA_Units_By_Year → deficit still present?
        ↓ yes
3. Run qa_lost_apns_vs_new_genealogy.py → qa_lost_vs_new_genealogy.csv
        ↓
4. Run detect_change_years.py → change_year_candidates.csv
        ↓
5. Copy Promote_Ready=YES rows into apn_genealogy_master.csv
   Verify MEDIUM_GAP rows in ArcGIS Pro → add confirmed ones
        ↓
6. Run build_genealogy_tahoe.py → apn_genealogy_tahoe.csv rebuilt
        ↓
7. Run ETL (--skip-s01 --skip-s05)
        ↓
8. Repeat from step 2
```

---

## Deficit Reduction History

| Date | Annual Deficit | Total Deficit | Key Change |
|------|---------------|---------------|------------|
| Mar 25, 2026 | −185/yr | −2,590 | Baseline (spatial genealogy first added) |
| Apr 14, 2026 (start) | −185/yr | −2,590 | Session start |
| Apr 14, 2026 | −3 to −13/yr | ~−109 | El Dorado split-format dedup added; 91 pairs promoted with change_year; 16 ALREADY_HANDLED pairs added |
| Apr 15, 2026 (Run 1) | −3/yr all years | −42 | 3 MANUAL_APN_FIXES formalized; post-genealogy dedup added to S02 |
| **Apr 15, 2026 (Run 2)** | **0/yr all years** | **0** | **El Dorado Case 2 fix: 3-digit-only parcels now padded + found in FC via S03 Case B expansion** |

**Zero deficit achieved.** The three APNs previously thought to have no geometry (`015-370-30`, `016-300-64`, `018-320-18`) were confirmed as El Dorado parcels born at or after 2018 - their padded 3-digit forms exist in the FC but were invisible to `build_el_dorado_fix()` (which only queried for 2-digit FC APNs). Extended to collect 3-digit-only parcels and add them to `pad_map`. S03 geometry lookup extended symmetrically. Both pre- and post-2018 year-rows were resolved. See REPORT_20260415b.md for full details.
