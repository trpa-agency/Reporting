# Canonical row-level schema for cumulative accounting

Designed 2026-05-15. The case for redesigning the cumulative accounting backend as a database-first system, plus the row-level schema that would let every current REST layer become a SQL view.

## The problem this fixes

Every layer in the `Cumulative_Accounting` REST service today is one of three shapes:

1. **Live row-level**: Layer 0 (PDH), Layer 1 (genealogy), Layer 4 (residential allocations grid), Layer 6 (transactions), Layer 7 (banked). These work because the underlying source is row-level: one row per allocation, one row per transaction, etc.
2. **Live aggregate from REST**: Layer 9 (banked by jurisdiction) - normalized from the analyst's pasted tally. Layer 3 (1987 RP). Already aggregated at the source.
3. **Snapshot of an analyst xlsx**: Layers 10-12 we just published, plus Layers 13-16 staged. The "data" is the analyst's hand-tally of what the numbers should be. There is no source table that produces them.

The third category is fragile. Every cumulative-accounting cycle, the analyst regenerates the xlsx, we re-run the converters, the snapshots refresh. The numbers are right, but the system that produces them is one person's spreadsheet workflow. When the workflow changes or the person changes, the numbers move and nobody can trace why.

Corral has the same problem at a deeper layer. It was built to support the visualizations and grids that the LT Info website needed - the `ResidentialAllocation/Manage` grid, the `DevelopmentRightPoolBalanceReport`, the `BankedDevelopmentRight/Index` page. Each of those was a UX requirement; the tables behind them grew to satisfy the UX, not as a coherent data model. The result: residential allocations are tracked at row level (because the grid required it), but CFA / TAU / RBU were only ever pool-aggregates because that's how the pool report displayed them. Pre-Accela history lives in spreadsheets, agency archives, and the analyst's head because there was no system yet to record it in.

**This document proposes the canonical row-level data model that would let every current snapshot layer become a database view.** Once the source tables exist, the analyst's xlsx becomes a validation check, not a data delivery. Once the views exist, the REST service publishes them with no per-cycle re-staging.

## The 8 canonical entities

### 1. `Parcel` (already exists)

The spatial unit. The current TRPA Parcels FeatureServer or Corral's `Parcel` table both already serve this role.

Key fields:
- APN (canonical form)
- Jurisdiction (FK)
- CurrentOwnerNotes (optional)
- Geometry (polygon)

### 2. `Jurisdiction` (already exists)

Small lookup table.

Key fields:
- JurisdictionCode ('PL', 'SLT', 'WA', 'DG', 'EL', 'TRPA')
- JurisdictionName
- IsTrpaManaged (boolean)

### 3. `DevelopmentRightPool` (already partially exists as Corral `CommodityPool`)

Defines where allocations / commodities can sit when not assigned to a parcel.

Key fields:
- PoolID
- CommodityType (RES / RBU / CFA / TAU)
- PoolName ('Residential Allocation - Placer County', 'TRPA Bonus Unit Pool - Affordable', etc.)
- Jurisdiction (FK; nullable for TRPA pools)
- PoolType ('Jurisdiction' | 'TRPA Managed' | 'Unreleased Reserve' | 'Bonus Subset')
- PlanEra ('1987' | '2012' | 'Both')

### 4. `AllocationRight` (new - the missing primary entity)

**One row per atomic allocation.** Residential = 1 row per residential unit. CFA = 1 row per sqft (or 1 row per "block" of sqft if individual sqft is impractical - more on this below). TAU = 1 row per tourist accommodation unit. RBU = 1 row per bonus unit.

This is the table that **doesn't exist today** for CFA / TAU / RBU. It exists for residential via Corral's `ResidentialAllocation` table (2,112 rows) and the new Layer 4 (2,600 rows including the 770 unreleased placeholders).

Key fields:
- AllocationRightID (PK)
- CommodityType (RES / RBU / CFA / TAU)
- Quantity (1 for RES/RBU/TAU; for CFA either 1 sqft per row OR a Quantity field on aggregated blocks)
- PlanEra ('1987' | '2012')
- IssuanceYear (when TRPA released it to a pool)
- CurrentPoolID (FK; nullable when assigned to a parcel)
- CurrentParcelID (FK; nullable when in a pool)
- CurrentStatus ('Allocated' | 'InPool' | 'TRPAPool' | 'Unreleased' | 'Banked' | 'Converted' | 'Retired')
- ConstructionStatus ('NotApplicable' | 'NotStarted' | 'InProgress' | 'Completed') - for Allocated rows
- AllocationNumber (human-readable ID like "Res-CSLT-1247")
- OriginatingEventID (FK to first event in its lifecycle)

**Granularity for CFA**: 1,000,000 sqft is a lot of rows. Two pragmatic options:
- **Option A (block-grained)**: one row per allocation event, with a Quantity field. Events: "El Dorado County released 50,400 sqft to TRPA Special Projects Pool in 2014". Resulting row in AllocationRight: Quantity=50,400, CurrentPool=TRPA Special Projects Pool, CommodityType=CFA. Splits via events ("Issuance, then 5,000 sqft assigned to Parcel X, then 1,500 sqft converted to TAU" generates child rows).
- **Option B (true atomic)**: 1 sqft per row. Pure data model but 1M rows for CFA alone. Probably overkill.

**Recommendation**: Option A. The lineage tracking is preserved through AllocationEvent splits; the row count stays manageable (thousands, not millions).

### 5. `AllocationEvent` (new - the missing temporal entity)

**One row per state change** of an AllocationRight. The lifecycle of every allocation, from issuance to retirement.

Key fields:
- AllocationEventID (PK)
- AllocationRightID (FK)
- EventType ('Issuance' | 'Release' | 'Assignment' | 'Transfer' | 'Conversion' | 'Bank' | 'Withdraw' | 'ConstructionPermit' | 'ConstructionComplete' | 'Retirement')
- EventDate
- FromStatus (varchar; nullable for issuance)
- FromPoolID (FK; nullable)
- FromParcelID (FK; nullable)
- ToStatus (varchar)
- ToPoolID (FK; nullable)
- ToParcelID (FK; nullable)
- QuantityAffected (default = the right's Quantity; only differs for splits)
- ApprovingAgency
- TransactionRef (LT Info / Accela transaction number, when available)
- Comments
- SourceSystemRecord (provenance: 'Corral_TdrTransaction_12345' etc.)

This is the table that lets `Layer 11 ResidentialAdditionsBySource` and `Layer 15 PoolBalancesMetering` become simple GROUP BY queries.

### 6. `BankedDevelopmentRight` (already exists; Corral pci.BankedQuantity)

Conceptually distinct from AllocationRight. Banked rights are not allocations - they're development rights that came from somewhere else (typically retirement of an existing development right elsewhere) and live on a parcel as a credit.

Key fields:
- BankedRightID (PK)
- ParcelID (FK)
- CommodityType
- Quantity
- BankedDate
- SourceTransactionID (FK to AllocationEvent that created the bank)
- Status ('Active' | 'Used' | 'Withdrawn' | 'Expired')
- UsedInTransactionID (FK; nullable until used)
- LandCapability, IPESScore (when relevant)

This already exists in Corral as `pci.BankedQuantity`. Known to be drift-prone (the 71% disagreement finding in `banked_data_quality.md`). Fixing it = making BankedQuantity a derived value from the transaction log instead of a stored field.

### 7. `ResidentialProject` (new - small but useful)

The "Major Completed Projects" rollup currently in Layer 13.

Key fields:
- ProjectID (PK)
- ProjectName ('Aspens', 'Sugar Pine', 'LTCC Dorms')
- YearCompleted
- PrimaryParcelID (FK)
- TotalUnits
- AffordableUnits
- ModerateUnits
- AchievableUnits
- Jurisdiction (FK)
- LinkedAllocationRightIDs (M:N junction)

The M:N junction lets you answer "which allocations were used for Aspens?" - reverse-lookup that's impossible today.

### 8. `QaCorrectionEvent` (already row-level; Layer 16)

Already designed correctly. Just needs to live in the canonical DB rather than a notebook output CSV.

---

## Derivation of every current REST layer as a view

With those 8 entities in place, every snapshot layer becomes a SQL view:

### Layer 10 `AllocationsBalances` (12 rows)

```sql
CREATE VIEW v_AllocationsBalances AS
SELECT
    src.SourceLabel    AS Source,
    c.Commodity        AS Commodity,
    c.CommodityCode    AS CommodityCode,
    SUM(ar.Quantity)   AS TotalAuthorized,
    SUM(CASE WHEN ar.CurrentStatus = 'Allocated'  THEN ar.Quantity ELSE 0 END) AS AllocatedToPrivate,
    SUM(CASE WHEN ar.CurrentStatus = 'InPool'     THEN ar.Quantity ELSE 0 END) AS JurisdictionPool,
    SUM(CASE WHEN ar.CurrentStatus = 'TRPAPool'   THEN ar.Quantity ELSE 0 END) AS TRPAPool,
    SUM(CASE WHEN ar.CurrentStatus = 'Unreleased' THEN ar.Quantity ELSE 0 END) AS Unreleased,
    SUM(CASE WHEN ar.CurrentStatus IN ('InPool','TRPAPool','Unreleased') THEN ar.Quantity ELSE 0 END) AS TotalBalanceRemaining,
    CURRENT_DATE       AS AsOfDate
FROM AllocationRight ar
JOIN Commodity c ON ar.CommodityType = c.CommodityType
CROSS APPLY (
    VALUES
      ('Grand Total',         NULL),
      ('1987 Regional Plan',  '1987'),
      ('2012 Regional Plan',  '2012')
) src(SourceLabel, FilterEra)
WHERE src.FilterEra IS NULL OR ar.PlanEra = src.FilterEra
GROUP BY src.SourceLabel, c.Commodity, c.CommodityCode;
```

### Layer 11 `ResidentialAdditionsBySource` (98 rows)

```sql
CREATE VIEW v_ResidentialAdditionsBySource AS
SELECT
    YEAR(ae.EventDate) AS Year,
    'Added' AS Direction,
    CASE ae.EventType
        WHEN 'Assignment'   THEN 'Allocations'
        WHEN 'Issuance'     THEN 'Allocations'  -- if RES, the bonus unit lookup distinguishes RBU
        WHEN 'Transfer'     THEN 'Transfers'
        WHEN 'Conversion'   THEN 'Conversions'
        WHEN 'Withdraw'     THEN 'Banked'       -- pulled from bank
    END AS Source,
    SUM(ae.QuantityAffected) AS Units
FROM AllocationEvent ae
JOIN AllocationRight ar ON ae.AllocationRightID = ar.AllocationRightID
WHERE ar.CommodityType = 'RES'
  AND ae.EventType IN ('Assignment','Transfer','Conversion','Withdraw')
  AND ae.ToStatus = 'Allocated'
GROUP BY YEAR(ae.EventDate), Source

UNION ALL

SELECT
    YEAR(ae.EventDate) AS Year,
    'Removed' AS Direction,
    CASE ae.EventType
        WHEN 'Bank'       THEN 'Banked'
        WHEN 'Conversion' THEN 'Converted'
    END AS Source,
    -SUM(ae.QuantityAffected) AS Units   -- negative for removal
FROM AllocationEvent ae
JOIN AllocationRight ar ON ae.AllocationRightID = ar.AllocationRightID
WHERE ar.CommodityType = 'RES'
  AND ae.EventType IN ('Bank','Conversion')
  AND ae.FromStatus = 'Allocated';
```

### Layer 12 `PoolBalances` (26 rows)

```sql
CREATE VIEW v_PoolBalances AS
SELECT
    c.Commodity,
    c.CommodityCode,
    'Combined' AS PlanEra,
    p.PoolName AS Pool,
    p.PoolType AS [Group],
    SUM(ar.Quantity) AS RegionalPlanMaximum,
    SUM(CASE WHEN ar.CurrentStatus = 'Allocated' THEN ar.Quantity ELSE 0 END) AS AssignedToProjects,
    SUM(CASE WHEN ar.CurrentStatus IN ('InPool','TRPAPool','Unreleased') THEN ar.Quantity ELSE 0 END) AS NotAssigned,
    CURRENT_DATE AS AsOfDate
FROM AllocationRight ar
JOIN DevelopmentRightPool p ON ar.CurrentPoolID = p.PoolID
JOIN Commodity c ON ar.CommodityType = c.CommodityType
GROUP BY c.Commodity, c.CommodityCode, p.PoolName, p.PoolType;
```

### Layer 13 `ResidentialProjects` (26 rows)

Direct table - already row-level.

### Layer 14 `ReservedNotConstructed` (3 rows)

```sql
CREATE VIEW v_ReservedNotConstructed AS
SELECT
    c.Commodity,
    c.CommodityCode,
    SUM(ar.Quantity) AS Units,
    CURRENT_DATE AS AsOfDate
FROM AllocationRight ar
JOIN Commodity c ON ar.CommodityType = c.CommodityType
WHERE ar.CurrentStatus = 'Allocated'
  AND ar.ConstructionStatus IN ('NotStarted','InProgress')
GROUP BY c.Commodity, c.CommodityCode;
```

Trivial query - once `ConstructionStatus` exists on every AllocationRight.

### Layer 15 `PoolBalancesMetering` (853 rows)

```sql
CREATE VIEW v_PoolBalancesMetering AS
SELECT
    c.Commodity,
    c.CommodityCode,
    COALESCE(pf.PoolName, pt.PoolName) AS Pool,
    YEAR(ae.EventDate) AS Year,
    CASE
        WHEN ae.ToStatus = 'InPool' AND ae.FromStatus IS NULL          THEN 'Released'      -- initial issuance to pool
        WHEN ae.ToStatus = 'Allocated' AND ae.FromStatus = 'InPool'    THEN 'Assigned'      -- pool -> parcel
    END AS Direction,
    SUM(ae.QuantityAffected) AS Units,
    CURRENT_DATE AS AsOfDate
FROM AllocationEvent ae
JOIN AllocationRight ar ON ae.AllocationRightID = ar.AllocationRightID
LEFT JOIN DevelopmentRightPool pf ON ae.FromPoolID = pf.PoolID
LEFT JOIN DevelopmentRightPool pt ON ae.ToPoolID   = pt.PoolID
JOIN Commodity c ON ar.CommodityType = c.CommodityType
WHERE c.CommodityCode = 'RES'   -- (extend to RBU/CFA/TAU once their event log exists)
GROUP BY c.Commodity, c.CommodityCode, COALESCE(pf.PoolName, pt.PoolName), YEAR(ae.EventDate), CASE...;
```

### Layer 16 `QaCorrections` (5,925 rows)

Direct table - already row-level.

### Layer 9 `BankedByJurisdiction` (24 rows)

```sql
CREATE VIEW v_BankedByJurisdiction AS
SELECT
    j.JurisdictionName AS Jurisdiction,
    c.CommodityType    AS Commodity,
    SUM(br.Quantity)   AS Value
FROM BankedDevelopmentRight br
JOIN Parcel p ON br.ParcelID = p.ParcelID
JOIN Jurisdiction j ON p.JurisdictionID = j.JurisdictionID
JOIN Commodity c ON br.CommodityType = c.CommodityType
WHERE br.Status = 'Active'
GROUP BY j.JurisdictionName, c.CommodityType;
```

---

## Gap analysis: what's missing today

| Layer | Required upstream | What exists in Corral today | Gap |
|---|---|---|---|
| Layer 4 (RES grid) | `AllocationRight` for RES | `ResidentialAllocation` (2,112 + 770 placeholders) | None (already row-level) |
| Layer 10 (AllocationsBalances) | `AllocationRight` for all 4 commodities | Only RES is row-level | **Major: need to backfill RBU + CFA + TAU as AllocationRight rows** |
| Layer 11 (AdditionsBySource) | `AllocationEvent` per RES unit per year | `TdrTransaction` covers ~2014-onward, post-Accela | **Major: pre-Accela RES events (1987-2013) don't exist as records; need to backfill from PDH year-over-year diffs + analyst attribution** |
| Layer 12 (PoolBalances) | `AllocationRight` for all 4 commodities | Same as Layer 10 | Same gap |
| Layer 13 (Projects) | `ResidentialProject` + junction to AllocationRight | Doesn't exist | **Medium: easy to add, but the junction-to-allocation backfill requires analyst attribution** |
| Layer 14 (ReservedNotConstructed) | `ConstructionStatus` on every AllocationRight | Exists for 2012 RP RES on Layer 4; not for 1987 RP RES, not for any non-RES | **Major: need to add ConstructionStatus to 1987 RP RES + all CFA/TAU/RBU rows** |
| Layer 15 (Metering) | `AllocationEvent` for RES with EventDate | Partial - Corral's TdrTransaction covers 2014+; analyst has 1986-2013 in xlsx | **Major: pre-2014 events are the per-year-released numbers in the analyst's xlsx; backfill from there** |
| Layer 16 (QaCorrections) | `QaCorrectionEvent` table | Lives in notebook output CSV | **Low: just create the table and load** |
| Layer 7 (Banked) | `BankedDevelopmentRight` derived from transaction log | `pci.BankedQuantity` is stored not derived | **Medium: rewrite as a view over `vTransactedAndBankedCommodities`** |

### The fundamental finding

**Three of the gaps are unrecoverable from any existing system**: the historical row-level CFA + TAU + RBU allocations (1987-2013), and the per-year pre-Accela residential event log (1986-2013). These were never digitized; they live only in agency archives, plan documents, and the analyst's spreadsheets.

For these, the backfill has to be **synthetic**: derive from the totals + plausible-distribution assumptions, document the synthesis methodology, and tag those rows as synthetic so future analysts know they're an interpretation, not a record. The going-forward data (post-2026) lands in the new schema natively.

---

## Migration path

### Phase 0 (DONE 2026-05)

All current dashboards live on REST. Snapshot layers (10/11/12/13/14/15/16) exist. Analyst delivers no more xlsx files. Eight months of muscle built up around the path-to-REST work, including the discovery that Corral has the same problem at a deeper layer.

### Phase 1: Schema + buy-in (months 1-2)

- This document gets reviewed by TRPA leadership + IT
- The 8-entity schema gets refined based on actual Corral constraints
- A new database is provisioned (recommendation: new schema in the same Enterprise GDB so REST publishing stays seamless; could be `dbo_canonical` or similar)
- DDL is written and reviewed
- A formal proposal goes to whoever owns Corral / LT Info engineering, with the goal of either (a) backfilling Corral to match this schema, or (b) standing up the new schema as the source of truth and having Corral consume IT

### Phase 2: Forward-build (months 2-6)

- The schema is created
- Every NEW allocation event (post-go-live) gets recorded in `AllocationRight` + `AllocationEvent`
- Dual-write: Corral's existing tables get updated as today, AND the new tables get updated. This is the migration period where both stay in sync.
- Views are built and shipped as new REST layers (e.g., `Cumulative_Accounting/MapServer/17`, `/18`, ...) shadowing the snapshot layers
- Dashboards are NOT yet repointed - they keep reading the snapshot layers

### Phase 3: Backfill (months 4-9, overlapping with Phase 2)

The hardest, longest phase. Working backward by commodity:

**RES backfill** (cleanest):
- Layer 4 has the 2,600 row-level rights already - load as 2,600 `AllocationRight` rows
- 1987 RP residential: 6,087 allocations exist as per-jurisdiction aggregates in Layer 3; synthesize 6,087 rows distributed per the jurisdiction breakdowns with Plan=1987
- TdrTransaction (2014+): load as `AllocationEvent` rows
- Pre-2014 events: use the analyst's `regional_plan_allocations.json` per-year released + assigned blocks as the source of truth; synthesize one event per (year, pool, action) combination

**RBU backfill** (medium):
- Layer 5 gives current pool state for the 12 RBU pools; sum = 1,119 active
- Cap is 2,000; gap of 881 is presumed-allocated-pre-Accela
- Synthesize 2,000 `AllocationRight` rows distributed across pools per the current balance + the assumption that the gap was allocated to known projects (cross-ref Layer 13 ResidentialProjects for affordable-bonus projects)

**CFA + TAU backfill** (hardest):
- No row-level history exists pre-Accela
- Use Layer 12 pool aggregates (`RegionalPlanMaximum`, `AssignedToProjects`, `NotAssigned`) per pool as the row-count discipline
- Synthesize one block-grained row per pool with `Quantity` = the aggregate (Option A from §4)
- For post-Accela transactions, use the 45 CFA + 4 TAU events in Layer 6 as the seed
- Tag all synthetic rows with a `SourceSystemRecord = 'SYNTHESIZED:2026-05-backfill'` so they're recognizable

### Phase 4: Cutover (months 9-12)

- Validate: run the views and compare against the analyst's most recent snapshot. Reconcile drift.
- Repoint dashboards from snapshot layers (10/11/12/etc.) to view layers (17/18/19/etc.)
- Snapshot layers stay published for one full cumulative-accounting cycle as a fallback
- Once verified at year-end, snapshot layers are retired
- The analyst's role permanently shifts from "produce snapshots" to "validate views"

### Phase 5: Corral disposition (month 12+)

Two paths forward, both viable:

- **Path A (Corral stays, dual-write continues)**: The new schema is treated as a derived warehouse; Corral remains the operational system. LT Info webservices keep going.
- **Path B (Corral migrates)**: The new schema becomes the operational system. Corral's UX layer (the grids, the reports) is reimplemented against the new schema. This is the long-term answer if TRPA wants Corral and the dashboards to share one canonical source.

Path A is faster. Path B is the right end-state. Most realistic: Path A for 1-2 years to prove the schema works at scale; Path B as the planned-deprecation arc.

---

## What this enables (the benefits)

- **Every layer is a query**: no more snapshots, no more analyst xlsx, no more converter scripts. Dashboards always agree with the database.
- **Lineage is traceable**: "where did this unit come from?" becomes a SELECT walking `AllocationEvent` history.
- **Project rollups are answerable**: "which allocations were used at Sugar Pine?" returns rows.
- **Construction tracking is uniform**: `ConstructionStatus` on every AllocationRight means Tracker section iii becomes a query, not a tally.
- **Banked is derived**: `BankedDevelopmentRight` becomes a view over the transaction log; the 71% drift problem disappears structurally.
- **New commodities are additive**: adding a new commodity (e.g., a future Stormwater Credit) is a new row in `Commodity` + new rows in `AllocationRight`/`AllocationEvent`, not a new xlsx schema.
- **Audit is built in**: every row in `AllocationEvent` carries `SourceSystemRecord` so you can always trace back to the originating Corral record (or "SYNTHESIZED" tag).

## What this costs

- **Database design + DDL**: 1-2 months of design work + review.
- **Forward-build engineering**: 3-4 months to wire the dual-write into whatever ETL feeds Corral today.
- **Backfill**: 3-6 months of analyst + engineer pair-work, especially for the CFA/TAU/RBU synthesis. The most painful and judgment-laden piece.
- **Dashboard repoint**: trivial (we've done it five times now; each swap is a one-line URL change).
- **Corral re-architecture (optional Path B)**: a multi-year project, separate funding.

## What this document does NOT do

- Solve the **organizational** question of who owns the new schema. Corral has an owner; LT Info has an owner; this would need a clear assignment.
- Solve the **funding** question. Phase 1 alone is multiple staff-weeks.
- Solve the **timing** question. Cumulative accounting cycles continue; the migration can't be a hard cutover.

But the architectural answer is straightforward once it's written down. **Every reporting question is a query over 8 tables.** Everything else - the snapshots, the spreadsheets, the per-cycle scrambles - is what happens when you don't have the tables.

## Recommendation

1. **Circulate this document** for review by the analyst, the cumulative-accounting program lead, the IT/Corral owner, and TRPA leadership.
2. **Spec the schema formally** as DDL in this repo (`erd/canonical_schema_ddl.sql`), based on feedback from step 1.
3. **Stand up a sandbox database** with the schema and load Layer 4's 2,600 rows as a proof-of-concept. Build one view (`v_AllocationsBalances` is the smallest) and confirm it reproduces Layer 10 exactly.
4. **From there, the migration is incremental.** Each backfill phase delivers one more layer as a view; each cutover retires one more snapshot.

The unblock is committing to the schema. The work that follows is mechanical.
