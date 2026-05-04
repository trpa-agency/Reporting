# Ken — Correction Category Mapping TODO

**Status: needs your triage. ~17 noncanonical labels to map.**

## What we found

When we loaded `CA Changes breakdown.xlsx` into the new schema, **70% of the category labels in your Sheet1 didn't match the controlled vocabulary in your Sheet2 exactly**. They paraphrase rather than match — same intent, different wording. The loader still captures every row, but the canonicality flag is `False` for those, so dashboards show them in orange ("needs mapping") rather than navy ("matched canonical vocab").

The good news: there are only **17 unique noncanonical labels** to map (16 from the 2023 cycle's `2023 Summary Reason` column, 1 from the 2026 cycle's `2026 Changes Reason` column). All 17 are listed in [`correction_category_mapping.csv`](./correction_category_mapping.csv) with their occurrence counts and sample APNs for context.

## What we need from you

Open [`correction_category_mapping.csv`](./correction_category_mapping.csv) and fill in the **`canonical_label`** column for each row. Two options:

**Option A — map to existing Sheet2 vocab.** If "Corrections - Units Removed Based on County Data" really means the same thing as Sheet2's "Units Removed Based on County/TRPA Records or GIS", write the Sheet2 label in `canonical_label`. The loader will use that mapping and the canonicality rate jumps from 30% to ~100%.

**Option B — add a new canonical label.** If a Sheet1 label is genuinely different from anything in Sheet2 (a category Sheet2 missed), invent a new canonical label and put it in `canonical_label`. We'll add it to Sheet2 / the loader's vocab on the next refresh.

Use the `notes` column for any context (e.g., "deprecated in 2026 — drop this label going forward").

## The 5 highest-volume labels (do these first)

| Reporting year | Noncanonical label | Occurrences |
|---:|---|---:|
| 2023 | Corrections - Units Removed Based on County Data | **890** |
| 2023 | Unit(s) not previously counted. Constructed in or before 2012. Verified with County. | **733** |
| 2023 | Correction Based on County Data | **696** |
| 2023 | Mobile Home Park Corrections | **582** |
| 2023 | Over-Correction | **349** |

These five alone account for ~3,250 of the ~4,100 noncanonical occurrences. Mapping them addresses ~80% of the issue.

## After you fill it in

1. Save the CSV in place.
2. Re-run [`notebooks/04_load_ca_changes.ipynb`](../../notebooks/04_load_ca_changes.ipynb) (one-shot, ~30 sec).
3. Re-run [`notebooks/05_qa_reconciliation.ipynb`](../../notebooks/05_qa_reconciliation.ipynb).
4. The canonical-vocab match rate in [`html/qa-change-rationale.html`](../../html/qa-change-rationale.html) jumps; the bar chart's orange bars become navy.

We can also fold this into a future canonical Sheet2 if you want to avoid the loose-text drift on the next big sweep.

## Background

Full track context: [`erd/qa_corrections_track.md`](../../erd/qa_corrections_track.md). Open issue O1 ("30% canonical-vocab match rate") is exactly this work.
