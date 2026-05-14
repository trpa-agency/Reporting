"""
Central configuration for the Development History ETL.
All paths, field names, service URLs, and constants live here.
"""

# ── Geodatabase ───────────────────────────────────────────────────────────────
GDB        = r"C:\GIS\ParcelHistory.gdb"
SOURCE_FC  = GDB + r"\Parcel_History_Attributed"   # original — never edited
WORKING_FC = GDB + r"\Parcel_History_Working"       # cleaned copy — preprocess output
OUTPUT_FC  = GDB + r"\Parcel_Development_History"   # ETL output (main.py)

# QA output directory — CSVs are written here in addition to the GDB
QA_DATA_DIR = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\qa_data"
)

# QA tables (written to GDB so they open directly in ArcGIS Pro)
QA_UNITS_BY_YEAR        = GDB + r"\QA_Units_By_Year"
QA_TAU_BY_YEAR          = GDB + r"\QA_TAU_By_Year"
QA_CFA_BY_YEAR          = GDB + r"\QA_CFA_By_Year"
QA_LOST_APNS            = GDB + r"\QA_Lost_APNs"
QA_APN_CROSSWALK        = GDB + r"\QA_APN_Crosswalk"
QA_DUPLICATE_APN_YEAR   = GDB + r"\QA_Duplicate_APN_Year"
QA_SPATIAL_COMPLETENESS = GDB + r"\QA_Spatial_Completeness"
QA_GENEALOGY_APPLIED    = GDB + r"\QA_Genealogy_Applied"
QA_FC_NOT_IN_CSV        = GDB + r"\QA_FC_Units_Not_In_CSV"
QA_TOPO_DUPLICATE       = GDB + r"\QA_Topo_DuplicateAPN"
QA_TOPO_OVERLAP         = GDB + r"\QA_Topo_Overlap"
QA_TOPO_AREA_SHIFT      = GDB + r"\QA_Topo_AreaShift"
QA_SOURCE_VS_SERVICE      = GDB + r"\QA_Source_vs_Service"
QA_UNIT_RECONCILIATION    = GDB + r"\QA_Unit_Reconciliation"

# ── Input CSV ─────────────────────────────────────────────────────────────────
CSV_PATH = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\raw_data\Final2026_Residential.csv"
)
# Tourist Accommodation Units — wide format, APN x CY2012..CY2025
TOURIST_UNITS_CSV = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\raw_data\Final2026_TAUs.csv"
)
# Commercial Floor Area SqFt — wide format, APN x CY<year>
COMMERCIAL_SQFT_CSV = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\raw_data\Final2026_CFA.csv"
)
# Service-only APNs — produced by compare_source_to_service.py
# APNs present in All Parcels service but missing from OUTPUT_FC
SERVICE_ONLY_CSV = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\raw_data\apn_service_only.csv"
)
# Original year-built lookup (CSV form of from_analyst/OriginalYrBuilt.xlsx).
# One row per APN, single integer year. Mixed pre/post-2018 APN formats —
# canonicalize before joining.
ORIGINAL_YR_BUILT_CSV = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\raw_data\original_year_built.csv"
)
# Output of build_2025_yrbuilt.py — PDH 2025 rows joined to OriginalYrBuilt
# with APN-genealogy fallback for unmatched rows.
PDH_2025_YRBUILT_CSV = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\processed_data\PDH_2025_OriginalYrBuilt.csv"
)
# Output of build_residential_units_inventory.py — one row per current
# (2025) residential unit in Tahoe.
RESIDENTIAL_UNITS_INVENTORY_CSV = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\processed_data\residential_units_inventory_2025.csv"
)
# 2025 Transactions and Allocations Details (from the analyst / TRPA permit system).
# Per-APN TransactionID + allocation metadata. Sourced from the 2025
# cumulative-accounting cycle.
TRANSACTIONS_2025_XLSX = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\raw_data\2025 Transactions and Allocations Details.xlsx"
)
# Per-allocation grid export from the analyst (one row per residential allocation,
# 2012 Plan additional = 2,600 allocations). Drives allocation-tracking.html
# and the live counts in regional-capacity-dial.html.
ALLOCATION_GRID_XLSX = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\raw_data\residentialAllocationGridExport_fromAnalyst.xlsx"
)
ALLOCATION_GRID_CSV = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\raw_data\residentialAllocationGridExport.csv"
)
# All Regional Plan Allocations Summary - analyst-delivered xlsx with the
# 1987 / 2012 / combined plan-era split, Regional Plan Maximum + assigned /
# not-assigned status, by jurisdiction, for all four commodities (RES / RBU /
# CFA / TAU), plus a residential allocations-by-year (1986-2026) block.
# This is the authoritative source for the "Assigned" reframe and the 8,687
# expansion. Pre-2012 (1987 Plan) figures are not in LT Info, so this xlsx
# is the only source for them.
REGIONAL_PLAN_ALLOCATIONS_XLSX = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\from_analyst\All Regional Plan Allocations Summary.xlsx"
)
# Tidy JSON form of the above, emitted by convert_regional_plan_allocations.py.
# Consumed by regional-capacity-dial.html, allocation-tracking.html,
# pool-balance-cards.html, and public-allocation-availability.html (Phase 2).
REGIONAL_PLAN_ALLOCATIONS_JSON = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\processed_data\regional_plan_allocations.json"
)
# Normalized 1987 Regional Plan baseline - the frozen historical half that is
# NOT in Corral / LT Info and must live as a hard-coded reference (the
# `RegionalPlanCapacity` seed in erd/regional_plan_allocations_service.md).
# Extracted from the JSON above by extract_regional_plan_1987_seed.py.
REGIONAL_PLAN_1987_BASELINE_CSV = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\processed_data\regional_plan_1987_baseline.csv"
)
# Many-to-many junction table: one row per (Residential_Unit_ID, Transaction_ID)
# pair. Captures the chronology of transactions affecting each unit and
# carries the transaction metadata inline so the table is self-sufficient
# for analysis.
RESIDENTIAL_UNIT_TRANSACTIONS_CSV = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\processed_data\residential_unit_transactions.csv"
)
# Output of build_buildings_inventory.py — one row per Buildings_2019 footprint.
BUILDINGS_INVENTORY_CSV = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\processed_data\buildings_inventory_2025.csv"
)
# Output of build_buildings_with_units.py — per-building unit assignment
# (sqft-weighted split of parcel units) + aggregated unit time series for the
# development-history-units dashboard.
BUILDINGS_WITH_UNITS_JSON = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\processed_data\buildings_with_units.json"
)
# Output of build_genealogy_solver_data.py — pre-joined genealogy graph +
# per-APN 2025 cross-reference (units / year built / jurisdiction) compacted
# into a single JSON for client-side BFS in html/genealogy_solver/.
# Co-located with the app (not data/processed_data/) since it's app-specific.
GENEALOGY_SOLVER_JSON = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\html\genealogy_solver\data\genealogy_solver.json"
)

# ── Parcel genealogy ───────────────────────────────────────────────────────────
# Raw notes CSVs from the CSV author (free-text, parsed once by build_genealogy_master.py)
GENEALOGY_NOTES_1 = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\qa_data\parcel_geneology_notes.csv"
)
GENEALOGY_NOTES_2 = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\qa_data\parcel_geneology_notes_2.csv"
)
# Structured master genealogy CSV — generated by build_genealogy_master.py,
# reviewed and edited by analyst, consumed by s02b on every ETL run.
GENEALOGY_MASTER = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\qa_data\apn_genealogy_master.csv"
)
# Spatially-derived genealogy CSV — generated by build_spatial_genealogy.py,
# consumed by s02b alongside the manual master.
GENEALOGY_SPATIAL = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\qa_data\apn_genealogy_spatial.csv"
)
# Accela permit-system genealogy — generated by parse_genealogy_sources.py.
# Covers 2021–2025 splits/merges/renames from the permit database.
GENEALOGY_ACCELA = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\qa_data\apn_genealogy_accela.csv"
)
# LTinfo parcel genealogy — generated by parse_genealogy_sources.py.
# change_year is blank for most rows (pre-2021); rows without change_year
# are skipped by s02b until dates are filled in.
GENEALOGY_LTINFO = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\qa_data\apn_genealogy_ltinfo.csv"
)
# Consolidated master table — generated by build_genealogy_tahoe.py.
# Merges all four sources with canonical APN formatting, deduplication,
# and lost_apn validation flags. This is what s02b reads when available.
GENEALOGY_TAHOE = (
    r"C:\Users\mbindl\Documents\GitHub\Reporting"
    r"\data\qa_data\apn_genealogy_tahoe.csv"
)
# Minimum fraction of an old parcel's area that must overlap a new APN
# for the event to be recorded (0.50 = 50 %).
SPATIAL_GENEALOGY_OVERLAP_THRESHOLD = 0.50

# ── Feature class field names ─────────────────────────────────────────────────
FC_APN              = "APN"
FC_YEAR             = "YEAR"
FC_UNITS            = "Residential_Units"
FC_COUNTY           = "COUNTY"
FC_TOURIST_UNITS    = "TouristAccommodation_Units"
FC_COMMERCIAL_SQFT  = "CommercialFloorArea_SqFt"

# Spatial attribute fields written by s05
SPATIAL_FIELDS = [
    "PARCEL_ACRES", "PARCEL_SQFT",
    "WITHIN_TRPA_BNDY", "WITHIN_BONUSUNIT_BNDY",
    "TOWN_CENTER", "LOCATION_TO_TOWNCENTER",
    "TAZ", "PLAN_ID", "PLAN_NAME",
    "ZONING_ID", "ZONING_DESCRIPTION",
    "REGIONAL_LANDUSE",
    "Building_SqFt",   # total footprint area of buildings within parcel (sq ft, from Buildings_2019)
]

# ── Buildings footprint (for Building_SqFt field in s05) ─────────────────────
BUILDINGS_FC = r"C:\GIS\Buildings.gdb\Buildings_2019"

# ── El Dorado APN format change ───────────────────────────────────────────────
# El Dorado County (COUNTY = 'EL') added a leading zero to the APN suffix
# starting in 2018. e.g. 080-155-11 → 080-155-011.
EL_PAD_YEAR = 2018

# ── CSV column detection markers ──────────────────────────────────────────────
# Used by s02_load_csv and s04b to detect year columns.
# If these change (e.g. CSV format is updated), update these constants and
# validation will raise a clear error rather than silently returning no data.
CSV_RESIDENTIAL_YEAR_MARKER = "Final"  # residential CSV year columns contain this
CSV_TOURIST_YEAR_PREFIX     = "CY"     # tourist/commercial CSV year columns start with this
CSV_COMMERCIAL_YEAR_PREFIX  = "CY"

# ── Years in scope ────────────────────────────────────────────────────────────
CSV_YEARS        = list(range(2012, 2026))   # 2012 – 2025 inclusive
# Years where SOURCE_FC already has native Residential_Units values curated
# from prior team efforts.  These years support a two-source reconciliation
# between the CSV (coworker's latest effort) and the FC native values.
FC_NATIVE_YEARS  = [2012] + list(range(2018, 2026))

# ── Parcels FeatureService (county-source attributes incl. YEAR_BUILT) ───────
# Used by build_2025_yrbuilt.py as a filler for OriginalYrBuilt gaps.
PARCELS_FS = "https://maps.trpa.org/server/rest/services/Parcels/FeatureServer/0"

# ── AllParcels MapServer (geometry fetch for missing parcels) ─────────────────
ALLPARCELS_URL = "https://maps.trpa.org/server/rest/services/AllParcels/MapServer"
# Layer 3 = current (all-years combined) parcel layer — used as geometry fallback in s03
ALL_PARCELS_CURRENT = ALLPARCELS_URL + "/3"

# Layer index per year — verify against the service directory if layers shift
# 2012 is intentionally excluded: polygons are taken from SOURCE_FC instead
# of the AllParcels service (Parcel_History_Attributed is more authoritative).
YEAR_LAYER = {
    2013:  7,
    2014:  6,
    2015:  5,
    2016: 18,
    2017: 17,
    2018: 20,
    2019: 22,
    2020: 27,
    2021: 29,
    2022: 30,
    2023: 31,
    2024: 32,
    # 2025 layer not yet published on AllParcels MapServer
}

# ── Jurisdictions spatial join service ────────────────────────────────────────
JURISDICTION_SVC = "https://maps.trpa.org/server/rest/services/Boundaries/FeatureServer/10"

# Maps full county names (as returned by the service) to 2-char codes
COUNTY_CODE_MAP = {
    "Washoe"                 : "WA",
    "El Dorado"              : "EL",
    "Placer"                 : "PL",
    "Douglas"                : "DG",
    "Carson City"            : "CC",
    "City of South Lake Tahoe": "CSLT",
}

# ── Spatial join service URLs (confirmed) ─────────────────────────────────────
SPATIAL_SOURCES = {
    "TRPA_bdy"         : "https://maps.trpa.org/server/rest/services/Boundaries/FeatureServer/4",
    "BonusUnit"        : "https://maps.trpa.org/server/rest/services/Housing/MapServer/8",
    "TownCenter"       : "https://maps.trpa.org/server/rest/services/Boundaries/FeatureServer/1",
    "LocationToTownCtr": "https://maps.trpa.org/server/rest/services/Planning/FeatureServer/4",
    "TAZ"              : "https://maps.trpa.org/server/rest/services/Transportation_Planning/MapServer/6",
    "LocalPlan"        : "https://maps.trpa.org/server/rest/services/Planning/FeatureServer/2",
    "Zoning"           : "https://maps.trpa.org/server/rest/services/Zoning/MapServer/0",
    "RegionalLandUse"  : "https://maps.trpa.org/server/rest/services/LocalPlan/MapServer/7",
}

# ── Crosswalk spatial join parameters ────────────────────────────────────────
CLOSEST_MAX_METERS = 50   # max distance for CLOSEST fallback in centroid join

# ── Internal sentinel ────────────────────────────────────────────────────────
# Year value used internally when a row's geometry comes from SOURCE_FC rather
# than the All Parcels MapServer (i.e. no real service layer exists for it).
SOURCE_FC_SENTINEL_YEAR = 9999

# ── Validation service URLs ───────────────────────────────────────────────────
# Stub values — fill in the real REST endpoints before running validation.py.
# Checks whose URL is empty are skipped with a warning (no error).
IMPERVIOUS_SVC    = ""  # Impervious Surface footprint REST layer
BMP_CERT_SVC      = ""  # BMP Certificate REST layer
VHR_PERMIT_SVC    = ""  # VHR Permit REST layer
LTINFO_PERMITS    = ""  # LTinfo API / Permits endpoint
LTINFO_ALLOCS     = ""  # LTinfo API / Allocations endpoint
LTINFO_DEV_RIGHTS = ""  # LTinfo API / Dev Rights endpoint

# Flag Table GDB path — written by validation.py, read-only for everything else
QA_FLAG_TABLE = GDB + r"\QA_Flag_Table"
