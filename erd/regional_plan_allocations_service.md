# Future-state spec: Regional Plan Allocations web service

> **Status: Active - the pool-balance sibling to
> [`residential_allocation_grid_service.md`](./residential_allocation_grid_service.md).**
> Companion to [`system_of_record_roadmap.md`](./system_of_record_roadmap.md)
> (the portfolio plan). A recommendation, not DDL - a starting point for the LT
> Info owner to validate against the live service.

## Why this doc exists

The cumulative-accounting dashboards (`tahoe-development-tracker`,
`allocation-tracking`, `pool-balance-cards`, `public-allocation-availability`)
need allocation data split by **plan era** (1987 / 2012 / combined) with
**assigned vs not-assigned** status, by jurisdiction, for all four commodities
(RES / RBU / CFA / TAU).

Today that data path is fully manual:

1. The analyst hand-assembles `data/from_analyst/All Regional Plan Allocations Summary.xlsx`
   from the LT Info pool balance report **plus hard-coded 1987 Plan figures**.
2. `parcel_development_history_etl/scripts/convert_regional_plan_allocations.py`
   converts that xlsx to `data/processed_data/regional_plan_allocations.json`.
3. The dashboards fetch the JSON.

Every accounting cycle repeats step 1 by hand. This doc defines what replaces
steps 1-2 so the dashboards self-refresh from the `Cumulative_Accounting`
service.

## What the service must return

The shape is pinned down by `regional_plan_allocations.json` (see the converter
for the exact JSON structure). In tabular terms:

| Grain | Fields |
|---|---|
| commodity x pool/jurisdiction x plan-era | `RegionalPlanMaximum`, `NotAssigned`, `AssignedToProjects` |
| residential x jurisdiction x year (1986-2026) | `Released`, `Assigned`, `NotAssigned`, `Unreleased` |

`plan-era` is one of `1987`, `2012`, `combined` (combined = 1987 + 2012).

## The fundamental split: 2012-era is live, 1987-era is frozen

The data comes from two places, and only one of them is live. Phase 1 already
stood up the frozen half as a published table.

| Need | Source | Status |
|---|---|---|
| 2012-era pool balances - assigned / not-assigned, by pool x commodity x jurisdiction | LT Info `GetDevelopmentRightPoolBalanceReport` web service | live service; consume via the staging ETL |
| 2012-era residential by-year (2013-2026) | `Cumulative_Accounting` layer 4 "Residential Allocations 2012 Regional Plan" - carries `IssuanceYear` per allocation | live (the allocation-grid interim load; the grid ETL keeps it fresh) |
| **1987 Plan per-jurisdiction maxima + status** | `Cumulative_Accounting` layer 3 "Allocations 1987 Regional Plan" - already a published table | live (Type C frozen reference - the analyst's 1987 baseline, no upstream system) |
| **1987-era residential by-year (1986-2012)** | the same 1987 frozen reference | confirm it is in layer 3 or needs a sibling reference table |
| **Per-era Regional Plan Maximum (the policy caps)** | TRPA Code + the regional plan documents (8,687 RES / 2,000 RBU / 400 TAU / 1,000,000 CFA) | frozen reference values |

The analyst's note in the source xlsx says it directly: the 1987 Plan figures,
"especially pre-2012 allocations, are not currently in LT Info." No Corral query
can produce the 1987 half. So the service is always **live 2012-era data UNION a
frozen 1987-era reference** - and the frozen half (layer 3) already exists. The
`RegionalPlanCapacity` seed-table idea from the earlier draft of this doc is
realized: layer 3 *is* that seed table, published.

## The existing LT Info service - reuse, do not rebuild

`https://www.laketahoeinfo.org/WebServices/GetDevelopmentRightPoolBalanceReport/JSON/<token>`
already returns a clean 54-record JSON array of **2012-era** pool balances:

```jsonc
{ "DevelopmentRightPoolName": "Residential Allocation - Placer County",
  "DevelopmentRight": "Residential Allocation",
  "Jurisdiction": "Placer County, CA (PLCO)",
  "TotalDisbursements": 558, "ApprovedTransactionsQuantity": 100,
  "PendingTransactionQuantity": 116, "BalanceRemaining": 342 }
```

It covers pool x commodity x jurisdiction for RES / RBU / CFA / TAU. **What it
does not have:** the 1987-vs-2012 split, the per-era Regional Plan Maximum, or
the residential by-year series - those are the frozen-reference gaps above. The
new service does not recompute 2012-era balances from raw Corral; it leans on
this existing service.

## How it gets to the dashboards

Same pattern as the residential allocation grid: the nightly LT Info staging ETL
does the pull, a SQL view does the combine.

1. **Stage.** `stage_ltinfo_allocations.py` pulls `GetDevelopmentRightPoolBalanceReport`,
   normalizes the 54 records, and truncate+inserts an `LTInfo_PoolBalance` table
   in the TRPA Enterprise GDB, stamped with a refresh timestamp.
2. **Combine.** A SQL view in the GDB UNIONs the three eras: `2012` from
   `LTInfo_PoolBalance`, `1987` from the layer 3 table, `combined` =
   `1987 + 2012` summed per commodity x jurisdiction.
3. **Publish.** The view publishes through the `Cumulative_Accounting` service,
   alongside the existing layers.
4. **Repoint.** `convert_regional_plan_allocations.py` and the four dashboards
   read the service instead of the hand-converted JSON; the manual xlsx step is
   retired. `Additional Development as of April2026.xlsx` folds in here too - it
   is the same pool balance report.

```sql
-- the combine view (sketch). LTInfo_PoolBalance = the staged 2012 data;
-- Allocations_1987_Regional_Plan = layer 3, the frozen 1987 reference.
SELECT Commodity, Jurisdiction, '2012' AS PlanEra,
       RegionalPlanMaximum, NotAssigned, AssignedToProjects
FROM   LTInfo_PoolBalance
UNION ALL
SELECT Commodity, Jurisdiction, '1987' AS PlanEra,
       RegionalPlanMaximum, NotAssigned, AssignedToProjects
FROM   Allocations_1987_Regional_Plan
UNION ALL
SELECT Commodity, Jurisdiction, 'combined' AS PlanEra,
       SUM(RegionalPlanMaximum), SUM(NotAssigned), SUM(AssignedToProjects)
FROM   ( /* the 1987 + 2012 rows above */ ) eras
GROUP BY Commodity, Jurisdiction;
```

Mapping the web service's fields onto `RegionalPlanMaximum` / `NotAssigned` /
`AssignedToProjects` is the **one unconfirmed piece** - see the open questions.
The ETL must not ship until the LT Info owner confirms it.

## The residential by-year series

The earlier draft of this doc punted the by-year residential grain to a
hypothetical Corral-resident table. It no longer needs one: layer 4 carries
`IssuanceYear` per allocation, so the 2012-era by-year released series is
`layer 4 GROUP BY jurisdiction, IssuanceYear`. The 1987-era by-year block
(1986-2012) is part of the frozen reference. This is also what unblocks the
per-year "metering" visualization deferred on the dashboards.

## Open questions for the LT Info owner

These gate the combine view - the ETL refresh itself ships without them.

1. **`GetDevelopmentRightPoolBalanceReport` field semantics.** *Partially
   resolved empirically* via `validate_layer5_mapping.py` (output in
   `data/qa_data/layer5_mapping_validation.md`). Findings:
    - `BalanceRemaining == json.not_assigned` is **exact** for RBU, CFA,
      and TAU at the commodity-total level. **Confirmed.**
    - Residential is off by exactly **770** - the unreleased allocations
      tracked in the residential allocation grid (layer 4), not in the pool
      balance report. The combine view must add these back in for
      residential.
    - `TotalDisbursements` is the 2012-era cumulative disbursed (Approved +
      Pending + Balance), **not** the Regional Plan cap. The cap has to
      come from layer 3 (1987 baseline) + a separate 2012-era reference.
    - `ApprovedTransactionsQuantity` is **not** equal to
      `assigned_to_projects` because the latter rolls in 1987-era
      assignments that live in layer 3.
   **Remaining open piece**: how to derive the **2012-era cap per
   RBU/CFA/TAU pool**? Empirical guess: 2012-era cap = `TotalDisbursements +
   BalanceRemaining`. For residential the cap is known (2,600 = 1,830 issued
   per layer 4 + 770 unreleased). For non-residential it needs LT Info
   owner confirmation before the combine view publishes.
2. **"Assigned" definition.** In the xlsx, "Assigned to Projects" - is that an
   `ALLOCASSGN` transaction (allocation drawn to a parcel), or built-through-
   permit-completion? The dashboards need the former; confirm.
3. **1987 Plan source stability.** Layer 3 is seeded from the "2012 Regional
   Plan Update Analysis" file. Confirm that file is authoritative and stable
   enough that layer 3 needs no per-cycle revision (the 1987 Plan is effectively
   frozen).
4. **Pool to plan-era mapping.** The LT Info pools are the 2012-era pools.
   Confirm no pool in the pool balance report represents 1987-era capacity (the
   assumption: 1987 is entirely in layer 3, 2012 entirely in the LT Info
   service).
5. **TAU internal discrepancy.** The current xlsx has a known gap: the TAU
   status table jurisdiction rows sum to 395 but the summary says 400 (the
   missing 5 is an "Unassigned to CPs" row that only appears in TAU's plan-era
   table). The staging ETL should reconcile this and fail loud, not inherit it.

## The ask

Two parts, mirroring the residential allocation grid:

- **Interim - done.** The pool balance report is loaded into the
  `Cumulative_Accounting` REST service as **layer 5, "Development Right Pool
  Balance Report"** (`Cumulative_Accounting/MapServer/5`) - the same seven
  fields the LT Info service returns (`BalanceRemaining`,
  `ApprovedTransactionsQuantity`, `TotalDisbursements`,
  `PendingTransactionQuantity`, `Jurisdiction`, `DevelopmentRight`,
  `DevelopmentRightPoolName`). The 1987 baseline already lives as layer 3.
  The dashboards still consume `regional_plan_allocations.json` for the era
  splits and the residential by-year metering (both derived from layers 3 + 4
  + 5); repoint when the combine view is published.
- **ETL - done.** `parcel_development_history_etl/scripts/stage_ltinfo_allocations.py`
  refreshes layer 5 from `GetDevelopmentRightPoolBalanceReport` nightly: fetch,
  schema-verify, truncate+insert, stamp a refresh-log row. The script just
  stages the 7 raw LT Info fields verbatim - field-semantics interpretation is
  a downstream concern (the combine view + dashboards), not the ETL's. Default
  write target is `STAGING_GDB`; repoint at an SDE path once direct SDE write
  is wired in.
- **Target - combine view + dashboard repoint.** Build the SDE combine view
  that UNIONs layer 5 (2012-era) + layer 3 (1987-era) into the era-split shape
  the dashboards consume, publish it through `Cumulative_Accounting`, then
  repoint the converter and the dashboards. **Gated on the field-semantics
  confirmation above** (this is where `BalanceRemaining` /
  `ApprovedTransactionsQuantity` / `TotalDisbursements` get mapped to
  `not_assigned` / `assigned_to_projects` / `regional_plan_maximum`; the wrong
  mapping silently produces wrong numbers).
