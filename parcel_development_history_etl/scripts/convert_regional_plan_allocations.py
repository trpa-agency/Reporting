"""
convert_regional_plan_allocations.py - Convert the analyst's "All Regional
Plan Allocations Summary" xlsx into one tidy JSON the Phase 2 dashboards can
fetch directly.

The source xlsx is a human-formatted report (merged headers, multiple
stacked tables per sheet, padded NaN columns), not tidy data. This converter
anchors on marker strings ("Regional Plan Maximum", "1987 Plan", "Grand
Total", and the by-year block names) rather than hard-coded row numbers, so
it survives small layout shifts in future analyst deliveries.

Source: data/from_analyst/All Regional Plan Allocations Summary.xlsx

  Sheet "Residential Allocations"
    - a status x plan-era summary block: combined / 1987 Plan / 2012 Plan,
      each with Regional Plan Maximum / Not Assigned / Assigned to Projects,
      by jurisdiction
    - four by-year (1986-2026) blocks: AllocationsByYear (released),
      Assigned, RemainingNotAssigned, UnReleasedAllocationsByYear

  Sheets "Residential Bonus Units" / "Commercial Floor Area" /
  "Tourist Accommodation Units" - each has TWO stacked tables:
    - a "status" table: Regional Plan Maximum / Not Assigned / Assigned to
      Projects, by pool, grouped (Community/Area Plans vs TRPA pools)
    - a "plan-era" table: 1987 Plan / 2012 Plan / Total, by pool

Output: data/processed_data/regional_plan_allocations.json

Run when the analyst sends a refreshed xlsx:

    PYTHONIOENCODING=utf-8 \\
    "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" \\
    parcel_development_history_etl/scripts/convert_regional_plan_allocations.py
"""
import json
import re
import sys
import datetime as _dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from config import REGIONAL_PLAN_ALLOCATIONS_XLSX, REGIONAL_PLAN_ALLOCATIONS_JSON
from utils import get_logger

log = get_logger("convert_regional_plan_allocations")

STATUS_KEYS = ["regional_plan_maximum", "not_assigned", "assigned_to_projects"]
ERA_KEYS    = ["plan_1987", "plan_2012", "total"]

COMMODITY_SHEETS = {
    "Residential Bonus Units":      "residential_bonus_units",
    "Commercial Floor Area":        "commercial_floor_area",
    "Tourist Accommodation Units":  "tourist_accommodation_units",
}
# By-year block header text -> tidy JSON key (Residential Allocations sheet)
YEAR_BLOCKS = {
    "AllocationsByYear":           "released",
    "Assigned":                    "assigned",
    "RemainingNotAssigned":        "not_assigned",
    "UnReleasedAllocationsByYear": "unreleased",
}


# ── cell helpers ─────────────────────────────────────────────────────────
def _num(v):
    """xlsx cell -> int (whole numbers) / float / None. NaN/blank -> None."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if not s:
            return None
        try:
            v = float(s)
        except ValueError:
            return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f == int(f) else f


def _clean_name(v):
    """Trim whitespace and strip trailing footnote markers so the same pool
    reads identically across the two stacked tables, e.g.
    'TRPA Allocation Incentive Pool1' / 'TRPA Bonus Unit Pools*' ->
    'TRPA Allocation Incentive Pool' / 'TRPA Bonus Unit Pools'."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    if not s:
        return None
    s = re.sub(r"(\D)\d+$", r"\1", s)   # trailing footnote digit
    s = re.sub(r"\s*\*+$", "", s)        # trailing footnote asterisk(s)
    return s.strip() or None


def _is_footnote_or_source(s):
    """True for footnote rows ('1.', '1)', '*', 'Note:') and 'Source:' rows."""
    if not s:
        return False
    s = str(s).strip()
    return (
        bool(re.match(r"^\d+[.\)]\s", s))
        or s.lower().startswith(("source:", "sources:", "note:", "http://", "https://"))
        or s.startswith("*")
    )


def _is_year(v):
    n = _num(v)
    return n is not None and 1900 <= n <= 2100


def _as_of(df):
    """Pull the 'As of <date>' line from the top of a sheet."""
    for r in range(min(4, len(df))):
        cell = df.iloc[r, 0]
        if isinstance(cell, str) and cell.strip().lower().startswith("as of"):
            return cell.strip()[len("As of"):].strip()
    return None


def _collect_notes(df):
    """All footnote / source / note rows on a sheet, in order."""
    notes = []
    for r in range(len(df)):
        raw = df.iloc[r, 0]
        if isinstance(raw, str) and _is_footnote_or_source(raw):
            notes.append(raw.strip())
    return notes


# ── generic table parsers ────────────────────────────────────────────────
def _parse_pool_table(df, hdr_row, value_keys, commodity_name):
    """Parse one status-by-pool or era-by-pool table starting just below
    `hdr_row`. Values are read from columns 2,3,4 and zipped to `value_keys`.
    Section-header rows (col0 set, no numbers) set the current group; pool
    rows carry their name in col1; a row with col0 + numbers that is neither
    the commodity summary nor 'Grand Total' is treated as a standalone pool.
    Stops at the next table's header row, a footnote, or 'Grand Total'."""
    summary, grand_total, by_pool = None, None, []
    current_group = None
    for r in range(hdr_row + 1, len(df)):
        raw0 = df.iloc[r, 0]
        c0 = _clean_name(raw0)
        c1 = _clean_name(df.iloc[r, 1])
        vals = [_num(df.iloc[r, 2 + i]) for i in range(3)]
        has_val = any(v is not None for v in vals)

        if isinstance(raw0, str) and _is_footnote_or_source(raw0):
            break
        # a string in the value column = the next stacked table's header row
        if isinstance(df.iloc[r, 2], str):
            break
        if c0 is None and c1 is None and not has_val:
            continue  # blank separator between sections

        triple = dict(zip(value_keys, vals))
        # 'Grand Total' lands in col0 on most tables but col1 on a few
        # (e.g. the RBU plan-era table) - accept either.
        if (c0 == "Grand Total" or c1 == "Grand Total") and has_val:
            grand_total = triple
            break
        if c0 is not None and has_val and c0 == commodity_name:
            summary = triple
        elif c0 is not None and not has_val:
            current_group = c0  # section header
        elif c0 is not None and has_val:
            by_pool.append({"group": "Standalone", "name": c0, **triple})
        elif c1 is not None and has_val:
            by_pool.append({"group": current_group or "Ungrouped",
                            "name": c1, **triple})
    return summary, by_pool, grand_total


def _reconcile(summary_or_total, by_pool, keys):
    """Does the pool detail sum to the table's headline? Informational - the
    analyst's source has some known internal gaps (e.g. TAU 'Unassigned to
    CPs')."""
    if not summary_or_total or not by_pool:
        return None
    pool_sum = {k: sum((p.get(k) or 0) for p in by_pool) for k in keys}
    return {
        "pool_sum": pool_sum,
        "matches": all((summary_or_total.get(k) or 0) == pool_sum[k] for k in keys),
    }


def _parse_year_block(df, hdr_row, ncol):
    """Parse one by-year block: header row has year numbers across the year
    columns plus optional 'Grand Total' / '1986-2011 Total' / '2012-2026
    Total' columns. Data rows follow until a blank col0, the next block
    header, a footnote, or (inclusive) a 'Grand Total' row."""
    hdr = df.iloc[hdr_row]
    year_cols, total_cols = [], {}
    for c in range(1, ncol):
        v = hdr.iloc[c]
        if isinstance(v, str):
            lbl = v.strip()
            if lbl in ("Grand Total", "1986-2011 Total", "2012-2026 Total"):
                total_cols[lbl] = c
        elif _is_year(v):
            year_cols.append((c, int(_num(v))))

    rows = []
    for r in range(hdr_row + 1, len(df)):
        raw0 = df.iloc[r, 0]
        c0 = _clean_name(raw0)
        if isinstance(raw0, str) and _is_footnote_or_source(raw0):
            break
        if c0 is None:
            break  # blank row ends the block
        if _is_year(df.iloc[r, 1]):
            break  # this row is the next block's header
        rows.append({
            "name": c0,
            "values": [_num(df.iloc[r, c]) for c, _ in year_cols],
            "grand_total":     _num(df.iloc[r, total_cols["Grand Total"]])     if "Grand Total" in total_cols else None,
            "total_1986_2011": _num(df.iloc[r, total_cols["1986-2011 Total"]]) if "1986-2011 Total" in total_cols else None,
            "total_2012_2026": _num(df.iloc[r, total_cols["2012-2026 Total"]]) if "2012-2026 Total" in total_cols else None,
        })
        if c0 == "Grand Total":
            break
    return {"years": [yr for _, yr in year_cols], "rows": rows}


# ── Residential Allocations sheet ────────────────────────────────────────
def parse_residential(df):
    ncol = df.shape[1]

    # 1. status x plan-era summary block - locate the "Regional Plan Maximum"
    #    header row; era labels ("1987 Plan", "2012 Plan") sit one row above.
    hdr_row = None
    for r in range(len(df)):
        if "Regional Plan Maximum" in [
            str(x).strip() if pd.notna(x) else "" for x in df.iloc[r]
        ]:
            hdr_row = r
            break
    if hdr_row is None:
        raise ValueError("Residential sheet: no 'Regional Plan Maximum' header")

    era_row = df.iloc[hdr_row - 1]
    groups = []  # (era_key, start_col)
    for c in range(ncol):
        cell = df.iloc[hdr_row, c]
        if isinstance(cell, str) and cell.strip() == "Regional Plan Maximum":
            lbl = str(era_row.iloc[c]).strip() if c < len(era_row) and pd.notna(era_row.iloc[c]) else ""
            key = {"1987 Plan": "plan_1987", "2012 Plan": "plan_2012"}.get(lbl, "combined")
            groups.append((key, c))
    log.info("  residential: plan-era groups %s", groups)

    def read_eras(row):
        return {key: dict(zip(STATUS_KEYS,
                              [_num(row.iloc[start + i]) for i in range(3)]))
                for key, start in groups}

    summary, grand_total, by_jurisdiction = None, None, []
    seen_summary = False
    for r in range(hdr_row + 1, len(df)):
        name = _clean_name(df.iloc[r, 0])
        if name is None:
            continue
        if name in YEAR_BLOCKS:
            break  # the summary block ends where the by-year blocks begin
        if name == "Residential Allocations" and not seen_summary:
            summary = read_eras(df.iloc[r]); seen_summary = True
        elif name == "Grand Total":
            grand_total = read_eras(df.iloc[r])
        elif seen_summary:
            by_jurisdiction.append({"name": name, **read_eras(df.iloc[r])})

    # 2. by-year blocks - scan for header rows (col0 is a known block name
    #    AND col1 is a year number), parse each.
    by_year = {}
    for r in range(len(df)):
        name = _clean_name(df.iloc[r, 0])
        if name in YEAR_BLOCKS and _is_year(df.iloc[r, 1]):
            by_year[YEAR_BLOCKS[name]] = _parse_year_block(df, r, ncol)

    return {
        "summary":         summary,
        "grand_total":     grand_total,
        "by_jurisdiction": by_jurisdiction,
        "by_year":         by_year,
        "notes":           _collect_notes(df),
    }


# ── RBU / CFA / TAU sheets (two stacked tables) ──────────────────────────
def parse_commodity_sheet(df, sheet_name):
    # table 1: status - header row where col2 startswith "Regional Plan Maximum"
    status_hdr = None
    for r in range(len(df)):
        cell = df.iloc[r, 2]
        if isinstance(cell, str) and cell.strip().startswith("Regional Plan Maximum"):
            status_hdr = r
            break
    if status_hdr is None:
        raise ValueError(f"{sheet_name}: no 'Regional Plan Maximum' header")
    s_summary, s_pools, s_total = _parse_pool_table(
        df, status_hdr, STATUS_KEYS, sheet_name)

    # table 2: plan-era - header row where col2 == "1987 Plan"
    era_hdr = None
    for r in range(len(df)):
        cell = df.iloc[r, 2]
        if isinstance(cell, str) and cell.strip() == "1987 Plan":
            era_hdr = r
            break
    e_pools, e_total = [], None
    if era_hdr is not None:
        _, e_pools, e_total = _parse_pool_table(
            df, era_hdr, ERA_KEYS, sheet_name)
    else:
        log.warning("  %s: no '1987 Plan' plan-era table found", sheet_name)

    return {
        "status": {
            "summary":        s_summary,
            "by_pool":        s_pools,
            "grand_total":    s_total,
            "reconciliation": _reconcile(s_summary, s_pools, STATUS_KEYS),
        },
        "by_plan_era": {
            "by_pool":        e_pools,
            "grand_total":    e_total,
            "reconciliation": _reconcile(e_total, e_pools, ERA_KEYS),
        },
        "notes": _collect_notes(df),
    }


def main():
    src = Path(REGIONAL_PLAN_ALLOCATIONS_XLSX)
    dst = Path(REGIONAL_PLAN_ALLOCATIONS_JSON)
    if not src.exists():
        raise SystemExit(f"Source xlsx not found: {src}")

    log.info("Reading %s", src)
    xl = pd.ExcelFile(src)
    log.info("  sheets: %s", xl.sheet_names)

    res_df = pd.read_excel(src, sheet_name="Residential Allocations", header=None)
    as_of = _as_of(res_df)
    log.info("  as-of: %s", as_of)

    payload = {
        "meta": {
            "generated":   _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source_file": "data/from_analyst/All Regional Plan Allocations Summary.xlsx",
            "as_of":       as_of,
        },
        "residential": parse_residential(res_df),
    }
    for sheet_name, json_key in COMMODITY_SHEETS.items():
        if sheet_name not in xl.sheet_names:
            log.warning("  sheet %r not found - skipping", sheet_name)
            continue
        cdf = pd.read_excel(src, sheet_name=sheet_name, header=None)
        payload[json_key] = parse_commodity_sheet(cdf, sheet_name)

    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    log.info("Wrote %s (%.1f KB)", dst, dst.stat().st_size / 1024)

    # ── console summary ──────────────────────────────────────────────────
    res = payload["residential"]
    log.info("=" * 66)
    log.info("RESIDENTIAL ALLOCATIONS")
    for era in ("combined", "plan_1987", "plan_2012"):
        t = (res["summary"] or {}).get(era, {})
        log.info("  %-10s max=%-6s not-assigned=%-6s assigned=%-6s",
                 era, t.get("regional_plan_maximum"),
                 t.get("not_assigned"), t.get("assigned_to_projects"))
    log.info("  by_jurisdiction rows: %d", len(res["by_jurisdiction"]))
    for k, blk in res["by_year"].items():
        yrs = blk["years"]
        log.info("  by_year[%-12s]: %d rows x %d years (%s-%s)",
                 k, len(blk["rows"]), len(yrs),
                 yrs[0] if yrs else "?", yrs[-1] if yrs else "?")
    log.info("  notes: %d", len(res["notes"]))

    for json_key in COMMODITY_SHEETS.values():
        if json_key not in payload:
            continue
        c = payload[json_key]
        s = c["status"]["summary"] or {}
        gt = c["by_plan_era"]["grand_total"] or {}
        log.info("-" * 66)
        log.info("%s", json_key.upper())
        log.info("  status   max=%-9s not-assigned=%-9s assigned=%-9s  (%d pools)",
                 s.get("regional_plan_maximum"), s.get("not_assigned"),
                 s.get("assigned_to_projects"), len(c["status"]["by_pool"]))
        log.info("  by-era   1987=%-9s 2012=%-9s total=%-9s  (%d pools)",
                 gt.get("plan_1987"), gt.get("plan_2012"), gt.get("total"),
                 len(c["by_plan_era"]["by_pool"]))
        rec = c["status"]["reconciliation"]
        if rec and not rec["matches"]:
            log.warning("  status pools do NOT sum to summary: pool_sum=%s vs summary=%s",
                        rec["pool_sum"], s)


if __name__ == "__main__":
    main()
