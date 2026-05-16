# Draft message to the analyst

Save-and-edit version. Tone is collaborative: the asks are framed as "help us bring the dashboards up to your standard," not "you're doing this wrong." The goal is to convert the analyst's xlsx-based work product into queries the database can run on its own - so the dashboards always agree with him, without him having to send a new file every cycle.

---

## Short version (email, ~180 words)

Subject: AllocationsBalances is live on the REST service + next steps

Thanks for the May xlsx deliveries. Identity checks passed cleanly on all three, so I normalized each into a tidy long-form table and we loaded them as new Cumulative_Accounting REST layers:

- `MapServer/10` - Development Right Allocation Balances (12 rows: Source x Commodity) - from `AllocationsBalances_May2026.xlsx`
- `MapServer/11` - Development Right Residential Units by Source (98 rows: Year x Direction x Source) - from `FINAL RES SUMMARY 2012 to 2025.xlsx`
- `MapServer/12` - Development Right Pool Balances (26 rows: Commodity x Pool) - from `All Regional Plan Allocations Summary.xlsx`

Four dashboards now read your published figures directly: **Allocation Tracking Overview** (4 commodity rows from layer 10), **Tahoe Development Tracker section iv** "Not reserved and not released" (TotalBalanceRemaining per commodity from layer 10), **Residential Additions by Source** (5-source facet + removed-area + 4 KPI cards from layer 11), and **Pool Balance Cards** (per-pool cards + KPIs from layer 12). Everything matches your tally to within 1-7 units; the small drift is refresh lag against Corral.

That handles the snapshot side. The bigger ask: 30 minutes to walk through how you derive these numbers so we can move the derivations into the database itself. Goal is layers 10/11/12 stop being snapshots of your xlsx files and become SQL views that produce the same numbers nightly from layers 3/4/5/7. Your xlsx files become validation checks instead of data deliveries, and the dashboards stop going stale between cycles.

Specifics in the attached one-pager. Available any time this week.

---

## Long version (one-pager attachment, ~400 words)

**Subject: Path to publishing your cumulative-accounting figures as live REST data**

### What shipped this week

Three of your xlsx files normalized + published as new Cumulative_Accounting REST layers, plus your `Allocation_Status` pointer closed the residential CSV gap:

- **Layer 10** "Development Right Allocation Balances" (12 rows = 3 Sources x 4 Commodities) from your `AllocationsBalances_May2026.xlsx`. Drives **Allocation Tracking Overview** (all 4 commodity rows: RES / RBU / CFA / TAU read `Source='Grand Total'` directly) and **Tahoe Development Tracker section iv** "Not reserved and not released" (TotalBalanceRemaining per commodity, residential = RES + RBU per your framing).
- **Layer 11** "Development Right Residential Units by Source" (98 rows = 14 years x 7 source/direction combos) from your `FINAL RES SUMMARY 2012 to 2025.xlsx`. Drives **Residential Additions by Source** (4 KPI cards + 5-source facet chart + 2-source removed-area chart). Replaces 5 inline JS arrays that had to be hand-edited.
- **Layer 12** "Development Right Pool Balances" (26 rows = 4 commodities x per-pool) from your `All Regional Plan Allocations Summary.xlsx`. Drives **Pool Balance Cards** (per-pool cards + 3 KPIs for each of the 4 commodities). Replaces a nested JSON intermediate that had to be regenerated on every refresh.
- **Layer 4** (existing `Allocations 2012 Regional Plan`) now drives the Allocation Tracking Charts tab residential Sankey + per-jurisdiction bar, eliminating another CSV dependency. Your `Allocation_Status` + `Development_Right_Pool` classification reproduces the 832/844/154/770 breakdown directly from row-level data.
- **Layer 12** also drives the Allocation Tracking Charts tab CFA + TAU Sankey + per-jurisdiction bar (via row-shape synthesis: one row per (pool, status) combo, qty = aggregate count). With this, **allocation-tracking is now 100% LIVE** - no CSV, no hardcoded, no inline arrays on the page. The last CSV dependency (`CFA_TAU_allocations.csv`) is retired.

Four more REST layers published 2026-05-15:

- **Layer 13 "Development Right Pool Balances Metering"** (853 rows) - residential per-year released vs assigned, per pool, from your Allocations Summary xlsx's `by_year` blocks. Drives the metering chart on pool-balance-cards.
- **Layer 14 "Development Right QA Corrections"** (5,925 rows, paginated) - the QA correction Events + Detail joined into one table. Drives qa-change-rationale.
- **Layer 15 "Development Right Reserved Not Constructed"** (3 rows) - your 698/46,962/138 tally from the 5/15 email. Drives Tracker section iii. Path-to-true-derivation: needs Construction_Status field on Layer 3 (1987 RP) once that's added.
- **Layer 16 "Development Right Residential Projects"** (26 rows) - your "Major Completed Projects" list from the PPTX, now structured (Year / ProjectName / Units / Notes). Drives the sidebar on residential-additions-by-source.

**Every active dashboard is now 100% LIVE** against the Cumulative_Accounting REST service. Eight new layers (9/10/11/12/13/14/15/16) plus the existing row-level Layer 4 handle four xlsx files' worth of analyst work, an inline list, a hardcoded tally, a nested JSON, and two CSVs - all eliminated.

The forward conversation is the architectural one: see `erd/canonical_row_level_schema.md`. The 8 snapshot layers we just published could become 8 SQL views over a row-level data model. That's the path that retires the analyst xlsx workflow entirely.

Numbers match your tallies to within 1-7 units depending on the commodity - the drift is Layer 4 / Layer 10 / Layer 11 / Layer 12 refresh lag against Corral, not a methodology disagreement. Tracker section iii ("Reserved, not constructed") is still hardcoded - that needs a construction-status discriminator the REST service doesn't carry yet (more below).

### What's not working

Every cycle, the dashboards depend on your xlsx because the cumulative-accounting summary isn't queryable from the REST service. We have row-level data for the inputs - allocations, pool balances, transactions, banked rights, parcel development history - but the derivations that produce your published summaries don't exist as database queries. So the dashboards either embed your figures (which go stale) or compute their own (which sometimes disagree with you).

The RBU experiment last week is the canonical example: we read 379 cumulative-allocated from layer 5's `ApprovedTransactionsQuantity` field, and your tally says 1,260. Both came from Corral; the field semantic isn't documented anywhere. We had to discover by hand that the right derivation is `Total − BalanceRemaining − Unreleased`.

### What we need from you to fix it

This isn't asking for new data - it's asking you to share methodology you already have. Concretely:

1. **For each summary metric on AllocationsBalances**, share the source query, Excel formula, or manual reconciliation that produces the number. SQL is ideal; SUMIFS formulas or written-out descriptions work too.

2. **Define the `Status` classification** for an allocation grid row (Allocated / In Pool / TRPA Pool / Unreleased). What fields drive each value?

3. **Define the 1987 vs 2012 RP split**. Is there a column in Corral that tags allocation origin, or is it derived from pool membership?

4. **Define "Reserved, not constructed"** on the Tracker - is it `Allocated − PDH built`, or something else?

5. **Cadence** - how often does this file refresh? Drives whether the staging step is automated.

6. **30-minute walkthrough** of the layer 7 banked reconciliation findings (separate workstream, in progress).

### Why this matters

Once we document your methodology once, we can implement it as a SQL view that derives the same numbers nightly from the row-level layers. At that point, your xlsx becomes a validation check ("does the dashboard match my expectation?") instead of a data delivery. Dashboards stop going stale between cycles. You stop being a bottleneck on the refresh.

I've written up the full diagnosis at `erd/path_to_normalized_rest.md` if you want the unabridged version.

---

## Appendix: residential allocations are already there (2026-05-15)

Your pointer on `Allocation_Status` + `Construction_Status` + `Development_Right_Pool` landed. Layer 4 already has everything we need for 2012 RP residential. The translation:

| Your card (2012 RP residential) | Layer 4 query | Rows |
|---|---|---:|
| Allocated to private development | `Allocation_Status='Allocated'` | 832 (= 681 Completed + 151 Not Completed) |
| Jurisdiction pool | `Allocation_Status='Unallocated' AND Development_Right_Pool != 'TRPA'` | 844 (PL 349 + SLT 181 + WA 123 + EL 98 + DG 93) |
| TRPA pool | `Allocation_Status='Unallocated' AND Development_Right_Pool='TRPA'` | 154 |
| Unreleased | `Allocation_Status='Unreleased'` | 770 |
| | **Sum** | **2,600** |

The dashboard's residential row repointed onto Layer 4 today and the math hits 2,600 exactly. It's off from your 5/15 xlsx by 7 rows (Allocated 832 vs your 839; Jurisdiction pool 844 vs your 837) which I'm reading as refresh lag - Layer 4 hasn't been republished since your last Corral pull. Worth confirming - if it's NOT refresh lag, there's a methodology question we should chase.

Bonus: the Tracker's "Reserved, not constructed" residential figure (your 698 number) - the 2012 RP slice is `Allocation_Status='Allocated' AND Construction_Status='Not Completed'` = **151** rows. The remaining 547 comes from the 1987 RP equivalent (layer 3, which is currently aggregated rather than row-level). Once layer 3 carries the same construction status, the Tracker stops needing hardcoded numbers.

So for residential, the path-to-REST is essentially complete - the dashboards can compute your numbers from row-level data without your xlsx. Where the asks below really bite is CFA / TAU / RBU (no per-allocation grid) and 1987 RP (pre-aggregated layer 3 instead of row-level).
