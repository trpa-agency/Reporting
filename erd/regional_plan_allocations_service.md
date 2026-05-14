# Future-state spec: Regional Plan Allocations web service

> **Status: RECOMMENDATION.** Companion to [`target_schema.md`](./target_schema.md).
> Not DDL. This is a starting point for the Corral / LT Info owner to validate
> against the live schema.

## Why this doc exists

The Phase 2 dashboards (`regional-capacity-dial`, `allocation-tracking`,
`pool-balance-cards`, `public-allocation-availability`) need allocation data
split by **plan era** (1987 / 2012 / combined) with **assigned vs not-assigned**
status, by jurisdiction, for all four commodities (RES / RBU / CFA / TAU).

Today that data path is fully manual:

1. The analyst hand-assembles `data/from_analyst/All Regional Plan Allocations Summary.xlsx`
   from the LT Info pool balance report **plus hard-coded 1987 Plan figures**.
2. `parcel_development_history_etl/scripts/convert_regional_plan_allocations.py`
   converts that xlsx to `data/processed_data/regional_plan_allocations.json`.
3. The dashboards fetch the JSON.

Every accounting cycle repeats step 1 by hand. The goal of this doc: define
the **web service** that would replace steps 1-2 so the dashboards
self-refresh from a live source.

## What the service must return

The shape is already pinned down by `regional_plan_allocations.json` (see the
converter for the exact JSON structure). In tabular terms:

| Grain | Fields |
|---|---|
| commodity x pool/jurisdiction x plan-era | `RegionalPlanMaximum`, `NotAssigned`, `AssignedToProjects` |
| residential x jurisdiction x year (1986-2026) | `Released`, `Assigned`, `NotAssigned`, `Unreleased` |

`plan-era` is one of `1987`, `2012`, `combined` (combined = 1987 + 2012).

## The fundamental split: what Corral has vs what it does not

This is the crux, and it is why a single clean SQL query is not enough.

| Need | In Corral / LT Info? | Source |
|---|---|---|
| 2012-era pool balances, assigned / not-assigned, by pool x commodity x jurisdiction | **Yes** | `dbo.CommodityPool` + `dbo.TdrTransaction*` + `dbo.ResidentialAllocation`; or the proposed `PoolDrawdownYearly`; or the existing LT Info web service |
| 2012-era per-year released / assigned | **Yes** | `dbo.ResidentialAllocation.IssuanceYear`, `dbo.TdrTransaction.ApprovalDate`; materialized in proposed `PoolDrawdownYearly` |
| **1987 Plan per-jurisdiction maxima + status** | **No** | Hard-code. The analyst's note in the xlsx cites the source: *"1987 Allocations from 2012 Regional Plan Update Analysis"* |
| **1987-era allocations-by-year (1986-2011)** | **No** | Hard-code. Same source. |
| **Per-era Regional Plan Maximum (the policy caps)** | **No** | Hard-code. TRPA Code + the 2026 PPTX slide 8 (8,687 RES / 2,000 RBU / 400 TAU / 1,000,000 CFA). |

The analyst's email said it directly: *"for now we would need to hard-code the
1987 plan amounts, as those figures (especially pre-2012 allocations) are not
currently in LT Info."* A perfect Corral query still cannot produce the 1987
half. So the service is always **live 2012-era data UNION a hard-coded 1987-era
reference**.

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
the residential by-year series. Those are exactly the hard-code gaps above.

So the existing service is a usable building block - the new service does not
need to recompute 2012-era balances from raw Corral if it can lean on this one.

## Recommended: a `RegionalPlanCapacity` seed table

Hold the hard-coded half in one small reference table, seeded from the *2012
Regional Plan Update Analysis* file (and re-checked each cycle, since the 1987
Plan is effectively frozen - 6,070 of 6,087 residential already assigned).

```sql
CREATE TABLE RegionalPlanCapacity (
    Commodity            varchar(20) NOT NULL,   -- 'RES','RBU','CFA','TAU'
    Jurisdiction         varchar(40) NOT NULL,   -- matches dbo.Jurisdiction.JurisdictionName
    PlanEra              varchar(10) NOT NULL,   -- '1987' (this table is the 1987 source of truth)
    RegionalPlanMaximum  int NOT NULL,
    NotAssigned          int NOT NULL,
    AssignedToProjects   int NOT NULL,
    SourceNote           varchar(200) NULL,      -- provenance, e.g. '2012 Regional Plan Update Analysis'
    CONSTRAINT PK_RegionalPlanCapacity PRIMARY KEY (Commodity, Jurisdiction, PlanEra)
);
-- Optionally a sibling RegionalPlanCapacityByYear for the 1986-2011 residential
-- by-year block (jurisdiction x year x released/assigned).
```

This is the same pattern `target_schema.md` already endorses for policy
constants - reference data the transactional system does not carry.

## Recommended SQL

### Primary path: query the proposed `PoolDrawdownYearly`

`target_schema.md` already proposes `PoolDrawdownYearly` - a nightly-materialized
table, one row per `(PoolID, Year)`, with columns `StartingBalance`, `Released`,
`Assigned`, `Used`, ... `EndingBalance`. If that table gets built, the 2012-era
half of this service is a simple read - no new derivation logic:

```sql
-- 2012-era status by pool (RES / RBU / CFA / TAU)
-- RegionalPlanMaximum = the pool's authorization (earliest-year StartingBalance)
-- NotAssigned         = what is still in the pool (latest-year EndingBalance)
-- AssignedToProjects  = Maximum - NotAssigned
SELECT
    cm.CommodityShortName                                  AS Commodity,
    j.JurisdictionName                                     AS Jurisdiction,
    cp.CommodityPoolName                                   AS Pool,
    '2012'                                                 AS PlanEra,
    pd_first.StartingBalance                               AS RegionalPlanMaximum,
    pd_last.EndingBalance                                  AS NotAssigned,
    pd_first.StartingBalance - pd_last.EndingBalance        AS AssignedToProjects
FROM dbo.CommodityPool cp
JOIN dbo.Commodity    cm ON cm.CommodityID   = cp.CommodityID
JOIN dbo.Jurisdiction j  ON j.JurisdictionID = cp.JurisdictionID
CROSS APPLY (SELECT TOP 1 * FROM PoolDrawdownYearly d
             WHERE d.PoolID = cp.CommodityPoolID ORDER BY d.Year ASC ) pd_first
CROSS APPLY (SELECT TOP 1 * FROM PoolDrawdownYearly d
             WHERE d.PoolID = cp.CommodityPoolID ORDER BY d.Year DESC) pd_last;
```

Residential by-year (released / assigned / end-of-year not-assigned) is then
just a straight read:

```sql
SELECT j.JurisdictionName AS Jurisdiction, pd.Year,
       pd.Released, pd.Assigned, pd.EndingBalance AS NotAssignedEoY
FROM PoolDrawdownYearly pd
JOIN dbo.CommodityPool cp ON cp.CommodityPoolID = pd.PoolID
JOIN dbo.Commodity    cm ON cm.CommodityID   = cp.CommodityID
JOIN dbo.Jurisdiction j  ON j.JurisdictionID = cp.JurisdictionID
WHERE cm.CommodityShortName IN ('SFRUU','MFRUU')          -- residential allocation
ORDER BY j.JurisdictionName, pd.Year;
```

### Combine the two eras

```sql
-- combined = live 2012 (from Corral / PoolDrawdownYearly) + frozen 1987 (seed table)
SELECT Commodity, Jurisdiction, PlanEra,
       RegionalPlanMaximum, NotAssigned, AssignedToProjects
FROM   v_RegionalPlanAllocations_2012        -- the query above, as a view
UNION ALL
SELECT Commodity, Jurisdiction, '1987' AS PlanEra,
       RegionalPlanMaximum, NotAssigned, AssignedToProjects
FROM   RegionalPlanCapacity
WHERE  PlanEra = '1987'
UNION ALL
SELECT Commodity, Jurisdiction, 'combined' AS PlanEra,
       SUM(RegionalPlanMaximum), SUM(NotAssigned), SUM(AssignedToProjects)
FROM ( /* the 1987 + 2012 rows above */ ) eras
GROUP BY Commodity, Jurisdiction;
```

### Until `PoolDrawdownYearly` exists

Two interim options, in order of preference:

1. **Consume the existing `GetDevelopmentRightPoolBalanceReport` service** for
   the live 2012-era numbers and UNION the `RegionalPlanCapacity` seed. The
   "service" is then a thin combiner - lowest effort, no Corral write access
   needed. Map `BalanceRemaining` -> `NotAssigned`,
   `ApprovedTransactionsQuantity` (and/or `TotalDisbursements`) -> the
   assigned side; confirm the exact mapping with the LT Info owner.
2. **Derive 2012-era status from raw Corral tables.** The join spine (verify
   column names against the live schema):

   ```sql
   -- SKETCH - validate joins against the live Corral schema before use.
   -- "Assigned" = an allocation drawn to a parcel via an ALLOCASSGN
   -- TdrTransaction; "Not Assigned" = still sitting in its CommodityPool.
   SELECT cm.CommodityShortName AS Commodity,
          j.JurisdictionName    AS Jurisdiction,
          cp.CommodityPoolName  AS Pool,
          COUNT(ra.ResidentialAllocationID)                          AS RegionalPlanMaximum,
          SUM(CASE WHEN asg.TdrTransactionID IS NULL THEN 1 ELSE 0 END) AS NotAssigned,
          SUM(CASE WHEN asg.TdrTransactionID IS NOT NULL THEN 1 ELSE 0 END) AS AssignedToProjects
   FROM dbo.CommodityPool cp
   JOIN dbo.Commodity    cm ON cm.CommodityID   = cp.CommodityID
   JOIN dbo.Jurisdiction j  ON j.JurisdictionID = cp.JurisdictionID
   LEFT JOIN dbo.ResidentialAllocation ra ON ra.CommodityPoolID = cp.CommodityPoolID
   -- ALLOCASSGN linkage: via dbo.TdrTransactionAllocation.SendingAllocationPoolID
   -- + ReceivingParcelID, or whatever FK the live schema exposes - CONFIRM.
   LEFT JOIN dbo.TdrTransactionAllocation asg
          ON asg.SendingAllocationPoolID = cp.CommodityPoolID
   GROUP BY cm.CommodityShortName, j.JurisdictionName, cp.CommodityPoolName;
   ```

   This is the logic `PoolDrawdownYearly`'s nightly job would run anyway (see
   the `vCommodityLedger` draft in `target_schema.md`), so building
   `PoolDrawdownYearly` first and reading it is the cleaner long-term move.

## Recommended delivery path

| Phase | What | Effort |
|---|---|---|
| **Now** | The hand-converted `regional_plan_allocations.json` (already done) drives Phase 2 dashboards. | done |
| **Near-term** | Seed `RegionalPlanCapacity`. Stand up the "thin combiner": existing LT Info service + the seed table -> the JSON shape. Removes the manual xlsx step. | small |
| **Long-term** | Build `PoolDrawdownYearly` per `target_schema.md`. Expose `v_RegionalPlanAllocations` as an SDE-registered ESRI REST service (the same publishing path `target_schema.md` describes for the future Parcel Development History service). Dashboards fetch it directly. | follows the `target_schema.md` build |

The near-term step alone retires the manual xlsx assembly; the long-term step
removes the dependency on the external LT Info service entirely.

## Open questions for the Corral / LT Info owner

1. **`GetDevelopmentRightPoolBalanceReport` field semantics.** Confirm the
   mapping: is `BalanceRemaining` exactly "not assigned to a project," and is
   `ApprovedTransactionsQuantity` + `BalanceRemaining` = the pool's
   authorization? `TotalDisbursements` did not cleanly equal the xlsx
   `RegionalPlanMaximum` in spot checks - what does it count?
2. **"Assigned" definition.** In the xlsx, "Assigned to Projects" - is that an
   `ALLOCASSGN` transaction (allocation drawn to a parcel), or built-through-
   permit-completion (`Used` in `PoolDrawdownYearly`)? The dashboards need the
   former; confirm.
3. **1987 Plan source.** The analyst cites "2012 Regional Plan Update Analysis"
   for the 1987 allocations. Is that file authoritative and stable enough to
   seed `RegionalPlanCapacity` once, or does it get revised?
4. **Pool -> jurisdiction -> plan-era mapping.** The LT Info pools are the
   2012-era pools. Confirm there is no pool in `dbo.CommodityPool` that
   represents 1987-era capacity (the assumption here is that 1987 is entirely
   in the seed table, 2012 entirely in Corral).
5. **TAU internal discrepancy.** The current xlsx has a known gap: the TAU
   status table jurisdiction rows sum to 395 but the summary says 400 (the
   missing 5 is an "Unassigned to CPs" row that only appears in TAU's
   plan-era table). A live service should reconcile this rather than inherit it.
