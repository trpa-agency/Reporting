# erd/ - data model for TRPA development-rights tracking

> **Status: architecture decided; the `Cumulative_Accounting` service is live on maps.trpa.org.**
> **Audience: TRPA dev team, TRPA leadership, partner jurisdictions, anyone working on the cumulative-accounting data layer.**

This folder holds the data-model work behind the annual TRPA cumulative
accounting cycle (TRPA Code §16.8.2). The architecture is no longer a
proposal under review - it has been decided and partly built:

- **Two valid data sources.** The TRPA Enterprise Geodatabase (published
  as REST services on `maps.trpa.org`) and the LT Info web services (for
  Corral-origin data).
- **The `Cumulative_Accounting` REST service is live** on `maps.trpa.org`
  with six populated layers/tables (Parcel Development History, Tahoe APN
  Genealogy, Residential Unit Inventory, Allocations 1987 Regional Plan,
  Residential Allocations 2012 Regional Plan, Development Right Pool
  Balance Report) and three more incoming: Development Right Transactions,
  Banked Development Rights, and Transacted and Banked Development Rights
  (the LT Info transaction/banking trio, refreshed nightly via the staging
  ETL; the older `Development_Rights_Transacted_and_Banked` REST service is
  being deprecated as a tagged copy of the same Corral data).

The vocabulary for the accounting framework is documented in the
`trpa-cumulative-accounting` Claude skill (a plain-markdown copy is kept at
[`_archive/cumulative_accounting_reference.md`](./_archive/cumulative_accounting_reference.md)
for team members who don't use Claude).

An earlier round of design work proposed a different shape - a set of new
tables resident inside Corral with foreign keys into it. That approach was
**superseded**: the real tables live in the TRPA Enterprise GDB and the
service is already live with a different design. Those proposal docs have
been moved to [`_archive/`](./_archive/) so the folder reflects current
reality. See "Archived / superseded" below.

---

## Start here

**[system_of_record_roadmap.md](./system_of_record_roadmap.md)** - the
architecture. Why the hand-assembled spreadsheets are the fragile root, the
three kinds of hand-crafted artifact (a system already has it / Corral has
the raw events / a human genuinely is the system of record), the target
layered architecture, and the phased path to a system of record for every
data element.

**[questions_for_analyst.md](./questions_for_analyst.md)** - the open
questions only the analyst can answer: data provenance, domain judgment,
which numbers are tracked in a system versus carried by hand. Collected as
they surface during the system-of-record work.

---

## Reading order by role

**If you want the architecture and the plan:**
1. [system_of_record_roadmap.md](./system_of_record_roadmap.md) - the portfolio-level plan
2. The `trpa-cumulative-accounting` skill for vocabulary
3. [questions_for_analyst.md](./questions_for_analyst.md) - what's still open

**If you want to know why the data layer is shaped this way (technical reviewers):**
1. [raw_data_vs_corral.md](./raw_data_vs_corral.md) - what's in the spreadsheets that Corral doesn't hold
2. [validation_findings.md](./validation_findings.md) - empirical gap analysis between Corral and the XLSX
3. [xlsx_decomposition.md](./xlsx_decomposition.md) - column-by-column map of the analyst's transactions XLSX

**If you're responsible for Corral, LT Info, or the GIS systems:**
1. [development_rights_erd.md](./development_rights_erd.md) - existing-systems inventory (Corral + LT Info + spreadsheets)
2. [inventory_tables_erd.md](./inventory_tables_erd.md) - the analyst-facing inventory tables built in the 2026 cycle

---

## What each file in this folder is

### Current

| File | Status | Purpose |
|---|---|---|
| [system_of_record_roadmap.md](./system_of_record_roadmap.md) | Current | **The architecture.** Portfolio-level plan for retiring every hand-assembled xlsx so each data element traces to a system of record. Sorts the analyst-delivered inputs into three types and lays out a phased migration. |
| [questions_for_analyst.md](./questions_for_analyst.md) | Current | **Open questions only the analyst can answer** - data provenance, domain judgment, which numbers are tracked in a system versus carried by hand. Collected as they surface during the system-of-record work. |
| [regional_plan_allocations_service.md](./regional_plan_allocations_service.md) | Active | Pool-balance sibling to the residential allocation grid spec. How the hand-assembled `All Regional Plan Allocations Summary.xlsx` gets retired: stage `GetDevelopmentRightPoolBalanceReport` into `LTInfo_PoolBalance`, UNION the live layer 3 (1987 reference), publish through `Cumulative_Accounting`. |
| [residential_allocation_grid_service.md](./residential_allocation_grid_service.md) | Active | Web-service spec for the residential allocation grid - the SQL (reverse-engineered, tested against `Corral_2026`) to replace the hand-exported `residentialAllocationGridExport_fromAnalyst.xlsx`. Ready to hand to the LT Info team. |
| [inventory_tables_erd.md](./inventory_tables_erd.md) | Current | Analyst-facing inventory tables (Residential Units / Buildings / PDH 2025 join) with field dictionaries. Built in the 2026 cycle; feeds the live Residential Unit Inventory layer. |

### Supporting analysis (the evidence base)

Still-valid analysis and inventory. This is the evidence the architecture
rests on, not superseded thinking - leave it in place.

| File | Status | Purpose |
|---|---|---|
| [development_rights_erd.md](./development_rights_erd.md) | Done | Inventory of the existing upstream systems (Corral + LT Info + spreadsheets). |
| [development_rights_erd.html](./development_rights_erd.html) | Done | Browser viewer for the existing-systems ERDs. |
| [raw_data_vs_corral.md](./raw_data_vs_corral.md) | Done | Gap analysis - what's in the transactions spreadsheet that Corral doesn't hold. |
| [validation_findings.md](./validation_findings.md) | Done | Empirical tests against the Feb-2024 Corral snapshot; quantifies what the spreadsheet covers beyond Corral views. |
| [xlsx_decomposition.md](./xlsx_decomposition.md) | Done | Column-by-column map from `2025 Transactions and Allocations Details.xlsx`. |

### Machine-readable data (regenerable)

| File | Purpose |
|---|---|
| [corral_schema.json](./corral_schema.json) | Full Corral schema dump (573 tables, 1,041 FKs) |
| [corral_tables.md](./corral_tables.md) | Human-readable Corral table list with row counts |
| [ltinfo_services.json](./ltinfo_services.json) | Probed LT Info JSON endpoint responses |
| [raw_data_inventory.json](./raw_data_inventory.json) | `data/raw_data/` file catalog |
| [validate_auditlog_replay.json](./validate_auditlog_replay.json) | AuditLog-replay validation results |
| [validate_transactions_view.json](./validate_transactions_view.json) | Transactions-view validation results |

### Scripts (read-only, SELECT only)

| File | Purpose |
|---|---|
| [probe_corral_2026.py](./probe_corral_2026.py) | Read-only investigation against the current `Corral_2026` copy - explains the allocation-grid row-count gap |
| [db_corral.py](./db_corral.py) | SQLAlchemy read-only engine (Windows Auth + `ApplicationIntent=ReadOnly`) |
| [dump_corral_schema.py](./dump_corral_schema.py) | Refresh Corral schema dump |
| [inventory_ltinfo_services.py](./inventory_ltinfo_services.py) | Probe LT Info endpoints |
| [compare_raw_data_to_corral.py](./compare_raw_data_to_corral.py) | Catalog `data/raw_data/` |
| [validate_auditlog_replay.py](./validate_auditlog_replay.py) | Test AuditLog-replay claim |
| [validate_transactions_view.py](./validate_transactions_view.py) | Test transactions-view claim |
| [build_erd.py](./build_erd.py) | Assemble `development_rights_erd.md` |
| [build_erd_html.py](./build_erd_html.py) | Render `development_rights_erd.html` |
| [build_md_pages.py](./build_md_pages.py) | Render the `.md` docs in this folder to standalone `.html` |

### Archived / superseded

These proposed an earlier architecture - a set of new tables resident
inside Corral with foreign keys into it. That approach was superseded; the
real tables live in the TRPA Enterprise GDB and the `Cumulative_Accounting`
service is already live with a different design. Kept in
[`_archive/`](./_archive/) for history. Each carries a `SUPERSEDED` banner
at the top pointing back to the current source of truth.

| File | Why archived |
|---|---|
| [_archive/target_schema.md](./_archive/target_schema.md) | The superseded proposal itself - new Corral-resident tables, ERDs, loading strategy, open questions. |
| [_archive/dashboards_to_schema_trace.md](./_archive/dashboards_to_schema_trace.md) | Traced built dashboards back through view contracts to `target_schema.md` columns; entirely anchored on the superseded schema. |
| [_archive/next_steps.md](./_archive/next_steps.md) | 5-minute working-session brief built around the superseded "cut DDL into Corral" plan. |
| [_archive/tracks_status.md](./_archive/tracks_status.md) | Combined Track A / B / C status, framed against the superseded schema as the destination. |
| [_archive/proposed_dashboards.md](./_archive/proposed_dashboards.md) | Earlier dashboard catalog (archived in a prior pass). |
| [_archive/allocation_track.md](./_archive/allocation_track.md), [_archive/genealogy_track.md](./_archive/genealogy_track.md), [_archive/qa_corrections_track.md](./_archive/qa_corrections_track.md) | Per-track docs later consolidated; archived in a prior pass. |
| [_archive/cumulative_accounting_reference.md](./_archive/cumulative_accounting_reference.md) | Plain-markdown copy of the `trpa-cumulative-accounting` skill; the skill is the source of truth. |

The `_archive/` folder also keeps `.html` renders of the archived docs.

---

## Architecture context (one paragraph)

The two valid data sources are the TRPA Enterprise Geodatabase (published
as REST services on `maps.trpa.org`) and the LT Info web services (for
Corral-origin data). Corral (`sql24/Corral`) is the LT Info web-application
backend; the repo's read connection is a backup snapshot, so live reads go
through the LT Info JSON web services at
`https://www.laketahoeinfo.org/WebServices/*`. The `Cumulative_Accounting`
REST service is live on `maps.trpa.org` with six populated layers/tables
(Parcel Development History, Tahoe APN Genealogy, Residential Unit Inventory,
Allocations 1987 Regional Plan, Residential Allocations 2012 Regional Plan,
Development Right Pool Balance Report) and three more incoming for the LT
Info transaction/banking trio (layers 6/7/8). The analyst's
`data/raw_data/` spreadsheets fill the gaps those systems don't hold
(pre-2012 baseline, year built, TRPA/MOU project IDs, completion status)
and get loaded via ETL. Shorezone (Mooring, Pier) is out of scope - handled
by a separate system.

---

## Regenerate

Uses the ArcGIS Pro Python env (`arcgispro-py3`) and a `.env` at the repo
root with `CORRAL_SERVER`, `CORRAL_DATABASE`, and `LTINFO_API_KEY`.

```
python erd/dump_corral_schema.py         # refresh Corral schema dump
python erd/inventory_ltinfo_services.py  # refresh LT Info service catalog
python erd/compare_raw_data_to_corral.py # refresh raw_data inventory
python erd/build_erd.py                  # rebuild development_rights_erd.md
python erd/build_erd_html.py             # rebuild development_rights_erd.html
python erd/build_md_pages.py             # rebuild the .html renders of the docs
```
