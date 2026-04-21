"""Catalog data/raw_data/ and dump shape + column lists to JSON.

Read-only. Refresh input for the hand-written gap analysis in
erd/raw_data_vs_corral.md.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

ERD_DIR = Path(__file__).resolve().parent
REPO_ROOT = ERD_DIR.parent
RAW = REPO_ROOT / "data" / "raw_data"


def count_csv_rows(path: Path) -> int:
    with open(path, encoding="utf-8", errors="replace") as f:
        return max(sum(1 for _ in f) - 1, 0)


def catalog_one(path: Path) -> dict:
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            df = pd.read_csv(path, dtype=str, low_memory=False, nrows=3)
            return {
                "file": path.name,
                "kind": "csv",
                "rows": count_csv_rows(path),
                "columns": list(df.columns),
                "sample": df.fillna("").to_dict("records"),
            }
        if suffix == ".xlsx":
            xl = pd.ExcelFile(path)
            sheets = {}
            for s in xl.sheet_names:
                df = pd.read_excel(path, sheet_name=s, nrows=3, dtype=str)
                sheets[s] = {
                    "columns": list(df.columns),
                    "sample": df.fillna("").to_dict("records"),
                }
            return {"file": path.name, "kind": "xlsx", "sheets": sheets}
    except Exception as exc:  # noqa: BLE001
        return {"file": path.name, "error": str(exc)[:300]}
    return {"file": path.name, "skipped": True}


def main() -> None:
    out = []
    for name in sorted(os.listdir(RAW)):
        p = RAW / name
        if p.is_dir():
            continue
        out.append(catalog_one(p))
    (ERD_DIR / "raw_data_inventory.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8"
    )
    print(f"Cataloged {len(out)} files -> {ERD_DIR / 'raw_data_inventory.json'}")


if __name__ == "__main__":
    main()
