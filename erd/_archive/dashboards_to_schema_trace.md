# Dashboards → Views → Schema trace

> **Status: DRAFT - first pass.** Working *backwards* from end-stage
> visualizations to confirm the view contracts and schema. Sibling to
> [_archive/proposed_dashboards.md](./_archive/proposed_dashboards.md) (the broad catalog) and
> [target_schema.md](./target_schema.md) (the proposed tables/views).

## Why this doc exists

The repo had been growing schema/ERD definitions from the bottom up, which
made it easy to over-spec tables that no dashboard actually needs. This doc
flips the direction: it starts from the **3 v1 dashboards already committed
to** and traces each one back through its view contract to the schema
columns it requires.

Anything in `target_schema.md` that doesn't show up here is a candidate for
deferral. Anything *missing* from `target_schema.md` that shows up here is
a real gap and belongs in a follow-up issue.

## Findings from the analyst's April 2026 deliverables (added 2026-04-30)

The analyst sent the 2026 Cumulative Accounting Report and 5 supporting XLSX files
(at [`from_analyst/`](../from_analyst/) outside this worktree) on 2026-04-30. Reading
them resolved several open gaps in this trace and surfaced four new ones.
Detail in the gap sections below; summary here:

| Gap | Status after the analyst's data |
|---|---|
| **G1.2** `MaxRegionalCapacity` source | ✅ Resolved - Regional Plan caps: RES Alloc **8,687**, RBU **2,000**, TBU **400**, CFA **1,000,000 sq ft** (since-1987 cumulative). The 2012 Plan's *additional* authorization on top of 1987 unused was 2,600. |
| **G2.1** `InitialCapacity` per pool | ✅ Resolved - the analyst's `LT Info Pool Balances` sheet has the per-pool starting capacities; PPTX slide 5 has the per-jurisdiction unused breakdown. |
| **G2.2** CSLT sub-pools | ✅ Confirmed real - the prototype HTML's CSLT split into Single-Family / Multi-Family / Town Center matches the analyst's pool breakdowns. |
| **G3.1–G3.4** ParcelDevelopmentChangeEvent | ✅ Schema landed - `target_schema.md` now has `RawAPN` audit column on `ParcelDevelopmentChangeEvent` and a sidecar `QaCorrectionDetail` (1:0..1) for QA-specific metadata. Loader notebook pending. |
| **NEW G2.7** Unreleased pool | Slide 5 names "UNRELEASED ALLOCATIONS = 770" as a distinct category - not modeled in current schema. |
| **NEW G2.8** Bonus Units as movement type | Slide 3: "Bonus Units became the #1 source of 2024 and 2025 additions." Schema treats them as a *bucket* only, not a first-class movement-type column on `PoolDrawdownYearly`. |
| **G3.3.*** `CorrectionCategory` + cycle-year column | ✅ Resolved by Track C - `QaCorrectionDetail` sidecar carries `ReportingYear` (annual, any value) + `SweepCampaign` (nullable big-sweep tag) + `CorrectionCategory` (9-value enum). Earlier draft used `ReportingCycleYear` and assumed biennial; corrected to `ReportingYear` per user's annual-cadence + periodic-sweep clarification. |
| **NEW G3.5** Project-level annotations | Each year's Summary has a free-text "Major Completed Projects" column (Sugar Pine, LTCC Dorms, Beach Club, etc.). Schema has no `Project` entity. |
| **NEW G3.6** APN format normalization | ⚠️ Partial - `RawAPN` audit column landed on `ParcelDevelopmentChangeEvent`. Canonicalization function `fn_canonical_apn` still pending the loader notebook. |
| **Q1 ADU modeling** | ✅ Resolved as option (b) - `IsADU bit` flag on `dbo.ResidentialAllocation` and `dbo.ResidentialBonusUnit*`, not a third use type. |

**Design constraint to note** - TRPA Pool reconciliation: the analyst annotated the LT Info pool report *"TRPA Pool: 154 - pool shows as 144, but that is incorrect - should be 154"*. The current [html/allocation_drawdown.html](../html/allocation_drawdown.html) prototype displays the wrong (144) value the analyst has flagged. The schema needs a reconciliation rule: don't blindly carry LT Info pool values without the analyst's manual corrections layered in.

(Reporting cadence note from earlier draft removed - see [tracks_status.md](./tracks_status.md) "Reporting cadence" section. TRPA reports annually; QA corrections are continuous; 2023 and 2026 are big-sweep campaigns, not biennial.)

The full PowerPoint maps directly onto the dashboards in this trace -
slide 8 (Regional Plan Additional Development Overview) is the headline
[Trace 1] view, slide 5 (Allocations Remaining) is [Trace 2], and the
per-APN data behind the report is [Trace 3].

## LT Info grid pages → Corral tables (data sources)

The dashboards in `html/` fetch CSVs that are static exports of LT Info
grid-view pages. **LT Info is the front-end for `corral.db`** - every
grid is just a SQL query against the Corral tables documented in
[development_rights_erd.md](./development_rights_erd.md). The CSV step
exists only because we don't yet have a direct read path from the
browser to Corral.

| Dashboard CSV (in `data/raw_data/`) | LT Info source page | Corral backing |
|---|---|---|
| [residentialAllocationGridExport.csv](../data/raw_data/residentialAllocationGridExport.csv) | `parcels.laketahoeinfo.org` → Residential Allocation grid | `dbo.ResidentialAllocation` joined to `ResidentialAllocationType`, `CommodityPool`, `Jurisdiction`, `TdrTransaction`, `TdrTransactionAllocation`, `Parcel`. ~2,113 rows ≈ 1:1 with `dbo.ResidentialAllocation`. |
| [CFA_TAU_allocations.csv](../data/raw_data/CFA_TAU_allocations.csv) | `parcels.laketahoeinfo.org` → CFA + TAU allocation grids | `dbo.TdrTransaction` filtered to CFA/TAU `CommodityID`, joined to `CommodityPool` and `Jurisdiction`. |

**Transaction number format**: `{LeadAgencyAbbreviation}-{TransactionTypeAbbreviation}-{TdrTransactionID}` -
e.g., `TRPA-ALLOCASSGN-1289`. Confirmed via the LT Info services probe at
[ltinfo_services.json](./ltinfo_services.json) and visible on the live
[TdrTransaction TransactionList page](https://parcels.laketahoeinfo.org/TdrTransaction/TransactionList) (login required).

**Refresh path today**: re-export the grid as CSV from LT Info → drop
into `data/raw_data/` → commit + push to MTB-Edits. Dashboards fetch
from the GitHub raw URL on the MTB-Edits branch.

**Long-term path** (per `target_schema.md`): replace the CSV-fetch with
a direct query against `vCommodityLedger` - same data, no manual export
step. The view UNIONs the same `dbo.TdrTransaction*` source tables that
LT Info's grid pages already query, plus
`dbo.ParcelPermitBankedDevelopmentRight` for banking events Corral
doesn't model as transactions.

---

The 3 committed dashboards (per [target_schema.md §"Ready-to-build v1" and
_archive/proposed_dashboards.md §"Already committed"](./target_schema.md)):

1. **Cumulative Accounting Report** - annual XLSX replacement; 5-bucket
   decomposition per (commodity × jurisdiction × year). Driven by
   `CumulativeAccountingSnapshot`. Realized CSV proxy:
   [ledger_prototype/views/v_cumulative_accounting.csv](../ledger_prototype/views/v_cumulative_accounting.csv) (430 rows).
2. **Allocation Drawdown** - stacked area: pool × year → remaining balance.
   Driven by `PoolDrawdownYearly`. Realized CSV proxy:
   [ledger_prototype/views/v_pool_drawdown.csv](../ledger_prototype/views/v_pool_drawdown.csv) (102 rows).
   **Live HTML prototype**: [html/allocation_drawdown.html](../html/allocation_drawdown.html).
3. **Parcel History Lookup** - per-APN timeline with change-rationale
   detail. Driven by `ParcelHistoryView` + `ParcelDevelopmentChangeEvent`.
   No CSV proxy yet - pure schema-side proposal.

## How to read each trace

Each section below has the same five-part structure:

1. **Chart shape** - what the user sees (axes, marks, filters, drill paths,
   audience).
2. **View contract** - the exact column shape the chart consumes
   `(name, type, grain, refresh expectation)`.
3. **Realized vs proposed** - side-by-side: what the prototype actually
   produces today vs what `target_schema.md` proposes.
4. **Schema trace** - every view column mapped back to the source column(s)
   in `target_schema.md` or `dbo.*`.
5. **Gaps** - concrete deltas worth tracking as issues.

---

## Trace 1 - Cumulative Accounting Report

> **Status of source code**: realized CSV exists; no live HTML prototype
> yet. The realized CSV is the closest ground truth.

### Chart shape

The Cumulative Accounting Report is the **annual XLSX replacement** that
TRPA publishes per TRPA Code §16.8.2. Today it lives in
[the analyst's transactions XLSX](../data/raw_data/) and is published at
[thresholds.laketahoeinfo.org/CumulativeAccounting/Index/{Year}](https://thresholds.laketahoeinfo.org/CumulativeAccounting/Index/2023).

For v1 the dashboard form should be a **filterable table + small-multiples
bar chart** (per [trpa-dashboard-stack](../README.md) - AG Grid for the
table, Plotly stacked bar per (jurisdiction × commodity)). Audience: leadership +
governing board + partner jurisdictions.

| Element | Spec |
|---|---|
| **Primary view** | AG Grid table; rows are `(Year × Jurisdiction × Commodity)`; columns are the 5 buckets + `MaxRegionalCapacity`. |
| **Secondary view** | Stacked bar chart per (Jurisdiction × Commodity) showing the 5-bucket decomposition over time. Year on x-axis. |
| **Filters** | Year (default = latest), Jurisdiction (multi-select), Commodity (multi-select). |
| **Drill** | Click a cell → underlying ledger entries that summed to that bucket value (links to a future `vCommodityLedger` filtered query). |
| **Branding** | TRPA Blue (#0072CE) for the header bar; bucket colors picked from the chart palette per [trpa-brand](../resources/) - Existing=Navy, Banked=Ice, Allocated=Orange, BonusUnits=Forest, UnusedCapacity=Earth. |

### View contract

The view feeding this dashboard is `CumulativeAccountingSnapshot` (proposed
name in [target_schema.md](./target_schema.md)). The realized prototype CSV
is [`v_cumulative_accounting.csv`](../ledger_prototype/views/v_cumulative_accounting.csv).

**Required column shape** (the dashboard's contract):

| Column | Type | Grain | Notes |
|---|---|---|---|
| `Year` | int | One row per (Year × Jurisdiction × Commodity) | 2004–latest |
| `JurisdictionID` | int FK → `dbo.Jurisdiction` | | Schema proposes ID; realized uses string `JurisdictionAbbrev`. **Both needed for join + display.** |
| `JurisdictionAbbrev` | varchar | | Display label (SLT, EL, PL, DG, WA, TRPA) |
| `CommodityID` | int FK → `dbo.Commodity` | | Schema proposes ID |
| `CommodityShortName` | varchar | | Display label (SFRUU, MFRUU, RBU, TAU, CFA, …) |
| `ExistingQuantity` | int (nullable) | | bucket 1 |
| `BankedQuantity` | int (nullable) | | bucket 2 |
| `AllocatedNotBuiltQuantity` | int (nullable) | | bucket 3 |
| `BonusUnitsRemaining` | int (nullable) | | bucket 4 |
| `UnusedCapacityRemaining` | int (nullable) | | bucket 5 |
| `MaxRegionalCapacity` | int (nullable) | | for the accounting identity |
| `ComputedAt` | datetime | | freshness label |

**Refresh expectation**: nightly recompute (per `target_schema.md` Q13).
The annual XLSX replacement only *needs* yearly accuracy, but the dashboard
should always reflect last-night's state.

### Realized vs proposed

**Realized today** ([v_cumulative_accounting.csv](../ledger_prototype/views/v_cumulative_accounting.csv), 430 rows):

```
Year, JurisdictionAbbrev, CommodityShortName, Allocated, Banked, Existing, UnusedCapacity
```

**Proposed in [target_schema.md](./target_schema.md)** (`CumulativeAccountingSnapshot`):

```
SnapshotID, Year, JurisdictionID, CommodityID,
ExistingQuantity, BankedQuantity, AllocatedNotBuiltQuantity,
BonusUnitsRemaining, UnusedCapacityRemaining, MaxRegionalCapacity,
ComputedAt
```

Differences:

| Concern | Realized CSV | Proposed schema | Direction |
|---|---|---|---|
| Identity column | none | `SnapshotID PK` | Schema is right (need PK for the table form). |
| Jurisdiction key | `JurisdictionAbbrev` (string) | `JurisdictionID` (int FK) | **Carry both** - ID for joins, Abbrev for display. View materializer should output both. |
| Commodity key | `CommodityShortName` (string) | `CommodityID` (int FK) | Same - carry both. |
| Bucket 1 (Existing) | `Existing` | `ExistingQuantity` | Rename realized → proposed (more explicit). |
| Bucket 2 (Banked) | `Banked` | `BankedQuantity` | Same. |
| Bucket 3 (Allocated-not-built) | `Allocated` | `AllocatedNotBuiltQuantity` | Same - and clarify: the realized `Allocated` is *all* allocated quantity, not specifically "not yet built". The notebook's bucket comes from `BucketType='Allocated'` ledger entries. Need to confirm semantics match. |
| Bucket 4 (Bonus Units) | **MISSING** | `BonusUnitsRemaining` | **Gap**. Realized notebook has a `classify_pool()` heuristic that assigns `BucketType='BonusUnits'` to pools with "bonus" in their name, but no rows landed in the prototype's output. Likely zero `BonusUnits` ledger entries exist yet because no movement type writes to that bucket. |
| Bucket 5 (Unused Capacity) | `UnusedCapacity` | `UnusedCapacityRemaining` | Same rename. |
| Capacity ceiling | **MISSING** | `MaxRegionalCapacity` | **Gap**. Realized notebook leaves `MaxCapacity` null on `account.csv` ("until the analyst confirms the authoritative source per commodity"). The dashboard *needs* this to show "% of capacity used." |
| Freshness stamp | **MISSING** | `ComputedAt` | Add to view output for the dashboard's "last updated" label. |

### Schema trace

How each `CumulativeAccountingSnapshot` column traces back to source (per
[target_schema.md](./target_schema.md) and [build_ledger.ipynb](../ledger_prototype/build_ledger.ipynb)):

| View column | Sourced from | Logic |
|---|---|---|
| `Year` | `vCommodityLedger.EntryDate` (year-extracted) | `YEAR(EntryDate)` |
| `JurisdictionID` | `dbo.Jurisdiction` via `vCommodityLedger.SendingParcelID` / `ReceivingParcelID` → `dbo.Parcel.JurisdictionID` | Parcel-keyed entries get jurisdiction via parcel; pool-keyed entries (no parcel) currently fall through to a synthetic "TRPA" row in the realized CSV. **Confirm this is the intended behavior or document the rule.** |
| `CommodityID` | `vCommodityLedger.CommodityID` | direct |
| `ExistingQuantity` | `vCommodityLedger` filtered to `BucketType='Existing'`, cumulative sum through `Year` | running balance |
| `BankedQuantity` | `vCommodityLedger` filtered to `BucketType='Banked'`, cumulative sum | running balance |
| `AllocatedNotBuiltQuantity` | `vCommodityLedger` filtered to `BucketType='Allocated'`, cumulative sum | The "not built" qualifier comes from the lifecycle: once an allocation is `ALLOCASSGN`'d (assigned to a permit and built), the ledger debits `Allocated` and credits `Existing` - so the cumulative sum naturally reflects "allocated and not yet built." |
| `BonusUnitsRemaining` | **No source yet.** Schema says "derivable from `dbo.CommodityPool` records plus the movement ledger, materialized nightly into `PoolDrawdownYearly`." | Need rule for how a pool's "bonus units remaining" is computed: starting capacity (from `dbo.CommodityPool` - which column?) minus drawdown ledger entries pointing at that pool. |
| `UnusedCapacityRemaining` | Same shape as `BonusUnitsRemaining` for non-bonus pools | Cumulative sum of `BucketType='UnusedCapacity'` ledger entries (negative = drawdown). |
| `MaxRegionalCapacity` | **No source yet.** | Per Q3 in build notebook: "until the analyst confirms the authoritative source per commodity." Likely lives on `dbo.CommodityPool` (one of the capacity columns) or in a TRPA Code reference table. |
| `ComputedAt` | Set at materialization time | `GETUTCDATE()` |

### Gaps for Trace 1 (issues to file)

- **G1.1 - `BonusUnitsRemaining` derivation.** Define the rule: which
  pools count as "bonus", which capacity column on `dbo.CommodityPool` is
  the starting balance, what ledger movement types debit/credit it. Today
  the realized CSV has zero rows in this bucket.
- **G1.2 - `MaxRegionalCapacity` source.** ✅ **Resolved by the analyst's 2026
  PPTX slide 8.** The since-1987 cumulative caps are: Residential
  Allocations 8,687 units, Residential Bonus Units 2,000 units, Tourist
  Bonus Units 400 units, Commercial Floor Area 1,000,000 sq ft. The 2012
  Regional Plan's *additional* authorization (Board-adopted 2013) on top
  of any unused 1987 allocations was 2,600 units. **Action**: model as a
  `RegionalPlanCapacity` reference table keyed by `(Commodity, PlanEra)`
  where `PlanEra ∈ {1987, 2012, since-1987-cumulative}` so dashboards
  can show whichever framing the audience needs.
- **G1.3 - Pool-keyed jurisdiction fallthrough.** Realized CSV rolls
  pool-keyed entries (no parcel) into a synthetic `TRPA` row. Confirm
  this matches the published cumulative accounting report's convention,
  or document a different aggregation rule.
- **G1.4 - Carry display labels alongside FK IDs.** Schema currently
  says `JurisdictionID` and `CommodityID`. Add `JurisdictionAbbrev` and
  `CommodityShortName` to the view output (denormalized) so the
  dashboard doesn't need an extra join just for labels.
- **G1.5 - Naming convention.** `Allocated` vs `AllocatedNotBuiltQuantity`,
  `Banked` vs `BankedQuantity` - pick one (proposed `*Quantity` suffix is
  explicit; realized short names are friendlier). Recommend the schema
  drop the `Quantity` suffix to match the realized prototype, since the
  bucket name already implies a quantity.

---

## Trace 2 - Allocation Drawdown

> **Status of source code**: realized CSV + **live HTML prototype**.
> The HTML is the most authoritative ground truth - it's what the
> dashboard already shows.

### Chart shape

[html/allocation_drawdown.html](../html/allocation_drawdown.html) - a Plotly
**stacked area chart**: x = Year (2013–2026), y = "Remaining Allocations",
one stacked series per pool. `hovermode: "x unified"` so hovering a year
shows all pools' remaining counts. `rangemode: "tozero"` on y-axis.

Title: **"Residential Allocation Drawdown by Pool (2013 Regional Plan)"**.
Series legend title: "Pool".

The series in the prototype (9 pools, all **residential allocation pools
under the 2013 Regional Plan's 2,600-home authorization** - this aligns
with the user's MEMORY note about the 2,600 total):

| Series name | 2013 value | 2026 value | Approx drawdown over 13 years |
|---|---:|---:|---:|
| TRPA Pool | 162 | 144 | -18 |
| Placer County | 462 | 349 | -113 |
| El Dorado County | 407 | 98 | -309 |
| City of South Lake Tahoe | 155 | 0 | -155 (exhausted) |
| Washoe County | 124 | 123 | -1 |
| CSLT – Single-Family | 143 | 78 | -65 |
| Douglas County | 134 | 93 | -41 |
| CSLT – Multi-Family | 59 | 52 | -7 |
| CSLT – Town Center | 59 | 51 | -8 |
| **Total starting capacity** | **1,705** | **988** | **−717 used** |

(2013-Plan total target is 2,600; 1,705 is the residential subset across
the pools listed. Other 895 likely sit in pools not yet in this prototype.)

| Element | Spec |
|---|---|
| **Mark** | Stacked area; one trace per pool; `fill='tonexty'`; `mode='lines'`. |
| **X axis** | Year, integer, 2013→latest+future-projection (2026). |
| **Y axis** | "Remaining Allocations", `rangemode='tozero'`. |
| **Hover** | `x unified` - single column shows all pools. |
| **Color** | Currently uses Wong/Tol palette (e.g., rgb 136,204,238). **Should swap to TRPA brand chart sequence** (`#0072CE, #003B71, #E87722, #4A6118, #9C3E27, #B5A64C, #7B6A8A, #B4CBE8`) per [trpa-brand](../resources/). With 9 series and 8 brand colors, the 9th wraps. |
| **Filters (v1)** | Pool group (jurisdiction vs CSLT subdivision vs TRPA-held). |
| **Drill** | Click a series at year Y → table of allocations released from that pool that year (links to `vCommodityLedger` filtered query). |

### View contract

What the chart consumes:

| Column | Type | Grain | Notes |
|---|---|---|---|
| `Year` | int | One row per (Pool × Year) | 2013–latest, but the prototype includes future projection rows (2024–2026 are flat extrapolations). |
| `PoolID` | int FK → `dbo.CommodityPool` | | Realized CSV uses this as `CommodityPoolID`. |
| `PoolName` | varchar | | Display label. The HTML uses values like "TRPA Pool", "Placer County", "CSLT – Single-Family" - these come from `dbo.CommodityPool.CommodityPoolName`. |
| `RemainingBalance` | numeric | | The y-value: cumulative remaining = StartingBalance − sum(drawdowns through Year). |
| `StartingBalance` | numeric | | Optional; useful for the "% used" derived metric. |
| `Released` (or movement-typed columns) | numeric | | Per-year drawdown by movement type - wide format per `target_schema.md`. The chart only consumes the running remaining, but the underlying view should still expose movement detail for the drill-down. |

**Refresh expectation**: nightly. The dashboard caption should read "as of
{ComputedAt:date} - pulled from `PoolDrawdownYearly`."

### Realized vs proposed

**Realized today** ([v_pool_drawdown.csv](../ledger_prototype/views/v_pool_drawdown.csv), 102 rows):

```
Year, CommodityPoolID, CommodityShortName, ALLOC
```

The single value column `ALLOC` holds **negative drawdown amounts** - i.e.,
how much was released from that pool in that year via `MovementType='ALLOC'`.
All values negative because allocations leave `UnusedCapacity`.

**Proposed in [target_schema.md](./target_schema.md)** (`PoolDrawdownYearly`):

```
DrawdownID PK, PoolID, Year,
StartingBalance, Released, Assigned, Used, Banked, Unbanked,
Transferred, Converted, ConvertedWithTransfer, LandBankIn, LandBankOut,
Retired, QAAdjusted, EndingBalance, ComputedAt
```

**HTML prototype's actual data shape** (extracted from
[allocation_drawdown.html](../html/allocation_drawdown.html)):

```
{ PoolName: string, x: [Years], y: [RemainingBalance per year] }   x9 series
```

i.e., long format `(Year, PoolName, RemainingBalance)` after pivoting.

Three different shapes for the same conceptual view. Differences:

| Concern | Realized CSV | Proposed schema | HTML actually consumes | Direction |
|---|---|---|---|---|
| Format | Long, sparse: only `ALLOC` movements present | Wide: 11 movement-type columns + StartingBalance + EndingBalance | Long: pool/year/remaining | View should produce wide (proposed); dashboard derives `RemainingBalance = StartingBalance − cumulative drawdowns` client-side. **Or** view materializes both `*RemainingBalance` and `*Drawdown` columns and dashboard reads `EndingBalance` directly. Recommend the latter - simpler client. |
| Pool key | `CommodityPoolID` (int) | `PoolID` (int FK) | `PoolName` (string) | **Carry both** - ID for joins, Name for display. View should denormalize. |
| Movement-type columns | Just `ALLOC` because no other movements wrote `UnusedCapacity` rows in the prototype | All 11: Released, Assigned, Used, Banked, Unbanked, Transferred, Converted, ConvertedWithTransfer, LandBankIn, LandBankOut, Retired, QAAdjusted | None - chart only needs net remaining | Schema is right (drill-down dashboards will need movement-typed detail); v1 prototype ships with mostly-zero columns until other movement types wire in. |
| StartingBalance | Not in realized | `StartingBalance` proposed | Implied in y-values (the 2013 value is effectively the starting balance for the 2,600-home era) | **Schema needs to specify what `StartingBalance` means**: is it (a) the pool's authorized initial capacity per the 2013 Regional Plan, (b) the rolling prior-year `EndingBalance`, or (c) both as separate columns? Recommend (c): `InitialCapacity` (static, set when pool is created) + `OpeningBalance` (carry-forward from prior year). |
| EndingBalance | Not in realized | `EndingBalance` proposed | This *is* the y-value | Confirm: `EndingBalance = OpeningBalance + Released + Assigned + Used + ... + QAAdjusted` (signed sum). Document that signing convention. |
| Pool-name granularity | One row per `CommodityPoolID` | One row per pool | The HTML splits CSLT into 3 sub-pools (Single-Family, Multi-Family, Town Center) | **The HTML's CSLT split is finer than `CommodityPoolID` alone.** Either CSLT has multiple pool IDs in `dbo.CommodityPool` (likely), or these are derived by joining `ResidentialAllocationUseType`. Need to confirm against `dbo.CommodityPool` directly. **This is the highest-confidence schema gap from the trace.** |
| Time horizon | 2010–2024 (full ledger history) | not specified | 2013–2026 (start of Regional Plan + future projection) | View should produce all years; dashboard filters to ≥2013 client-side. **Future projection rows (post-current-year) need to come from somewhere** - currently the HTML extrapolates flat. Document whether the view returns only historical rows or includes a forward-projection. Recommend historical only; projection logic stays in the dashboard. |
| Refresh stamp | Not in realized | `ComputedAt` proposed | Not currently shown in HTML | Add `ComputedAt` to view + caption to dashboard. |

### Schema trace

How each `PoolDrawdownYearly` column traces back to source:

| View column | Sourced from | Logic |
|---|---|---|
| `PoolID` | `dbo.CommodityPool.CommodityPoolID` | direct |
| `PoolName` | `dbo.CommodityPool.CommodityPoolName` | direct |
| `Year` | `vCommodityLedger.EntryDate` (year-extracted), driven by ledger entries with `FromPoolID = PoolID` or `ToPoolID = PoolID` | |
| `OpeningBalance` | Prior year's `EndingBalance` for this `PoolID`. First year = `InitialCapacity`. | recursive |
| `InitialCapacity` | `dbo.CommodityPool.{?}` - authoritative initial capacity column | **Need to identify**: which column on `dbo.CommodityPool` holds the 2013 Regional Plan authorization. May not exist; might need to seed from a static reference. |
| `Released` | `SUM(Quantity)` from `vCommodityLedger WHERE MovementType='ALLOC' AND FromPoolID=PoolID` (negative - drawdowns) | |
| `Assigned` | `SUM(Quantity)` from `vCommodityLedger WHERE MovementType='ALLOCASSGN' AND FromPoolID=PoolID` | This is the schema's word for what the build notebook does in branch 1 of `corral_tdr`. |
| `Used` | "Built through permit completion" - unclear how this differs from `Assigned`. | **Schema clarification needed**: in the build notebook, `ALLOCASSGN` already moves the unit from `Allocated` to `Existing` (i.e., "built"). Is `Used` the same as `Assigned` or a separate event downstream of permit final inspection? |
| `Banked`, `Unbanked` | `SUM(Quantity)` from `vCommodityLedger` filtered to `MovementType IN ('Banking','Unbanking')` and matching pool | `Unbanking` not yet in build notebook. |
| `Transferred`, `Converted`, `ConvertedWithTransfer`, `LandBankIn`, `LandBankOut`, `Retired` | Same pattern, filtered by MovementType | All present in build notebook except `Unbanking`. |
| `QAAdjusted` | `vCommodityLedger.MovementType='QACorrection'` filtered to pool | Manual ledger branch - currently empty. |
| `EndingBalance` | `OpeningBalance + Released + Assigned + Used + Banked + Unbanked + Transferred + Converted + ConvertedWithTransfer + LandBankIn + LandBankOut + Retired + QAAdjusted` | Signed sum of all movement-type columns. |
| `ComputedAt` | `GETUTCDATE()` at materialization | |

### Gaps for Trace 2 (issues to file)

- **G2.1 - `InitialCapacity` source.** ✅ **Resolved by the analyst's
  `Additional Development as of April2026.xlsx` "LT Info Pools Balances"
  sheet + PPTX slide 5.** Per-pool starting capacities are in the analyst's
  spreadsheet; per-jurisdiction unused-allocation breakdown
  (Placer 349, El Dorado 135, SLT 0, Washoe 93, Carson 98, Douglas 186,
  TRPA Pool 154, Unreleased 770) is in slide 5. **Action**: load these
  as the initial seed for `PoolDrawdownYearly.InitialCapacity`; flag
  source as `kens_xlsx_april_2026` for traceability.
- **G2.2 - CSLT pool-name granularity.** ✅ **Confirmed real.** the analyst's
  pool reports + PPTX confirm CSLT does have multiple sub-pools (Town
  Center, Single-Family, Multi-Family). **Action**: model as 3 distinct
  `CommodityPoolID` rows in the schema (matches the HTML prototype's
  series); no derived `PoolSubgroup` column needed.
- **G2.7 - Unreleased allocations as a distinct category** (NEW from
  the analyst's data). PPTX slide 5 names "UNRELEASED ALLOCATIONS = 770" as a
  jurisdiction-tier category between "TRPA Pool" and the per-jurisdiction
  pools. These are units the Regional Plan authorized but TRPA hasn't
  yet released to any pool. May be equivalent to "TRPA-level
  UnusedCapacity" but worth confirming. **Action**: either model as a
  pseudo-pool (`PoolName='Unreleased', JurisdictionID=NULL`) or add a
  `ReleaseStatus` column to `dbo.CommodityPool`. Decide before
  populating `PoolDrawdownYearly`.
- **G2.8 - Bonus Units as a first-class movement type** (NEW from the analyst's
  data). PPTX slide 3: "Bonus Units became the #1 source of 2024 and 2025
  additions" (Sugar Pine 70 + LTCC 85 = 155 affordable bonus units).
  Schema currently treats Bonus Units as a *bucket* on
  `CumulativeAccountingSnapshot` and not as a movement-type column on
  `PoolDrawdownYearly`. **Action**: add `BonusUnitReleased` and
  `BonusUnitUsed` columns to `PoolDrawdownYearly`, OR stand up a sibling
  `BonusUnitDrawdownYearly` view. Bonus units have their own pool with
  its own 2,000-unit cap (per G1.2), so a separate view may be cleaner.
- **G2.3 - `Assigned` vs `Used` semantic.** Schema lists both as separate
  columns. Build notebook treats `ALLOCASSGN` as the moment
  Allocated→Existing happens (i.e., the "built" event). Either rename one
  or define the lifecycle stage that distinguishes them (e.g., `Assigned`
  = allocated to a parcel; `Used` = permit finaled / CO issued). This
  matters for the dashboard's drill-down semantics.
- **G2.4 - Branding swap.** Replace the Wong/Tol palette in
  `allocation_drawdown.html` with the TRPA chart sequence. Cosmetic but
  visible. Tracks against [trpa-brand](../resources/).
- **G2.5 - Forward projection.** The HTML extends to 2026 with flat
  values for the latest 2 years (current = 2026, no real data yet for
  beyond `EntryDate`). Document that `PoolDrawdownYearly` returns only
  historical rows; any projection is dashboard logic.
- **G2.6 - `Unbanking` movement type.** Schema lists it; build notebook
  doesn't synthesize any. Document where `Unbanking` events come from
  (re-permitting of a previously-banked right? a Corral table not yet
  joined?) or remove from the schema.

---

## Trace 3 - Parcel History Lookup

> **Status of source code**: no HTML prototype, but the analyst's
> `CA Changes breakdown.xlsx` Sheet1 (44,372 rows) is the realized
> `ParcelDevelopmentChangeEvent` data, and `FINAL RES SUMMARY 2012 to
> 2025.xlsx` Sheet `Residential` (42,500 rows) is the realized
> `ParcelExistingDevelopment`. Use those as ground truth.

### Chart shape

A **per-APN lookup page**. User enters a parcel number (or clicks a parcel
on a map) → page renders that parcel's full development-rights history.
Audience: TRPA staff for QA; eventually public for developer due-diligence
(per `_archive/proposed_dashboards.md` cluster G2).

| Element | Spec |
|---|---|
| **Hero panel** | Current state: what commodities does this parcel have today, and how many of each. Plus a small map of the parcel. |
| **Timeline** | Vertical timeline of `(Year, Commodity, Quantity, ChangeSource, Rationale)` events for this APN. Each event is a card showing the change (Previous → New), the source, and a link to evidence (permit number, transaction ID). |
| **Genealogy panel** | If the APN has been split/merged/renamed, show the parent/child APNs and link to their pages. |
| **Filters** | Commodity (multi-select), Year range, ChangeSource (multi-select). |
| **Branding** | TRPA Blue header, Navy body. Links to permit / TDR records via `EvidenceURL`. |

### View contract

This dashboard reads from **two tables jointly**: `ParcelHistoryView` (the
year-by-year quantity snapshot) and `ParcelDevelopmentChangeEvent` (the
change-rationale audit trail).

**`ParcelHistoryView` shape** (per [target_schema.md](./target_schema.md)):

| Column | Type | Grain | Notes |
|---|---|---|---|
| `HistoryID` | int PK | one row per (Parcel × Year × Commodity) | |
| `ParcelID` | int FK → `dbo.Parcel` | | |
| `ParcelNumber` | varchar | | denormalized for display + lookup |
| `Year` | int | | |
| `CommodityID` | int FK → `dbo.Commodity` | | |
| `CommodityShortName` | varchar | | denormalized |
| `Quantity` | int | | year-end count for that commodity |
| `ChangeCount` | int | | how many `ParcelDevelopmentChangeEvent` rows fire'd this year for this (parcel, commodity) |
| `LastChangeSource` | varchar | | summary; full detail comes from `ParcelDevelopmentChangeEvent` |
| `LastChangeRationale` | varchar | | summary |

**`ParcelDevelopmentChangeEvent` shape** (per [target_schema.md](./target_schema.md)):

| Column | Type | Notes |
|---|---|---|
| `ChangeEventID` | int PK | |
| `ParcelID` | int FK | |
| `CommodityID` | int FK | |
| `Year` | int | |
| `PreviousQuantity` | int | |
| `NewQuantity` | int | |
| `ChangeSource` | varchar | enum: permit_completion, tdr_transfer, qa_correction, genealogy_restatement, assessor_update, manual |
| `Rationale` | varchar | free text |
| `EvidenceURL` | varchar | link to permit / TDR / source doc |
| `LinkedTdrTransactionID` | int FK (nullable) | exactly one of three Linked* must be non-null per CHECK |
| `LinkedParcelPermitBankedDevelopmentRightID` | int FK (nullable) | |
| `LinkedManualAdjustmentID` | int FK (nullable) | |
| `LinkedPermitID` | int FK (nullable) | |
| `RecordedBy` | varchar | |
| `RecordedAt` | datetime | |

**Refresh expectation**: weekly (matches the GIS sync cadence in
`target_schema.md` §"Loading strategy"). Per-parcel reads, so query latency
matters more than freshness.

### Realized vs proposed

**Realized data found in the analyst's deliverables (2026-04-30):**

- **`FINAL RES SUMMARY 2012 to 2025.xlsx` → sheet `Residential`** (42,500
  rows): wide format `(APN, Jurisdiction, 2012 Final, 2013 Final, …,
  2025 Final)`. Unpivot to long → 14 years × ~30K non-null rows ≈ the
  realized `ParcelExistingDevelopment` table for residential commodities.
- **`CA Changes breakdown.xlsx` → sheet `Sheet1`** (44,372 rows):
  per-APN change rationale, columns `(APN, 2023 Updates, 2023 Update
  Reason, 2023 Summary Reason, 2026 Changes, 2026 Detailed, 2026 Changes
  Reason, 2023 CA Report Change Reason, 2023 CA Report Change)`. This is
  the realized `ParcelDevelopmentChangeEvent` table.
- **`CA Changes breakdown.xlsx` → sheet `Sheet2`** (52 rows): controlled
  vocabulary of 9 correction categories - the realized `CorrectionCategory`
  enum:
  1. `No Update Required`
  2. `None - 2023 Update Correct`
  3. `Under-Correction in 2023; Unit(s) added`
  4. `Unit(s) Not Previously Counted - Added in 2026`
  5. `Over-Correction in 2023; Unit(s) Removed in 2026`
  6. `Unit(s) Incorrectly Removed in 2023 - Unit(s) Added Back in 2026`
  7. `2026 Additional Corrections to Previously Reported - Unit(s) Previously Not Counted`
  8. `Additional Unit(s) Removed in 2026`
  9. `Correction to Prior Analysis - Additional Unit(s) Removed in 2026`

Three things to add to the schema before implementation:

1. **`ParcelHistoryView` denormalizations.** The schema lists `ParcelID`
   and `CommodityID` as FKs; for the dashboard's lookup-by-APN flow we
   want `ParcelNumber` and `CommodityShortName` denormalized into the
   view. Same pattern as G1.4 / G2.x.
2. **Genealogy panel data.** The dashboard needs to render parent/child
   APNs. That comes from `ParcelGenealogyEventEnriched` (proposed, not
   in `ParcelHistoryView`). Document: should the dashboard query
   `ParcelGenealogyEventEnriched` directly, or should `ParcelHistoryView`
   include a `RelatedAPNs` array column / linked table?
   Recommend: dashboard queries `ParcelGenealogyEventEnriched` directly
   for the genealogy panel; `ParcelHistoryView` stays focused on
   `(Parcel × Year × Commodity)` quantity rows.
3. **`CorrectionCategory` enum + `ReportingCycleYear` column on
   `ParcelDevelopmentChangeEvent`.** Both required to load the analyst's CA
   Changes Sheet1 cleanly. The current `ChangeSource` value
   `qa_correction` is too coarse - needs a sub-categorization column
   sourced from the 9 Sheet2 values. `ReportingCycleYear` distinguishes
   the 2023 cycle from the 2026 cycle (and future cycles). Without it,
   a 2026 correction-of-a-2023-correction is indistinguishable from a
   fresh 2026 finding.

### Schema trace

| View / table column | Sourced from | Logic |
|---|---|---|
| `ParcelHistoryView.Quantity` | `ParcelExistingDevelopment.Quantity` for `(ParcelID, Year, CommodityID)` | direct row pivot from the parcel snapshot table |
| `ParcelHistoryView.ChangeCount` | `COUNT(*)` from `ParcelDevelopmentChangeEvent` for that `(Parcel, Year, Commodity)` triple | aggregation |
| `ParcelHistoryView.LastChangeSource`, `.LastChangeRationale` | `ParcelDevelopmentChangeEvent` ordered by `RecordedAt DESC` for that triple, take row 1 | window function |
| `ParcelDevelopmentChangeEvent.PreviousQuantity` / `NewQuantity` | Computed at change-event creation time from `ParcelExistingDevelopment` before/after | snapshot |
| `ParcelDevelopmentChangeEvent.LinkedTdrTransactionID` | `dbo.TdrTransaction.TdrTransactionID` (nullable) | when source is permit-completion or tdr-transfer |
| `ParcelDevelopmentChangeEvent.LinkedParcelPermitBankedDevelopmentRightID` | `dbo.ParcelPermitBankedDevelopmentRight.ParcelPermitBankedDevelopmentRightID` (nullable) | when source is banking |
| `ParcelDevelopmentChangeEvent.LinkedManualAdjustmentID` | `LedgerManualAdjustment.AdjustmentID` (nullable) | when source is qa_correction or manual |
| `ParcelDevelopmentChangeEvent.LinkedPermitID` | `dbo.ParcelPermit.ParcelPermitID` (nullable) | the permit that drove the change, regardless of source |
| `ParcelDevelopmentChangeEvent.EvidenceURL` | Constructed in ETL: e.g., `https://thresholds.laketahoeinfo.org/.../{TdrTransactionID}` or `https://parcels.laketahoeinfo.org/.../{ParcelNumber}` | string template per `ChangeSource` |

### Gaps for Trace 3 (issues to file)

- **G3.1 - `ParcelHistoryView` denormalizations.** Add `ParcelNumber` and
  `CommodityShortName` to the view. Same pattern as G1.4 / G2 carry-both.
- **G3.2 - Genealogy panel data flow.** Document whether the dashboard
  queries `ParcelGenealogyEventEnriched` directly or via a join. Recommend
  direct - keeps `ParcelHistoryView` focused on quantity rows.
- **G3.3 - `EvidenceURL` template per `ChangeSource`.** Define the URL
  patterns: permit_completion → permits site, tdr_transfer → thresholds
  site, etc. Belongs in ETL spec, not schema, but should be referenced
  from `target_schema.md` so it doesn't get lost.
- **G3.4 - Permission model.** Per `_archive/proposed_dashboards.md`, this becomes
  public eventually (G2 in cluster G). Confirm what subset of fields
  goes public (e.g., redact `RecordedBy` for the public view) before
  shipping the public-facing variant.
- **G3.5 - Project-level annotations** (NEW from the analyst's data). Each
  year's Summary sheet has a free-text "Major Completed Projects" column
  with project names (Sugar Pine = 69 units, LTCC Dorms = 41 units,
  Beach Club, Edgewood Casitas, Lakeside Inn Banking, etc.). Schema has
  no `Project` entity. **Action**: add a `Project` table
  `(ProjectID PK, ProjectName, ProjectType, JurisdictionID,
  CompletionYear, ParcelID nullable, AffordableUnits, MarketUnits, Notes)`
  and a join table `ProjectChangeEventLink` so each
  `ParcelDevelopmentChangeEvent` can reference 0..N projects. Enables a
  project-rollup view for the dashboard's narrative panel.
- **G3.6 - APN format normalization** (NEW from the analyst's data). Many parcels
  appear under both `015-331-04` and `015-331-004` formats - a leading-zero
  change happened mid-stream in 2018. This is **distinct** from
  `ParcelGenealogyEventEnriched`'s split/merge/rename concept.
  **Action**: add a canonicalization function `fn_canonical_apn(@apn)` in
  the load layer that strips leading zeros from the segment AND keeps a
  `RawAPN` column on `ParcelExistingDevelopment` and
  `ParcelDevelopmentChangeEvent` so we can trace back to source
  spreadsheet rows. Loader UPSERTs by canonical APN; raw value carried for
  audit.

---

## Trace 4 - Residential Additions by Source (A4, built)

> **Status of source code**: built today as
> [`html/residential-additions-by-source.html`](../html/residential-additions-by-source.html)
> with data inlined (Option A - see `_archive/proposed_dashboards.md` A4). Reverse-
> engineering this trace establishes how the dashboard re-binds when the
> view layer (`vCommodityLedger`) lands.

### Chart shape

Multi-line chart by year, x = 2013–2025, y = residential units added that
year, **5 lines** (one per source category): Allocations, Bonus Units,
Transfers, Conversions, Banked. Toggle: lines → stacked area → stacked %.
Annotation highlights the 2024–25 bonus-units inflection. Sidebar of
"Major Completed Projects" per year (Sugar Pine, LTCC Dorms, Beach Club,
etc.) anchors inflections in narrative.

### Where the analyst got this data (today)

The 5 categorical totals per year live in
[`from_analyst/FINAL RES SUMMARY 2012 to 2025.xlsx`](../from_analyst/FINAL%20RES%20SUMMARY%202012%20to%202025.xlsx)
**Summary sheet** under rows labeled *"Added Residential Units from
{Allocations, Bonus Units, Transfers, Conversions, Banked}"*. These are
**hand-aggregated by the analyst** from the per-APN data on the same workbook's
Residential sheet (42,500 rows). Cross-checked annually against the
public cumulative accounting report at
[`thresholds.laketahoeinfo.org/CumulativeAccounting/Index/{Year}`](https://thresholds.laketahoeinfo.org/CumulativeAccounting/Index/2023).

The "Major Completed Projects" narrative column is **also the analyst's** - manual
project tagging that doesn't currently exist in any structured store
(this is gap **G3.5** - `Project` entity proposal).

### View contract (target shape, once `vCommodityLedger` exists)

The dashboard wants one row per `(Year, Source)` with a count:

| Column | Type | Notes |
|---|---|---|
| `Year` | int | 2013–latest |
| `Source` | varchar | enum: `Allocations`, `BonusUnits`, `Transfers`, `Conversions`, `Banked` |
| `UnitsAdded` | int | residential units (SFRUU + MFRUU + ADU per Q1) added in that year via that source |

That's 5 sources × 13 years = 65 rows for the current data window.

### Schema trace - SQL against `vCommodityLedger`

Approximate query (assumes the schema additions for G2.8 land - Bonus
Units as a first-class movement type):

```sql
WITH residential_adds AS (
  SELECT
    YEAR(EntryDate)                        AS Year,
    CASE
      WHEN MovementType = 'ALLOCASSGN'                THEN 'Allocations'
      WHEN MovementType = 'BonusUnitAssigned'         THEN 'BonusUnits'    -- needs G2.8
      WHEN MovementType = 'TRF'                       THEN 'Transfers'
      WHEN MovementType IN ('CONV','CONVTRF')         THEN 'Conversions'
      WHEN MovementType = 'Unbanking'                 THEN 'Banked'        -- needs G2.6
    END                                    AS Source,
    Quantity
  FROM vCommodityLedger l
  JOIN dbo.Commodity c ON c.CommodityID = l.CommodityID
  WHERE c.CommodityShortName IN ('SFRUU','MFRUU')         -- residential only
    AND l.ToBucketType = 'Existing'                       -- only counts as an "add" when it lands as Existing
    AND l.Quantity > 0                                    -- only positive adds
)
SELECT Year, Source, SUM(Quantity) AS UnitsAdded
FROM residential_adds
WHERE Source IS NOT NULL
GROUP BY Year, Source
ORDER BY Year, Source;
```

The query **depends on**:
- **G2.8 (Bonus Units as movement type)** - the schema currently treats
  bonus units as a *bucket*, not a movement. Without a `BonusUnitAssigned`
  (or similar) `MovementType`, the analyst's "From Bonus Units" line can't be
  derived from `vCommodityLedger`. **A4 is the dashboard that makes G2.8
  unavoidable.**
- **G2.6 (`Unbanking` movement type)** - the analyst's "From Banked" line counts
  rebuild-from-banked events. The schema lists `Unbanking` as a planned
  `MovementType` but the build notebook doesn't yet synthesize it. Same
  unblock as G2.8 - needed for A4 to drop the spreadsheet dependency.

### LT Info endpoint candidate

No single LT Info JSON endpoint returns this exact 5-source breakdown.
The closest is **`GetTransactedAndBankedDevelopmentRights`** (5,186 records
per [ltinfo_services.json](./ltinfo_services.json)) - covers all
transacted and banked dev-rights events. Aggregating that response by
year and movement-type maps to the same Source enum above. Worth probing
whether that endpoint already exposes a `MovementType` (or equivalent)
field; if so, the dashboard can switch to a JSON fetch instead of CSV
and stop depending on the analyst's manual aggregation.

### Why this trace strengthens existing gaps

A4 doesn't surface *new* schema gaps. It strengthens two existing ones:

- **G2.6 (Unbanking)** - A4's "From Banked" line is a 171-unit total
  across 13 years. Real, non-trivial signal. Concrete reason to land
  `Unbanking` as a real movement type, not "TBD."
- **G2.8 (Bonus Units as movement type)** - 222 units / 14 percent of
  total additions, with the 2024–25 surge being the dashboard's
  headline finding. This is the single highest-impact schema clarification
  for the v1 dashboards shelf.

### Gaps for Trace 4 (no new gaps)

- ↗ **G2.6** (Unbanking) - strengthened, no change to action.
- ↗ **G2.8** (Bonus Units as movement type) - strengthened, no change to action.
- ↗ **G3.5** (Project entity) - strengthened by A4's project sidebar.
  Without a `Project` entity, the dashboard hardcodes the 10-year
  project list in HTML. With it, the sidebar reads from a query.

---

## Roll-up: gap delta against `target_schema.md`

After the analyst's April 2026 data: **18 gaps total - 4 resolved by the analyst's data,
14 still open** (10 original + 4 new). Sorted into three buckets:

### Add to schema

| ID | What | Where |
|---|---|---|
| G1.1 | Rule for `BonusUnitsRemaining` derivation | `target_schema.md` §`PoolDrawdownYearly` and §`CumulativeAccountingSnapshot` |
| ~~G1.2~~ | ~~`MaxRegionalCapacity` source~~ - ✅ **resolved**: model as `RegionalPlanCapacity(Commodity, PlanEra)` lookup; seed from the analyst's PPTX slide 8 | `target_schema.md` §"reference entities" |
| G1.4 / G2.x / G3.1 | Denormalize display labels (`JurisdictionAbbrev`, `CommodityShortName`, `PoolName`, `ParcelNumber`) into all 3 materialized views | `target_schema.md` §"materialized dashboard outputs" |
| ~~G2.1~~ | ~~`InitialCapacity` column on `PoolDrawdownYearly`~~ - ✅ **resolved**: seed from the analyst's `LT Info Pools Balances` sheet, flag `Source='kens_xlsx_april_2026'` | `target_schema.md` §`PoolDrawdownYearly` |
| ~~G2.2~~ | ~~CSLT sub-pool derivation~~ - ✅ **resolved**: model as 3 distinct `CommodityPoolID` rows | `target_schema.md` §"reference entities" + `dbo.CommodityPool` |
| **G2.7** | Unreleased pool category - model as pseudo-pool or add `ReleaseStatus` column on `dbo.CommodityPool` | `target_schema.md` §`PoolDrawdownYearly` + §"reference entities" |
| **G2.8** | Bonus Units as movement-type columns on `PoolDrawdownYearly` OR sibling `BonusUnitDrawdownYearly` view | `target_schema.md` §`PoolDrawdownYearly` |
| ~~G3.3.* `CorrectionCategory` + cycle-year column~~ | ✅ **resolved** - `QaCorrectionDetail` sidecar in `target_schema.md` carries `ReportingYear` (annual) + `SweepCampaign` + `CorrectionCategory` (9-value enum). Loader notebook still pending. | `target_schema.md` §"ERD - QA corrections sidecar" |
| G3.3 | `EvidenceURL` template registry per `ChangeSource` | new section in `target_schema.md` or in an ETL spec |
| **G3.5** | `Project` entity + `ProjectChangeEventLink` for the "Major Completed Projects" narrative | `target_schema.md` §"new core tables" |
| **G3.6 (partial)** | ✅ `RawAPN` audit column landed on `ParcelDevelopmentChangeEvent`; `fn_canonical_apn` still pending the loader notebook | `target_schema.md` §`ParcelDevelopmentChangeEvent` (column added); ETL spec for the function |
| ~~Q1 ADU modeling~~ | ✅ **resolved as option (b)** - `IsADU bit` flag on `dbo.ResidentialAllocation` + `dbo.ResidentialBonusUnit*`; not a third use type | `target_schema.md` Q1 |

### Clarify in schema

| ID | What | Where |
|---|---|---|
| G1.3 | Pool-keyed entries' jurisdiction fallthrough convention | `target_schema.md` §`CumulativeAccountingSnapshot` |
| G1.5 | Naming convention: drop `Quantity` suffix (or keep - pick one) | `target_schema.md` §`CumulativeAccountingSnapshot` |
| G2.3 | `Assigned` vs `Used` lifecycle distinction | `target_schema.md` §`PoolDrawdownYearly` and §"Mapping Corral TransactionType → MovementType" |
| G2.5 | Document: `PoolDrawdownYearly` returns historical only, projection is dashboard logic | `target_schema.md` §`PoolDrawdownYearly` |
| G2.6 | Either source `Unbanking` events or remove the column | `target_schema.md` §`PoolDrawdownYearly` |
| G3.2 | Document genealogy panel reads `ParcelGenealogyEventEnriched` directly | `target_schema.md` §`ParcelHistoryView` |
| G3.4 | Permission model for public variant of Parcel History Lookup | `target_schema.md` §`ParcelHistoryView` |

### Outside schema (dashboard / branding work)

| ID | What | Where |
|---|---|---|
| G2.4 | Replace Wong/Tol palette with TRPA chart sequence in `allocation_drawdown.html` | dashboard task, separate from schema |
| **G2.x TRPA Pool reconciliation** | Dashboard currently shows TRPA Pool = 144; the analyst says correct value is 154. Don't blindly carry LT Info pool values; require the analyst's manual corrections layer before display. | dashboard + ETL reconciliation, separate from schema |

### Triage suggestion

The over-generated database/ERD issues you mentioned should be sanity-checked
against this list. **An issue that doesn't ladder up to one of the 14 gaps
above is a candidate for closing**, since none of the 3 v1 dashboards needs
it. (Exceptions: cluster A–H dashboards in `_archive/proposed_dashboards.md` may
require things this trace doesn't surface - but that's a v2 conversation.)

---

## Open questions before issue creation

1. **CSLT sub-pool resolution.** ✅ Resolved by the analyst's data. Skip the
   `dbo.CommodityPool` query - the analyst's pool reports confirm 3 distinct
   sub-pools.
2. **Bonus pool roster.** Before filing G1.1, list the actual pools in
   `dbo.CommodityPool` whose names match the `classify_pool()`
   "bonus" heuristic. If the list is empty, the bucket may legitimately
   stay zero in v1 and G1.1 can defer to v2. (Now also relevant for
   G2.8 - the bonus pool inventory determines whether bonus units get
   their own sibling view.)
3. **Initial-capacity column on `dbo.CommodityPool`.** ✅ Resolved by
   the analyst's data. Skip the `SELECT TOP 1 *` - load initial capacities
   directly from the analyst's `LT Info Pools Balances` sheet, flag source.
4. **Unreleased pool modeling.** Before filing G2.7, decide: pseudo-pool
   row (`PoolName='Unreleased', JurisdictionID=NULL`) vs `ReleaseStatus`
   enum on `dbo.CommodityPool`. Talk through with the analyst - this changes
   the join shape of any "% remaining capacity" calculation.
5. **Bonus Units as separate view vs columns.** Before filing G2.8,
   decide between sibling `BonusUnitDrawdownYearly` view (cleaner; bonus
   pools have their own 2,000-unit cap) vs adding `BonusUnitReleased` /
   `BonusUnitUsed` columns to `PoolDrawdownYearly`. The 2024–2025
   bonus-unit surge (Sugar Pine + LTCC) makes this a near-term ask.
6. **`Project` entity granularity.** Before filing G3.5, scope:
   one `Project` per "Major Completed Projects" entry (~15-30 projects
   total since 2012)? Or finer-grain (one per construction phase)?
   the analyst's narrative tracks at the report-card level - start there.
7. **APN canonicalization edge cases.** Before filing G3.6, verify the
   leading-zero rule covers all observed APN-format issues. Spot-check
   for other patterns (dashes, county prefixes, alpha suffixes) by
   running uniqueness on `(canonical_apn, year)` against the analyst's
   Residential sheet.
