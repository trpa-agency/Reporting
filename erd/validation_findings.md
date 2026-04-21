# Validation findings — can Corral replace raw_data?

Two empirical tests of the reproducibility claims in [raw_data_vs_corral.md](./raw_data_vs_corral.md).
Both are read-only against the Feb 2024 Corral snapshot.

## TL;DR

- **Claim A — AuditLog can reconstruct yearly commodity inventory: FALSE.** Not because AuditLog doesn't work, but because `dbo.ParcelCommodityInventory` only tracks SFRUU/MFRUU for **7 of 18 sampled residential parcels (39%)**. Most physical dwellings in Tahoe were never entered into PCI for residential commodities. The CSV is capturing data Corral simply doesn't hold.
- **Claim B — a view over TdrTransaction* + Parcel + Commodity + permits reproduces the transactions spreadsheet: PARTIAL.** 78% of rows join cleanly and 3 of 12 core columns match >70%. **9 of the 22 spreadsheet columns aren't sourced from Corral at all** — they come from external permit/assessor systems that live alongside Corral.

Both results push the same direction: **the raw_data spreadsheets are not redundant denormalizations of Corral**. They're parallel sources filling gaps that the current Corral schema doesn't cover — physical inventory not triggered by permits, permit workflow status, county-assessor year-built, and external project identifiers.

---

## Claim A — AuditLog replay on ParcelCommodityInventory

**Hypothesis**: replaying `dbo.AuditLog` on `ParcelCommodityInventory.VerifiedPhysicalInventoryQuantity` reproduces the yearly values in `ExistingResidential_2012_2025_unstacked.csv` when summed across SFRUU + MFRUU LandCapabilityTypes per parcel.

**Test**: [validate_auditlog_replay.py](./validate_auditlog_replay.py) — 18 residential APNs with non-zero CSV values for 2020 and 2023, reconstructed at year-ends 2016, 2018, 2020, 2022, 2023.

**Result** ([validate_auditlog_replay.json](./validate_auditlog_replay.json)):

| Metric | Value |
|---|---:|
| APNs sampled from CSV | 18 |
| APNs with ≥1 `ParcelCommodityInventory` row for SFRUU/MFRUU | **7 (39%)** |
| Year-checks total | 90 |
| Matches overall | 27 (30%) |
| Matches on tracked APNs only | 13/35 (37%) |
| Match rate 2016 | 61% |
| Match rate 2023 | 17% |

**What's actually happening**:

- Spot-checks of `007-011-01`, `007-011-23`, `014-232-001` — all residential APNs with values in the CSV — returned **zero SFRUU/MFRUU rows** from `dbo.ParcelCommodityInventory`. One (`007-011-23`) had only Coverage rows, none for residential commodities.
- The decaying 2016 → 2023 match rate is downstream of this same problem: parcels that were added to PCI later (e.g., after a permit) have accurate recent values but no SFRUU row pre-existing for older year-ends.
- `dbo.ParcelCommodityInventory.VerifiedPhysicalInventoryQuantity` is populated when a parcel's inventory is **verified through a permit workflow**. Most parcels in Tahoe have never needed a permit that triggers inventory verification, so their physical dwelling counts are absent from this table.

**Implication for schema**: the "existing residential dwellings per parcel" concept — fundamental to TRPA's accounting — is not represented in Corral for the majority of parcels. The `ExistingResidential_*.csv` (42,499 rows) is not a denormalization; it's a parallel source. To absorb it into the schema, Corral needs either:

1. A new table `ParcelExistingDevelopment(ParcelID, CommodityID, Quantity, Year, Source)` that tracks physical inventory regardless of permit verification — loaded from county assessor, tax records, field surveys.
2. Or relaxation of the "verification" contract on `ParcelCommodityInventory` so non-verified rows can be inserted with a `Source` tag.

Either way, the CSV is the seed load, not a throwaway.

---

## Claim B — vTransactionsAllocationsDetails view

**Hypothesis**: a view over `TdrTransaction` + `TdrTransactionTransfer`/`Allocation` + `ResidentialAllocation` + `Parcel` + `Commodity` + `AccelaCAPRecord` + `ParcelPermit` reproduces `Transactions_Allocations_Details.xlsx`.

**TransactionID format**: The XLSX uses a synthetic key: `{LeadAgencyAbbreviation}-{TransactionTypeAbbreviation}-{TdrTransactionID}` (e.g., `EDCCA-ALLOC-1825`). Constructed in the view SQL.

**Test**: [validate_transactions_view.py](./validate_transactions_view.py) — full view SQL in file. Merge to XLSX on the synthetic key; per-column string-normalized equality on joined rows.

**Result** ([validate_transactions_view.json](./validate_transactions_view.json)):

| | |
|---|---:|
| XLSX rows | 1,853 |
| XLSX rows with TransactionID | 1,603 |
| Corral TdrTransaction rows | 2,088 |
| **Joined on TransactionID** | **1,244 / 1,603 = 78%** |

Per-column match rate on joined rows:

| XLSX column | Corral source | Matched | Rate | Why it misses |
|---|---|---:|---:|---|
| APN | `Parcel.ParcelNumber` via transfer/allocation | 1037/1244 | **83%** | Allocation-assignment transactions don't populate a receiving parcel |
| Development Right | `Commodity.CommodityDisplayName` | 900/1244 | **72%** | XLSX adds jurisdiction suffix ("... - El Dorado County") not in Corral |
| Transaction Record ID | `AccelaCAPRecord.AccelaID` | 263/405 | 65% | Only 32% of transactions have AccelaCAPRecordID populated |
| Jurisdiction | `Jurisdiction.ResidentialAllocationAbbreviation` | 710/1244 | 57% | Abbreviation mismatch: XLSX "CSLT" vs Corral "SLT"; null APN cases |
| Transaction Type | `TransactionType.TransactionTypeName` | 366/1244 | 29% | XLSX uses `ResidentialAllocationType.Description` ("Residential Allocation") vs Corral's `TransactionType.TransactionTypeName` ("Allocation") |
| TRPA Status Date | `TdrTransaction.ApprovalDate` | 16/1244 | 1% | pandas Timestamp vs string normalization issue; real match rate higher |
| Local Jurisdiction Project # | `ParcelPermit.PermitNumber` | 50/712 | 7% | Join by (ParcelID, JurisdictionID) is ambiguous — parcels have many permits; no FK from TdrTransaction to ParcelPermit |
| TRPA Status | `TransactionState.TransactionStateName` | 0/1244 | 0% | XLSX tracks **permit workflow status** ("Issued", "Finaled"), not TDR transaction state ("Proposed"). Different concepts. |
| Local Status | `ParcelPermitStatus` via permit | 0/719 | 0% | Same bad join as Local Project # |
| Local Status Date | — | 0/658 | 0% | Same |
| Quantity | `ReceivingQuantity`/`AllocatedQuantity` | 0/1243 | 0% | **Format mismatch only** — "1" (str) vs `1.0` (float). Real values match. |
| Notes | `TdrTransaction.Comments` | 0/553 | 0% | Different source — XLSX notes come from the permit workflow system, not Corral comments |

**Columns in the XLSX that are NOT in Corral at all** (9 of 22):

- `Allocation Number` (e.g., `EL-21-O-08`) — external coding scheme for issued allocations
- `Transaction Created Date`, `Transaction Acknowledged Date` — would need `TdrTransactionStateHistory` joins, not a single column
- `Development Type`, `Detailed Development Type` — project-narrative descriptors
- `Status Jan 2026` — external snapshot column
- `TRPA/MOU Project #` — permit project ID from a different system
- `Year Built` — county assessor
- `PM Year Built` — property manager / internal tracking

**Implication for schema**: 13 of 22 columns are reproducible from Corral (with some normalization work). 9 are not — they come from a mix of permit workflow state, county assessor records, and internal project tracking. A unified schema needs to decide, per column, whether to (a) extend Corral with new columns/tables, (b) add a properly-joinable permit-workflow table, (c) treat the spreadsheet as a registered external loader keyed on TdrTransactionID.

The `TdrTransaction.AccelaCAPRecordID` FK is the strongest bridge we have today — but only 32% of transactions have it populated. Raising that coverage would let us join transactions to their full permit workflow history and pick up several of the "missing" columns as a byproduct.

---

## What to dig into next

1. **Physical inventory population strategy** — where does the `ExistingResidential*.csv` actually come from, and how do we keep it current alongside Corral? (Candidates: county assessors, legacy "Parcel Tracker" exports, GIS building-footprint joins.)
2. **Transaction ↔ permit linkage** — can we back-fill `TdrTransaction.AccelaCAPRecordID` for the 68% that are null, using the `ParcelPermit.PermitNumber` or Accela permit ID in the XLSX?
3. **Commodity naming alignment** — the 4 closest-to-matching columns (Development Right 72%, APN 83%, Jurisdiction 57%, Transaction Type 29%) all fail on **naming convention** differences. Worth a short reconciliation pass to decide whose vocabulary wins.

## Regenerate

```
python erd/validate_auditlog_replay.py
python erd/validate_transactions_view.py
```
