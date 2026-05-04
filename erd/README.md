# erd/ — Proposed schema for TRPA development-rights tracking

> **Status: draft proposal, ready for team review.**
> **Audience: TRPA dev team, Ken, Dan, partner jurisdictions, anyone reviewing the schema design.**

This folder holds the proposal for a new set of tables that fold into the
existing SDE SQL backend (alongside Corral and the enterprise GIS
geodatabase) to drive three v1 dashboards:

1. **Cumulative accounting report** (annual; replaces the XLSX)
2. **Allocation drawdown dashboard** (stacked area by pool × year)
3. **Parcel history lookup** (per-APN, with change log)

All of this is anchored on the TRPA Cumulative Accounting framework
(TRPA Code §16.8.2). The vocabulary is documented in the
[`cumulative_accounting_reference.md`](./cumulative_accounting_reference.md)
(plain-markdown copy of the Claude skill) so future sessions (and reviewers) share the same terms.

---

## Start here

**[next_steps.md](./next_steps.md)** — 5-minute read for a working
session. What we're building, where the data comes from, and the
questions we need to close before DDL.

**[target_schema.md](./target_schema.md)** — full proposal. Read after
`next_steps.md` if you want the detail. It has:

- Design principles (never duplicate Corral; five-bucket model; ETL-only writes)
- 5 Mermaid ERDs (reference entities · new core tables · movement ledger · permit completion · dashboard outputs)
- Loading strategy (where each table's data comes from)
- Open questions for the team
- Final table list

**[development_rights_erd.html](./development_rights_erd.html)** — browser-friendly
viewer. 6 tabs total: 2 showing existing systems (Corral, LTinfo), 4 showing
the proposed new schema. Pan/zoom with scroll/drag. Dark theme.

---

## Reading order by role

**If you're reviewing the schema design (Dan, DB admins, architecture):**
1. [target_schema.md](./target_schema.md) — the proposal
2. The `trpa-cumulative-accounting` skill for vocabulary
3. Go straight to the "Questions for the team" section at the end

**If you want to know why these tables and not others (technical reviewers):**
1. [raw_data_vs_corral.md](./raw_data_vs_corral.md) — what's in the spreadsheets that Corral doesn't hold
2. [validation_findings.md](./validation_findings.md) — empirical gap analysis between Corral and the XLSX
3. [xlsx_decomposition.md](./xlsx_decomposition.md) — column-by-column map from the XLSX into the proposed schema

**If you're responsible for Corral, LTinfo, or the GIS systems:**
1. [development_rights_erd.md](./development_rights_erd.md) — existing-systems inventory
2. [target_schema.md](./target_schema.md) *Loading strategy* section
3. [target_schema.md](./target_schema.md) *Reference entities — reused from Corral* table

**If you just want the diagrams:**
- Open [development_rights_erd.html](./development_rights_erd.html) in a browser.

---

## Top questions we need the team to answer

Full list in [target_schema.md](./target_schema.md). The three highest-priority:

1. **ADU modeling** — is ADU a third value in `ResidentialAllocationUseType`, a
   flag on the allocation, or a separate concept linked to a parent unit?
2. **`PermitAllocation` linkage strategy** — Corral has no direct FK between
   `ParcelPermit` and `ResidentialAllocation`; the AccelaID bridge is only
   32% populated. Prioritize back-filling in Corral, or accept the crosswalk
   limitations?
3. **Dashboard refresh cadence** — can we commit to nightly recomputation for
   `PoolDrawdownYearly` and `CumulativeAccountingSnapshot`?

---

## What each file in this folder is

### The proposal
| File | Status | Purpose |
|---|---|---|
| [target_schema.md](./target_schema.md) | **Draft — for team review** | The proposal itself. ERD + loading strategy + open questions. |
| [proposed_dashboards.md](./proposed_dashboards.md) | Draft — for team review | Dashboard & visualization proposal (~25 candidates in 8 clusters); extends the existing `allocation_drawdown.html` prototype. |
| [dashboards_to_schema_trace.md](./dashboards_to_schema_trace.md) | Active | Backward design from built dashboards through view contracts to schema columns. 14 open gaps roll-up against `target_schema.md`. |
| [genealogy_track.md](./genealogy_track.md) | Active | **Track A** — APN canonicalization + genealogy event sourcing + resolver. The substrate every other track joins through. |
| [allocation_track.md](./allocation_track.md) | Active | **Track B** — Allocation accounting layer: schema, view contracts, 5 built dashboards, 14 open gaps. The public-facing reporting work. |
| [qa_corrections_track.md](./qa_corrections_track.md) | Active | **Track C** — Ken's CA Changes XLSX → schema sidecar + loader + reconciliation + dashboard E1. Full track docs. |
| [cumulative_accounting_reference.md](./cumulative_accounting_reference.md) | Reference | TRPA Cumulative Accounting framework (plain-markdown copy of the Claude skill) — vocabulary, bucket model, movement types, pool structure. |
| [development_rights_erd.html](./development_rights_erd.html) | Draft | Browser viewer for all ERDs (existing + proposed). |

### Supporting analysis (context for the proposal)
| File | Status | Purpose |
|---|---|---|
| [development_rights_erd.md](./development_rights_erd.md) | Done | Inventory of the existing upstream systems (Corral + LTinfo + spreadsheets). |
| [raw_data_vs_corral.md](./raw_data_vs_corral.md) | Done | Gap analysis — what's in the transactions spreadsheet that Corral doesn't hold. |
| [validation_findings.md](./validation_findings.md) | Done | Empirical tests against the Feb-2024 Corral snapshot; quantifies what the spreadsheet covers beyond Corral views. |
| [xlsx_decomposition.md](./xlsx_decomposition.md) | Done | Column-by-column map from `2025 Transactions and Allocations Details.xlsx` into the proposed schema. |
| [next_steps.md](./next_steps.md) | Draft | 5-minute working-session brief: architecture summary + questions to close before DDL. |

### Machine-readable data (regenerable)
| File | Purpose |
|---|---|
| [corral_schema.json](./corral_schema.json) | Full Corral schema dump (573 tables, 1,041 FKs) |
| [corral_tables.md](./corral_tables.md) | Human-readable Corral table list with row counts |
| [ltinfo_services.json](./ltinfo_services.json) | Probed LTinfo JSON endpoint responses |
| [raw_data_inventory.json](./raw_data_inventory.json) | `data/raw_data/` file catalog |
| [validate_auditlog_replay.json](./validate_auditlog_replay.json) | AuditLog-replay validation results |
| [validate_transactions_view.json](./validate_transactions_view.json) | Transactions-view validation results |

### Regeneration scripts (read-only, SELECT only)
| File | Purpose |
|---|---|
| [db_corral.py](./db_corral.py) | SQLAlchemy read-only engine (Windows Auth + `ApplicationIntent=ReadOnly`) |
| [dump_corral_schema.py](./dump_corral_schema.py) | Refresh Corral schema dump |
| [inventory_ltinfo_services.py](./inventory_ltinfo_services.py) | Probe LTinfo endpoints |
| [compare_raw_data_to_corral.py](./compare_raw_data_to_corral.py) | Catalog `data/raw_data/` |
| [validate_auditlog_replay.py](./validate_auditlog_replay.py) | Test AuditLog-replay claim |
| [validate_transactions_view.py](./validate_transactions_view.py) | Test transactions-view claim |
| [build_erd.py](./build_erd.py) | Assemble `development_rights_erd.md` |
| [build_erd_html.py](./build_erd_html.py) | Render `development_rights_erd.html` with tabs for existing + proposed schema |

---

## Architecture context (one paragraph)

Corral (`sql24/Corral`) is the LTinfo web-application backend, hosted on an
SDE-registered SQL Server instance. Our read connection is a Feb-2024 backup
snapshot — live reads for any production use case go through the LTinfo JSON
web services at `https://www.laketahoeinfo.org/WebServices/*`. The future
Parcel Development History REST service (patterned on
[`Existing_Development/MapServer/2`](https://maps.trpa.org/server/rest/services/Existing_Development/MapServer/2))
will live on the same SDE instance and become the authoritative spatial
source of truth for existing development per parcel per year. **The new
tables in this proposal fold into that same SDE instance** — no parallel
database, no cross-DB bridging. Ken's `data/raw_data/` spreadsheets fill the
gaps those systems don't hold (pre-2012 baseline, Year Built, TRPA/MOU
project IDs, completion status) and get loaded via ETL into the new tables.
Shorezone (Mooring, Pier) is out of scope — handled by a separate system.

---

## Regenerate

Uses the ArcGIS Pro Python env (`arcgispro-py3`) and a `.env` at the repo root
with `CORRAL_SERVER`, `CORRAL_DATABASE`, and `LTINFO_API_KEY`.

```
python erd/dump_corral_schema.py         # refresh Corral schema dump
python erd/inventory_ltinfo_services.py  # refresh LTinfo service catalog
python erd/compare_raw_data_to_corral.py # refresh raw_data inventory
python erd/build_erd.py                  # rebuild development_rights_erd.md
python erd/build_erd_html.py             # rebuild development_rights_erd.html
```

Edit `target_schema.md` directly to iterate on the proposal; re-run
`build_erd_html.py` to pick up new Mermaid blocks as tabs in the viewer.

---

## How to give feedback

- **On specific entities or fields**: comment on the relevant section of
  [target_schema.md](./target_schema.md).
- **On the open questions**: reply with your preferred option (or a new one).
- **On the overall shape**: look at the HTML viewer; comment on what's
  missing, duplicated, or in the wrong place.
- **On how XLSX columns land in the schema**: see [xlsx_decomposition.md](./xlsx_decomposition.md).
