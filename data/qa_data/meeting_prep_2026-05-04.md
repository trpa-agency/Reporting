# Meeting prep - QA tracking schema + parcel data handoff

**For:** TRPA analyst
**From:** Mason Bindl
**Date:** May 4, 2026
**Re:** Your three asks (schema walkthrough + parcel genealogy + 2012–2026 parcel data)

---

Quick prep for our chat. Three asks from your message - here's what's ready and what needs a confirm-from-you.

## 1. QA tracking schema (the main ask) - ready

We've prototyped the database for tracking changes to your previously-reported Cumulative Accounting data. It's a sidecar table called `QaCorrectionDetail` that hangs off a broader `ParcelDevelopmentChangeEvent` table, with a 1-to-(0 or 1) relationship triggered when `ChangeSource = 'qa_correction'`. Key design choices:

- **Annual reporting cadence + periodic big-sweep campaigns** (your 2023 + 2026) - the schema models both. `ReportingYear` is any annual value; `SweepCampaign` is a nullable tag for sweep years specifically.
- **9-value controlled vocabulary** for `CorrectionCategory`, sourced directly from your Sheet2.
- **`RawAPN` audit column** preserves the pre-canonicalization APN string for traceability.
- **APN canonicalization** as a single function (`parcel_development_history_etl/utils.py:canonical_apn`) used by all three tracks.

Three things to look at before / during the meeting:

- **Concise track doc:** [`erd/qa_corrections_track.md`](https://github.com/trpa-agency/Reporting/blob/MTB-Edits/erd/qa_corrections_track.md) - overview, data flow diagram, refresh workflow, open issues
- **The actual schema:** [`erd/target_schema.md`](https://github.com/trpa-agency/Reporting/blob/MTB-Edits/erd/target_schema.md), section "ERD - QA corrections sidecar (Track C)"
- **Working dashboard:** [`html/qa-change-rationale.html`](https://github.com/trpa-agency/Reporting/blob/MTB-Edits/html/qa-change-rationale.html) - open in any browser; AG Grid filterable by year/sweep/canonicality, sidebar bar chart of top correction categories color-coded canonical (navy) vs noncanonical (orange)

The dashboard already loaded your `CA Changes breakdown.xlsx` end-to-end: 5,925 normalized change events, 218,192 reconciliation findings labeled against the existing s06_qa.py automated detection outputs.

## 2. Final parcel genealogy lookups - ready

The consolidated lookup is at `data/qa_data/apn_genealogy_master.csv` (297 KB, 5-source merge). Plus the 4 unmerged source files if you want to see lineage:

| File | Source |
|---|---|
| `apn_genealogy_master.csv` | the consolidated merge - what you probably want |
| `apn_genealogy_tahoe.csv` | your historical genealogy data |
| `apn_genealogy_accela.csv` | from Accela permit records |
| `apn_genealogy_ltinfo.csv` | from LT Info |
| `apn_genealogy_spatial.csv` | derived from spatial overlap analysis |

I can attach all 5 to an email, share via OneDrive, or you can clone the repo (MTB-Edits branch) - let me know which path is easiest on your end.

## 3. Final 2012–2026 parcel-level data - needs format confirm

The parcel_development_history_etl pipeline produces a feature class called `OUTPUT_FC` that's the canonical 2012–2026 per-APN per-year residential development data. Roughly 50K rows × 15 columns, including geometry. Need to know what format works best for your end:

- **CSV export** - flat table, easiest for Excel / pandas work
- **Shapefile** - preserves geometry for ArcMap / Pro
- **Direct GDB read access** - if you want to query live

Tell me the format and I'll send within the day.

## 4. One thing for you to look at (optional homework)

When the loader normalized your CA Changes XLSX, only **30.2% of your Sheet1 category labels matched the controlled vocabulary in your Sheet2**. The other 70% paraphrase rather than match exactly. We pulled together a triage CSV with the **17 unique noncanonical labels**, their occurrence counts, and 5 sample APNs each:

- **Explainer:** [`data/qa_data/correction_category_mapping_TODO.md`](https://github.com/trpa-agency/Reporting/blob/MTB-Edits/data/qa_data/correction_category_mapping_TODO.md)
- **Triage CSV:** [`data/qa_data/correction_category_mapping.csv`](https://github.com/trpa-agency/Reporting/blob/MTB-Edits/data/qa_data/correction_category_mapping.csv)

The top 5 noncanonical labels alone account for ~80% of the mismatches:

| Reporting year | Label | Occurrences |
|---:|---|---:|
| 2023 | Corrections - Units Removed Based on County Data | **890** |
| 2023 | Unit(s) not previously counted. Constructed in or before 2012. Verified with County. | **733** |
| 2023 | Correction Based on County Data | **696** |
| 2023 | Mobile Home Park Corrections | **582** |
| 2023 | Over-Correction | **349** |

If you can fill in the `canonical_label` column (map to existing Sheet2 vocab, or invent a new label and we'll add it), the dashboard's match rate jumps from 30% to ~100%.

## Suggested 30-minute agenda

| Min | What |
|---:|---|
| 0–3 | Context recap - three-track framing (Genealogy / Allocations / QA Corrections); where your CA Changes data fits |
| 3–10 | Walk through the `QaCorrectionDetail` schema; why we chose sidecar over column extension |
| 10–15 | Loader demo - your XLSX → normalized rows (~30 sec live run) |
| 15–22 | Dashboard E1 demo + the 30% canonical-vocab triage discussion |
| 22–27 | Hand-off - genealogy CSVs + parcel-level data format confirmation |
| 27–30 | Open questions, cadence going forward, next steps |

## Three quick questions to think about

1. **Mapping approach** - expand Sheet2 to include the 17 noncanonical labels the analyst's been using, OR keep Sheet2 tight and maintain a separate `correction_category_mapping.csv` lookup?
2. **Parcel-level data format** - CSV / shapefile / direct GDB access for the 2012–2026 OUTPUT_FC?
3. **CA Changes XLSX cadence** - are you maintaining it continuously (rolling corrections every reporting year), or only during sweep campaigns? Affects how often we re-run the loader.

## Quick links (all on the MTB-Edits branch)

- **Track doc:** `erd/qa_corrections_track.md`
- **Schema:** `erd/target_schema.md` → "ERD - QA corrections sidecar"
- **Dashboard:** `html/qa-change-rationale.html`
- **Your action item:** `data/qa_data/correction_category_mapping_TODO.md` + `correction_category_mapping.csv`
- **Genealogy master:** `data/qa_data/apn_genealogy_master.csv`
- **Repo:** `https://github.com/trpa-agency/Reporting/tree/MTB-Edits`

Talk soon -
Mason
