# erd/

ERD tooling, existing-system inventory, gap analysis, and the **proposed
schema** for a new TRPA development-rights tracking store.

## Read first

- **[target_schema.md](./target_schema.md)** — the proposed ERD, anchored
  on the TRPA Cumulative Accounting framework (5 buckets per commodity per
  jurisdiction, 7 movement types). This is the artifact under active
  iteration.
- **[.claude/skills/trpa-cumulative-accounting/SKILL.md](../.claude/skills/trpa-cumulative-accounting/SKILL.md)**
  — the vocabulary the proposed schema is built on.
- **[development_rights_erd.html](./development_rights_erd.html)** — a
  browser viewer with pan/zoom that shows both the **existing** upstream
  systems (Corral, LTinfo) and the **proposed** new schema as tabs.

## What each file is for

### Proposed schema (the active work)
- **[target_schema.md](./target_schema.md)** — proposed ERD + design principles + loading strategy

### Existing systems (context / inputs)
- [development_rights_erd.md](./development_rights_erd.md) — Corral + LTinfo + spreadsheet inventory
- [corral_schema.json](./corral_schema.json) — full 573-table Corral schema dump
- [corral_tables.md](./corral_tables.md) — human-readable Corral table list
- [ltinfo_services.json](./ltinfo_services.json) — LTinfo JSON endpoint probes
- [raw_data_inventory.json](./raw_data_inventory.json) — `data/raw_data/` file catalog

### Gap analysis + validation
- [raw_data_vs_corral.md](./raw_data_vs_corral.md) — what's in the spreadsheets vs Corral
- [validation_findings.md](./validation_findings.md) — empirical tests of reproducibility claims
- [validate_auditlog_replay.json](./validate_auditlog_replay.json) — AuditLog-replay validation output
- [validate_transactions_view.json](./validate_transactions_view.json) — transaction-view validation output

### Regeneration scripts (read-only, SELECT only)
- [db_corral.py](./db_corral.py) — SQLAlchemy read-only engine (Windows Auth + ApplicationIntent=ReadOnly)
- [dump_corral_schema.py](./dump_corral_schema.py) — reflect Corral → `corral_schema.json` + `corral_tables.md`
- [inventory_ltinfo_services.py](./inventory_ltinfo_services.py) — probe LTinfo endpoints → `ltinfo_services.json`
- [compare_raw_data_to_corral.py](./compare_raw_data_to_corral.py) — catalog `data/raw_data/` → `raw_data_inventory.json`
- [validate_auditlog_replay.py](./validate_auditlog_replay.py) — test AuditLog-replay claim
- [validate_transactions_view.py](./validate_transactions_view.py) — test transactions-view claim
- [build_erd.py](./build_erd.py) — assemble `development_rights_erd.md`
- [build_erd_html.py](./build_erd_html.py) — render `development_rights_erd.html` (tabs for existing + proposed)

## Regenerate

Uses the ArcGIS Pro Python env (`arcgispro-py3`) and a `.env` at the repo root
with `CORRAL_SERVER`, `CORRAL_DATABASE`, and `LTINFO_API_KEY`.

```
python erd/dump_corral_schema.py        # refresh Corral schema dump
python erd/inventory_ltinfo_services.py # refresh LTinfo service catalog
python erd/compare_raw_data_to_corral.py # refresh raw_data inventory
python erd/build_erd.py                 # rebuild development_rights_erd.md
python erd/build_erd_html.py            # rebuild development_rights_erd.html (picks up target_schema.md)
```

Edit `target_schema.md` directly to iterate on the proposed ERD; re-run
`build_erd_html.py` to pick up the new Mermaid blocks as tabs in the viewer.

## Architecture context

- **Corral SQL Server** (`sql24/Corral`) is the LTinfo backend. Our
  connection is a **Feb-2024 backup snapshot** — use for schema reference,
  not for live reads.
- **LTinfo web services** (`https://www.laketahoeinfo.org/WebServices/*`)
  are the live read layer over Corral. Token-gated.
- **GIS enterprise GDB** (future; today `C:\GIS\Scratch.gdb\Parcel_History_Attributed`)
  is the spatial source of truth for existing development per parcel × year.
- **Accela** — permit workflow system of record; today accessed via Corral's
  `AccelaCAPRecord` bridge.
- **`data/raw_data/` spreadsheets** — Ken's authoritative sources that fill
  gaps the above systems don't hold; loaded into the new DB as ETL inputs.
