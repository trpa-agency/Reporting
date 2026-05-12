"""
convert_transactions_summary.py — Aggregate the 2025 Transactions and
Allocations Details xlsx (Ken's full transaction registry, 2,030 rows) into
a small JSON suitable for the Regional Plan Capacity Dial dashboard.

Filtering / bucketing:
  - Filter to residential commodities (Development Right contains
    Residential / SFRUU / MFRUU / PRUU / RBU).
  - Bucket each transaction's `Detailed Development Type` into one of
    Dan's source categories: Allocation / Banked / Transfer / Conversion /
    Bonus Unit / Allocation/Transfer / Other.
  - Use `Status Jan 2026` as the completion signal: Completed vs Not Completed
    vs No Project vs TBD.

Output (compact JSON):
  {
    "meta": {
      "total_residential_rows": N,
      "completed": N,
      "in_pipeline": N,
      "generated_at": "..."
    },
    "by_source": [               # 6 buckets, sorted by Completed desc
      { "source": "Allocation",  "completed": 894, "not_completed": 139, "no_project": ... },
      ...
    ],
    "by_year": [                 # cumulative + per-year completions
      { "year": 2009, "completed": 1, "cumulative": 1 },
      ...
    ],
    "by_year_source": [          # year × source matrix for stacked area
      { "year": 2009, "source": "Allocation",  "completed": 1 },
      ...
    ]
  }

Run when Ken sends a refreshed xlsx:
    PYTHONIOENCODING=utf-8 \\
    "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" \\
    parcel_development_history_etl/scripts/convert_transactions_summary.py
"""
import datetime as _dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from config import (
    TRANSACTIONS_2025_XLSX,
    RESIDENTIAL_TRANSACTIONS_SUMMARY_JSON,
)
from utils import get_logger

log = get_logger("convert_transactions_summary")


def bucket_source(detailed: str) -> str:
    s = str(detailed or "").lower()
    # Order matters — "banking" and "conversion" should win over plain
    # "transfer" or "allocation" when both appear.
    if "banked" in s or "banking" in s:               return "Banked"
    if "conver" in s:                                  return "Conversion"
    if "bonus" in s:                                   return "Bonus Unit"
    if "transfer" in s and "allocation" in s:          return "Allocation/Transfer"
    if "transfer" in s:                                return "Transfer"
    if "allocation" in s:                              return "Allocation"
    return "Other"


def main() -> None:
    src = Path(TRANSACTIONS_2025_XLSX)
    dst = Path(RESIDENTIAL_TRANSACTIONS_SUMMARY_JSON)
    if not src.exists():
        raise SystemExit(f"Source xlsx not found: {src}")

    log.info("Reading %s", src)
    df = pd.read_excel(src, dtype=str)
    df["Year Built"] = pd.to_numeric(df["Year Built"], errors="coerce")
    log.info("  raw rows: %d", len(df))

    # Filter to residential
    res_mask = df["Development Right"].fillna("").str.contains(
        "Residential|SFRUU|MFRUU|PRUU|RBU", regex=True, case=False, na=False
    )
    res = df[res_mask].copy()
    log.info("  residential rows: %d", len(res))

    res["Source"] = res["Detailed Development Type"].apply(bucket_source)
    res["Status Jan 2026"] = res["Status Jan 2026"].fillna("(unknown)")

    # ── By source × status ────────────────────────────────────────────────
    by_source_pivot = (res.groupby(["Source", "Status Jan 2026"])
                          .size()
                          .unstack(fill_value=0))
    # Ensure all expected status columns exist
    for col in ("Completed", "Not Completed", "No Project", "TBD", "Expired", "(unknown)"):
        if col not in by_source_pivot.columns:
            by_source_pivot[col] = 0

    by_source_pivot = by_source_pivot.sort_values("Completed", ascending=False)
    by_source = []
    for src_name, row in by_source_pivot.iterrows():
        by_source.append({
            "source":        src_name,
            "completed":     int(row["Completed"]),
            "not_completed": int(row["Not Completed"]),
            "no_project":    int(row["No Project"]),
            "tbd":           int(row["TBD"]),
            "expired":       int(row.get("Expired", 0)),
            "unknown":       int(row.get("(unknown)", 0)),
        })

    # ── Per-year (cumulative) completed ──────────────────────────────────
    comp = res[res["Status Jan 2026"] == "Completed"].copy()
    comp["Year Built"] = comp["Year Built"].astype("Int64")

    # Coerce Year Built to a contiguous range 2009-2026
    YEAR_MIN, YEAR_MAX = 2009, 2026
    by_year = []
    cum = 0
    yc = comp.dropna(subset=["Year Built"]).groupby("Year Built").size()
    for y in range(YEAR_MIN, YEAR_MAX + 1):
        n = int(yc.get(y, 0))
        cum += n
        by_year.append({"year": y, "completed": n, "cumulative": cum})

    # ── Year × Source matrix (for stacked area / bar) ─────────────────────
    by_year_source = []
    sources_in_order = [b["source"] for b in by_source]
    yc2 = (comp.dropna(subset=["Year Built"])
                .groupby(["Year Built", "Source"]).size().unstack(fill_value=0))
    for y in range(YEAR_MIN, YEAR_MAX + 1):
        for s in sources_in_order:
            n = int(yc2.loc[y, s]) if (y in yc2.index and s in yc2.columns) else 0
            if n:
                by_year_source.append({"year": y, "source": s, "completed": n})

    # ── Meta ─────────────────────────────────────────────────────────────
    meta = {
        "total_residential_rows": int(len(res)),
        "completed":              int((res["Status Jan 2026"] == "Completed").sum()),
        "in_pipeline":            int((res["Status Jan 2026"] == "Not Completed").sum()),
        "no_project":             int((res["Status Jan 2026"] == "No Project").sum()),
        "year_min":               YEAR_MIN,
        "year_max":               YEAR_MAX,
        "generated_at":           _dt.datetime.now().isoformat(timespec="seconds"),
        "source_file":            str(src.name),
    }

    out = {
        "meta": meta,
        "by_source": by_source,
        "by_year": by_year,
        "by_year_source": by_year_source,
    }

    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))

    log.info("Wrote %s (%.1f KB)", dst, dst.stat().st_size / 1024)
    log.info("Meta: %s", meta)
    log.info("By source (top 3):")
    for b in by_source[:3]:
        log.info("  %-22s  Completed=%d  Not Completed=%d", b["source"], b["completed"], b["not_completed"])


if __name__ == "__main__":
    main()
