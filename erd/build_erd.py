"""Assemble the development-rights ERD markdown.

Reads:
  erd/corral_schema.json
  erd/ltinfo_services.json

Writes:
  erd/development_rights_erd.md
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ERD_DIR = Path(__file__).resolve().parent

# Curated subset of Corral tables relevant to development / dev-rights.
CORRAL_FOCUS = {
    # Parcel core
    "dbo.Parcel", "dbo.ParcelGeometry", "dbo.ParcelGenealogy", "dbo.ParcelStatus",
    "dbo.ParcelNote",
    # Accela linkage
    "dbo.AccelaCAPRecord", "dbo.ParcelAccelaCAPRecord", "dbo.AccelaCAPRecordStatus",
    # Parcel permit
    "dbo.ParcelPermit", "dbo.ParcelPermitType", "dbo.ParcelPermitStatus",
    "dbo.ParcelPermitBankedDevelopmentRight",
    "dbo.ParcelPermitProposedDevelopmentRight",
    "dbo.ParcelPermitProposedDevelopmentRightDetail",
    "dbo.ParcelPermitProposedDevelopmentRightDetailType",
    "dbo.ParcelPermitDeedRestriction",
    "dbo.ParcelPermitBuildingType",
    # Allocations
    "dbo.ResidentialAllocation", "dbo.ResidentialAllocationType",
    "dbo.ResidentialAllocationUseType",
    "dbo.ResidentialAllocationCommodityPoolHistory",
    "dbo.ResidentialBonusUnitCommodityPoolTransfer",
    "dbo.ShorezoneAllocation", "dbo.ShorezoneAllocationType",
    # Commodities
    "dbo.Commodity", "dbo.CommodityPool", "dbo.CommodityPoolDisbursement",
    "dbo.CommodityUnitType", "dbo.TransactionTypeCommodity",
    "dbo.CommodityConvertedToCommodity",
    # TDR
    "dbo.TdrListing", "dbo.TdrListingStatus", "dbo.TdrListingType",
    "dbo.TdrTransaction", "dbo.TdrTransactionAllocation",
    "dbo.TdrTransactionAllocationAssignment",
    "dbo.TdrTransactionTransfer", "dbo.TdrTransactionConversion",
    "dbo.TdrTransactionConversionWithTransfer",
    "dbo.TdrTransactionLandBankAcquisition",
    "dbo.TdrTransactionLandBankTransfer",
    "dbo.TdrTransactionShorezoneAllocation",
    "dbo.TdrTransactionStateHistory",
    "dbo.LandBank",
    # Deed restrictions
    "dbo.DeedRestriction", "dbo.DeedRestrictionType", "dbo.DeedRestrictionStatus",
    "dbo.DeedRestrictionDeedRestrictionType",
    # IPES / Land capability
    "dbo.IpesScore", "dbo.IpesScoreStatus", "dbo.IpesScoreParcelInformation",
    "dbo.LandCapabilityType", "dbo.ParcelLandCapabilityVerification",
    "dbo.ParcelLandCapabilityBaileyRating",
    # Inventory
    "dbo.ParcelCommodityInventory",
    # Notable views
    "dbo.vGeoServerAllParcels",
    "dbo.vGeoServerParcelDevelopmentRightTransfers",
    "dbo.vParcelCurrentInventoryByCommodity",
    "dbo.vTransactedAndBankedCommodities",
}


def mermaid_safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def trim_type(t: str, max_len: int | None) -> str:
    if max_len and max_len > 0 and t in ("varchar", "nvarchar", "char", "nchar"):
        return f"{t}({max_len})"
    return t


def build_corral_block(schema: dict) -> str:
    tables = [t for t in schema["tables"] if f"{t['schema']}.{t['name']}" in CORRAL_FOCUS]
    tbl_names = {f"{t['schema']}.{t['name']}" for t in tables}
    lines = ["```mermaid", "erDiagram"]
    for t in tables:
        ent = mermaid_safe(t["name"])
        pks = set(t.get("primary_key") or [])
        lines.append(f"    {ent} {{")
        for c in t["columns"]:
            typ = mermaid_safe(c["type"])
            marker = " PK" if c["name"] in pks else ""
            lines.append(f"        {typ} {mermaid_safe(c['name'])}{marker}")
        lines.append("    }")
    for fk in schema["foreign_keys"]:
        if fk["parent"] not in tbl_names or fk["ref"] not in tbl_names:
            continue
        p = mermaid_safe(fk["parent"].split(".", 1)[1])
        r = mermaid_safe(fk["ref"].split(".", 1)[1])
        lines.append(f"    {r} ||--o{{ {p} : \"{fk['parent_column']} -> {fk['ref_column']}\"")
    lines.append("```")
    return "\n".join(lines)


def build_webservices_block(services: list[dict]) -> str:
    lines = ["```mermaid", "erDiagram"]
    for s in services:
        probe = s.get("probe") or {}
        if probe.get("status") != "ok":
            continue
        ent = mermaid_safe("WS_" + s["name"])
        lines.append(f"    {ent} {{")
        for fname, ftype in (probe.get("fields") or {}).items():
            lines.append(f"        {mermaid_safe(ftype)} {mermaid_safe(fname)}")
        lines.append("    }")
    lines.append("```")
    return "\n".join(lines)


SPREADSHEETS = [
    {
        "path": "data/raw_data/ExistingResidential_2012_2025_unstacked.csv",
        "domain": "Units (RU)",
        "key_cols": "APN, Final2012..Final2025",
        "consumed_by": "parcel_development_history_etl/steps/s02_load_csv.py",
    },
    {
        "path": "data/raw_data/TouristUnits_2012to2025.csv",
        "domain": "Units (TAU)",
        "key_cols": "APN, CY2012..CY2025",
        "consumed_by": "parcel_development_history_etl/steps/s04b_update_tourist_commercial.py",
    },
    {
        "path": "data/raw_data/CommercialFloorArea_2012to2025.csv",
        "domain": "Units (CFA sqft)",
        "key_cols": "APN, CY2012..CY2025",
        "consumed_by": "parcel_development_history_etl/steps/s04b_update_tourist_commercial.py",
    },
    {
        "path": "data/raw_data/apn_genealogy_tahoe.csv",
        "domain": "Genealogy (consolidated)",
        "key_cols": "apn_old, apn_new, change_year, source",
        "consumed_by": "parcel_development_history_etl/steps/s02b_genealogy.py",
    },
    {
        "path": "data/raw_data/apn_genealogy_master.csv",
        "domain": "Genealogy (manual master)",
        "key_cols": "old_apn, new_apn, change_year, change_type, is_primary",
        "consumed_by": "parcel_development_history_etl/scripts/build_genealogy_master.py",
    },
    {
        "path": "data/raw_data/apn_genealogy_accela.csv",
        "domain": "Genealogy (Accela)",
        "key_cols": "old_apn, new_apn, change_year",
        "consumed_by": "parcel_development_history_etl/scripts/parse_genealogy_sources.py",
    },
    {
        "path": "data/raw_data/apn_genealogy_ltinfo.csv",
        "domain": "Genealogy (LTinfo)",
        "key_cols": "old_apn, new_apn, change_year",
        "consumed_by": "parcel_development_history_etl/scripts/parse_genealogy_sources.py",
    },
    {
        "path": "data/raw_data/apn_genealogy_spatial.csv",
        "domain": "Genealogy (spatial overlap)",
        "key_cols": "old_apn, new_apn, change_year",
        "consumed_by": "parcel_development_history_etl/scripts/build_spatial_genealogy.py",
    },
    {
        "path": "data/raw_data/Transactions_InactiveParcels.csv",
        "domain": "TDR / inactive APN mapping",
        "key_cols": "InactiveAPN, ActiveAPN, TransactionNumber",
        "consumed_by": "general/cumulative_accounting.py",
    },
    {
        "path": "data/raw_data/Transactions_Allocations_Details.xlsx",
        "domain": "TDR / allocation details",
        "key_cols": "TransactionNumber, AllocationID, APN",
        "consumed_by": "general/cumulative_accounting.py",
    },
    {
        "path": "data/permit_data/Allocation_Tracking.xlsx",
        "domain": "Allocations (RBU)",
        "key_cols": "Jurisdiction, Year, RBU_Allocated, RBU_Used",
        "consumed_by": "general/cumulative_accounting.py",
    },
    {
        "path": "data/permit_data/ADU Tracking.xlsx",
        "domain": "Accessory Dwelling Units",
        "key_cols": "APN, Permit#, ApprovalDate",
        "consumed_by": "general/cumulative_accounting.py",
    },
    {
        "path": "data/permit_data/HousingDeedRestrictions_All.csv",
        "domain": "Housing / deed restrictions",
        "key_cols": "Permit#, APN, TRPA_AllocationID, HousingType, Units",
        "consumed_by": "general/cumulative_accounting.py",
    },
    {
        "path": "data/permit_data/Detailed Workflow History.xlsx",
        "domain": "Permit workflow",
        "key_cols": "Permit#, WorkflowStep, StatusDate",
        "consumed_by": "(reference / manual review)",
    },
    {
        "path": "data/permit_data/Full RBU History Feb 2024.xlsx",
        "domain": "RBU history snapshot",
        "key_cols": "APN, AllocationID, Year",
        "consumed_by": "(reference / manual review)",
    },
    {
        "path": "data/permit_data/PermitData_ElDorado_040124.csv",
        "domain": "County permits",
        "key_cols": "APN, Permit#, IssueDate, Units",
        "consumed_by": "general/cumulative_accounting.py",
    },
    {
        "path": "data/permit_data/PermitData_Placer_040924.csv",
        "domain": "County permits",
        "key_cols": "APN, Permit#, IssueDate, Units",
        "consumed_by": "general/cumulative_accounting.py",
    },
    {
        "path": "data/permit_data/PermitData_CSLT_040224.csv",
        "domain": "County permits",
        "key_cols": "APN, Permit#, IssueDate, Units",
        "consumed_by": "general/cumulative_accounting.py",
    },
    {
        "path": "data/raw_data/FINAL-2026-Cumulative-Accounting_ALL_04032026.xlsx",
        "domain": "Accounting snapshot",
        "key_cols": "Jurisdiction, Year, RU, TAU, CFA",
        "consumed_by": "(output / review)",
    },
]


def build_spreadsheets_block() -> str:
    lines = ["| Path | Domain | Key columns | Consumed by |",
             "|---|---|---|---|"]
    for s in SPREADSHEETS:
        lines.append(f"| `{s['path']}` | {s['domain']} | {s['key_cols']} | `{s['consumed_by']}` |")
    return "\n".join(lines)


def build_webservices_table(services: list[dict]) -> str:
    lines = ["| Endpoint | Records | Purpose | Likely Corral backing | Token required |",
             "|---|---:|---|---|:---:|"]
    backing = {
        "GetAllParcels": "dbo.Parcel, dbo.vGeoServerAllParcels",
        "GetTransactedAndBankedDevelopmentRights": "dbo.TdrTransaction*, dbo.ParcelPermitBankedDevelopmentRight, dbo.vGeoServerParcelDevelopmentRightTransfers, dbo.vTransactedAndBankedCommodities",
        "GetBankedDevelopmentRights": "dbo.ParcelPermitBankedDevelopmentRight, dbo.vTransactedAndBankedCommodities",
        "GetParcelDevelopmentRightsForAccela": "dbo.ParcelCommodityInventory, dbo.vParcelCurrentInventoryByCommodity",
        "GetDeedRestrictedParcels": "dbo.DeedRestriction, dbo.DeedRestrictionType, dbo.DeedRestrictionStatus",
        "GetParcelIPESScores": "dbo.IpesScore, dbo.IpesScoreParcelInformation",
        "GetAccelaRecordDetailsExcel": "dbo.AccelaCAPRecord, dbo.AccelaCAPRecordDocument (per-record export)",
    }
    for s in services:
        p = s.get("probe") or {}
        rc = p.get("record_count")
        rc_str = f"{rc:,}" if isinstance(rc, int) else "—"
        yes = "Yes"
        lines.append(
            f"| `{s['name']}` | {rc_str} | {s['description']} | {backing.get(s['name'], '—')} | {yes} |"
        )
    return "\n".join(lines)


CROSS_KEY_MAP = """
| Key | Corral | LTinfo web service | Spreadsheets |
|---|---|---|---|
| **APN** (Parcel ID) | `dbo.Parcel.ParcelNumber` — referenced by ~60+ tables | Every JSON endpoint returns `APN` | Every `*.csv` / `*.xlsx` row is keyed on APN |
| **Accela Record ID / CAP ID** | `dbo.AccelaCAPRecord.AccelaCAPRecordID`, link table `dbo.ParcelAccelaCAPRecord` | `GetTransactedAndBankedDevelopmentRights.AccelaID`, `GetAccelaRecordDetailsExcel/{GUID}` | `HousingDeedRestrictions_All.csv.AccelaDoc` |
| **TRPA Allocation ID** | `dbo.ResidentialAllocation.ResidentialAllocationID` (+ `dbo.TdrTransactionAllocation`) | Implicit in `GetTransactedAndBankedDevelopmentRights` via `TransactionNumber` | `HousingDeedRestrictions_All.csv.TRPA_AllocationID`, `Transactions_Allocations_Details.xlsx` |
| **TDR Transaction #** | `dbo.TdrTransaction.TransactionNumber` | `GetTransactedAndBankedDevelopmentRights.TransactionNumber` | `Transactions_InactiveParcels.csv.TransactionNumber` |
| **Jurisdiction Permit #** | `dbo.ParcelPermit.JurisdictionPermitNumber` | `GetTransactedAndBankedDevelopmentRights.JurisdictionPermitNumber` | County permit CSVs `Permit#` |
| **Land Capability / IPES** | `dbo.LandCapabilityType`, `dbo.IpesScore` | `GetParcelIPESScores`, `LandCapability` field on dev-rights endpoints | IPES referenced in `FINAL-*-Cumulative-Accounting*.xlsx` |
| **Commodity type** (RU / TAU / CFA / RFA / TFA / PRUU / MFRUU / SFRUU) | `dbo.Commodity`, `dbo.CommodityPool`, `dbo.CommodityUnitType` | `GetAllParcels` exposes one column per type; dev-rights endpoints carry `DevelopmentRight` string | `ExistingResidential_*`, `TouristUnits_*`, `CommercialFloorArea_*` CSVs |
| **Parcel genealogy** (old → new APN) | `dbo.ParcelGenealogy` (2,405 rows) | *(not exposed)* | `apn_genealogy_tahoe.csv` merges Corral + Accela + LTinfo + spatial sources |
| **Deed restriction** | `dbo.DeedRestriction`, `dbo.ParcelPermitDeedRestriction` | `GetDeedRestrictedParcels` | `HousingDeedRestrictions_All.csv`, `DeedRestricted_HousingUnits.csv` |
"""


INTRO = """# Development & Development-Rights ERD (Tahoe / TRPA)

Generated from three disparate sources to inform the design of a unified schema.

- **SQL Server `Corral`** on `sql24` — 573 tables / 1,041 FKs, read-only mirror of the system of record. Full table list: [corral_tables.md](corral_tables.md). Machine-readable schema dump: [corral_schema.json](corral_schema.json).
- **LTinfo web services** — public JSON endpoints at `https://www.laketahoeinfo.org/WebServices/*`, token-gated. Full probe results: [ltinfo_services.json](ltinfo_services.json).
- **Repo spreadsheets** — CSV/XLSX inputs under `data/` that feed the parcel-history and cumulative-accounting ETLs.

Scope of the diagrams below: development, allocations, TDR transactions, deed restrictions, IPES / land capability, commodity pools, parcel genealogy. The Corral ERD is a curated ~50-table subset; the remainder is catalogued in `corral_tables.md`.

Regenerate with:
```
python erd/dump_corral_schema.py
python erd/inventory_ltinfo_services.py
python erd/build_erd.py
```
"""


def main() -> None:
    schema = json.loads((ERD_DIR / "corral_schema.json").read_text())
    services = json.loads((ERD_DIR / "ltinfo_services.json").read_text())
    parts = [
        INTRO,
        "## 1. Corral SQL Server — curated ERD",
        "",
        build_corral_block(schema),
        "",
        "## 2. LTinfo web-service response entities",
        "",
        build_webservices_block(services),
        "",
        "### Web-services inventory",
        "",
        build_webservices_table(services),
        "",
        "## 3. Repo spreadsheet inventory",
        "",
        build_spreadsheets_block(),
        "",
        "## 4. Cross-system key map",
        CROSS_KEY_MAP,
    ]
    out = ERD_DIR / "development_rights_erd.md"
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
