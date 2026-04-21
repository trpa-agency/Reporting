# raw_data/ vs. Corral — gap analysis

> **See [target_schema.md](./target_schema.md) for how the proposed new
> schema closes each gap below.** This doc is the diagnostic;
> `target_schema.md` is the treatment plan, anchored on the TRPA Cumulative
> Accounting framework (see
> [.claude/skills/trpa-cumulative-accounting/SKILL.md](../.claude/skills/trpa-cumulative-accounting/SKILL.md)).

> **Context correction**: Corral IS the LTinfo backend. The `sql24/Corral`
> snapshot is a Feb-2024 backup; live data flows through LTinfo JSON web
> services. The findings below about staleness reflect the backup, not the
> live system.

Compares the 23 CSV/XLSX files under [`data/raw_data/`](../data/raw_data/) against
the `Corral` SQL Server schema we reflected into [corral_schema.json](./corral_schema.json).
Goal: understand what's in Corral, what's missing, and where a view could mimic
what we're maintaining by hand in spreadsheets.

## TL;DR — three key findings

1. **Corral is frozen at 2024-02-29.** Max `AuditLogDate`, max `ParcelCommodityInventory.LastUpdateDate`, max `TdrTransaction.ApprovalDate`, max `ResidentialAllocation.IssuanceYear`, max `AccelaCAPRecord.FileDate` — all land on or before `2024-02-29`. Today is 2026-04-20. This backup is ~2 years stale. Any mimicked view will be accurate only through Feb 2024; the raw_data files carry 2024–2026 updates that Corral does not.

2. **Corral stores current state + a column-level audit log, not yearly snapshots.** `dbo.AuditLog` has 8.3M rows, including 96K on `ParcelCommodityInventory`. The per-year wide CSVs (`ExistingResidential_2012_2025_unstacked.csv`, `TouristUnits_2012to2025.csv`, `CommercialFloorArea_2012to2025.csv`) don't exist as tables — they're denormalized views. **Most yearly values are reconstructable by replaying `AuditLog` on `ParcelCommodityInventory.VerifiedPhysicalInventoryQuantity`**, but only back to 2016 (AuditLog's earliest entry). 2012–2015 values must come from outside Corral.

3. **`dbo.ParcelGenealogy` is a skeleton.** Just 3 columns: `ParcelGenealogyID`, `ParentParcelID`, `ChildParcelID`. No `change_year`, no `change_type`, no `is_primary`, no source attribution, no `overlap_pct`. The repo's `apn_genealogy_tahoe.csv` has 23 columns and 42,159 rows spanning 5 derivation sources (manual notes, Accela, LTinfo, spatial overlap, consolidated). **Corral genealogy is missing most of the semantic metadata that drives the ETL's APN substitution logic.**

## Per-file comparison

Categories: ✅ reproducible from Corral as a view · ⚠️ partial (needs augmentation) · ❌ missing (needs new table or external feed) · 🔎 diagnostic (should not need replication)

| File | Rows | Category | Nearest Corral equivalent | Gap |
|---|---:|:---:|---|---|
| `ExistingResidential_2012_2025_unstacked.csv` | 42,499 | ⚠️ | `ParcelCommodityInventory` (current) + `AuditLog` (2016+) | No 2012–2015 history in Corral; 2024-03+ missing (stale) |
| `TouristUnits_2012to2025.csv` | 378 | ⚠️ | same, filtered on TAU commodity | same |
| `CommercialFloorArea_2012to2025.csv` | 1,500 | ⚠️ | same, filtered on CFA commodity | same |
| `fc_native_residential_units.csv` | 339,687 | 🔎 | — | ArcGIS feature-class derived; QA input, not authoritative |
| `apn_genealogy_tahoe.csv` (consolidated) | 42,159 | ❌ | `ParcelGenealogy` (2,405 rows) | Missing change_year, change_type, source, overlap_pct, confidence. 17× more rows than Corral holds. |
| `apn_genealogy_master.csv` | 1,968 | ❌ | — | Manual analyst-reviewed; no Corral table for free-text genealogy notes |
| `apn_genealogy_accela.csv` | 37,446 | ⚠️ | `AccelaCAPRecord` + `ParcelAccelaCAPRecord` | Accela parent/child APN transitions not surfaced as direct relationships in Corral |
| `apn_genealogy_ltinfo.csv` | 3,533 | ❌ | — | Derived from external LTinfo API; not in Corral |
| `apn_genealogy_spatial.csv` | 737 | ❌ | — | Derived from GIS geometry overlap; requires ArcGIS, not in Corral |
| `parcel_geneology_notes.csv` | 689 | ⚠️ | `ParcelNote` (1,927 rows), `Parcel.ParcelPublicNotes` | Free-text notes; likely overlaps `ParcelNote` but not the same set |
| `parcel_geneology_notes_2.csv` | 75,543 | ⚠️ | same | Much larger than Corral holds; probable external export |
| `Accela_Genealogy_March2026.xlsx` | ? | ❌ | — | Dated Mar 2026 — post-Corral-snapshot; source of truth for 2024–2026 |
| `Accela genealogy from addresses.xlsx` | ? | ❌ | — | Address-based matching, derivation workflow |
| `LTinfo_Parcel_Genealogy.xlsx` | ? | ❌ | — | External LTinfo export |
| `Parcel Genealogy Lookups KK.xlsx` | ? | 🔎 | — | Analyst worksheet ("Fill IN" column) |
| `Transactions_Allocations_Details.xlsx` | ? | ✅ | `TdrTransaction*` + `ResidentialAllocation` + `Parcel` + `Commodity` | Reproducible as a view; some columns (`Status Jan 2026`, `Year Built`, `PM Year Built`) are external status snapshots |
| `FINAL-2026-Cumulative-Accounting_ALL_04032026.xlsx` | 4 sheets | ⚠️ | — | Derived report (Summary / Residential / TAU / CFA); not a raw source |
| `apn_fc_only.csv`, `apn_service_only.csv` | 2,928 / 1,993 | 🔎 | — | QA diff files (FC vs ArcGIS service), not data of record |
| `apns_to_investigate.csv`, `change_year_candidates.csv`, `qa_lost_vs_new_genealogy.csv`, `unknown_apns_diagnosis.csv` | various | 🔎 | — | Analyst workbench artifacts; not data of record |

## Deep dive: where views could work

### A. Historical yearly commodity inventory (the three `*_20{12,12}to2025` CSVs)

**Structure of the CSVs**: APN × Year → quantity. Three files = three commodities: RU (Residential Units), TAU (Tourist Accommodation Units), CFA (Commercial Floor Area sqft).

**Corral model**: `ParcelCommodityInventory` keyed on `(ParcelID, LandCapabilityTypeID)` — `LandCapabilityType` rolls up to `Commodity`. One row per parcel-LCT pair holds the **current** `VerifiedPhysicalInventoryQuantity`, not a per-year history. The history only exists in `AuditLog`.

**View sketch — inventory snapshot at end of year N**:

```sql
-- vParcelCommodityInventoryAsOf(@asof datetime)
-- replays AuditLog on VerifiedPhysicalInventoryQuantity to reconstruct inventory on any date.
WITH ordered_changes AS (
  SELECT
    al.RecordID         AS ParcelCommodityInventoryID,
    al.NewValue,
    al.AuditLogDate,
    ROW_NUMBER() OVER (PARTITION BY al.RecordID ORDER BY al.AuditLogDate DESC) AS rn
  FROM dbo.AuditLog al
  WHERE al.TableName = 'ParcelCommodityInventory'
    AND al.ColumnName = 'VerifiedPhysicalInventoryQuantity'
    AND al.AuditLogDate <= @asof
),
last_change_before AS (
  SELECT ParcelCommodityInventoryID, NewValue, AuditLogDate
  FROM ordered_changes WHERE rn = 1
)
SELECT
  p.ParcelNumber                    AS APN,
  YEAR(@asof)                       AS Year,
  c.CommodityShortName              AS Commodity,   -- 'RU','TAU','CFA'
  TRY_CAST(COALESCE(lcb.NewValue,
                    CAST(pci.VerifiedPhysicalInventoryQuantity AS varchar)) AS int) AS Quantity
FROM dbo.ParcelCommodityInventory pci
JOIN dbo.Parcel            p   ON pci.ParcelID            = p.ParcelID
JOIN dbo.LandCapabilityType lct ON pci.LandCapabilityTypeID = lct.LandCapabilityTypeID
JOIN dbo.Commodity          c  ON lct.CommodityID         = c.CommodityID
LEFT JOIN last_change_before lcb ON pci.ParcelCommodityInventoryID = lcb.ParcelCommodityInventoryID;
```

A table-valued function wrapping this, called once per year 2016–2024, reproduces the interior columns of the three CSVs. **2012–2015 columns cannot be reproduced from Corral alone** — AuditLog's earliest entry is 2014-06-01 and the first `VerifiedPhysicalInventoryQuantity` audit is 2016-12-19. That pre-2016 history is owned by the spreadsheet, which was hand-compiled from legacy parcel-tracker data.

**Recommendation**: Build `vParcelCommodityYearlyInventory` as `APN × Year × Commodity → Quantity` using the recipe above for 2016–current; import the 2012–2015 columns from the existing CSVs into a new supplemental table `ParcelCommodityInventoryHistoricalBaseline(ParcelID, Year, CommodityID, Quantity, Source)`; UNION them in the view. Populate `Source = 'legacy_csv_2012_2015'` so the provenance is visible.

### B. Genealogy

**Corral model**: `dbo.ParcelGenealogy` holds 2,405 (parent, child) pairs and nothing else. No timing, no typing, no source.

**Repo model** (`apn_genealogy_tahoe.csv`, 42,159 rows, 23 columns): `event_id`, `apn_old`, `apn_new`, `apn_old_raw`, `apn_new_raw`, `county`, `is_el_dorado`, `change_year`, `change_date`, `event_type`, `n_parents`, `n_children`, `is_primary`, `overlap_pct`, `source`, `source_priority`, `confidence`, `verified`, `notes`, `added_date`, `in_fc_old`, `in_fc_new`, `lost_apn`.

**The gap is semantic, not structural** — the repo captures the *event* of a parcel change with full metadata; Corral captures only the static parent-child link. Views can't conjure the missing columns.

**Recommendation — extend, don't view**: add columns (or a sibling table) to Corral's `ParcelGenealogy`:

```sql
-- Additive migration; existing FKs preserved.
ALTER TABLE dbo.ParcelGenealogy ADD
    ChangeYear          int          NULL,
    ChangeDate          date         NULL,
    EventType           varchar(20)  NULL,   -- 'split' | 'merge' | 'rename' | 'unknown'
    IsPrimary           bit          NULL,
    OverlapPct          decimal(5,2) NULL,
    SourcePriority      int          NULL,
    Source              varchar(30)  NULL,   -- 'manual' | 'accela' | 'ltinfo' | 'spatial'
    Confidence          varchar(10)  NULL,
    Notes               varchar(1000) NULL;
```

Then a loader takes `apn_genealogy_tahoe.csv` and upserts into `ParcelGenealogy`, creating new (parent, child) rows where they don't exist and back-filling metadata where they do. Once loaded, the repo CSVs for genealogy become regenerable from Corral with a simple view:

```sql
CREATE VIEW dbo.vParcelGenealogyDetailed AS
SELECT
  pp.ParcelNumber AS apn_old,
  cp.ParcelNumber AS apn_new,
  g.ChangeYear    AS change_year,
  g.ChangeDate    AS change_date,
  g.EventType     AS event_type,
  g.IsPrimary     AS is_primary,
  g.OverlapPct    AS overlap_pct,
  g.Source        AS source,
  g.Confidence    AS confidence,
  g.Notes         AS notes
FROM dbo.ParcelGenealogy g
JOIN dbo.Parcel pp ON g.ParentParcelID = pp.ParcelID
JOIN dbo.Parcel cp ON g.ChildParcelID  = cp.ParcelID;
```

**What Corral still can't own**:
- `apn_genealogy_spatial.csv` — derived from GIS geometry overlap. Source = ArcGIS; belongs in a GIS workflow that writes *back* to `ParcelGenealogy` with `Source='spatial'`.
- El Dorado APN format history (2-digit ↔ 3-digit suffix). `dbo.Parcel` holds only the current form of `ParcelNumber`. Add `AlternateParcelNumber` or a `ParcelNumberAlias(ParcelID, ParcelNumber, ValidFrom, ValidTo)` table.

### C. Transactions & allocations

`Transactions_Allocations_Details.xlsx` — 22 columns. Most map cleanly:

| Spreadsheet column | Corral source |
|---|---|
| TransactionID | `TdrTransaction.TdrTransactionID` |
| Transaction Type | `TdrTransaction.TransactionTypeAbbreviation` / `TransactionTypeCommodity` |
| APN | `Parcel.ParcelNumber` via `TdrTransactionTransfer.ReceivingParcelID` / `SendingParcelID` |
| Jurisdiction | `Jurisdiction` (via parcel) |
| Development Right | `Commodity.CommodityShortName` |
| Allocation Number | `ResidentialAllocation.AllocationSequence` + `IssuanceYear` |
| Quantity | `TdrTransactionTransfer.ReceivingQuantity` / `TdrTransactionAllocation.AllocatedQuantity` |
| Transaction Record ID | `TdrTransaction.AccelaCAPRecordID` → `AccelaCAPRecord.AccelaID` |
| Transaction Created Date | `TdrTransactionStateHistory` min `TransitionDate` |
| Transaction Acknowledged Date | `TdrTransactionStateHistory` for the Acknowledged state |
| TRPA/MOU Project # | `TdrTransaction.ProjectNumber` |
| Local Jurisdiction Project # | `ParcelPermit.PermitNumber` (via related permit) |
| TRPA Status / TRPA Status Date | `TdrTransactionStateHistory` latest |
| Local Status / Local Status Date | `ParcelPermit.ParcelPermitStatusID` + latest status history |
| Year Built | ⚠️ not tracked in Corral |
| PM Year Built | ⚠️ not tracked in Corral |
| Status Jan 2026 | ⚠️ stale-snapshot column; not applicable in a live view |
| Notes | `TdrTransaction.Comments` |

**Reproducible as `vTransactionsAllocationsDetails`** except for `Year Built`, `PM Year Built`, and any post-2024-02 rows.

### D. Notes

`parcel_geneology_notes.csv` (689) and `parcel_geneology_notes_2.csv` (75,543) vs. `dbo.ParcelNote` (1,927) and `dbo.Parcel.ParcelPublicNotes`:

- Corral's `ParcelNote` is much smaller than the larger CSV (1.9K vs 75.5K). The CSV is likely an export from an upstream "parcel tracker" system before Corral-ification, or includes historical notes that were truncated.
- `Parcel.ParcelPublicNotes` and `ParcelNickname` might hold some of these strings; worth a string-match audit.

**Recommendation**: one-time diff between `ParcelNote.Note` and the CSVs; anything in the CSV but not in Corral, import as new `ParcelNote` rows with a `Source='imported_geneology_notes_csv'` audit tag. Requires adding a `Source` column to `ParcelNote`.

## What Corral is genuinely missing (needs new tables, not views)

1. **Yearly commodity inventory baseline 2012–2015.** Earlier than AuditLog's horizon. Needs a `ParcelCommodityInventoryHistoricalBaseline` table, loaded from the CSVs with `Source` tagged.
2. **Genealogy event metadata.** Change year / type / source / confidence columns on `ParcelGenealogy` (see above).
3. **APN format aliases** (El Dorado 2D↔3D). A `ParcelNumberAlias` table or a versioned `ParcelNumber` field.
4. **Year built / construction completion date per permit.** Not in `ParcelPermit`. Add `YearBuilt`, `FinalCOIssuedDate`.
5. **Refresh cadence.** Corral is a backup — whoever owns the refresh should either: (a) automate restores more frequently than the current ~2-year gap, or (b) the schema-design exercise should assume Corral is read-only archive and a new primary writes live data elsewhere.

## Proposed direction for the unified schema

Working from Corral outward:

- **Promote Corral to canonical structure; keep spreadsheets as loaders.** The 573-table Corral schema is already richly modeled for current-state development rights. The spreadsheets are *loaders* of historical context and GIS-derived analysis — treat them as batch inputs into new supplemental tables (`*HistoricalBaseline`, `ParcelNumberAlias`, genealogy metadata columns), not as parallel systems of record.
- **Lean on `AuditLog` for yearly reconstruction from 2016 onward.** A pair of table-valued functions — `fnParcelCommodityAsOf(@asof)` and `fnParcelAsOf(@asof)` — reduces the denormalized wide CSVs to computed views.
- **Write GIS-derived genealogy *into* Corral, not beside it.** The spatial overlap workflow currently outputs `apn_genealogy_spatial.csv`; re-point it at `ParcelGenealogy` with `Source='spatial'`.
- **Refresh Corral, or change its role.** A 2-year-stale mirror can't be the backbone of a new schema. Either automate refresh or formally split Corral (archive) from a new live store.

## Regenerate

```
python erd/compare_raw_data_to_corral.py   # refreshes erd/raw_data_inventory.json
```

Source inputs: [corral_schema.json](./corral_schema.json), [raw_data_inventory.json](./raw_data_inventory.json).
