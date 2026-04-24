# Target schema — TRPA Cumulative Accounting tracking store

> **Status: DRAFT PROPOSAL — ready for team review.**
> **Audience: TRPA dev team, Ken, Dan, DB/GIS admins, partner jurisdictions.**

Proposed ERD for new tables in the **existing SDE SQL backend** that hosts
Corral + the enterprise GIS geodatabase. Anchored on the TRPA Cumulative
Accounting framework (TRPA Code §16.8.2). See
[cumulative_accounting_reference.md](./cumulative_accounting_reference.md)
for the full vocabulary.

> **Scope**: residential (SFRUU, MFRUU, RBU, ADU), tourist accommodation
> (TAU), commercial floor area (CFA). **Shorezone** (Mooring, Pier,
> `ShorezoneAllocation`, SHORE transaction type) is handled by a separate
> system and **out of scope**. PAOT and mitigation funds are deferred to v2+.

> **This is an ERD proposal, not DDL.** It captures entities, attributes, and
> relationships so the shape can be reviewed before CREATE TABLE statements.
> DDL is a later step.

### Changes since independent review

Addressing issues found by an architectural review before circulation:

- **Fixed `PermitCompletion` / `FinalInspectionDate` contradiction.** `FinalInspectionDate` is a separate workflow event *before* CO issuance; `PermitCompletion.CertificateOfOccupancyDate` is the CO date Corral doesn't carry. Comments in both places make the distinction explicit.
- **Fixed `ParcelDevelopmentChangeEvent.LinkedLedgerEntryID`** (was an invalid FK to a view). Replaced with three nullable typed FKs (`LinkedTdrTransactionID`, `LinkedParcelPermitBankedDevelopmentRightID`, `LinkedManualAdjustmentID`); CHECK constraint enforces exactly one non-null.
- **Added the accounting-identity validation job.** Schema can't enforce `Max = Existing + Banked + Allocated + Bonus + Unused` via CHECK; now spelled out as a nightly SQL query that must return empty.
- **Added `PairedAdjustmentID`** to `LedgerManualAdjustment`. `vCommodityLedger` exposes a `PairingKey` column so Dashboard C3 (Conversion Sankey) can group paired entries from both Corral conversions and manual adjustments.
- **`PermitAllocation` → `vPermitAllocation` (view, not table).** Don't build a second source of truth; Phase 2 back-fills Corral to improve the view's coverage above 32%.
- **Added `WithinSEZ`** to `ParcelSpatialAttribute` (derived from Bailey rating 1a/1b/1c). Enables Dashboard C2 (SEZ-Out Tracker) without extra joins.
- **Expanded `PoolDrawdownYearly` columns** from 6 movement types to 11 (added `Assigned` ALLOCASSGN, `Unbanked`, `ConvertedWithTransfer`, `LandBankIn`, `LandBankOut`, `QAAdjusted`). Reconciliation won't fail silently.
- **Added Implementation Notes section**: uniqueness / idempotency keys per table, accounting-identity validation, multi-hop genealogy resolver algorithm with cycle detection, concurrent-write contract, Corral dependency contract.
- **Added glossary + worked example** for non-TRPA readers.
- **Moved the 39% PCI coverage finding into the key-numbers TL;DR.**
- **Noted `vCommodityLedger` can't be an indexed view**; documented materialization fallback if performance becomes an issue.

## For reviewers — how to read this

1. **Skim the Design principles and Scope notes above** to orient on the
   constraints that shaped the design.
2. **Read the five ERDs in order** — they flow from reference data into the
   five buckets, the movement ledger, permits, and dashboard outputs. All
   diagrams render together in [development_rights_erd.html](./development_rights_erd.html).
3. **Jump to [Questions for the team](#questions-for-the-team)** at the end.
   That's the review checklist. Every question has a proposed answer;
   confirm or override.
4. **Check the supporting docs if you want to know *why*:**
   - [raw_data_vs_corral.md](./raw_data_vs_corral.md) — what Corral doesn't hold.
   - [validation_findings.md](./validation_findings.md) — empirical tests.
   - [xlsx_decomposition.md](./xlsx_decomposition.md) — how each XLSX column lands in the proposed schema.

### Key numbers at a glance

- **Corral's `ParcelCommodityInventory` tracks SFRUU/MFRUU for only 39% of
  residential parcels.** This 61% coverage gap is the core reason the
  proposal exists — the transactions spreadsheet fills a structural hole
  that a Corral-only schema can't. See
  [validation_findings.md](./validation_findings.md) for the empirical test.
- **7 new physical tables + 2 views + 3 materialized snapshots** in this proposal.
- **16 Corral reference / transaction tables** reused as-is (no duplication).
- **5 buckets per (Commodity, Jurisdiction)**: Existing, Banked, Allocated, Bonus Units, Unused Capacity.
- **10 ledger movement types** (9 from Corral's `TransactionType` + Banking + QACorrection, minus Shorezone).
- **3 v1 dashboards**: partial cumulative accounting (residential + TAU + CFA only), allocation drawdown, parcel history lookup.
- **Corral freshness**: our backup is Feb 2024; live reads use LTinfo web services until deployment.
- **GIS freshness**: FC covers 2006–2023 with a 2016–2017 gap (see Questions).

### Glossary (for non-TRPA readers)

Terms that appear throughout this doc, defined once:

| Term | Meaning |
|---|---|
| **SFRUU** | Single-Family Residential Unit of Use — one detached dwelling |
| **MFRUU** | Multi-Family Residential Unit of Use — one apartment/condo/townhome unit |
| **PRUU** | Potential Residential Unit of Use — a subdivided lot that could host a dwelling but hasn't been built |
| **ADU** | Accessory Dwelling Unit — a secondary unit on a single-family lot |
| **TAU** | Tourist Accommodation Unit — one hotel/motel/time-share room |
| **CFA** | Commercial Floor Area — non-residential building area, in square feet |
| **RBU** | Residential Bonus Unit — an extra residential entitlement awarded for environmental benefit |
| **PAOT** | People At One Time — recreation capacity (out of scope for v1) |
| **Commodity** | One of the above types (SFRUU, MFRUU, TAU, CFA, etc.); there are 17 in `dbo.Commodity` |
| **Pool** | A container of commodity capacity, scoped to a jurisdiction or subzone; 129 total in `dbo.CommodityPool` |
| **Allocation** | A specific drawdown from a pool that entitles a unit of development on a parcel |
| **Bucket** | One of 5 states a unit of commodity can be in: Existing, Banked, Allocated, Bonus Units, Unused Capacity |
| **LCT / LandCapabilityType** | `Commodity × BaileyRating` — e.g., "CFA at Bailey 1a" is one LCT; 114 total |
| **SEZ** | Stream Environment Zone — land protected by the Bailey classification system (rating 1a) |
| **Corral** | The SQL Server DB that backs the LTinfo web app; our read connection is a Feb-2024 snapshot |
| **LTinfo** | `laketahoeinfo.org` — public web app sitting on top of Corral |

See [cumulative_accounting_reference.md](./cumulative_accounting_reference.md)
for the full vocabulary with examples.

### Worked example — how one TDR transaction lands in the accounting

Concrete trace showing how the proposed schema processes a single event.

**Event**: In 2021, El Dorado County issued residential allocation `EL-21-O-08`
(`ResidentialAllocationTypeCode='O'` = Original, sequence 08) from its
jurisdiction pool. In 2022, it was assigned to parcel 014-234-002. The parcel
permit `0339627` was finaled 2022-10-12.

**Source rows** (in Corral, today):
- `dbo.ResidentialAllocation` row: `IssuanceYear=2021, AllocationSequence=8, ResidentialAllocationTypeID=1(O), CommodityPoolID=<EL pool>, TdrTransactionID=<T1>`
- `dbo.TdrTransaction` row `T1`: `TransactionTypeAbbreviation='ALLOC', ApprovalDate=2021-09-16, CommodityID=<SFRUU>`
- `dbo.TdrTransaction` row `T2`: `TransactionTypeAbbreviation='ALLOCASSGN', ApprovalDate=2022-10-12, AccelaCAPRecordID=<Accela row matching 0339627>`

**What the new schema does with it**:

1. `vCommodityLedger` exposes two rows (derived — no storage added):
   - From T1: `MovementType=ALLOC, EntryDate=2021-09-16, FromBucket=UnusedPool, ToBucket=Allocated, Quantity=+1`
   - From T2: `MovementType=ALLOCASSGN, EntryDate=2022-10-12, FromBucket=Allocated, ToBucket=Existing, Quantity=+1`
2. `PoolDrawdownYearly` nightly job credits `EL county pool`: `Released` for 2021 +=1, `Used` for 2022 +=1.
3. `ParcelExistingDevelopment` gets a row from the GIS FC weekly sync:
   `(ParcelID=014-234-002, CommodityID=SFRUU, Year=2022, Quantity=1,
   YearBuilt=2022, Source='gis_fc')`.
4. The prior year's row had Quantity=0, so ETL also inserts:
   `ParcelDevelopmentChangeEvent(ParcelID=014-234-002, Year=2022, PreviousQuantity=0,
   NewQuantity=1, ChangeSource='permit_completion', LinkedTdrTransactionID=T2,
   LinkedPermitID=<0339627's ParcelPermitID>, Rationale='Allocation EL-21-O-08
   finaled 2022-10-12')`.
5. `CumulativeAccountingSnapshot` for (Year=2022, Jurisdiction=EL, Commodity=SFRUU)
   increments `ExistingQuantity` by 1 and decrements `AllocatedNotBuiltQuantity` by 1.
6. Dashboard A1 (Regional Capacity Dial), B1 (Pool Balance), E1 (Change Rationale
   Audit Trail) all pick up the change on next refresh.

**Nothing about this event is duplicated.** `dbo.ResidentialAllocation` and
`dbo.TdrTransaction` remain Corral's authoritative records. The new tables
carry only: the GIS-derived existing-development row (#3), the change-rationale
row (#4), and the materialized snapshot (#5).

## Design principle — never duplicate Corral

Corral is the system of record for TDR transactions, residential allocations,
banked rights, commodity pools, parcels, permits, deed restrictions, IPES, and
all reference lookups. **The new DB only creates tables for data Corral
genuinely lacks.** Everything else is FK'd, UNION'd in a view, or sidecar'd
with net-new columns only. When in doubt: don't duplicate.

## Where this lives — architecture

The new tables fold into the **same SDE-registered SQL Server instance** as
Corral and the enterprise GIS geodatabase. That means:

- **No bridge columns.** Foreign keys go directly to `dbo.Parcel`,
  `dbo.Commodity`, `dbo.CommodityPool`, `dbo.ResidentialAllocation`, etc.
  No more string-ID round-tripping.
- **Reference data is reused, not duplicated.** `Commodity`, `Jurisdiction`,
  `BaileyRating`, `LandCapabilityType`, `CommodityPool`, `TransactionType`,
  `ResidentialAllocationType`, `ResidentialAllocationUseType`,
  all stay in Corral as-is. We FK into them.
- **Publishing via ESRI is native.** SDE-registered tables can be exposed as
  MapServer / FeatureServer layers (like
  [Existing_Development/MapServer/2](https://maps.trpa.org/server/rest/services/Existing_Development/MapServer/2) — the future **Parcel Development History** service).
- **LTinfo JSON web services** remain the live read path for external
  systems but are not needed for in-DB queries once we're deployed.

## The accounting identity the schema serves

For every `(Commodity, Jurisdiction)`:

```
Max Regional Capacity  =  Existing + Banked + Allocated (not built)
                       +  Bonus Units + Unused Capacity
```

Every event moves commodity between these five buckets.

## Reference entities — reused from Corral

These tables **already exist in `dbo.*`** and don't get recreated. Listed so
you can see what the new tables FK into.

| Corral table | Row count | Role |
|---|---:|---|
| `dbo.Commodity` | 17 | Canonical commodity taxonomy (SFRUU, MFRUU, CFA, TAU, RBU, etc.) |
| `dbo.Jurisdiction` | 10 | Jurisdictions + abbreviations |
| `dbo.BaileyRating` | — | Bailey land-capability ratings (1a, 1b, 2, 3, ...) |
| `dbo.LandCapabilityType` | 114 | `Commodity × BaileyRating` |
| `dbo.CommodityPool` | 129 | All pools (Community Plan, Area Plan, Incentive, Bonus, CEP, generic) |
| `dbo.TransactionType` | 9 | The 9 canonical transaction types — see below |
| `dbo.ResidentialAllocationType` | 4 | **Allocation source**: Original, Reissued, LitigationSettlement, AllocationPool |
| `dbo.ResidentialAllocationUseType` | 2 | **Allocation use**: SingleFamily, MultiFamily |
| `dbo.Parcel` | 72K | Canonical parcel identity + geometry |
| `dbo.ParcelGenealogy` | 2.4K | Parent/Child parcel links (skeleton — enriched by new table below) |
| `dbo.ResidentialAllocation` | 1.9K | Allocation records (FK target; not redefined) |
| `dbo.TdrTransaction` + family | 2K | Transaction records — become inputs to the ledger |
| `dbo.AccelaCAPRecord` + `dbo.ParcelAccelaCAPRecord` | 124K / 179K | Accela bridge |
| `dbo.ParcelPermit` | 1.3K | Permit records — we extend, not replace |
| `dbo.ParcelCommodityInventory` | 10.5K | Current verified inventory (61% gap for residential; supplemented by `ParcelExistingDevelopment` below) |

### Found domain values

**`dbo.ResidentialAllocationType`** — what I earlier called "AllocationType":

| ID | Name | Code | Description |
|---:|---|---|---|
| 1 | Original | O | Original |
| 2 | Reissued | R | Reissued |
| 3 | LitigationSettlement | LS | Litigation Settlement |
| 4 | AllocationPool | AP | Allocation Pool |

My earlier sketch of `Allocation | BonusUnit | ADU` was wrong — those aren't
types, they're either sub-entities (`ResidentialBonusUnit`) or modeled
elsewhere (ADU probably as a flag on the permit or as a
`ResidentialAllocationUseType` value to be added).

**`dbo.ResidentialAllocationUseType`**:

| ID | Name | Display |
|---:|---|---|
| 1 | SingleFamily | Single-Family |
| 2 | MultiFamily | Multi-Family |

**`dbo.TransactionType`** — the 9 authoritative movement types:

| ID | Name | Abbr | Sending? | Receiving? | Conversion? | LandBank? |
|---:|---|---|:---:|:---:|:---:|:---:|
| 1 | Allocation | ALLOC | | ✓ | | |
| 2 | Conversion | CONV | | | ✓ | |
| 3 | ECM Retirement | ECM | ✓ | | | |
| 4 | Land Bank Acquisition | LBA | ✓ | | | |
| 5 | Transfer | TRF | ✓ | ✓ | | |
| 7 | Allocation Assignment | ALLOCASSGN | | ✓ | | |
| 8 | Conversion With Transfer | CONVTRF | ✓ | ✓ | | |
| 9 | Land Bank Transfer | LBT | | ✓ | | ✓ |

(ID 10 — Shorezone Allocation — is handled by the separate shorezone system
and **out of scope** for this schema.)

**`dbo.CommodityPool` — no formal PoolType column.** Pool type is encoded in
the pool name. Empirical classification by commodity:

| Commodity | Bonus | Incentive | Community Plan | Area Plan | CEP | Total |
|---|---:|---:|---:|---:|---:|---:|
| CFA | 0 | 0 | 15 | 5 | 1 | 30 |
| RBU | 2 | 1 | 5 | 3 | 1 | 18 |
| TAU | 0 | 0 | 1 | 4 | 0 | 21 |
| PAOT | 0 | 0 | 9 | 0 | 0 | 43 |
| Res. Alloc. | 0 | 0 | 0 | 0 | 0 | 9 |

Recommendation: **don't add a `PoolType` enum column to `CommodityPool`**.
Instead add a derived classification in the ETL layer or a view — parses
the name into `{CommunityPlan, AreaPlan, Bonus, Incentive, CEP, Generic}`.
Keeps the source table unchanged; accounting queries use the derived view.

## GIS source — the future Parcel Development History service

The existing prototype at
[Existing_Development/MapServer/2](https://maps.trpa.org/server/rest/services/Existing_Development/MapServer/2)
("Parcel Annual Attributes") is the shape the new **Parcel Development
History** service will have. Key fields:

| Field | Type | Role |
|---|---|---|
| `APN` | String(16) | Parcel key |
| `YEAR` | Integer | Year (part of composite key) |
| `Residential_Units` | Integer | RES count (→ new `ParcelExistingDevelopment`) |
| `TouristAccommodation_Units` | Integer | TAU count |
| `CommercialFloorArea_SqFt` | Double | CFA sq ft |
| `YEAR_BUILT` | String(5) | Assessor year-built |
| `JURISDICTION` | String(4) | |
| `COUNTY` | String(2) | |
| `OWNERSHIP_TYPE` | String(12) | |
| `EXISTING_LANDUSE` | String(50) | |
| `COUNTY_LANDUSE_DESCRIPTION` | String(150) | |
| `PLAN_ID`, `PLAN_NAME` | String | → new `ParcelSpatialAttribute` |
| `ZONING_ID`, `ZONING_DESCRIPTION` | String | |
| `TOWN_CENTER`, `LOCATION_TO_TOWNCENTER` | String | |
| `TAZ` | Double | |
| `WITHIN_TRPA_BNDY`, `WITHIN_BONUSUNIT_BNDY` | SmallInt | 0/1 flags |
| `PARCEL_ACRES`, `PARCEL_SQFT` | Double | |
| `Shape` | Polygon | |

No coded-value domains on the layer today. The new tables mirror these
field names 1:1 to simplify the loader.

## ERD — new core tables (parcel-keyed buckets)

```mermaid
erDiagram
    ParcelExistingDevelopment {
        int PEDID PK
        int ParcelID FK "dbo.Parcel"
        int CommodityID FK "dbo.Commodity"
        int Year "year-end snapshot"
        int Quantity
        int YearBuilt "from GIS YEAR_BUILT"
        varchar ExistingLanduse "from GIS EXISTING_LANDUSE"
        varchar CountyLanduseDescription
        varchar OwnershipType
        int FcObjectID "GIS OBJECTID for traceability"
        varchar Source "gis_fc, legacy_csv, manual"
        datetime LoadedAt
    }
    ParcelSpatialAttribute {
        int PSAID PK
        int ParcelID FK "dbo.Parcel"
        int Year
        varchar Jurisdiction
        varchar County
        decimal ParcelAcres
        decimal ParcelSqFt
        bit WithinTrpaBndy
        bit WithinBonusUnitBndy
        bit WithinSEZ "derived: true when predominant Bailey rating = 1a/1b/1c"
        varchar TownCenter
        varchar LocationToTownCenter
        varchar PlanID
        varchar PlanName
        varchar ZoningID
        varchar ZoningDescription
        double TAZ
        datetime LoadedAt
    }
    ParcelGenealogyEventEnriched {
        int EventID PK
        int ParcelGenealogyID FK "dbo.ParcelGenealogy (nullable for events not yet in Corral)"
        varchar ApnOld
        varchar ApnNew
        int ChangeYear
        date ChangeDate
        varchar EventType "split, merge, rename, unknown"
        bit IsPrimary
        decimal OverlapPct
        varchar Source "manual, accela, ltinfo, spatial"
        int SourcePriority
        varchar Confidence
        bit Verified
        varchar Notes
    }
    ParcelDevelopmentChangeEvent {
        int ChangeEventID PK
        int ParcelID FK "dbo.Parcel"
        int CommodityID FK "dbo.Commodity"
        int Year
        int PreviousQuantity
        int NewQuantity
        varchar ChangeSource "permit_completion, tdr_transfer, qa_correction, genealogy_restatement, assessor_update, manual"
        varchar Rationale
        varchar EvidenceURL
        int LinkedTdrTransactionID FK "dbo.TdrTransaction - null unless ChangeSource in (permit_completion, tdr_transfer)"
        int LinkedParcelPermitBankedDevelopmentRightID FK "dbo.ParcelPermitBankedDevelopmentRight - null unless ChangeSource='banking'"
        int LinkedManualAdjustmentID FK "LedgerManualAdjustment - null unless ChangeSource='qa_correction' or 'manual'"
        int LinkedPermitID FK "dbo.ParcelPermit"
        varchar RecordedBy
        datetime RecordedAt
    }
    dbo_Parcel {
        int ParcelID PK
        varchar ParcelNumber "external Corral table"
    }
    dbo_Commodity {
        int CommodityID PK
        varchar ShortName "external Corral table"
    }
    dbo_ParcelGenealogy {
        int ParcelGenealogyID PK
        int ParentParcelID FK
        int ChildParcelID FK
    }

    dbo_Parcel                   ||--o{ ParcelExistingDevelopment   : "has (per year x commodity)"
    dbo_Parcel                   ||--o{ ParcelSpatialAttribute      : "has (per year)"
    dbo_Parcel                   ||--o{ ParcelDevelopmentChangeEvent : "has change events"
    dbo_Commodity                ||--o{ ParcelExistingDevelopment   : "typed as"
    dbo_Commodity                ||--o{ ParcelDevelopmentChangeEvent : "typed as"
    dbo_ParcelGenealogy          ||--o| ParcelGenealogyEventEnriched : "extended by"
    ParcelExistingDevelopment    ||--o{ ParcelDevelopmentChangeEvent : "year-over-year change triggers"
```

The two pool-keyed buckets (`Bonus Units`, `Unused Capacity`) don't need
new tables — they're derivable from the existing `dbo.CommodityPool`
records plus the movement ledger, materialized nightly into
`PoolDrawdownYearly` (below).

## ERD — movement ledger

**No physical ledger table.** Corral is the system of record for every TDR
transaction (`dbo.TdrTransaction` + children) and every banked right
(`dbo.ParcelPermitBankedDevelopmentRight`). Don't duplicate. Instead:

- **`vCommodityLedger` (view)** — UNIONs Corral's transaction and banking
  tables into a unified `(EntryDate, CommodityID, Quantity, MovementType,
  From*, To*)` shape. Read-only.
- **`LedgerManualAdjustment` (small new table)** — the only net-new ledger
  data we hold: manual QA corrections that don't correspond to any Corral
  event. UNIONed into `vCommodityLedger`.

```mermaid
erDiagram
    dbo_TdrTransaction {
        int TdrTransactionID PK
        varchar TransactionTypeAbbreviation
        datetime ApprovalDate
        int CommodityID
    }
    dbo_ParcelPermitBankedDevelopmentRight {
        int ParcelPermitBankedDevelopmentRightID PK
        int ParcelPermitID FK
        int LandCapabilityTypeID FK
        int Quantity
    }
    LedgerManualAdjustment {
        int AdjustmentID PK
        date EntryDate
        int CommodityID FK "dbo.Commodity"
        int Quantity "signed: + deposits, - withdrawals"
        varchar MovementType "QACorrection (only kind allowed here)"
        varchar FromBucketType
        varchar ToBucketType
        int FromPoolID FK "dbo.CommodityPool"
        int ToPoolID FK "dbo.CommodityPool"
        int SendingParcelID FK "dbo.Parcel"
        int ReceivingParcelID FK "dbo.Parcel"
        int PairedAdjustmentID FK "self-ref for manual conversion paired entries"
        varchar Rationale
        varchar RecordedBy
        datetime RecordedAt
    }
    vCommodityLedger {
        varchar source "corral_tdr | corral_banking | manual_qa"
        int source_id
        int PairingKey "null unless conversion"
        date EntryDate
        int CommodityID
        int Quantity
        varchar MovementType
    }

    dbo_TdrTransaction                       ||--o{ vCommodityLedger : "branch 1: fans out into ledger rows"
    dbo_ParcelPermitBankedDevelopmentRight   ||--o{ vCommodityLedger : "branch 2: banking events"
    LedgerManualAdjustment                   ||--o{ vCommodityLedger : "branch 3: manual QA"
    LedgerManualAdjustment                   ||--o| LedgerManualAdjustment : "paired (self-ref)"
```

### `vCommodityLedger` — the view

Shape of the view: `(source, source_id, PairingKey, EntryDate, CommodityID,
Quantity, MovementType, FromBucketType, ToBucketType, FromPoolID, ToPoolID,
SendingParcelID, ReceivingParcelID, Rationale)`. Three branches UNION ALL'd.

`source` is an enum (`corral_tdr` | `corral_banking` | `manual_qa`). `source_id`
is the PK in that source's table. Together `(source, source_id)` uniquely
identifies a ledger row — this is the composite key `ParcelDevelopmentChangeEvent`
and dashboards should reference.

`PairingKey` links the two sides of a Conversion: for `corral_tdr` rows, the
conversion produces two fan-out rows from the *same* `TdrTransactionID`, so
`PairingKey = TdrTransactionID`. For `manual_qa` conversions, `PairingKey =
LEAST(AdjustmentID, PairedAdjustmentID)` (canonical choice of the two). For
non-conversion rows `PairingKey = NULL`. Dashboard C3 (Sankey) filters
`WHERE MovementType IN ('CONV','CONVTRF')` and groups by `PairingKey`.

```sql
-- branch 1: TDR transactions from Corral (the bulk)
-- For Conversions (CONV/CONVTRF), the TdrTransactionConversion table has
-- two rows per conversion (one per commodity side); the JOIN fans out into
-- two ledger rows with the same TdrTransactionID = PairingKey.
SELECT
    'corral_tdr'                      AS source,
    tt.TdrTransactionID               AS source_id,
    tt.TdrTransactionID               AS PairingKey,   -- NULL unless conversion; dashboards filter
    tt.ApprovalDate                   AS EntryDate,
    COALESCE(ttc.CommodityID, tt.CommodityID) AS CommodityID,
    COALESCE(ttt.ReceivingQuantity, tta.AllocatedQuantity,
             ttc.Quantity, tla.Quantity, tlt.Quantity) AS Quantity,
    tty.TransactionTypeAbbreviation   AS MovementType,
    -- FromBucketType / ToBucketType derived from TransactionType flags
    ...
FROM dbo.TdrTransaction tt
JOIN dbo.TransactionType tty ON tty.TransactionTypeID = tt.TransactionTypeID
LEFT JOIN dbo.TdrTransactionTransfer ttt ON ttt.TdrTransactionID = tt.TdrTransactionID
LEFT JOIN dbo.TdrTransactionAllocation tta ON tta.TdrTransactionID = tt.TdrTransactionID
LEFT JOIN dbo.TdrTransactionConversion ttc ON ttc.TdrTransactionID = tt.TdrTransactionID
LEFT JOIN dbo.TdrTransactionLandBankAcquisition tla ON tla.TdrTransactionID = tt.TdrTransactionID
LEFT JOIN dbo.TdrTransactionLandBankTransfer tlt ON tlt.TdrTransactionID = tt.TdrTransactionID
WHERE tty.TransactionTypeAbbreviation <> 'SHORE'   -- shorezone out of scope

UNION ALL

-- branch 2: banking events (Corral has them but not as transactions)
SELECT
    'corral_banking'                        AS source,
    ppbdr.ParcelPermitBankedDevelopmentRightID AS source_id,
    NULL                                    AS PairingKey,
    pp.FinalInspectionDate                  AS EntryDate,  -- see Q5 - banking-date question
    lct.CommodityID,
    -ppbdr.Quantity                         AS Quantity,   -- negative: leaves Existing
    'Banking'                               AS MovementType,
    ...
FROM dbo.ParcelPermitBankedDevelopmentRight ppbdr
JOIN dbo.ParcelPermit pp ON pp.ParcelPermitID = ppbdr.ParcelPermitID
JOIN dbo.LandCapabilityType lct ON lct.LandCapabilityTypeID = ppbdr.LandCapabilityTypeID

UNION ALL

-- branch 3: manual QA adjustments (the only net-new data in the ledger)
SELECT
    'manual_qa'                      AS source,
    lma.AdjustmentID                 AS source_id,
    CASE WHEN lma.PairedAdjustmentID IS NULL THEN NULL
         ELSE LEAST(lma.AdjustmentID, lma.PairedAdjustmentID)
    END                              AS PairingKey,
    lma.EntryDate,
    lma.CommodityID,
    lma.Quantity,
    lma.MovementType,
    ...
FROM LedgerManualAdjustment lma;
```

### Performance ceiling — plan B if the view is too slow

Today's row counts: 2,088 TDR transactions + 707 banked rights + 0 manual
adjustments = ~2,800 ledger rows. Dashboards query filtered subsets; the view
is fine at this scale.

**The view can't be SCHEMABINDing + indexed** because the `LEFT JOIN`s against
the 5 TdrTransaction child tables disqualify it under SQL Server's indexed-view
rules. If dashboards hit performance limits as data grows:

- **Fall back to a nightly-materialized** `CommodityLedgerSnapshot` table with
  indexes on `(MovementType, EntryDate)`, `(FromPoolID, EntryDate)`,
  `(ToPoolID, EntryDate)`. Rebuild nightly from `vCommodityLedger`.
- **Drawback**: that physical table *is* a partial duplication of Corral. The
  design principle tolerates this when it's a materialized derivation (like
  `CumulativeAccountingSnapshot` and `PoolDrawdownYearly` already are), not
  a source of record.

### Mapping Corral `TransactionType` → `MovementType`

| Corral abbr | MovementType in ledger | Bucket move | Source branch |
|---|---|---|---|
| ALLOC | ALLOC | UnusedPool → Allocated | corral_tdr |
| ALLOCASSGN | ALLOCASSGN | Allocated → Existing (on permit final) | corral_tdr |
| CONV | CONV | Existing → Existing (paired entries) | corral_tdr |
| CONVTRF | CONVTRF | Existing(parcel A) → Existing(parcel B) with commodity swap | corral_tdr |
| TRF | TRF | Existing(A) → Existing(B) | corral_tdr |
| ECM | ECM | Existing → OutOfSystem | corral_tdr |
| LBA | LBA | Existing → LandBank | corral_tdr |
| LBT | LBT | LandBank → Existing | corral_tdr |
| (none — Corral event) | Banking | Existing → Banked | corral_banking |
| (none — manual) | QACorrection | any → any | manual_qa |

## ERD — permit completion + cross-system IDs

```mermaid
erDiagram
    PermitCompletion {
        int PermitCompletionID PK
        int ParcelPermitID FK "dbo.ParcelPermit (UNIQUE - 1:1)"
        int YearBuilt "county assessor (not in Corral)"
        int PmYearBuilt "property-manager internal year if distinct from assessor"
        date CertificateOfOccupancyDate "the actual CO date - Corral has only HasCertificateOfOccupancyBeenIssued bit; FinalInspectionDate is earlier in the workflow"
        varchar CompletionStatusEnriched "enum: Applied|Issued|UnderConstruction|Finaled|Expired|Withdrawn; supersedes Corral's 2-value ParcelPermitStatusID for reporting"
        varchar DetailedDevelopmentType "free-text project descriptor (not in Corral)"
        varchar SupplementalNotes "Ken's operational/QA notes (distinct from dbo.ParcelPermit.Notes which holds permit description)"
        datetime LoadedAt
    }
    vPermitAllocation {
        int ParcelPermitID FK "dbo.ParcelPermit"
        int ResidentialAllocationID FK "dbo.ResidentialAllocation"
        varchar LinkageSource "corral_fk (via TdrTransaction.AccelaCAPRecordID) or xlsx_seeded (from Ken via CrossSystemID)"
        int Quantity
    }
    CrossSystemID {
        int CrossID PK
        varchar EntityType "parcel, permit, allocation, transaction, deed_restriction"
        int EntityID "polymorphic"
        varchar IDType "accela, ltinfo, trpa_mou, local_jurisdiction, assessor"
        varchar IDValue
        datetime LoadedAt
    }
    dbo_ParcelPermit {
        int ParcelPermitID PK
        varchar PermitNumber
        datetime IssuedDate
    }
    dbo_ResidentialAllocation {
        int ResidentialAllocationID PK
        int IssuanceYear
        int AllocationSequence
    }

    dbo_ParcelPermit             ||--o| PermitCompletion        : "1:1 sidecar"
    dbo_ParcelPermit             ||--o{ vPermitAllocation       : "permit uses..."
    dbo_ResidentialAllocation    ||--o{ vPermitAllocation       : "...allocation"
    dbo_ParcelPermit             ||--o{ CrossSystemID           : "EntityType=permit"
    dbo_ResidentialAllocation    ||--o{ CrossSystemID           : "EntityType=allocation"
```

`PermitCompletion` extends `dbo.ParcelPermit` with the fields that live in
Ken's XLSX today. Eventually this becomes a direct sync from Accela once a
live feed is wired.

## ERD — materialized dashboard outputs

```mermaid
erDiagram
    CumulativeAccountingSnapshot {
        int SnapshotID PK
        int Year
        int JurisdictionID FK "dbo.Jurisdiction"
        int CommodityID FK "dbo.Commodity"
        int ExistingQuantity
        int BankedQuantity
        int AllocatedNotBuiltQuantity
        int BonusUnitsRemaining
        int UnusedCapacityRemaining
        int MaxRegionalCapacity
        datetime ComputedAt
    }
    PoolDrawdownYearly {
        int DrawdownID PK
        int PoolID FK "dbo.CommodityPool"
        int Year
        int StartingBalance
        int Released "ALLOC"
        int Assigned "ALLOCASSGN"
        int Used "AllocationUse (built through permit completion)"
        int Banked "Banking"
        int Unbanked "Unbanking"
        int Transferred "TRF"
        int Converted "CONV"
        int ConvertedWithTransfer "CONVTRF"
        int LandBankIn "LBA"
        int LandBankOut "LBT"
        int Retired "ECM"
        int QAAdjusted "QACorrection - signed, net"
        int EndingBalance
        datetime ComputedAt
    }
    ParcelHistoryView {
        int HistoryID PK
        int ParcelID FK "dbo.Parcel"
        int Year
        int CommodityID FK "dbo.Commodity"
        int Quantity
        int ChangeCount
        varchar LastChangeSource
        varchar LastChangeRationale
    }
    dbo_Jurisdiction {
        int JurisdictionID PK
        varchar Abbreviation
    }
    dbo_Commodity {
        int CommodityID PK
        varchar ShortName
    }
    dbo_CommodityPool {
        int CommodityPoolID PK
        varchar CommodityPoolName
    }
    dbo_Parcel {
        int ParcelID PK
        varchar ParcelNumber
    }

    dbo_Jurisdiction      ||--o{ CumulativeAccountingSnapshot : "rows per..."
    dbo_Commodity         ||--o{ CumulativeAccountingSnapshot : "...Jur x Commodity"
    dbo_CommodityPool     ||--o{ PoolDrawdownYearly           : "rows per pool x year"
    dbo_Parcel            ||--o{ ParcelHistoryView            : "rows per parcel x year x commodity"
    dbo_Commodity         ||--o{ ParcelHistoryView            : "typed as"
```

| Dashboard | Driven by |
|---|---|
| **Cumulative accounting report** (annual XLSX replacement) | `CumulativeAccountingSnapshot` |
| **Allocation drawdown** (stacked area by pool × year; `html/allocation_drawdown.html`) | `PoolDrawdownYearly` |
| **Parcel history lookup** (per-APN + change log) | `ParcelHistoryView` + `ParcelDevelopmentChangeEvent` |

## Implementation notes — constraints, invariants, and algorithms

The ERD shapes are necessary but not sufficient. These notes capture the
operational contracts that make the schema actually work.

### Uniqueness + idempotency per table

Every table has a natural key that ETL must respect so reloads are idempotent
and concurrent writes don't create duplicates:

| Table | Natural key (UNIQUE constraint) | Notes |
|---|---|---|
| `ParcelExistingDevelopment` | `(ParcelID, CommodityID, Year)` | UPSERT on weekly GIS sync |
| `ParcelSpatialAttribute` | `(ParcelID, Year)` | UPSERT on weekly GIS sync |
| `ParcelGenealogyEventEnriched` | `(ApnOld, ApnNew, ChangeYear, Source)` | INSERT-only; conflicts flagged for analyst review |
| `ParcelDevelopmentChangeEvent` | `(ParcelID, CommodityID, Year, ChangeSource, LinkedTdrTransactionID, LinkedParcelPermitBankedDevelopmentRightID, LinkedManualAdjustmentID)` | a change-event is unique per (what changed, what caused it); filtered index for the nullable linked IDs |
| `PermitCompletion` | `ParcelPermitID` (UNIQUE, 1:1 with `dbo.ParcelPermit`) | INSERT on new permit; UPDATE on status change |
| `LedgerManualAdjustment` | `AdjustmentID` (surrogate only; no natural key) | every manual entry is a distinct event |
| `CrossSystemID` | `(EntityType, EntityID, IDType)` | UPSERT on seed load |

Three-nullable-FK validity on `ParcelDevelopmentChangeEvent`: add a
`CHECK` constraint that exactly one of the three linked IDs is non-null
(`(CASE WHEN LinkedTdrTransactionID IS NULL THEN 0 ELSE 1 END) + ... = 1`).

### Accounting-identity validation

The `Max Capacity = Existing + Banked + Allocated + Bonus + Unused` identity
is not enforced by the schema — no CHECK constraint can span the five
different tables. Enforce it via a nightly validation job:

```sql
-- fn_ValidateAccountingIdentity: returns rows where the identity doesn't hold
SELECT s.Year, j.Name AS Jurisdiction, c.ShortName AS Commodity,
       s.ExistingQuantity + s.BankedQuantity + s.AllocatedNotBuiltQuantity
     + s.BonusUnitsRemaining + s.UnusedCapacityRemaining AS ComputedTotal,
       s.MaxRegionalCapacity,
       (s.ExistingQuantity + s.BankedQuantity + s.AllocatedNotBuiltQuantity
      + s.BonusUnitsRemaining + s.UnusedCapacityRemaining)
      - s.MaxRegionalCapacity AS Imbalance
FROM CumulativeAccountingSnapshot s
JOIN Jurisdiction j ON j.JurisdictionID = s.JurisdictionID
JOIN Commodity   c ON c.CommodityID   = s.CommodityID
WHERE (s.ExistingQuantity + s.BankedQuantity + s.AllocatedNotBuiltQuantity
     + s.BonusUnitsRemaining + s.UnusedCapacityRemaining)
     <> s.MaxRegionalCapacity
ORDER BY ABS(Imbalance) DESC;
```

Run this after every `CumulativeAccountingSnapshot` rebuild. Any non-empty
result is a data-quality failure — page someone. For v1 we'll fire email
alerts; v2+ can plug into a proper observability stack.

### Multi-hop genealogy resolver

`fn_resolve_apn(@apn varchar(30), @as_of date)` walks `ParcelGenealogyEventEnriched`
forward. Contract:

- **Termination**: iterate up to 10 hops (genealogy should never chain deeper
  in practice); abort with error on 11th hop.
- **Hop selection**: at each hop, choose the `ApnNew` where
  `ChangeYear <= YEAR(@as_of) AND IsPrimary = 1 AND Verified = 1`.
- **Tie-breaking**: if multiple candidates match, take the highest
  `SourcePriority`, then earliest `ChangeDate`, then smallest `EventID`.
  Deterministic.
- **Ambiguity handling**: if more than one row matches after tie-breaking
  (shouldn't happen with priority in place), log to `ParcelGenealogyResolutionLog`
  with `Status='ambiguous'` and return `@apn` unchanged (fail-safe: keep the
  raw value rather than pick wrong).
- **Cycle detection**: maintain a visited set; if a new hop would revisit an
  APN already seen, log `Status='cycle'` and return `@apn` unchanged.
- **No match**: return `@apn` unchanged; log `Status='unchanged'` only if
  verbose logging is on (otherwise noisy).

Logged rows land in `ParcelGenealogyResolutionLog` (already in the proposal).
This table's growth + the cycle log are early indicators of genealogy data
quality drift.

### Concurrent-write contract

ETL jobs are the only writers. Contract:

- **Each job owns a specific `Source` value** on the tables it writes
  (`ParcelExistingDevelopment.Source='gis_fc'` for the GIS loader,
  `'legacy_csv'` for Ken's pre-2012 baseline, etc.). Jobs do not write rows
  with another job's `Source`.
- **Writes are UPSERT keyed by the natural key** (above), wrapped in a single
  transaction per APN-year batch.
- **Schedule separation**: the GIS weekly sync and the `CumulativeAccountingSnapshot`
  nightly recompute run at different times; there's no lock contention.
- **Manual QA adjustments** write only to `LedgerManualAdjustment` +
  `ParcelDevelopmentChangeEvent`; they never touch `ParcelExistingDevelopment`
  directly. The accounting-identity validation catches inconsistencies on
  the next nightly run.

### Corral dependency contract

The new tables FK into `dbo.Parcel`, `dbo.Commodity`, `dbo.TdrTransaction`,
`dbo.ParcelPermit`, `dbo.CommodityPool`, `dbo.LandCapabilityType`,
`dbo.ParcelGenealogy`, `dbo.ParcelPermitBankedDevelopmentRight`,
`dbo.ResidentialAllocation`, `dbo.Jurisdiction`, `dbo.BaileyRating`,
`dbo.AccelaCAPRecord`.

Risks if the LTinfo team changes those tables:

- **Column added**: no impact (we don't `SELECT *`).
- **Column renamed**: breaks the loader; our integration tests should catch.
- **Column dropped**: breaks FK if we reference it — but we only reference PKs.
- **New row added to `dbo.TransactionType` or `dbo.ResidentialAllocationType`**:
  silently unhandled in our `MovementType` mapping or bucket derivation. *This
  is the most likely way we get bitten.* Mitigation: a monthly
  reconciliation query that flags TransactionType / ResidentialAllocationType
  IDs the new schema doesn't have a rule for.

## Loading strategy

| Source | Target tables | Cadence | Notes |
|---|---|---|---|
| **Parcel Development History REST service** (future; `C:\GIS\Scratch.gdb\Parcel_History_Attributed` today) | `ParcelExistingDevelopment`, `ParcelSpatialAttribute`; `ParcelDevelopmentChangeEvent` on year-over-year diffs | Weekly | Field-for-field map. APN resolved through `ParcelGenealogyEventEnriched` at load. |
| **`dbo.TdrTransaction*` + `dbo.ParcelPermitBankedDevelopmentRight`** | *(none — exposed through `vCommodityLedger` view)* | — | Corral is the system of record; no table-level duplication. |
| **Manual QA workflow** | `LedgerManualAdjustment` | As-needed | Only for events that don't correspond to any Corral transaction or banking record. |
| **`Transactions_Allocations_Details.xlsx`** (Ken) | `PermitCompletion`, `PermitAllocation`, `CrossSystemID` | Seed + manual refresh | Only load the 8 Ken-unique columns per [xlsx_decomposition.md](./xlsx_decomposition.md). |
| **`ExistingResidential_2012_2025_unstacked.csv`** (Ken) | `ParcelExistingDevelopment` 2012–2015 baseline | Seed once | Retire after GIS FC fills pre-2016. |
| **`apn_genealogy_tahoe.csv`** + ongoing derivation jobs | `ParcelGenealogyEventEnriched` | Seed + scheduled | Resolver reads this on every APN-keyed write. |

## What v2+ adds (deferred)

- `IPESScore` + `ParcelLandCapabilityVerification` (already exist in `dbo.*` — wrap as view for the new DB)
- `DeedRestriction` + `ParcelDeedRestriction` (already in `dbo.*` — wrap as view)
- `QaChecklist` + `QaChecklistItem` + `QaChecklistResponse` (manual workflow)
- PAOT recreation pools (overnight / summer day / winter day)
- `MitigationFundAccount` + `MitigationFundLedger` (threshold-attainment category)
- Resource Utilization metrics (VMT, DVTE, impervious, water, sewage, SEZ)

## Questions for the team

Each question has a **proposed answer** (our current leaning). The review
task is to confirm, override, or add context. Mark with ✅ / ❌ / comment as
you go.

### Data model

**Q1. ADU modeling.** Corral's `dbo.ResidentialAllocationUseType` has only
two values: `SingleFamily` and `MultiFamily`. No ADU. How should we represent
ADUs?

- (a) Add a third value `ADU` to `ResidentialAllocationUseType`.
- (b) Add an `IsADU` bit to the allocation or permit.
- (c) Separate ADU concept tied to a parent unit (ADU = accessory to an existing SFRUU).
- **Proposed**: (a). Cleanest — ADU becomes a first-class use type alongside Single/Multi-Family.
- *Needs input from*: Ken + whoever manages the ADU Tracking XLSX today.

**Q2. `AllocationType` enum values.** `dbo.ResidentialAllocationType` has:
`Original`, `Reissued`, `LitigationSettlement`, `AllocationPool`. Does that
cover all the allocation "sources" TRPA cares about, or are there more we'll
encounter (e.g., `CommunityEnhancement`, `TransferOfDevelopmentRights`)?

- **Proposed**: accept the current 4; add values if we hit a case they don't cover.

**Q3. Conversion representation in the ledger.** A Conversion event (e.g.,
`1 TAU → 1 SFRUU`) is modeled as **two paired ledger entries** linked via
`PairedEntryID` — one row debits `TAU`, one row credits `SFRUU`, both for
the same parcel on the same date.

- Alternative: a single row with `FromCommodityID` / `ToCommodityID` columns.
- **Proposed**: two-entry. Keeps bucket-balance arithmetic clean (`SUM(Quantity)` by commodity is always correct).

**Q4. Conversion ratios — lookup table or hardcoded?** The 2013 Regional
Plan sets `600 CFA = 2 TAU = 2 SFRUU = 3 MFRUU`. Store as rows in a new
`ConversionRatio` lookup, or hardcode in ETL logic?

- **Proposed**: lookup table. Future-proofs against policy changes; also
  gives the dashboard something to display.

**Q5. `Banking` and `Unbanking` as ledger MovementTypes.** Corral has no
"Banking" transaction in `dbo.TdrTransaction` — banking events live in
`dbo.ParcelPermitBankedDevelopmentRight` (707 rows). We synthesize `Banking`
ledger rows at read time by joining `ParcelPermitBankedDevelopmentRight` to
the permit's `FinalInspectionDate`.

- Concern: is `FinalInspectionDate` the right "BankedDate"? Is there a
  better source in Corral?
- **Proposed**: accept `FinalInspectionDate` as a proxy; revisit if a
  stronger banking-date field exists.

### Integration with Corral

**Q6. `PermitCompletion` sidecar vs extending `dbo.ParcelPermit`.** The
completion-state fields (YearBuilt, PMYearBuilt, enriched completion status,
detailed development type, supplemental notes) don't exist in Corral.

- Option A: **Sidecar `PermitCompletion` table** FK'd to `dbo.ParcelPermit`.
  Avoids touching a live Corral table. Adds one join to read.
- Option B: `ALTER TABLE dbo.ParcelPermit ADD ...` — columns live next to
  existing permit fields. Cleaner long-term, but modifies a table the LTinfo
  app writes to.
- **Proposed**: (A) sidecar for v1. Migrate fields into `dbo.ParcelPermit`
  in a later phase if TRPA is comfortable with it.

**Q7. `vPermitAllocation` linkage strategy.** Corral has no direct FK between
`dbo.ParcelPermit` and `dbo.ResidentialAllocation`. The bridge today is via
`dbo.TdrTransaction.AccelaCAPRecordID` → `dbo.AccelaCAPRecord.AccelaID` →
(matched against permit's Accela record in the workflow system). **But only
32% of `TdrTransaction` rows have `AccelaCAPRecordID` populated.**

**Resolved direction** (revised from earlier draft): `vPermitAllocation` is a
**view**, not a table — don't build a second source of truth while the first
one has known gaps. Upgrade path:

1. **Phase 1** — `vPermitAllocation` joins via `TdrTransaction.AccelaCAPRecordID`
   for the 32% with direct FK, UNIONs additional matches from `CrossSystemID`
   rows seeded from Ken's XLSX, and flags `LinkageSource` so dashboards can
   show confidence.
2. **Phase 2** (separate project, out of v1 scope): **back-fill
   `dbo.TdrTransaction.AccelaCAPRecordID`** from Ken's XLSX into Corral so the
   view's coverage rises above 32%. This fixes both Corral and our view.

*Phase 2 is the highest-leverage Corral cleanup we've identified.* Worth
sequencing alongside v1 but separately scoped.

**Q8. Retroactive genealogy restatements.** When `apn_genealogy_tahoe.csv`
gets a new `old_apn → new_apn` mapping that affects historical rows, do we
rewrite the `ParcelExistingDevelopment` rows in place, or leave them and
insert `ChangeSource='genealogy_restatement'` rows in
`ParcelDevelopmentChangeEvent`?

- **Proposed**: the latter. Preserves an audit trail; matches Dan's
  change-rationale framing.

### GIS integration

**Q9. Geometry on `ParcelExistingDevelopment`.** Carry the polygon from the
GIS service for spatial queries inside this DB, or reference only by
`ParcelID` + `Year`?

- **Proposed**: carry. SDE-registered on the same server means the polygon
  is ~free, and it makes the ERD diagrams easier to publish as ESRI services
  directly.
- *Counterargument*: one more thing to keep in sync.

**Q10. 2016–2017 gap in the GIS FC.** `Parcel_History_Attributed` covers
2006–2015 and 2018–2023. 2016 and 2017 are missing.

- Is that real data loss, or just "we haven't published yet"?
- If real: do we leave nulls in `ParcelExistingDevelopment` for those years,
  interpolate, or reconstruct from AuditLog (which only has post-2016-Dec
  data for PCI)?
- **Needs input from**: whoever owns the FC population pipeline.

**Q11. Pre-2012 data horizon.** Dan's email framed scope as "2012 and on."
The FC actually has 2006–2011 records.

- Do we load 2006–2011 as `Source='pre_2012_baseline'` (future-proofed), or
  load only 2012+?
- **Proposed**: load everything; flag with `Source` so reports can filter.

### Operations

**Q12. Ken's XLSX transition.** Keep `Transactions_Allocations_Details.xlsx`
as Ken's authoring surface with a scheduled ETL that upserts the 8 Ken-unique
columns into the new tables (see [xlsx_decomposition.md](./xlsx_decomposition.md))
— or build a form-entry app to replace the XLSX?

- **Proposed**: v1 keeps the XLSX (zero disruption to Ken's workflow). v2+
  can replace with a form once the new DB is stable.

**Q13. Dashboard refresh cadence.** Can we commit to **nightly** recomputation
for `PoolDrawdownYearly` and `CumulativeAccountingSnapshot`? Affects ETL SLA.

- **Proposed**: yes, nightly. Annual cumulative accounting is produced once;
  the drawdown dashboard refreshes nightly.

### Scope

**Q14. PAOT and mitigation funds — v2 timing.** The TRPA Cumulative
Accounting framework also tracks PAOT (recreation) and mitigation fund
accounts. Currently deferred to v2+. Is that OK, or are there stakeholders
who need them in v1?

**Q15. Shorezone** — confirmed out of scope (handled by a separate system).
No action; noting for completeness.

---

### Quick vote sheet

Copy this and return with your votes:

```
Q1  ADU modeling:                    (a) / (b) / (c) / comment:
Q2  AllocationType enum:             accept-4 / add:___________
Q3  Conversion representation:       two-entry / one-row / comment:
Q4  Conversion ratios:               lookup / hardcoded / comment:
Q5  Banking date source:             FinalInspectionDate OK / use:___________
Q6  PermitCompletion placement:      sidecar / extend-ParcelPermit / comment:
Q7  PermitAllocation (now view):     Phase-1-view-OK / comment on Phase-2 scope:
Q8  Retroactive genealogy:           rewrite-in-place / correction-entries / comment:
Q9  Geometry on PED:                 carry-polygon / ID-only / comment:
Q10 2016-2017 GIS gap:               leaving-null / reconstruct / comment:
Q11 Pre-2012 data:                   load-all-flag / 2012-only / comment:
Q12 Ken XLSX transition:             keep-XLSX / form-entry-v1 / comment:
Q13 Dashboard refresh:               nightly-OK / other:___________
Q14 PAOT/mitigation v2 timing:       OK / need-in-v1
```

## Ready-to-build v1 new-table list

Folded into existing SDE backend. **7 new physical tables + 2 views + 3 materializations**.
Every item holds data Corral doesn't — no duplication.

New physical tables:

1. `ParcelExistingDevelopment` — per-parcel × year × commodity quantity (GIS-sourced; Corral has no year-indexed inventory for non-permit-verified parcels)
2. `ParcelSpatialAttribute` — per-parcel × year spatial context (GIS-sourced year snapshot; distinct from `dbo.Parcel` current state)
3. `ParcelGenealogyEventEnriched` — 10+ metadata columns on top of `dbo.ParcelGenealogy` (3 columns)
4. `ParcelDevelopmentChangeEvent` — Dan's change rationale; no Corral analog
5. `PermitCompletion` — sidecar on `dbo.ParcelPermit` with YearBuilt, CertificateOfOccupancyDate, CompletionStatusEnriched, DetailedDevelopmentType (all net-new)
6. `LedgerManualAdjustment` — manual QA-correction ledger entries only (TDR + Banking live in Corral)
7. `CrossSystemID` — polymorphic ID map (Accela, LTinfo, TRPA_MOU, Local Jurisdiction, Assessor)

Views (no physical storage — Corral remains the source of truth):

- `vCommodityLedger` — UNIONs `dbo.TdrTransaction*` + `dbo.ParcelPermitBankedDevelopmentRight` + `LedgerManualAdjustment` into a unified movement log. Exposes `PairingKey` for conversion pairing.
- `vPermitAllocation` — crosswalk of `dbo.ParcelPermit` ↔ `dbo.ResidentialAllocation` via `TdrTransaction.AccelaCAPRecordID` + `CrossSystemID`. Phase 1 has ~32% coverage; Phase 2 back-fills Corral to raise it.

Materialized (computed nightly; derived denormalizations are allowed):
- `CumulativeAccountingSnapshot`
- `PoolDrawdownYearly`
- `ParcelHistoryView`
