# CSV Data Quality — Known Issues

**Last updated:** 2026-04-16  
**Context:** Residential units CSV (`ExistingResidential_2012_2025_unstacked.csv`) vs `Parcel_Development_History` FC  
**Bottom line:** ETL totals match CSV totals exactly for all 14 years. The genealogy steps resolved all parcel transition cases. The issues below are genuine data quality questions requiring human judgment — not ETL failures.

---

## What is NOT an issue

Before digging into real issues, two QA table categories are commonly misread as problems:

**`PARCEL_SPLIT` (515 APNs, 6,281 units) — handled, not broken.**  
These APNs appear in the CSV for years after the parcel was re-platted. They look "lost" because the old APN identity doesn't exist in the FC for those years. But `QA_Units_By_Year` shows Diff=0 for every year, which proves s02b (genealogy) already remapped those CSV rows to successor APNs before the unit write. The units are on the right geometry. No action needed.

**`PARCEL_NEW` (62 of 63 APNs, 655 units) — handled, not broken.**  
The CSV uses the new/successor APN identity; the ETL traces back through the genealogy and writes the units to the predecessor row that has geometry. Same proof: totals balance.

---

## Issue 1 — CSV vs FC Native unit count disagreements

**Scale: ~1,700 APNs across FC_NATIVE_YEARS (2012, 2018–2025)**  
**Table:** `QA_Unit_Reconciliation` (category = `DISAGREE`)  
**ETL behavior:** CSV wins. FC native values from `SOURCE_FC` are overwritten.

For years where SOURCE_FC already had curated unit counts (2012 and 2018–2025), many parcels have different counts between the old curated FC values and the new CSV. The ETL treats the CSV as authoritative, so the FC ends up with the CSV's numbers.

**This is the most important issue to resolve.** Most cases are small (1–2 unit difference), but the top cases involve large multi-family / resort parcels:

| APN | CSV Units | FC Native | Diff | Direction | Notes |
|---|---|---|---|---|---|
| 032-202-004 | 78 | 393 | 315 | CSV < FC | Large multi-family — which count is right? |
| 1318-22-316-002 | 155 | 1 | 154 | CSV > FC | Was FC native = 1 a placeholder? |
| 1318-22-310-011 | 154 | 1 | 153 | CSV > FC | Same pattern as above |
| 1318-22-310-012 | 154 | 1 | 153 | CSV > FC | Same pattern |
| 025-021-077 | 63 | 126 | 63 | CSV < FC | Double-count in old FC? |
| 023-181-046 | 31 | 61 | 30 | CSV < FC | Same ratio as above — systematic? |
| 023-221-039 | 34 | 60 | 26 | CSV < FC | |
| 132-202-05 | 75 | 50 | 25 | CSV > FC | CSV higher |
| 1318-26-101-012 | 40 | 64 | 24 | CSV < FC | |
| 032-201-009 | 16 | 40 | 24 | CSV < FC | |
| 031-290-034 | 22 | 43 | 21 | CSV < FC | |
| 023-241-010 | 18 | 38 | 20 | CSV < FC | |
| 023-181-029 | 17 | 37 | 20 | CSV < FC | |
| 093-130-014 | 0 | 17 | 17 | CSV < FC | CSV says 0, FC says 17 — demolished? |

**Pattern to investigate:** Many `CSV < FC` cases show the FC having almost exactly 2× the CSV value (78 vs 393 is off, but 63 vs 126, 31 vs 61 are exact 2×). This could mean the old FC curation double-counted units (e.g., counted each unit twice for condos), or the CSV is counting only one building of a two-building complex.

**Action:** Review the top ~20 largest-diff APNs on the map. Confirm which count is actually correct and update either the CSV or flag the FC native value as incorrect. Full list is in `QA_Unit_Reconciliation.csv`.

---

## Issue 2 — Sporadic / unexplained APN presence

**Scale: 131 APNs, 826 units**  
**Table:** `QA_Lost_APNs` (category = `UNKNOWN`)

These APNs appear in the FC for some years but not others, and the CSV attributes units to them for the gap years. Unlike PARCEL_SPLIT, there's no genealogy record explaining the transition — the APN just goes missing mid-series and comes back, or disappears entirely after a few years.

Top cases by units:

| APN | Units | In FC | Lost Years | Notes |
|---|---|---|---|---|
| 117-230-004 | 72 | 2013–2014, 2023–2025 | 2012, 2015–2022 | Long gap — data entry or parcel change? |
| 1418-10-802-011 | 48 | 2024–2025 only | 2012–2023 | Recently added to CSV? |
| 094-171-007 | 24 | 2013–2014 | All other years | Only 2 years in FC — transient? |
| 097-130-029 | 13 | 2013 only | All other years | Single year |
| 126-080-25 | 13 | 2013 only | All other years | Short format APN (missing leading zero?) |
| 117-020-009 | 12 | 2013–2014 | All other years | |
| 031-213-016 | 11 | 2023–2025 | 2012–2022 | New in recent years |

**Possible causes:**
- APN existed briefly (parcel created and merged back before genealogy was tracked)
- CSV was populated for some years but not others by mistake
- Short-format APNs (e.g., `126-080-25` should be `126-080-025`) — padding error

**Action:** Check each on the map. If the parcel physically existed during the gap years, either add a genealogy record or correct the CSV. If the parcel didn't exist, the CSV should have 0 units for those years.

---

## Issue 3 — APN format typo

**Scale: 1 APN, 1 unit/year, 2012–2025**

| CSV APN | Likely Correct APN | Years | Units/yr |
|---|---|---|---|
| `015-370-30` | `015-370-11` | 2012–2025 | 1 |

The CSV uses suffix `30` but the physical parcel in the FC uses suffix `11`. These are different parcel identifiers — not a zero-padding difference. The units are already counted correctly in the FC under `015-370-11` / `015-370-011` / `015-370-030` (the parcel that changed format across years), so totals are not affected. This is a CSV labeling error.

**Action:** Confirm on the map that `015-370-11` and `015-370-30` refer to the same physical property, then update the CSV to use the correct APN.

---

## How the ETL resolves parcel transitions (for reference)

For anyone wondering why PARCEL_SPLIT/PARCEL_NEW don't cause total discrepancies:

1. `s02_load_csv.py` reads the CSV and applies the El Dorado APN padding fix (2-digit → 3-digit suffix for El Dorado County parcels, year ≥ 2018).
2. `s02b_genealogy.py` loads `apn_genealogy_tahoe.csv` and remaps old APN identities to successor APNs for years ≥ change_year. This runs *before* `csv_lookup` is built, so all downstream steps see the corrected APN.
3. If a CSV APN is remapped to a successor that already has non-zero units for that year, the remap is skipped (conflict protection) to avoid double-counting.
4. `s06_qa.py` computes `QA_Units_By_Year` using the same genealogy-corrected `df_csv`. So CSV_Total and FC_Total are both measured with the same APN normalization — a "lost" old APN identity doesn't inflate CSV_Total.

The result: totals balance because units are counted once, under the correct current APN.

---

## Files referenced

| File | Location | Purpose |
|---|---|---|
| `QA_Unit_Reconciliation.csv` | `data/qa_data/` | Full CSV vs FC native comparison |
| `QA_Lost_APNs.csv` | `data/qa_data/` | All APNs missing from FC for some years |
| `QA_Units_By_Year.csv` | `data/qa_data/` | Year-level CSV vs FC total reconciliation |
| `apn_genealogy_tahoe.csv` | `data/raw_data/` | Master genealogy table (editable) |
| `diagnose_parcel_new.csv` | `data/qa_data/` | Scenario classification for PARCEL_NEW APNs |
