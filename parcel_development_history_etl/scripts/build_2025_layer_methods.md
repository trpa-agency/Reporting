# Methods: 2025 Parcel Development Layer

## Overview

The 2025 Parcel Development feature class (`Parcel_Development_2025`) was built by combining 2025 parcel geometry from the SOURCE_FC (`Parcel_History_Attributed`) with unit data from externally maintained CSVs for residential units, tourist accommodation units (TAUs), and commercial floor area (sqft). The CSV data is treated as the sole authority for 2025 values.

**Output:** `C:\GIS\Parcel_Development_2025.gdb\Parcel_Development_2025`

## Data Sources

| Source | Description |
|--------|-------------|
| `Parcel_History_Attributed` (YEAR=2025) | Parcel polygon geometry — 61,240 parcels |
| Residential CSV (`2025 Final` column) | 42,418 parcels with residential unit counts |
| Tourist Units CSV (`CY2025` column) | 374 parcels with TAU counts |
| Commercial Sqft CSV (`CY2025` column) | 1,499 parcels with commercial floor area |
| Genealogy Master Table | 32,484 APN succession records (splits, merges, renames) |
| TRPA Jurisdictions Service | County and jurisdiction boundary polygons |
| TAZ Service | Traffic Analysis Zone boundaries (280 zones) |

## Processing Steps

### Step 1: Build Feature Class from SOURCE_FC

Extracted all 61,240 parcels with `YEAR = 2025` from SOURCE_FC. Deduplicated by APN (kept largest polygon per APN). Explicitly set the spatial reference to NAD83 UTM Zone 10N (WKID 26910), as SOURCE_FC metadata has WKID 0 / undefined SR despite coordinates being in UTM 10N.

### Step 2: Populate County and Jurisdiction

Spatial join of parcel centroids to the TRPA Jurisdictions service layer. Used `WITHIN` match first, then `CLOSEST` (100m search radius) for parcels on boundaries. Populated COUNTY code and JURISDICTION name.

For El Dorado County parcels, APNs were normalized to 3-digit last-segment format (the 2025 SOURCE_FC already uses 3-digit format).

**County breakdown:** CC=47, DG=6,261, EL=29,833, PL=15,646, WA=9,453

### Step 3: Load CSVs and Apply APN Corrections

Each CSV was processed through a correction pipeline:

1. **El Dorado 2-digit to 3-digit padding** — The CSVs use 2-digit last-segment format for El Dorado APNs (e.g., `027-323-10`), while the 2025 FC uses 3-digit (e.g., `027-323-010`). Padded 19,343 residential, 126 tourist, and 452 commercial APNs.

2. **Genealogy application** — Applied APN succession mappings from the consolidated genealogy master table to remap retired/split/merged APNs to their current successors. Applied 306 residential, 15 tourist, and 28 commercial substitutions.

3. **Manual APN fixes** — Six APNs were manually identified as retired El Dorado parcels whose successors were not in the genealogy table. These were verified visually in ArcGIS Pro:
   - `027-323-010` → `027-323-019` (48 residential units)
   - `028-301-006` → `028-301-068`
   - `027-313-002` → `027-313-016`
   - `035-301-001` → `035-301-009`
   - `015-304-031` → `015-304-034`
   - `034-691-020` → `034-691-022`

**Decision: CSV as sole authority.** The 2024 SOURCE_FC had 860 parcels with residential units that had no corresponding CSV entry. After investigation, these were determined to be stale carryovers and were not used. Only CSV values populate the output.

### Step 4: APN Crosswalk (Spatial Matching)

456 CSV APNs had no direct match in the 2025 FC after all corrections. These were resolved spatially:

1. Built centroid points for missing APNs using geometry from SOURCE_FC (any historical year). For El Dorado APNs, also searched using the depadded 2-digit format — this recovered 209 additional centroids from older years where APNs were stored in 2-digit format.

2. Spatial join of centroids to the 2025 FC polygons:
   - **INTERSECT** pass first (centroid falls inside a 2025 parcel)
   - **CLOSEST** pass for remaining (within configured search radius)

3. **455 of 456** missing APNs were resolved. When a crosswalked APN mapped to an FC parcel that already had its own CSV value, the units were **summed** (not replaced) to preserve the full CSV total.

### Step 5: Write Units to Feature Class

Wrote residential units, tourist accommodation units, and commercial floor area to the output FC from the corrected CSV lookups. Each parcel received a `Unit_Source` tag:
- **BOTH** (41,969): CSV had a value and 2024 FC native also had a value
- **CSV** (19,271): CSV had a value but no 2024 FC native value (includes zero-value parcels)

`FC_Native_Units` field preserved the 2024 SOURCE_FC residential value for reference/comparison but was not used for the output unit count.

### Step 6: TAZ Spatial Join

Spatial join of parcel polygons to the TAZ (Traffic Analysis Zone) service layer using INTERSECT. Populated 61,227 of 61,240 parcels (13 null — likely on the basin boundary).

### Step 7: QA Summary

Generated QA tables in the output GDB:
- `QA_2025_Summary` — High-level metrics
- `QA_2025_Lost_APNs` — CSV APNs with values that could not be placed (0 after all fixes)
- `QA_2025_Crosswalk` — Spatial match details for 455 crosswalked APNs
- `QA_2025_Genealogy` — 349 APN succession substitutions applied
- `APN_Mapping` — Consolidated map of all APN remappings (804 resolved, 0 unresolved)

## Final Totals

| Type | CSV Total | FC Output | Diff |
|------|-----------|-----------|------|
| Residential Units | 49,078 | 49,078 | 0 |
| Tourist Accommodation Units | 10,738 | 10,738 | 0 |
| Commercial Floor Area (sqft) | 6,533,405 | 6,533,405 | 0 |

- **All three types match exactly between CSV and FC output.**
- **0 lost APNs** — all CSV units are accounted for in the output FC.
- **0 unresolved APN mappings.**

## Key APN Correction Pipeline

```
CSV APN
  │
  ├─ El Dorado 2-digit → 3-digit padding (19,343 residential APNs)
  │
  ├─ Genealogy substitution (306 residential APNs)
  │
  ├─ Manual APN fixes (6 APNs)
  │
  ├─ Direct match to 2025 FC? ──YES──→ Write units
  │                │
  │               NO
  │                │
  └─ Crosswalk: find historic geometry (also try El Dorado depad)
       │
       ├─ Centroid intersects 2025 parcel? ──→ Map + sum units
       │
       └─ Closest 2025 parcel within radius? ──→ Map + sum units
```

## Output Fields

| Field | Type | Description |
|-------|------|-------------|
| APN | Text | Assessor's Parcel Number |
| Year | Long | 2025 |
| COUNTY | Text | County code (CC, DG, EL, PL, WA) |
| JURISDICTION | Text | Jurisdiction name |
| Residential_Units | Long | Residential unit count (from CSV) |
| TouristAccommodation_Units | Long | Tourist accommodation units (from CSV) |
| CommercialFloorArea_SqFt | Double | Commercial floor area in sqft (from CSV) |
| FC_Native_Units | Long | Residential units from 2024 SOURCE_FC (reference only) |
| Unit_Source | Text | BOTH or CSV — indicates data provenance |
| TAZ | Text | Traffic Analysis Zone ID |

## Reproducibility

Script: `parcel_development_history_etl/scripts/build_2025_layer.py`

```
& "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" parcel_development_history_etl/scripts/build_2025_layer.py
```

Runtime: ~2 minutes. Logs written to `parcel_development_history_etl/logs/etl_YYYYMMDD.log`.
