# `Transactions_Allocations_Details.xlsx` — what to keep, what to kill

> **Purpose**: response to the "just load Ken's XLSX as a table" proposal.
> **Audience**: anyone advocating that approach. Read before the target
> schema review.
> **TL;DR**: 1 column dies, 12 columns sync from their real upstream
> sources, 8 columns ETL into net-new tables in [target_schema.md](./target_schema.md),
> 1 column is derived. Don't load the XLSX as-is.


Column-by-column mapping of Ken's 22-column transactions spreadsheet
([data/raw_data/Transactions_Allocations_Details.xlsx](../data/raw_data/Transactions_Allocations_Details.xlsx),
1,853 rows) to the proposed v1 schema in [target_schema.md](./target_schema.md).

**Bottom line**: **do not** load the XLSX as a table in the new DB. It's a
denormalized report that merges three upstream systems plus stale snapshot
columns. Decompose it into the appropriate normalized tables instead.

## The three categories every column falls into

| # | Category | What to do |
|---|---|---|
| **1** | Already in LTinfo/Corral | Don't duplicate; sync from LTinfo JSON web services into the proposed bucket tables |
| **2** | In Accela permit workflow | Sync from Accela (or today via Corral's `AccelaCAPRecord` bridge) into `Permit` |
| **3** | Ken's unique contribution | Genuinely new data; ETL into specific new-schema tables on a one-time seed, with ongoing updates from Ken until we can automate the source |
| **X** | Stale / derived / junk | Kill it. Don't migrate. |

## Column-by-column decomposition

| # | XLSX column | Category | Destination in proposed schema | Notes |
|---|---|:---:|---|---|
| 1 | TransactionID | 1 | *derived*: `{LeadAgencyAbbreviation}-{TransactionTypeAbbreviation}-{TdrTransactionID}` | Synthetic key. Expose as a computed column on `CommodityLedgerEntry` or a view; don't store. |
| 2 | Transaction Type | 1 | `CommodityLedgerEntry.MovementType` (via TransactionType mapping) | 9 Corral `TransactionType` codes map to the 7 canonical `MovementType` values. |
| 3 | APN | 1 | `ParcelAllocation.ParcelID` → `Parcel.APN`, or `CommodityLedgerEntry.ReceivingParcelID` | Resolved through genealogy at load time. |
| 4 | Jurisdiction | 1 | `Parcel.JurisdictionID` → `Jurisdiction.Abbreviation` | Already in Corral; don't duplicate. |
| 5 | Development Right | 1 | `Commodity.DisplayName` via `ParcelAllocation.CommodityID` | XLSX adds jurisdiction suffix ("... - El Dorado County") — that's derivable from the pool, not a property of the commodity. |
| 6 | Allocation Number | 1 | `ParcelAllocation.AllocationNumber` | e.g. `EL-21-O-08`. Already issued by Corral. |
| 7 | Quantity | 1 | `ParcelAllocation.Quantity` or `CommodityLedgerEntry.Quantity` | Cast to int on load; XLSX has format inconsistencies. |
| 8 | Transaction Record ID | 2 | `Permit.AccelaID` (via `CrossSystemID` with `IDType='accela'`) | Examples: `ERSP2014-0375`. Primary bridge to Accela. |
| 9 | Transaction Created Date | 1 | `CommodityLedgerEntry.EntryDate` for the `AllocationRelease` entry | Derivable from `TdrTransactionStateHistory` minimum `TransitionDate`. |
| 10 | Transaction Acknowledged Date | 1 | `CommodityLedgerEntry.EntryDate` for the `AllocationUse` entry (or `ParcelAllocation.AssignedDate`) | Derivable from `TdrTransactionStateHistory`. |
| 11 | Development Type | 3 | `Permit.PermitType` (or new `PermitDevelopmentType` enum) | "Allocation", "Banked Unit", etc. High-level classification. |
| 12 | Detailed Development Type | 3 | `Permit.ProjectDescription` or `Permit.PermitSubType` | Free-text / semi-structured ("Multi-Family Condo Unit from Banked..."). Keep as text on `Permit`. |
| 13 | Status Jan 2026 | X | **drop** | Stale snapshot. Replaced by live `Permit.CompletionStatus` + `ParcelAllocation.Status` from LTinfo/Accela sync. |
| 14 | TRPA/MOU Project # | 3 | `CrossSystemID` with `IDType='trpa_mou'` | Can be multi-value ("ERSP2014-0375 plus Revisions") — parse on load. |
| 15 | TRPA Status | 3 | `ParcelAllocation.Status` | "Issued", "Finaled", "Completed" — maps to the 6-value `Status` enum. **Not** the same as `TdrTransaction.TransactionStateID` (which was "Proposed" for all the samples we checked — different concept). |
| 16 | TRPA Status Date | 3 | `ParcelAllocation.AssignedDate` or `ParcelAllocation.UsedDate` | Depends on which status the date belongs to. |
| 17 | Local Jurisdiction Project # | 2 | `Permit.PermitNumber` (and `CrossSystemID` with `IDType='local_jurisdiction'` if distinct) | e.g. `339626`. |
| 18 | Local Status | 2 | `Permit.CompletionStatus` | "Issued", "Finaled", "Expired". Lives with the permit, not the allocation. |
| 19 | Local Status Date | 2 | `Permit.FinalInspectionDate` / `Permit.IssuedDate` etc. | Depends on which status. |
| 20 | Year Built | 3 | `Permit.YearBuilt` | **Ken's unique contribution.** From county assessor; not in Corral or LTinfo. |
| 21 | PM Year Built | 3 | `Permit.PMYearBuilt` (new column) or `Permit.InternalYearBuilt` | "Property Manager" year-built — Ken's internal tracking, may differ from assessor. |
| 22 | Notes | 3 | `Permit.Notes` or `ParcelDevelopmentChangeEvent.Rationale` | Free text; route to whichever entity the note is really about. |

## Counts by category

| Category | # cols | Action |
|---|---:|---|
| 1 — already in LTinfo/Corral | 8 | Sync, don't duplicate |
| 2 — in Accela permit workflow | 4 | Sync from Accela / Corral bridge |
| 3 — Ken's unique contribution | 8 | ETL into new-schema tables |
| X — stale / junk | 1 | Drop (`Status Jan 2026`) |
| *Derived from other columns* | 1 | (TransactionID is synthetic) |

## Why "just load the XLSX" is the wrong answer

1. **Embeds format inconsistencies as data.** "1" vs `1.0`, date strings with
   `00:00:00` suffixes, multi-valued cells like `"ERSP2014-0375 plus Revisions"`.
   Loading as-is means the new DB carries these forever.
2. **No FKs, no integrity.** APN → Parcel, TransactionID → TdrTransaction,
   AccelaID → Permit — all would be string columns with no referential
   constraints. You can't trust any join.
3. **Stale snapshot columns are load-bearing.** `Status Jan 2026` is a point-in-time
   column that becomes wrong the moment it's loaded. Perpetuating that pattern
   means adding a `Status Feb 2026`, `Status Mar 2026`, ... columns every month.
4. **Denormalization hides the business model.** The XLSX collapses allocation ↔
   transaction ↔ permit ↔ parcel ↔ commodity into one wide row. The TRPA
   Cumulative Accounting framework is explicitly a **bucket model**; forcing
   it into a single flat table loses the bucket structure that makes the
   whole accounting identity work.
5. **Duplicates sources of truth.** 12 of the 22 columns are already in LTinfo
   or Accela. Loading them copies data that goes stale as soon as the source
   updates. Worse, the loaded copy can silently diverge (and *has* diverged,
   per the 22% of rows that don't join on TransactionID in
   [validation_findings.md](./validation_findings.md)).

## What to load instead

**One-time seed (Ken's unique contribution, category 3 columns only)**:

- UPSERT into `Permit` keyed on `AccelaID`: `PermitType`, `ProjectDescription`,
  `YearBuilt`, `PMYearBuilt`, `CompletionStatus` (derived from TRPA Status +
  Local Status merge), `Notes`.
- INSERT into `CrossSystemID` for each `TRPA/MOU Project #` with
  `IDType='trpa_mou'`.

**Ongoing (everything else)**:

- Pull from LTinfo `GetTransactedAndBankedDevelopmentRights` → fan out into
  `ParcelAllocation` + `CommodityLedgerEntry` (covers categories 1).
- Pull from Accela (via Corral bridge for now, direct API later) →
  `Permit.PermitNumber`, `CompletionStatus`, `FinalInspectionDate`, etc.
  (covers category 2).

**Kill list**:

- `Status Jan 2026` column — not loaded at all. Replaced by live `ParcelAllocation.Status`.
- Synthetic `TransactionID` — not stored; derive on demand in views.

## How to handle the handoff from Ken

Until county-assessor + TRPA-MOU project tracking is automated, Ken's XLSX
stays as the manual source for category-3 columns. Options:

1. **Replace the XLSX** with a simple form-entry app against the new DB.
   Ken types `YearBuilt` once; no more reconciling spreadsheet copies.
2. **Keep the XLSX** as Ken's authoring surface; add a scheduled ETL
   (`python erd/load_ken_transactions.py`) that reads the XLSX, upserts the
   category-3 columns, and logs what changed.

Option 2 is cheaper short-term and zero-risk to Ken's workflow. Option 1
is the v2+ target.

## Summary for your coworker

The XLSX is valuable. The **data in it** about Year Built and TRPA/MOU
Project # is authoritative nowhere else. But loading the table as-is means
importing the denormalization, the stale snapshot columns, and the
duplicate-source problem. The right move is to decompose it: 8 columns
become the seed for 3 new-schema tables, 12 columns sync from their real
upstream sources, 1 column gets killed. The TRPA Cumulative Accounting
framework requires a bucket model — a flat transactions table can't
express it.
