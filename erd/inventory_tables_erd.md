# Inventory tables - Residential Units + Buildings + PDH 2025

> **Status: analyst-facing artifacts (CSV).**
> **Audience: anyone consuming the per-unit / per-building cumulative-accounting derivations.**

Three CSVs produced from the PDH 2025 ETL output, plus the analyst's deliverables and live REST services. These are **derived analyst products** (not yet promoted to SDE tables) that join the per-parcel PDH FC with year-built data, the genealogy chain, the transactions/allocations registry, and the buildings footprint layer.

For the SDE proposal these would eventually fold into, see [target_schema.md](./target_schema.md).

## Pipeline

```
PDH FC (YEAR=2025)  ─┐
                     ├─► PDH_2025_OriginalYrBuilt.csv  ─┐
OriginalYrBuilt.csv ─┤                                   ├─► residential_units_inventory_2025.csv
Parcels FS YEAR_BUILT┘                                   │
                                                         │
apn_genealogy_tahoe.csv ─────► Previous_APNs ────────────┤
Transactions xlsx ───► Era/Source/Pool/Tx/Permit ───────┤
Buildings_2019 FC (spatial join) ──► Building_IDs ──────┤
Parcels FS APO_ADDRESS ──────► Address ─────────────────┘

Buildings_2019 FC ──┐
                    ├─► buildings_inventory_2025.csv (one row per footprint)
PDH 2025 (LARGEST_OVERLAP) ──► APN + parcel context ─┘
```

Sources by script - **run in this order** (the buildings ↔ units assignment requires this DAG):
1. [`build_2025_yrbuilt.py`](../parcel_development_history_etl/scripts/build_2025_yrbuilt.py) → `PDH_2025_OriginalYrBuilt.csv`
2. [`build_buildings_inventory.py`](../parcel_development_history_etl/scripts/build_buildings_inventory.py) → `buildings_inventory_2025.csv` *(first pass - `Units_Assigned` null)*
3. [`build_buildings_with_units.py`](../parcel_development_history_etl/scripts/build_buildings_with_units.py) → `buildings_with_units.json` *(sqft-weighted unit-to-building assignment)*
4. [`build_buildings_inventory.py`](../parcel_development_history_etl/scripts/build_buildings_inventory.py) → `buildings_inventory_2025.csv` *(second pass - backfills `Units_Assigned`)*
5. [`build_residential_units_inventory.py`](../parcel_development_history_etl/scripts/build_residential_units_inventory.py) → `residential_units_inventory_2025.csv`
6. [`build_unit_transaction_relations.py`](../parcel_development_history_etl/scripts/build_unit_transaction_relations.py) → `residential_unit_transactions.csv` (junction)

---

## Entity-relationship diagram

```mermaid
erDiagram
    Parcel2025 ||--o{ ResidentialUnit : "explodes_into_units"
    Parcel2025 ||--o{ Building        : "contains_footprints"
    Parcel2025 }o--o{ GenealogyEvent  : "has_predecessors"
    ResidentialUnit ||--o{ UnitTransaction : "has_chronology"
    UnitTransaction }o--|| Transaction : "references"
    Building ||--o{ ResidentialUnit   : "hosts"

    Parcel2025 {
        string APN_canon PK
        string APN
        string COUNTY
        string JURISDICTION
        int Residential_Units
        int TouristAccommodation_Units
        float CommercialFloorArea_SqFt
        int OriginalYrBuilt
        int CountyYearBuilt
        int COMBINED_YEAR_BUILT
        string combined_source
        string match_method
        float PARCEL_ACRES
    }

    ResidentialUnit {
        string Residential_Unit_ID PK
        string APN_canon FK
        string APN
        string Previous_APNs
        int Original_Year_Built
        int Year_Redeveloped
        string Era
        string Source
        string Pool
        string Transaction_ID
        string Permit_Number
        int Building_ID FK
        string Address
        string COUNTY
        string JURISDICTION
    }

    UnitTransaction {
        string Relation_ID PK
        string Residential_Unit_ID FK
        string APN_canon
        string Transaction_ID FK
        int Sequence
        bool Is_Latest
        string Transaction_Type
        string Development_Type
        string Detailed_Development_Type
        string Allocation_Number
        int Quantity
        date Transaction_Created_Date
        date Transaction_Acknowledged_Date
        int Year_Built
        string TRPA_Project_Number
        string Local_Project_Number
        string TRPA_Status
        date TRPA_Status_Date
        string Local_Status
        date Local_Status_Date
        string Status_Jan_2026
        string Notes
    }

    Building {
        int Building_ID PK
        string APN FK
        string APN_canon
        float Square_Feet
        int Original_Year_Built
        string Feature
        string Surface
        float Parcel_Acres
        int Residential_Units
        int Units_Assigned
        string COUNTY
        string JURISDICTION
    }

    GenealogyEvent {
        string event_id PK
        string apn_old
        string apn_new
        int change_year
        string event_type
        int is_primary
        int in_fc_new
        string source
    }

    Transaction {
        string TransactionID PK
        string APN
        string Transaction_Type
        string Development_Right
        string Allocation_Number
        string TRPA_MOU_Project
        string Local_Jurisdiction_Project
        int Year_Built
    }
```

### Relationship notes

- **`Parcel2025 ‖−o{ ResidentialUnit`** - one parcel explodes into N units (N = `Residential_Units` count). A vacant residential parcel yields zero unit rows.
- **`Parcel2025 ‖−o{ Building`** - one parcel can have 0..N building footprints; a parcel with no detected footprint (1.3% of unit parcels) gets `Building_IDs` empty.
- **`Parcel2025 }o−o{ GenealogyEvent`** - many-to-many. A parcel can appear in many genealogy events (as either `apn_old` or `apn_new`); a single event can have multiple parents/children. Predecessors are walked up to 5 hops back from each current APN.
- **`Parcel2025 }o−o{ Transaction`** - many-to-many. A parcel can have multiple transactions (allocation + transfer, banking + conversion, etc.); the `Source` and `Pool` fields capture the **highest-priority** transaction per the order Allocation > Bonus Unit > Banked Unit > Transfer > Conversion.
- **`Building ‖−o{ ResidentialUnit`** - proper one-to-many. Each unit has exactly one `Building_ID` (foreign key to `Building.Building_ID`), and a building can host many units. Assignment is **sqft-weighted via Hamilton's largest-remainder method**: on a parcel with N units and M buildings, the units are distributed in proportion to each building's `Square_Feet`, with leftover units handed to the largest-remainder buildings first. The buildings inventory's `Units_Assigned` column carries the corresponding count per building (sum equals the parcel's `Residential_Units`). When a parcel has fewer building footprints than units (post-2019 construction not in `Buildings_2019`, or no overlapping footprint at all), some units get `Building_ID = null` - currently 8,830 of 49,018 units (18%).
- **`ResidentialUnit ‖−o{ UnitTransaction }o−‖ Transaction`** - many-to-many between units and transactions, properly normalized via the `UnitTransaction` junction. Each row pairs one `Residential_Unit_ID` with one `Transaction_ID` and carries the transaction's metadata inline so the table is self-sufficient for analysis. `Sequence` orders transactions chronologically per unit (by `Transaction_Created_Date`, falling back to TRPA / Local status dates); `Is_Latest=true` marks the most recent transaction per unit. The summary `Transaction_ID` semicolon-string on the inventory is kept as a convenience for human scans; the junction is the queryable source of truth.

---

## Field dictionary

### `residential_units_inventory_2025.csv` - one row per current (2025) residential unit

| Field | Type | Source | Notes |
|---|---|---|---|
| `Residential_Unit_ID` | string PK | synthetic | `RU-<APN_canon>-<seq>`; sequential 001..N within each APN. Regenerates deterministically. |
| `APN` | string | PDH FC | Raw APN as stored in `Parcel_Development_History.APN`. Mixed pre/post-2018 format. |
| `APN_canon` | string | `utils.canonical_apn()` | Padded to NNN-NNN-NNN form for joining. The canonical join key. |
| `Previous_APNs` | string | `apn_genealogy_tahoe.csv` | Semicolon-separated predecessor canonical APNs walked backward up to 5 hops. Empty when no genealogy. |
| `Original_Year_Built` | int (nullable) | `PDH_2025_OriginalYrBuilt.csv` | The parcel's earliest structure year - `COMBINED_YEAR_BUILT` from the join (the analyst's value primary, county YEAR_BUILT filler). 98.7% coverage. |
| `Year_Redeveloped` | int (nullable) | derived from `Final2026_Residential.csv` | Year units came back up after a demolition gap (units > 0 → 0 → units > 0). Empty for non-redev units. Currently catches 8 units (strict demolish-rebuild definition). |
| `Era` | enum | `Original_Year_Built` | `Pre-1987 Plan` (≤1987), `1987 Plan` (1988–2011), `2012 Plan` (≥2012), `Unknown` (null). Per the **original** year - redev does not change era because no new allocation is drawn. |
| `Source` | enum | Transactions xlsx | How the unit was authorized: `Existing` (pre-2012 default), `Allocation`, `Bonus Unit`, `Banked Unit`, `Transfer`, `Conversion`, `Unknown`. Tie-break priority: Allocation > Bonus Unit > Banked Unit > Transfer > Conversion. |
| `Pool` | enum | Transactions xlsx | Which account the allocation drew from: `TRPA`, `El Dorado`, `Placer`, `Washoe`, `Douglas`, `Carson City`, `CSLT`, `Banked Inventory`, `Private`, `N/A (Pre-Allocation)`, `Unknown`. Derived from `Development Right` text + `Allocation Number` prefix (EL/PL/DG/WA/SLT). |
| `Transaction_ID` | string | Transactions xlsx | Semicolon-separated `TransactionID` values from `2025 Transactions and Allocations Details.xlsx` matching this APN (e.g., `TRPA-ALLOC-758`, `WCNV-ALLOC-613`). |
| `Permit_Number` | string | Transactions xlsx | Semicolon-separated permit IDs prefixed `TRPA-` (from `TRPA/MOU Project #`) and `LOCAL-` (from `Local Jurisdiction Project #`). E.g., `TRPA-ERSP2023-0515; LOCAL-WDADAR24-0004`. |
| `Building_ID` | int FK (nullable) | sqft-weighted Hamilton assignment from `buildings_with_units.json` | Single `Buildings_2019.OBJECTID` this unit is hosted by. Building→Unit is 1:N (a building hosts many units; each unit has exactly one building). Within a parcel, units are sorted into buildings by descending sqft, with leftover units handed to the largest-remainder buildings. Null for ~18% of units (8,830) where the parcel has no overlapping footprint - post-2019 construction or no primary building match. |
| `Address` | string | Parcels FS `APO_ADDRESS` | Mailing/site address from the public Parcels FeatureService. 100% populated (49,017 of 49,018). |
| `COUNTY` | string | PDH FC | 2-char code: `EL`, `PL`, `DG`, `WA`, `CSLT`, `CC`. |
| `JURISDICTION` | string | PDH FC | Same as COUNTY in most cases; CSLT may differ from EL. |

**Row scope**: One row per **currently existing** (2025) unit. A duplex on one parcel = 2 rows sharing APN, year, address, buildings. A parcel with 0 units in 2025 = 0 rows. Demolished units are NOT represented; the redev year is captured separately on the surviving unit rows.

### `buildings_inventory_2025.csv` - one row per Buildings_2019 footprint

| Field | Type | Source | Notes |
|---|---|---|---|
| `Building_ID` | int PK | `Buildings_2019.OBJECTID` | Stable identifier from the source GIS layer. |
| `APN` | string | `LARGEST_OVERLAP` spatial join to PDH 2025 | The parcel with the most overlap with this footprint. 99.4% matched. |
| `APN_canon` | string | `utils.canonical_apn()` | Canonical form for joining to other tables. |
| `Square_Feet` | float | `SHAPE@.getArea("PLANAR","SquareFeetUS")` | Computed at script run time, not the source `Shape_Area` field (which is in projection-dependent units). |
| `Original_Year_Built` | int (nullable) | Parcel's `COMBINED_YEAR_BUILT` | **Parcel-level**, not per-building. Buildings_2019 has no per-building year. Use as best-available approximation. 93.1% populated. |
| `Feature` | string | `Buildings_2019.Feature` | Building type from source. Currently always `"Building"` - no further subtype data. |
| `Surface` | string | `Buildings_2019.Surface` | Building material/surface - sparsely populated in source. |
| `Parcel_Acres` | float | PDH FC | Parent parcel acreage (context). |
| `Residential_Units` | int | PDH FC | Number of residential units on the **parent parcel** (0 for non-residential parcels). Same value for all buildings on the same parcel. |
| `Units_Assigned` | int (nullable) | `buildings_with_units.json` | Number of units hosted by **this specific building** - the sqft-weighted Hamilton split of the parcel's `Residential_Units` across its building footprints. Sum across a parcel's buildings equals `Residential_Units`. Null on first build before `buildings_with_units.json` exists; re-run this script after it's built to backfill. |
| `COUNTY`, `JURISDICTION` | string | PDH FC | Same as parent parcel. |

**Row scope**: One row per Buildings_2019 footprint (44,739 total). 269 footprints (0.6%) don't match a 2025 parcel - usually dock/pier polygons outside the PDH boundary.

**Top multi-unit buildings** (highest `Units_Assigned`): Building 8122 at parcel `032-291-028` hosts 91 units (Sugar Pine), Building 39142 at `127-040-09` hosts 51, Building 2203 at `034-270-059` hosts 43.

### `residential_unit_transactions.csv` - junction: one row per (unit × transaction) pair

| Field | Type | Source | Notes |
|---|---|---|---|
| `Relation_ID` | string PK | synthetic | `RUT-<APN_canon>-<unit_seq>-<tx_seq>`; stable, regenerates deterministically. |
| `Residential_Unit_ID` | string FK | units inventory | `RU-<APN_canon>-<seq>`. |
| `APN` | string | units inventory | Raw APN (PDH form). |
| `APN_canon` | string | units inventory | Canonical join key. |
| `Transaction_ID` | string FK | the analyst's transactions xlsx | e.g. `TRPA-ALLOC-758`. Compound IDs (`A/B`) are preserved as-is - the analyst's batch-allocation format. |
| `Sequence` | int | derived | Chronological order within the unit (1 = earliest). Tie-breaks by stable input order. |
| `Is_Latest` | bool | derived | `true` on the most recent transaction per unit; exactly one row per unit has it true. |
| `Transaction_Type` | enum | xlsx | `Residential Allocation`, `Allocation`, `Allocation Assignment`, `Transfer`, `Banking of Existing Development`, `Conversion`, `Conversion With Transfer`, `Residential Bonus Unit (RBU)`, `Land Bank Transfer`, … |
| `Development_Type` | string | xlsx | `Allocation`, `Banked Unit`, `Transfer`, `Banking From`, `Conversion`, … |
| `Detailed_Development_Type` | string | xlsx | the analyst's free-text description (e.g. `New Single-Family Residential from Allocation`). |
| `Development_Right` | string | xlsx | The kind of right being moved (e.g. `Residential Allocation - El Dorado County`, `SFRUU`, `MFRUU`, `RBU`). |
| `Allocation_Number` | string | xlsx | e.g. `EL-21-O-08`; prefix encodes the source pool (EL / PL / DG / WA / SLT). |
| `Quantity` | int | xlsx | Usually 1, occasionally batch (>1). |
| `Transaction_Created_Date` | date | xlsx | Primary chronology key. |
| `Transaction_Acknowledged_Date` | date | xlsx | When TRPA acknowledged. |
| `Year_Built` | int (nullable) | xlsx | The construction year recorded by the analyst on this transaction. Distinct from the parcel's `Original_Year_Built`. |
| `TRPA_Project_Number` | string | xlsx | `TRPA/MOU Project #`. |
| `Local_Project_Number` | string | xlsx | `Local Jurisdiction Project #`. |
| `TRPA_Status` / `TRPA_Status_Date` | string / date | xlsx | TRPA permit state and date. |
| `Local_Status` / `Local_Status_Date` | string / date | xlsx | Local permit state and date. |
| `Status_Jan_2026` | enum | xlsx | `Completed` / `Not Completed` / `No Project` / `TBD`. The construction-rolled-up status as of the January 2026 snapshot. |
| `Notes` | string | xlsx | the analyst's free-text notes (often parcel/project-specific). |

**Row scope**: 2,220 rows (1,529 units with at least one transaction; 295 units have >1 transaction; max 9 transactions on one unit). 1,135 unique transactions referenced.

**Assignment caveat (v1)**: every transaction on an APN is linked to every unit on that APN. This is over-inclusive when one parcel had transactions of different kinds affecting different sub-sets of units (e.g. an allocation creating Unit 1 + a separate banking event for Unit 2). A future v2 using `Quantity` + chronology could bind specific transactions to specific units. Until then, expect the relation table to slightly over-count for multi-event parcels - the totals on a per-transaction basis are correct, but the per-unit transaction lists may include transactions that semantically belong to a sibling unit on the same parcel.

### `PDH_2025_OriginalYrBuilt.csv` - intermediate: parcel × year built

| Field | Type | Source | Notes |
|---|---|---|---|
| `APN` | string | PDH FC | Raw 2025 APN. |
| `APN_canon` | string | canonical | Join key. |
| `YEAR` | int | PDH FC | Always 2025 in this CSV. |
| `Residential_Units`, `TouristAccommodation_Units`, `CommercialFloorArea_SqFt` | numeric | PDH FC | 2025 counts. |
| `COUNTY`, `JURISDICTION`, `PARCEL_ACRES` | mixed | PDH FC | Parcel attributes. |
| `OriginalYrBuilt` | int (nullable) | the analyst's `original_year_built.csv` | Direct join or genealogy fallback. |
| `OriginalYrBuilt_source_APN` | string | the analyst's file | The APN actually matched (for genealogy cases, the predecessor APN). |
| `match_method` | enum | join logic | `direct`, `genealogy_old_from_new`, `genealogy_new_from_old`, `unmatched`. |
| `CountyYearBuilt` | int (nullable) | Parcels FS `YEAR_BUILT` | County assessor's value - used as filler. |
| `COMBINED_YEAR_BUILT` | int (nullable) | derived | `OriginalYrBuilt` if present, else `CountyYearBuilt`. This is what feeds `Original_Year_Built` in the units inventory. |
| `combined_source` | enum | derived | `original`, `county`, or `none`. |

**Row scope**: One row per PDH 2025 parcel (61,240 rows). Includes vacant parcels (units = 0).

---

## Coverage summary (current run)

| Table | Rows | Notable coverage |
|---|---:|---|
| `PDH_2025_OriginalYrBuilt.csv` | 61,240 | 73.4% have a year-built from any source; 16,023 truly null (mostly vacant land) |
| `residential_units_inventory_2025.csv` | 49,018 | 98.7% Original_Year_Built; 82.0% Building_ID assigned (sqft-weighted); 100% Address; 3.3% Permit_Number; 3.0% Era=2012 Plan |
| `buildings_inventory_2025.csv` | 44,739 | 99.4% APN-matched; 93.1% Original_Year_Built; 79.1% with `Units_Assigned ≥ 1` (35,368 buildings host 40,188 units); 86.9M sq ft total footprint |
| `residential_unit_transactions.csv` | 2,220 | 1,529 units linked; 1,135 unique transactions; 295 units with >1 transaction; max 9 transactions on a single unit; 1,926 Completed / 249 Not Completed / 44 No Project |

## Known data limitations

1. **Pre-2012 allocations are not in the transactions xlsx**. About 5,500 of the 6,731 cumulative residential allocations since 1987 fall before the xlsx coverage. Those units' `Source` defaults to `Existing` and `Pool` defaults to `N/A (Pre-Allocation)`. A future ingestion of historical allocation records would refine those classifications.
2. **Bonus Units undercounted**. Only 45 RBU units detected vs the analyst's 736 cumulative. The xlsx tracks BANKING/TRANSFER of RBUs but only 11 rows have `Transaction Type = "Residential Bonus Unit (RBU)"`. The actual unit-construction events for RBUs appear to be tracked under a different transaction type.
3. **`Building_IDs` is a concatenated string, not a junction table**. Units on the same parcel share the same string. If a future SDE schema needs per-unit-per-building links, this is the right place to normalize.
4. **`Year_Redeveloped` uses a strict definition** (units > 0 → 0 → units > 0). Loose redevelopment (replacing a structure without ever zeroing out the unit count) is not flagged.

## Future SDE promotion

If these tables get promoted into the SDE proposal in [target_schema.md](./target_schema.md), the cleanest path:

- **`ResidentialUnit`** becomes a new table in the development-rights schema, with FKs to `ParcelExistingDevelopment` (provides Era + counts) and `vPermitAllocation` (provides Source + Pool + Permit_Number).
- **`Building`** becomes a new spatial table sharing the same SDE instance as the parcel FC; FK to `ParcelExistingDevelopment` via APN.
- **`UnitBuilding`** junction table replaces the concatenated `Building_IDs` string.
- `Era` / `Source` / `Pool` become enum lookups (small reference tables), not free-text columns.
