"""Dump Corral schema via INFORMATION_SCHEMA + sys catalogs to JSON and markdown.

Read-only: uses SELECTs only. Output is intermediate input for build_erd.py.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_corral import get_engine  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent


TABLES_SQL = """
SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA NOT IN ('sys','INFORMATION_SCHEMA')
ORDER BY TABLE_SCHEMA, TABLE_NAME
"""

COLUMNS_SQL = """
SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, ORDINAL_POSITION,
       DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA NOT IN ('sys','INFORMATION_SCHEMA')
ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
"""

PK_SQL = """
SELECT kcu.TABLE_SCHEMA, kcu.TABLE_NAME, kcu.COLUMN_NAME
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
  ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
 AND tc.TABLE_SCHEMA   = kcu.TABLE_SCHEMA
WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
"""

FK_SQL = """
SELECT
    fk.name                AS fk_name,
    sch_p.name             AS parent_schema,
    tp.name                AS parent_table,
    cp.name                AS parent_column,
    sch_r.name             AS ref_schema,
    tr.name                AS ref_table,
    cr.name                AS ref_column
FROM sys.foreign_keys fk
JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
JOIN sys.tables   tp     ON fkc.parent_object_id      = tp.object_id
JOIN sys.schemas  sch_p  ON tp.schema_id              = sch_p.schema_id
JOIN sys.columns  cp     ON fkc.parent_object_id      = cp.object_id
                         AND fkc.parent_column_id     = cp.column_id
JOIN sys.tables   tr     ON fkc.referenced_object_id  = tr.object_id
JOIN sys.schemas  sch_r  ON tr.schema_id              = sch_r.schema_id
JOIN sys.columns  cr     ON fkc.referenced_object_id  = cr.object_id
                         AND fkc.referenced_column_id = cr.column_id
ORDER BY fk_name, fkc.constraint_column_id
"""

ROWCOUNT_SQL = """
SELECT s.name AS schema_name, t.name AS table_name, SUM(p.rows) AS row_count
FROM sys.tables t
JOIN sys.schemas s ON t.schema_id = s.schema_id
JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0,1)
GROUP BY s.name, t.name
"""


def main() -> None:
    engine = get_engine()
    with engine.connect() as conn:
        tables = [dict(r._mapping) for r in conn.execute(text(TABLES_SQL))]
        columns = [dict(r._mapping) for r in conn.execute(text(COLUMNS_SQL))]
        pks = [dict(r._mapping) for r in conn.execute(text(PK_SQL))]
        fks = [dict(r._mapping) for r in conn.execute(text(FK_SQL))]
        rowcounts = {
            (r.schema_name, r.table_name): int(r.row_count or 0)
            for r in conn.execute(text(ROWCOUNT_SQL))
        }

    cols_by_tbl: dict[tuple, list] = defaultdict(list)
    for c in columns:
        cols_by_tbl[(c["TABLE_SCHEMA"], c["TABLE_NAME"])].append(
            {
                "name": c["COLUMN_NAME"],
                "ordinal": c["ORDINAL_POSITION"],
                "type": c["DATA_TYPE"],
                "max_len": c["CHARACTER_MAXIMUM_LENGTH"],
                "nullable": c["IS_NULLABLE"] == "YES",
            }
        )
    pk_by_tbl: dict[tuple, list] = defaultdict(list)
    for p in pks:
        pk_by_tbl[(p["TABLE_SCHEMA"], p["TABLE_NAME"])].append(p["COLUMN_NAME"])

    fk_list = [
        {
            "name": f["fk_name"],
            "parent": f"{f['parent_schema']}.{f['parent_table']}",
            "parent_column": f["parent_column"],
            "ref": f"{f['ref_schema']}.{f['ref_table']}",
            "ref_column": f["ref_column"],
        }
        for f in fks
    ]

    tables_out = []
    for t in tables:
        key = (t["TABLE_SCHEMA"], t["TABLE_NAME"])
        tables_out.append(
            {
                "schema": t["TABLE_SCHEMA"],
                "name": t["TABLE_NAME"],
                "type": t["TABLE_TYPE"],
                "row_count": rowcounts.get(key),
                "columns": cols_by_tbl.get(key, []),
                "primary_key": pk_by_tbl.get(key, []),
            }
        )

    schema_json = {"tables": tables_out, "foreign_keys": fk_list}
    (OUT_DIR / "corral_schema.json").write_text(
        json.dumps(schema_json, indent=2, default=str), encoding="utf-8"
    )

    lines = ["# Corral — Table Inventory", "", f"{len(tables_out)} tables/views. Source: sql24/Corral (read-only).", ""]
    lines.append("| Schema | Table | Type | Rows | Cols | PK |")
    lines.append("|---|---|---|---:|---:|---|")
    for t in tables_out:
        pk = ", ".join(t["primary_key"]) or "—"
        rc = t["row_count"] if t["row_count"] is not None else "—"
        lines.append(
            f"| {t['schema']} | {t['name']} | {t['type']} | {rc} | {len(t['columns'])} | {pk} |"
        )
    (OUT_DIR / "corral_tables.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {OUT_DIR / 'corral_schema.json'}")
    print(f"Wrote {OUT_DIR / 'corral_tables.md'}")
    print(f"Tables: {len(tables_out)}  FKs: {len(fk_list)}")


if __name__ == "__main__":
    main()
