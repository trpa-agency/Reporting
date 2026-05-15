# Questions for the analyst

Open questions only the analyst can answer - data provenance, domain judgment,
and which numbers are tracked in a system versus carried by hand. Collected as
they surface during the system-of-record work. Mark a question answered (or
~~strike it~~) once resolved, and fold the answer into the relevant spec.

## 1. Is the 2012-Plan 2,600-allocation authorization tracked anywhere queryable? [ANSWERED]

Corral's `ResidentialAllocation` holds only *instantiated* allocations - 2,112
rows in `Corral_2026`, all sitting in named jurisdiction or TRPA pools. The
analyst's grid export has 2,600 rows; the extra 770 are "Unreleased" /
"TBD"-pool rows, the un-released remainder of the 2,600 authorization. Those
770 are not in `ResidentialAllocation`, and not in `CommodityPoolDisbursement`
(every residential pool's instantiated count equals its disbursed amount).

So the residential allocation grid is a union: a Corral query for the
instantiated allocations, plus the unreleased remainder from somewhere else.
**Is the 2,600 total a queryable value, or the analyst's own reference number?**
This decides whether the "unreleased" rows come from a query or from a
`RegionalPlanCapacity`-style reference table. See `probe_corral_2026.py` and
`regional_plan_allocations_service.md`.

**Answered (tested against `Corral_2026`).** The 2,600 is the 2012-Plan
residential authorization - a number from the regional plan document, not a
Corral query. The grid is a **union**: the saved query, filtered to
`IssuanceYear > 2012`, gives the instantiated 2012-Plan allocations; the 770
"TBD" rows are the unreleased remainder. Model: `(IssuanceYear > 2012) + 770 =
2,600`. Tested: `Corral_2026` returns 1,820 for `IssuanceYear > 2012`, so
`1,820 + 770 = 2,590` - within ~10 of the 2,600 authorization (the April grid
export and the `Corral_2026` snapshot differ slightly; reconcile before the ETL
goes live). The 770 "TBD" rows are blank placeholder padding, not records - in
the architecture the unreleased count is a scalar reference value (the
regional-plan figure), never phantom rows. See
`residential_allocation_grid_service.md`.

## 2. Where does `CFA_TAU_allocations.csv` come from?

It feeds the allocation-tracking Commercial and Tourist tabs (fetched off a
GitHub branch URL), but it is not a `config.py` constant and its origin is
unrecorded. **Who builds this file, and from what source - LT Info, Corral, or
by hand?**

## 3. `2025 Transactions and Allocations Details.xlsx` - Corral or the Accela permit system?

The roadmap inventory lists its system of record as Corral's `TdrTransaction`
family, but the `config.py` comment says "the analyst / TRPA permit system."
Those are different systems. **Which one is the real source?** It changes the
migration path for this artifact.

## 4. The "reconciled by the analyst" files - mechanical or judgment?

`FINAL RES SUMMARY 2012 to 2025.xlsx` and the `Final * Tracking` files are
Corral plus county-assessor data "reconciled by the analyst." **Is that
reconciliation mechanical record-matching, or does it involve judgment when the
sources disagree?** If it is judgment, there is a Type C component hiding in
these files - like the QA-correction log - and they need a structured intake
surface, not just a feed.

## 5. Smaller confirmations

- **xlsx vs CSV delivery:** for `OriginalYrBuilt.xlsx` and the `Final2026_*.csv`
  inputs, does the analyst deliver xlsx that someone converts to CSV, or are the
  CSVs delivered directly?
- **QA-correction scope:** is QA-correction tracking (`CA Changes breakdown.xlsx`
  -> a `QaCorrectionDetail` table) in scope for the `Cumulative_Accounting`
  service, or handled separately for now?
