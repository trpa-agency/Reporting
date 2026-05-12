"""
convert_allocation_grid.py — Convert Ken's residentialAllocationGridExport
xlsx into the canonical CSV that allocation-tracking.html and
regional-capacity-dial.html consume.

Reads the `residentialAllocationGridExport` sheet (NOT the Sheet1 pivot
summary), writes UTF-8 CSV with the original column names preserved.

Run when Ken sends a refreshed xlsx:

    PYTHONIOENCODING=utf-8 \\
    "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" \\
    parcel_development_history_etl/scripts/convert_allocation_grid.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from config import ALLOCATION_GRID_XLSX, ALLOCATION_GRID_CSV
from utils import get_logger

log = get_logger("convert_allocation_grid")

SHEET_NAME = "residentialAllocationGridExport"


def main() -> None:
    src = Path(ALLOCATION_GRID_XLSX)
    dst = Path(ALLOCATION_GRID_CSV)

    if not src.exists():
        raise SystemExit(f"Source xlsx not found: {src}")

    log.info("Reading %s [sheet=%s]", src, SHEET_NAME)
    df = pd.read_excel(src, sheet_name=SHEET_NAME, dtype=str)
    log.info("  shape: %s", df.shape)
    log.info("  columns: %s", list(df.columns))

    # Strip whitespace from string cells (Ken sometimes has trailing spaces)
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].astype(str).str.strip()
            df.loc[df[c].isin(["nan", "NaN", "None"]), c] = ""

    dst.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(dst, index=False, encoding="utf-8")
    log.info("Wrote %d rows -> %s", len(df), dst)

    # Quick summary
    log.info("Allocation Status × Construction Status:")
    pivot = df.groupby(
        ["Allocation Status", "Construction Status"],
        dropna=False
    ).size()
    for k, v in pivot.items():
        log.info("  %-12s × %-15s : %d", k[0], k[1], v)


if __name__ == "__main__":
    main()
