# erd/

Tooling + outputs for the unified development-rights ERD across the `Corral`
SQL Server DB, LTinfo web services, and repo spreadsheets.

## View the diagram
Open [development_rights_erd.html](./development_rights_erd.html) in a browser
(pan/zoom, tab switcher, dark theme). Or read
[development_rights_erd.md](./development_rights_erd.md) if you prefer markdown.

## Regenerate from source

Uses the ArcGIS Pro Python env (`arcgispro-py3`) and a `.env` at the repo root
with `CORRAL_SERVER`, `CORRAL_DATABASE`, and `LTINFO_API_KEY`.

```
python erd/dump_corral_schema.py        # reflects Corral -> corral_schema.json + corral_tables.md
python erd/inventory_ltinfo_services.py # probes LTinfo JSON endpoints -> ltinfo_services.json
python erd/build_erd.py                 # assembles development_rights_erd.md
python erd/build_erd_html.py            # renders standalone development_rights_erd.html
```

The SQL helper ([db_corral.py](./db_corral.py)) uses Windows Auth and
`ApplicationIntent=ReadOnly`; no write paths are exposed.
