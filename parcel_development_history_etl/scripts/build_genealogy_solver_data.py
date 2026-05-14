"""
build_genealogy_solver_data.py - Pre-join the genealogy graph with 2025
per-APN cross-reference data into one compact JSON for the
html/genealogy_solver/ client-side dashboard.

Inputs:
  - data/qa_data/apn_genealogy_tahoe.csv        (42K edges, consolidated)
  - data/processed_data/PDH_2025_OriginalYrBuilt.csv
  - data/processed_data/residential_units_inventory_2025.csv

Output: html/genealogy_solver/data/genealogy_solver.json

Schema:
  {
    "meta": {generated, source_file, n_edges, n_nodes, applied_by_etl},
    "edges": [                       // sorted by (source_priority, change_year)
      {o, n, y, t, s, p, ip, fo, fn, ab}
       apn_old, apn_new, change_year, event_type, source, source_priority,
       is_primary, in_fc_old, in_fc_new, applied_by_etl
    ],
    "apns": {                        // one entry per APN in graph or in cross-ref
      "<canonical_apn>": {co, ju, ru, tu, cf, yb, ad, in, po, pi}
       COUNTY, JURISDICTION, Residential_Units, TouristAccommodation_Units,
       CommercialFloorArea_SqFt, COMBINED_YEAR_BUILT, Address, in_2025,
       parents_out_edges[], parents_in_edges[]
    }
  }

Short keys keep the JSON small; the client expands them on load.

Run:
    PYTHONIOENCODING=utf-8 \\
    "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" \\
    parcel_development_history_etl/scripts/build_genealogy_solver_data.py
"""
import json
import sys
import datetime as _dt
from collections import defaultdict
from pathlib import Path

# Make the parent package importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from config import (
    GENEALOGY_TAHOE,
    PDH_2025_YRBUILT_CSV,
    RESIDENTIAL_UNITS_INVENTORY_CSV,
    GENEALOGY_SOLVER_JSON,
)
from utils import canonical_apn, get_logger

log = get_logger("build_genealogy_solver_data")


def _to_int_or_none(v):
    if pd.isna(v):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _str_or_none(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s if s else None


def main() -> None:
    log.info("=" * 70)
    log.info("BUILD GENEALOGY_SOLVER_DATA")
    log.info("=" * 70)

    # 1. Load genealogy edges (ALL rows; we mark applied_by_etl rather than filter)
    log.info("Loading genealogy: %s", GENEALOGY_TAHOE)
    gen = pd.read_csv(GENEALOGY_TAHOE,
                      dtype={"apn_old": str, "apn_new": str},
                      low_memory=False)
    log.info("  %d edge rows", len(gen))

    # Re-canonicalize defensively (genealogy_tahoe.csv already does this,
    # but a stray legacy row could slip through)
    gen["apn_old"] = gen["apn_old"].apply(canonical_apn)
    gen["apn_new"] = gen["apn_new"].apply(canonical_apn)
    # Drop rows where either side is null (can't traverse without both endpoints)
    before = len(gen)
    gen = gen[gen["apn_old"].notna() & gen["apn_new"].notna()].copy()
    log.info("  %d rows after dropping null-endpoint edges (-%d)",
             len(gen), before - len(gen))

    # Coerce types
    gen["change_year"]      = pd.to_numeric(gen["change_year"], errors="coerce")
    gen["source_priority"]  = pd.to_numeric(gen["source_priority"], errors="coerce").fillna(99).astype(int)
    gen["is_primary"]       = pd.to_numeric(gen["is_primary"], errors="coerce").fillna(0).astype(int)
    gen["in_fc_old"]        = pd.to_numeric(gen["in_fc_old"], errors="coerce").fillna(0).astype(int)
    gen["in_fc_new"]        = pd.to_numeric(gen["in_fc_new"], errors="coerce").fillna(0).astype(int)

    # The ETL apply-filter (mirrors s02b_genealogy.py)
    gen["applied_by_etl"] = (
        (gen["is_primary"] == 1)
        & (gen["change_year"].notna())
        & (gen["in_fc_new"] == 1)
    ).astype(int)

    n_applied = int(gen["applied_by_etl"].sum())
    log.info("  %d edges would be applied by the ETL filter", n_applied)

    # Sort by (source_priority, change_year) so the edge order matches s02b's
    # tie-breaking. NaN years sort last via na_position.
    gen = gen.sort_values(by=["source_priority", "change_year"],
                          na_position="last").reset_index(drop=True)

    # Deduplicate (apn_old, apn_new) keeping the highest-priority row
    # (priority sorted ascending: 1 = MANUAL is best, 4 = SPATIAL is worst)
    before = len(gen)
    gen = gen.drop_duplicates(subset=["apn_old", "apn_new"], keep="first")
    log.info("  %d rows after dedup on (apn_old, apn_new) (-%d duplicates)",
             len(gen), before - len(gen))

    # 2. Load PDH 2025 cross-reference (one row per current parcel)
    log.info("Loading PDH 2025 cross-ref: %s", PDH_2025_YRBUILT_CSV)
    pdh = pd.read_csv(PDH_2025_YRBUILT_CSV,
                      dtype={"APN": str, "APN_canon": str},
                      low_memory=False)
    log.info("  %d PDH 2025 rows", len(pdh))

    pdh = pdh[["APN_canon", "Residential_Units", "TouristAccommodation_Units",
               "CommercialFloorArea_SqFt", "COUNTY", "JURISDICTION",
               "COMBINED_YEAR_BUILT"]].copy()
    pdh["APN_canon"] = pdh["APN_canon"].apply(canonical_apn)
    pdh = pdh[pdh["APN_canon"].notna()].drop_duplicates(subset=["APN_canon"])

    # 3. Load units inventory; we only need an Address per APN (modal)
    log.info("Loading units inventory: %s", RESIDENTIAL_UNITS_INVENTORY_CSV)
    units = pd.read_csv(RESIDENTIAL_UNITS_INVENTORY_CSV,
                        dtype={"APN": str, "APN_canon": str},
                        usecols=["APN_canon", "Address"],
                        low_memory=False)
    log.info("  %d unit rows", len(units))
    units["APN_canon"] = units["APN_canon"].apply(canonical_apn)
    addr_by_apn = (units.dropna(subset=["APN_canon", "Address"])
                        .groupby("APN_canon")["Address"]
                        .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else None)
                        .to_dict())

    pdh_by_apn = pdh.set_index("APN_canon").to_dict(orient="index")

    # 4. Assign integer edge IDs and build adjacency
    log.info("Building adjacency lookup...")
    edges = []
    apns_in_graph = set()
    out_of_apn = defaultdict(list)   # apn -> list of edge indices where apn = apn_old
    in_of_apn  = defaultdict(list)   # apn -> list of edge indices where apn = apn_new

    for i, row in gen.reset_index(drop=True).iterrows():
        o = row["apn_old"]
        n = row["apn_new"]
        apns_in_graph.add(o)
        apns_in_graph.add(n)
        out_of_apn[o].append(i)
        in_of_apn[n].append(i)
        edges.append({
            "o":  o,
            "n":  n,
            "y":  _to_int_or_none(row["change_year"]),
            "t":  _str_or_none(row.get("event_type")) or "",
            "s":  _str_or_none(row.get("source")) or "",
            "p":  int(row["source_priority"]),
            "ip": int(row["is_primary"]),
            "fo": int(row["in_fc_old"]),
            "fn": int(row["in_fc_new"]),
            "ab": int(row["applied_by_etl"]),
        })

    # 5. Build per-APN nodes (union of graph APNs + PDH 2025 APNs)
    all_apns = apns_in_graph | set(pdh_by_apn.keys())
    log.info("  %d total APN nodes (graph: %d, PDH-only: %d)",
             len(all_apns), len(apns_in_graph),
             len(all_apns) - len(apns_in_graph))

    apns_out = {}
    for apn in all_apns:
        node = {"po": out_of_apn.get(apn, []),
                "pi": in_of_apn.get(apn, [])}
        x = pdh_by_apn.get(apn)
        if x:
            node["co"] = _str_or_none(x.get("COUNTY"))
            node["ju"] = _str_or_none(x.get("JURISDICTION"))
            ru = _to_int_or_none(x.get("Residential_Units"))
            tu = _to_int_or_none(x.get("TouristAccommodation_Units"))
            cf = _to_int_or_none(x.get("CommercialFloorArea_SqFt"))
            yb = _to_int_or_none(x.get("COMBINED_YEAR_BUILT"))
            if ru is not None: node["ru"] = ru
            if tu is not None: node["tu"] = tu
            if cf is not None: node["cf"] = cf
            if yb is not None: node["yb"] = yb
            node["in"] = 1   # present in PDH 2025
        else:
            node["in"] = 0
        ad = addr_by_apn.get(apn)
        if ad:
            node["ad"] = ad
        # Drop empty adjacency arrays to save space
        if not node["po"]:
            del node["po"]
        if not node["pi"]:
            del node["pi"]
        apns_out[apn] = node

    # 6. Emit
    payload = {
        "meta": {
            "generated":       _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source_file":     "data/qa_data/apn_genealogy_tahoe.csv",
            "n_edges":         len(edges),
            "n_nodes":         len(apns_out),
            "n_graph_nodes":   len(apns_in_graph),
            "applied_by_etl":  n_applied,
            "schema_version":  1,
        },
        "edges": edges,
        "apns":  apns_out,
    }

    out_path = Path(GENEALOGY_SOLVER_JSON)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        # Compact: no whitespace, no indent
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = out_path.stat().st_size / 1024
    log.info("Wrote %s (%.1f KB)", out_path, size_kb)
    log.info("  edges: %d  |  nodes: %d  |  applied: %d",
             len(edges), len(apns_out), n_applied)

    # Quick sanity scan of distributions
    log.info("  source breakdown:")
    src_counts = gen["source"].value_counts(dropna=False).to_dict()
    for s, c in src_counts.items():
        log.info("    %-10s %d", s, c)
    log.info("  event_type breakdown:")
    et_counts = gen["event_type"].value_counts(dropna=False).to_dict()
    for et, c in et_counts.items():
        log.info("    %-10s %d", et, c)


if __name__ == "__main__":
    main()
