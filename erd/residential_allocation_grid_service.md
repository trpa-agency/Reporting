# Web service spec: the residential allocation grid

> **Status: Active - SQL reverse-engineered and tested against Corral. The LT
> Info team already has the real query (they built the Manage grid); this SQL is
> a reference artifact, and the ask is a JSON endpoint over the existing grid.**
> Companion to
> [`system_of_record_roadmap.md`](./system_of_record_roadmap.md) (the portfolio
> plan) and [`regional_plan_allocations_service.md`](./regional_plan_allocations_service.md)
> (the sibling spec, for pool balances).

## The problem

`allocation-tracking.html` runs on `residentialAllocationGridExport_fromAnalyst.xlsx` -
a manual export the analyst takes from the in-app grid at
`parcels.laketahoeinfo.org/ResidentialAllocation/Manage`. That page is not
public, non-analyst staff cannot reach it, and "export and drop the file" is
exactly the hand-assembly step the roadmap is retiring.

The grid is Corral-origin data, so per the two-source rule it has to come out
through an LT Info web service. **No such endpoint exists yet.** This doc is the
spec to stand one up - working name `GetResidentialAllocationGrid`, same JSON
pattern as `GetDevelopmentRightPoolBalanceReport`.

## The grid: 11 columns, one row per residential allocation

`Residential Allocation Number`, `Development Right Pool`, `Issuance Year`,
`Type`, `Sequence`, `Allocation Status`, `Transaction`, `Pool`,
`Previous Transaction(s)`, `Receiving Parcel APN`, `Construction Status`.

## The SQL

Reverse-engineered against the Corral schema dump (`corral_schema.json`) and
**tested against `Corral_2026`** via `probe_corral_2026.py` (SQL Server, `dbo`
schema). Two bugs the test caught are fixed below: the `Transaction` CONCAT/NULL
handling and the `AllocationStatus` derivation.

```sql
SELECT
    -- Residential Allocation Number  e.g. "DG-13-R-01"  (computed - not stored)
    CONCAT(j.ResidentialAllocationAbbreviation, '-',
           RIGHT(CAST(ra.IssuanceYear AS varchar(4)), 2), '-',
           rat.ResidentialAllocationTypeCode, '-',
           FORMAT(ra.AllocationSequence, 'D2'))        AS ResidentialAllocationNumber,

    j.ResidentialAllocationAbbreviation                AS DevelopmentRightPool,
    ra.IssuanceYear                                    AS IssuanceYear,
    rat.ResidentialAllocationTypeCode                  AS [Type],
    ra.AllocationSequence                              AS [Sequence],
    cp.CommodityPoolName                               AS Pool,
    rp.ParcelNumber                                    AS ReceivingParcelAPN,

    -- Transaction - FIXED: CONCAT converts NULLs to '' and returns '--' rather
    -- than NULL, so the no-transaction case needs an explicit CASE.
    CASE
        WHEN tx.TdrTransactionID IS NULL THEN 'Start Transaction'
        ELSE CONCAT(tx.LeadAgencyAbbreviation, '-',
                    tx.TransactionTypeAbbreviation, '-',
                    CAST(tx.TdrTransactionID AS varchar(10)))
    END                                                AS [Transaction],

    -- Allocation Status - CORRECTED to the validated 2-state derivation. The
    -- earlier "AssignedToJurisdictionID IS NULL -> Unreleased" rule was wrong
    -- (2,092 of 2,112 rows have it null). Validated: Unallocated count = 998,
    -- an exact match to the analyst's grid.
    CASE
        WHEN ra.TdrTransactionID IS NOT NULL
          OR ra.IsAllocatedButNoTransactionRecord = 1 THEN 'Allocated'
        ELSE 'Unallocated'
    END                                                AS AllocationStatus,

    -- Previous Transaction(s) - LT Info app logic; source not found in Corral
    CAST(NULL AS varchar(100))                         AS PreviousTransactions,

    -- Construction Status - needs the ParcelPermit / workflow tables; LT Info to supply
    CASE WHEN tta.ReceivingParcelID IS NULL THEN 'Unallocated'
         ELSE NULL  /* 'Completed' / 'Not Completed' from permit completion state */
    END                                                AS ConstructionStatus

FROM       dbo.ResidentialAllocation      ra
JOIN       dbo.Jurisdiction               j   ON j.JurisdictionID  = ra.JurisdictionID
JOIN       dbo.ResidentialAllocationType  rat ON rat.ResidentialAllocationTypeID = ra.ResidentialAllocationTypeID
JOIN       dbo.CommodityPool              cp  ON cp.CommodityPoolID = ra.CommodityPoolID
LEFT JOIN  dbo.TdrTransaction             tx  ON tx.TdrTransactionID = ra.TdrTransactionID
LEFT JOIN  dbo.TdrTransactionAllocation   tta ON tta.TdrTransactionID = ra.TdrTransactionID
LEFT JOIN  dbo.Parcel                     rp  ON rp.ParcelID = tta.ReceivingParcelID
WHERE      ra.IssuanceYear > 2012   -- scope to the 2012-Plan era (matches the analyst's grid)
ORDER BY   j.ResidentialAllocationAbbreviation, ra.IssuanceYear, ra.AllocationSequence;
```

## Column mapping and confidence

| Grid column | Corral source | Confidence |
|---|---|---|
| Residential Allocation Number | computed: `Jurisdiction.ResidentialAllocationAbbreviation` + `IssuanceYear` + `ResidentialAllocationType.ResidentialAllocationTypeCode` + `AllocationSequence` | high |
| Development Right Pool | `Jurisdiction.ResidentialAllocationAbbreviation` | high |
| Issuance Year / Type / Sequence | `ResidentialAllocation` + `ResidentialAllocationType` | high |
| Pool | `CommodityPool.CommodityPoolName` | high |
| Receiving Parcel APN | `Parcel.ParcelNumber` via `TdrTransactionAllocation.ReceivingParcelID` | high - join cardinality verified clean |
| Transaction | computed from `TdrTransaction` (no stored `TransactionNumber` column) | medium - confirm the number-suffix rule |
| Allocation Status | derived 2-state CASE (no status column in Corral) | high - validated against the grid |
| Previous Transaction(s) | not found in the Corral schema | low - LT Info app logic |
| Construction Status | needs `ParcelPermit` / workflow tables | low - LT Info app logic |

## Verified against Corral_2026

- The query runs clean - every joined table and column exists.
- Unfiltered it returns **2,112 rows** = exactly the `ResidentialAllocation` row
  count (no fan-out from the `TdrTransactionAllocation` LEFT JOIN). With the
  `IssuanceYear > 2012` filter it returns **1,820** - the 2012-Plan scope - and
  `1,820 + 770 = 2,590`, within ~10 of the 2,600 authorization.
- `AllocationStatus`: the corrected 2-state CASE produced **Unallocated = 998**
  on the full-table run, matching the analyst's grid's Unallocated count -
  re-confirm against the filtered set at build time.
- The `Transaction` fix works: no-transaction rows read `'Start Transaction'`,
  not `'--'`.

## Open questions for the LT Info team

1. **RESOLVED - the 770 are a regional-plan reference number, not records.** The
   ~770 "Unreleased" / "TBD"-pool rows in the analyst's grid are blank
   placeholder padding - `TBD` in every field - representing a *count*, not
   allocation records. That count is the unreleased remainder of the 2012-Plan's
   **2,600** residential authorization (a regional-plan-document figure). The
   grid is a union: this query (now filtered `IssuanceYear > 2012`) gives the
   instantiated 2012-Plan allocations, plus the unreleased count. Tested against
   `Corral_2026`: 1,820 rows have `IssuanceYear > 2012`, and `1,820 + 770 = 2,590`
   - within ~10 of the 2,600 authorization (a snapshot-timing reconciliation, not
   a structural gap). The unreleased count is supplied as a scalar reference
   value, never as rows. See `questions_for_analyst.md` Q1.
2. **`Previous Transaction(s)`** - the source is not in the Corral schema dump.
   What populates this column in the app?
3. **`Construction Status`** (`Completed` / `Not Completed`) - which permit or
   workflow table drives this? `ParcelPermit` is the likely candidate.
4. **The transaction-number format.** `TdrTransaction` has no stored
   `TransactionNumber`; the grid shows e.g. `DCNV-ALLOC-170`. The query computes
   `LeadAgencyAbbreviation` + `TransactionTypeAbbreviation` + `TdrTransactionID` -
   confirm the numeric suffix is `TdrTransactionID` and not a per-agency sequence.

## The ask

The LT Info team built the `ResidentialAllocation/Manage` grid, so they already
have the query that backs it - this doc does **not** ask them to implement the
SQL above. That SQL is a **reference artifact**: it documents the 11 columns,
their Corral sources, and the derivations (the `AllocationStatus` and
`Transaction` logic), and it confirms - tested against `Corral_2026` - that the
data is all there. The ask is just: **expose the existing grid as a JSON web
service endpoint**, same pattern as `GetDevelopmentRightPoolBalanceReport`
(working name `GetResidentialAllocationGrid`).

**Interim - done.** The analyst's `residentialAllocationGridExport_fromAnalyst.xlsx`
(the CSV the repo already has) is loaded into the `Cumulative_Accounting` REST
service as **layer 4, "Residential Allocations 2012 Regional Plan"**
(`Cumulative_Accounting/MapServer/4`) - parallel to layer 3, the 1987 table - so
the dashboards can repoint onto the service now. When the LT Info endpoint is
live, the nightly staging ETL (`stage_ltinfo_allocations.py`) truncate+inserts
into that **same layer**, so no dashboard repoint is needed - the manual load is
just the first refresh.
