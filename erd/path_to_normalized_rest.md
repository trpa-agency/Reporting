# Path to normalized REST data - diagnosis + asks

Written 2026-05-15 after receiving the analyst's `AllocationsBalances_May2026.xlsx`. Captures why the dashboards keep depending on snapshot spreadsheets, what would have to change to fix it, and the specific asks of the analyst + TRPA Engineering / IT to get there.

## The pattern we're stuck in

Every cumulative-accounting cycle, the analyst sends a fresh xlsx (or several). The xlsx contains pre-aggregated summary numbers - the "right" answers for residential allocated, RBU jurisdiction pool, CFA unreleased, etc. The dashboards then either (a) embed those numbers as constants in the HTML or (b) approximate them by computing against the row-level data the REST service does publish.

Both modes are wrong. Mode (a) means the dashboards go stale the moment the xlsx is out of date. Mode (b) means the dashboards disagree with the analyst's published figures - sometimes by a lot. The RBU discovery on 2026-05-15 is the canonical example: dashboard read 379 allocated from layer 5; analyst's xlsx says 1,260. Both came from the same Corral data; the difference is which field you trust and how you derive cumulative-allocated.

The pattern is structural, not a personal failing. The analyst is doing the right thing by sending the data in the form he produces it. The fix is moving the derivation out of his Excel and into the database, where it can be queried instead of refreshed.

## Why this hasn't happened yet

Three blockers, in priority order.

### 1. Critical fields aren't on the REST surface

The cumulative-accounting summary needs a per-allocation `Status` (Allocated / In Pool / TRPA Pool / Unreleased) and a per-row source attribution (1987 RP / 2012 RP). Neither is on layer 4 today. The grid (2,600 rows) is published but without the classification that makes the summary computable. Without `Status`, the dashboard has no way to count "how many are still in the jurisdiction pool" - so it either reads a CSV the analyst built outside the REST service or it embeds a hardcoded count.

Similarly for `AllocationsBalances` layer 10 (the one this cycle's xlsx normalizes into): the row-level inputs to those numbers live across layers 3, 4, 5, 6, and 7, but the joins + filters that produce the analyst's totals aren't documented or implemented anywhere queryable. Layer 10 itself is just a snapshot of the answer, not a derivation.

### 2. Field semantics are undocumented

Layer 5 (`Cumulative_Accounting/MapServer/5`, pool balance report) exposes two count-like fields per pool: `BalanceRemaining` and `ApprovedTransactionsQuantity`. The 2026-05-15 RBU experiment confirms `BalanceRemaining` means "still in pool, unassigned" (it sums correctly with the analyst's jurisdiction-pool + TRPA-pool tallies). But `ApprovedTransactionsQuantity` does **not** mean cumulative-allocated - the dashboard read it as 379 for RBU, vs the analyst's 1,260. It evidently means something narrower (recent transactions? active reservations?). No documentation accompanies the layer, so every consumer has to reverse-engineer it.

This is a problem because consumers will get it wrong silently. The right derivation (`Total − BalanceRemaining − Unreleased = AllocatedToPrivate`) works for now but depends on knowing the field semantics; the moment a new consumer comes along and trusts the field name, they get a wrong number.

### 3. The analyst's derivations live in Excel, not SQL

The analyst is reconciling across Accela, Corral (the cumulative-accounting source-of-record database), the LT Info webservices, and parcel registry data. He's the abstraction layer. His Excel files encode logic like "sum these pools but exclude these statuses" or "subtract banked from issued before computing allocated" - logic that doesn't exist in any single database view today.

Until that logic is migrated into a queryable artifact (a database view, a stored procedure, an ETL output), every dashboard refresh requires him to regenerate the xlsx by hand. That's the bottleneck.

## What "normalized REST" actually means

The goal is: every dashboard reads row-level data from the REST service and computes its own summaries client-side. No xlsx in the loop. The analyst's role shifts from "produce the summary numbers" to "validate that the dashboards' computed summaries match expectations." When they don't match, the database (not the Excel file) gets fixed.

Concretely, the end-state schema:

| Layer | Today | What it would carry in the end-state |
|---|---|---|
| 0 PDH | LIVE row-level | unchanged |
| 3 Allocations 1987 | row-level, ~6,087 rows | add `Status` field |
| 4 Allocations 2012 | row-level, 2,600 rows | add `Status` field; add `SourcePlanYear` tagging the 488 unreleased reserve vs the 2,112 issued |
| 5 Pool Balance Report | aggregated per-pool | add formal field documentation; tag pools by SourcePlanYear (1987 / 2012); rename `ApprovedTransactionsQuantity` or add a CumulativeAllocated companion field |
| 6 Transactions | row-level | unchanged |
| 7 Banked Rights | row-level but disagrees with Corral 71% of the time | reconcile + document the discrepancy |
| **10 AllocationsBalances** | proposed (snapshot of the xlsx) | downgrade to a database VIEW that derives the same numbers from layers 3/4/5/7, removing the snapshot dependency entirely |

Layer 10 as a view (not a snapshot) is the eventual target. The snapshot is a stepping-stone: ship it now to unblock dashboards, but build the view in parallel so we can swap it out without changing the API contract.

## Asks of the analyst

The analyst's job for the next two weeks is to share enough of his methodology that we can replicate it in SQL or Python. Specific asks:

1. **For each metric on `AllocationsBalances_May2026.xlsx`**, share the source query, Excel formula, or manual calculation that produced it. Example: "AllocatedToPrivate (RES, 2012 RP) = 839" - what data did you sum, with what filters, from what database/view? If it's a Corral SQL query, share the SQL. If it's an Excel SUMIFS, share the formula. If it's reconciled by hand, describe the reconciliation.

2. **Define `Status` for an allocation row.** When you classify an allocation grid row as Allocated / In Pool / TRPA Pool / Unreleased, what fields drive that classification? Is it a single column in Corral, or is it derived from multiple fields (e.g., presence of an APN, assignment date, etc.)?

3. **Define `Source` for the 1987 vs 2012 split.** Is there a field in Corral that says "this allocation came from the 1987 RP authorization" vs "the 2012 RP authorization"? Or is it derived from pool membership / year-issued / something else?

4. **Define "Reserved, not constructed"** on the Tracker (section iii). Is this `AllocatedToPrivate − PDH on-the-ground built`? Some other derivation?

5. **Cadence of the xlsx.** Monthly, quarterly, year-end? Drives whether the staging-into-SDE step is automated or done by hand on receipt.

6. **Layer 7 `BankedQuantity` discrepancy.** 71% of (APN, commodity) pairs in layer 7 disagree with the Corral `pci.BankedQuantity` table. Walkthrough scheduled - need ~30 min to triage the flag taxonomy in `data/qa_data/banked_reconciliation_findings.csv`.

None of these are asks for new data. Every one is "what's already in your head or Excel file - help us write it down so the database can reproduce it."

## Asks of TRPA Engineering / IT

These are the database / publishing changes that have to happen for the analyst's hand-work to become automatable. Roughly priority-ordered.

1. **Add `Status` field to layer 4** (the 2012 allocation grid). Allowed values: `Allocated`, `In Pool`, `TRPA Pool`, `Unreleased`. The classification rules come from the analyst (ask #2 above). Without this field, allocation-tracking has to read a CSV.

2. **Add `Status` field to layer 3** (the 1987 allocations). Same idea, derived from whatever Corral uses. May be simpler since most are `Allocated` by definition.

3. **Document layer 5 field semantics formally.** A field-level README on the layer itself or in the GIS metadata. Minimum: a one-sentence definition of `BalanceRemaining`, `ApprovedTransactionsQuantity`, `PreviousReleases`, `Carryover`, `OneTimeReleases` per the LT Info webservice schema. If `ApprovedTransactionsQuantity` is not cumulative-allocated, say what it is.

4. **Build the `AllocationsBalances` view as a database view** (not a snapshot table). Once the analyst documents his derivation (ask #1 above), translate it to a SQL view in the Enterprise GDB that derives the same 12 rows from layers 3/4/5/7 in real time. Replaces layer 10 snapshot with layer 10 view; no change to the REST API contract for consumers.

5. **Tag layer 5 pools by `SourcePlanYear`** (1987 / 2012). Currently inferable from pool name (e.g., "TRPA 2012 Regional Plan Allocation"), but fragile. Adding a field makes the per-source split queryable.

6. **Reconcile layer 7 with Corral pci**. Per the 2026-05-13 reconciliation, the stored `pci.BankedQuantity` field is the root cause of drift between layer 7 and the analyst's tally. Either fix the stored field or replace it with a derived computation in the layer 7 ETL.

## The intermediate move (what we're doing this cycle)

Until the asks above land, we're shipping the snapshot path:

1. The analyst's xlsx normalizes into 12 rows (`data/processed_data/allocations_balances.csv`).
2. Those 12 rows load into SDE as `dbo.AllocationsBalances` and publish as layer 10.
3. Dashboards repoint from their current CSV/hardcoded values to layer 10.
4. When the analyst sends a refreshed xlsx, we re-run the converter, re-load SDE, dashboards pick up the new figures automatically.

This is a Band-Aid. It removes the per-dashboard hardcoded values and replaces "the analyst said 1,260 in an email" with "layer 10 returns 1,260 because the analyst's xlsx says so." Better than today; not the goal. The goal is layer 10 becomes a view derived from layers 3/4/5/7, and the xlsx stops being part of the pipeline.

## Files referenced

- `data/from_analyst/AllocationsBalances_May2026.xlsx` - the snapshot
- `data/processed_data/allocations_balances.csv` + `.json` - normalized form
- `parcel_development_history_etl/scripts/convert_allocations_balances.py` - converter
- `erd/allocations_balances_layer.md` - schema + publishing plan for the snapshot layer
- `data/qa_data/dashboard_data_lineage.md` - per-dashboard data source audit
- `data/qa_data/banked_reconciliation_summary.md` - layer 7 vs Corral findings
