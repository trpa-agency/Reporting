# `2025 Transactions and Allocations Details.xlsx` - column mapping

Column-by-column map of the 22-column transactions spreadsheet
([`data/raw_data/2025 Transactions and Allocations Details.xlsx`](../data/raw_data/2025%20Transactions%20and%20Allocations%20Details.xlsx),
2,030 rows) to the proposed schema in [target_schema.md](./target_schema.md).

Purpose: show where each XLSX column belongs in the v1 schema so the
spreadsheet can keep functioning as an authoring surface while
downstream reports read from normalized tables.

## Three categories

| # | Category | What happens at ETL time |
|---|---|---|
| **1** | Already in Corral / LTinfo | Sync from LTinfo JSON web services into the proposed bucket tables |
| **2** | In the Accela permit workflow | Sync from Accela (or today via Corral's `AccelaCAPRecord` bridge) into `PermitCompletion` |
| **3** | XLSX is the authoritative source | ETL into specific new-schema tables on a one-time seed, with ongoing updates from the XLSX until the source system is automated |
| **X** | Derived or point-in-time snapshot | Not copied into the schema - computed on demand instead |

## Column-by-column

| # | XLSX column | Category | Destination in proposed schema | Notes |
|---|---|:---:|---|---|
| 1 | TransactionID | 1 | *derived*: `{LeadAgencyAbbreviation}-{TransactionTypeAbbreviation}-{TdrTransactionID}` | Synthetic key. Exposed as a computed column on `LedgerEntry` or a view; not stored. |
| 2 | Transaction Type | 1 | `LedgerEntry.MovementType` (via TransactionType mapping) | 9 Corral `TransactionType` codes map to the 10 canonical `MovementType` values in the ledger. |
| 3 | APN | 1 | `LedgerEntry.ParcelNumber` via `dbo.Parcel` | Resolved through genealogy at load time. |
| 4 | Jurisdiction | 1 | `Parcel.JurisdictionID` → `Jurisdiction.Abbreviation` | Already in Corral. |
| 5 | Development Right | 1 | `Commodity.CommodityDisplayName` via the ledger's `CommodityShortName` | XLSX adds a jurisdiction suffix ("... - El Dorado County") - derivable from the pool. |
| 6 | Allocation Number | 3 | `LedgerEntryAnnotation.AllocationNumber` | e.g. `EL-21-O-08`. Issued by Corral upstream; kept on the annotation for traceability. |
| 7 | Quantity | 1 | `LedgerEntry.Quantity` | Signed value in the ledger; XLSX stores the absolute value + a separate debit flag. |
| 8 | Transaction Record ID | 2 | `CrossSystemID` with `IDType='accela'` | Examples: `ERSP2014-0375`. Primary bridge to Accela. |
| 9 | Transaction Created Date | 3 | `LedgerEntryAnnotation.TransactionCreatedDate` | Earliest `TdrTransactionStateHistory` date where Corral populates it; XLSX is authoritative where Corral is empty. |
| 10 | Transaction Acknowledged Date | 3 | `LedgerEntryAnnotation.TransactionAcknowledgedDate` | Same - XLSX fills in where Corral's state history is sparse. |
| 11 | Development Type | 3 | `LedgerEntryAnnotation.DevelopmentType` | "Allocation", "Banked Unit", etc. - high-level classification not in Corral. |
| 12 | Detailed Development Type | 3 | `LedgerEntryAnnotation.DetailedDevelopmentType` | Free text / semi-structured ("Multi-Family Condo Unit from Banked..."). Kept as-is; parsed downstream if needed. |
| 13 | Status Jan 2026 | X | *not copied* | Point-in-time snapshot replaced by live `CompletionStatus` from the LTinfo / Accela sync. |
| 14 | TRPA/MOU Project # | 3 | `CrossSystemID` with `IDType='trpa_mou'` | Can be multi-value ("ERSP2014-0375 plus Revisions") - parsed on load. |
| 15 | TRPA Status | 3 | `PermitCompletion.CompletionStatusEnriched` | "Issued", "Finaled", "Completed" - permit workflow state, not TDR-transaction state. |
| 16 | TRPA Status Date | 3 | `PermitCompletion.LastStatusDate` | Date accompanying the status above. |
| 17 | Local Jurisdiction Project # | 2 | `ParcelPermit.PermitNumber` (+ `CrossSystemID` with `IDType='local_jurisdiction'`) | e.g. `339626`. |
| 18 | Local Status | 2 | `PermitCompletion.LocalStatus` | "Issued", "Finaled", "Expired" from the local permit workflow. |
| 19 | Local Status Date | 2 | `PermitCompletion.LocalStatusDate` | |
| 20 | Year Built | 3 | `LedgerEntryAnnotation.YearBuilt` | **XLSX-authoritative** - sourced from county assessor; not in Corral or LTinfo today. |
| 21 | PM Year Built | 3 | `LedgerEntryAnnotation.PmYearBuilt` | Internal year-built that may differ from the assessor's value. |
| 22 | Notes | 3 | `LedgerEntryAnnotation.SupplementalNotes` | Free text; routed to the annotation on the matching ledger entry. |

## Counts by category

| Category | # cols | ETL action |
|---|---:|---|
| 1 - Already in Corral / LTinfo | 6 | Sync from source; don't copy into the ledger itself |
| 2 - In the Accela permit workflow | 4 | Sync from Accela / Corral bridge |
| 3 - XLSX-authoritative | 10 | Seed + ongoing updates into `LedgerEntryAnnotation` + `CrossSystemID` |
| X - Derived / snapshot | 1 | Replaced by live-status join (`Status Jan 2026`) |
| *Synthetic* | 1 | `TransactionID` - computed on demand |

## How the XLSX and the new schema coexist

- The **XLSX stays** as the authoring surface for the 10 category-3 columns
  until county-assessor and TRPA/MOU project tracking can be automated at
  source. No change to the daily workflow.
- The **ledger reads** the XLSX on a scheduled cadence (nightly or manual
  refresh) and upserts the category-3 columns into
  `LedgerEntryAnnotation`. Every update is keyed on `(SourceFile,
  SourceRowNumber)` so re-loads are idempotent.
- **Downstream reports** (cumulative accounting, allocation drawdown,
  parcel history) read from the ledger views, not the XLSX directly.
  This means the XLSX's local quirks (trailing spaces, format variance,
  multi-value cells) don't propagate into published numbers - they're
  normalized at load time.

## What this replaces

The v0 prototype of `LedgerEntryAnnotation` is already shipping as
[`notebooks/02_build_transition_table.ipynb`](../notebooks/02_build_transition_table.ipynb)
writing to `notebooks/out/corral_transition_table.csv`. The ledger
prototype in [`ledger_prototype/build_ledger.ipynb`](../ledger_prototype/build_ledger.ipynb)
reads that CSV as input. When the SDE DB lands, both move into SQL
tables with the same column shape.
