"""
build_spatial_genealogy.py — Detect parcel genealogy events spatially.

For each consecutive year pair (2012→2013, …, 2024→2025):
  1. Find APNs that disappeared (in year N, not in year N+1) and
     APNs that appeared  (in year N+1, not in year N).
  2. Run arcpy.analysis.Identity on just those changed parcels —
     each old parcel is sliced against new parcels so every piece
     is tagged with the new APN it lands in (or null if it lands in
     a gap / unchanged parcel).
  3. Compute overlap_pct = piece_area / original_old_parcel_area.
  4. Classify the event as rename (1→1, ≥90% overlap),
     split (1→N), or merge (N→1).
  5. Write apn_genealogy_spatial.csv and QA_Spatial_Genealogy GDB table.

The output CSV is intended to supplement apn_genealogy_master.csv in
s02b_genealogy.py — manual records take priority; spatial records fill gaps.

Output CSV columns
------------------
  old_apn       APN as it exists in year N
  new_apn       APN as it exists in year N+1
  change_year   First year the new APN is active (= N+1)
  overlap_pct   area(intersection) / area(old_apn)
  change_type   rename | split | merge
  is_primary    1 if largest-overlap successor for this old_apn, else 0
  source        SPATIAL

Run from ArcGIS Pro Python:
  & "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" `
    "C:/Users/mbindl/Documents/GitHub/Reporting/parcel_development_history_etl/build_spatial_genealogy.py"
"""

import sys
import csv
import re
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import arcpy

from config import (
    WORKING_FC as SOURCE_FC, FC_APN, FC_YEAR, CSV_YEARS,
    GDB,
    GENEALOGY_SPATIAL,
    SPATIAL_GENEALOGY_OVERLAP_THRESHOLD,
)

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("build_spatial_genealogy")

QA_TABLE = GDB + r"\QA_Spatial_Genealogy"
_MEM     = "memory"


# ── Geometry readers ──────────────────────────────────────────────────────────

def _read_apn_geometry(year: int) -> dict:
    """
    Read SOURCE_FC for one year and return {APN: (geometry, area_sqft)}.
    Duplicate APNs (if any) keep the first row encountered.
    """
    result = {}
    lyr = f"sgen_src_{year}"
    if arcpy.Exists(lyr):
        arcpy.management.Delete(lyr)
    arcpy.management.MakeFeatureLayer(SOURCE_FC, lyr, f"{FC_YEAR} = {year}")

    with arcpy.da.SearchCursor(lyr, [FC_APN, "SHAPE@", "SHAPE@AREA"]) as cur:
        for apn, geom, area in cur:
            if apn and geom and area and area > 0:
                apn = str(apn).strip()
                if apn not in result:
                    result[apn] = (geom, float(area))

    if arcpy.Exists(lyr):
        arcpy.management.Delete(lyr)

    log.info("  Year %d : %d unique APNs with geometry", year, len(result))
    return result


# ── Identity analysis ─────────────────────────────────────────────────────────

def _build_polygon_fc(name: str, apn_field: str,
                      apn_geom: dict, sr) -> str:
    """Create a simple in-memory polygon FC with one field for APN."""
    fc = f"{_MEM}/{name}"
    if arcpy.Exists(fc):
        arcpy.management.Delete(fc)
    arcpy.management.CreateFeatureclass(_MEM, name, "POLYGON",
                                        spatial_reference=sr)
    arcpy.management.AddField(fc, apn_field, "TEXT", field_length=50)
    with arcpy.da.InsertCursor(fc, ["SHAPE@", apn_field]) as ic:
        for apn, (geom, _) in apn_geom.items():
            ic.insertRow([geom, apn])
    return fc


def _identity_overlap(disappeared: dict, appeared: dict,
                      yr_n: int, sr) -> list[dict]:
    """
    Identity(disappeared parcels, appeared parcels) for one year transition.

    Returns raw overlap records:
      {old_apn, new_apn, overlap_area, old_area, change_year}

    Pieces that land in gaps (new_apn is null or empty) are discarded.
    """
    if not disappeared or not appeared:
        return []

    tag      = f"{yr_n}to{yr_n + 1}"
    fc_old   = _build_polygon_fc(f"sgen_old_{tag}", "OLD_APN", disappeared, sr)
    fc_new   = _build_polygon_fc(f"sgen_new_{tag}", "NEW_APN", appeared,    sr)
    fc_ident = f"{_MEM}/sgen_id_{tag}"
    if arcpy.Exists(fc_ident):
        arcpy.management.Delete(fc_ident)

    arcpy.analysis.Identity(fc_old, fc_new, fc_ident,
                            join_attributes="ALL",
                            relationship=False)

    # Detect the new-APN field name in the Identity output
    # (renamed to NEW_APN_1 if Identity sees a collision, which it shouldn't
    #  since OLD_APN ≠ NEW_APN, but we guard for safety)
    id_fields  = {f.name for f in arcpy.ListFields(fc_ident)}
    new_fld    = "NEW_APN_1" if "NEW_APN_1" in id_fields else "NEW_APN"

    results = []
    with arcpy.da.SearchCursor(
            fc_ident, ["OLD_APN", new_fld, "SHAPE@AREA"]) as cur:
        for old_apn, new_apn, area in cur:
            if not old_apn or not new_apn or not area or area <= 0:
                continue
            old_apn = str(old_apn).strip()
            new_apn = str(new_apn).strip()
            if not new_apn:
                continue
            results.append({
                "old_apn"      : old_apn,
                "new_apn"      : new_apn,
                "overlap_area" : float(area),
                "old_area"     : disappeared.get(old_apn, (None, 0.0))[1],
                "change_year"  : yr_n + 1,
            })

    for fc in [fc_old, fc_new, fc_ident]:
        if arcpy.Exists(fc):
            arcpy.management.Delete(fc)

    return results


# ── El Dorado format-change filter ────────────────────────────────────────────

# El Dorado APNs: "083-030-22" → "083-030-022" (zero-pad suffix in 2018)
# These are already handled by s02's El Dorado fix and must not appear in the
# spatial genealogy output.
_EL_SUFFIX_RE = re.compile(r'^(\d{3}-\d{3}-)0?(\d{2})$')


def _is_el_dorado_format_change(old_apn: str, new_apn: str) -> bool:
    """Return True if old→new differ only by zero-padding the two-digit suffix."""
    if old_apn == new_apn:
        return False
    m_old = _EL_SUFFIX_RE.match(old_apn)
    m_new = _EL_SUFFIX_RE.match(new_apn)
    if not (m_old and m_new):
        return False
    return m_old.group(1) == m_new.group(1) and m_old.group(2) == m_new.group(2)


# ── Classification ────────────────────────────────────────────────────────────

def _classify(overlap_rows: list[dict],
              threshold: float) -> list[dict]:
    """
    Aggregate raw Identity pieces into genealogy events.

    For each old_apn:
      - Sum overlap areas by new_apn
      - Discard new_apns below threshold
      - Classify: rename (1 successor, ≥90%) | split (>1 successor) | merge
      - Assign is_primary=1 to the largest-overlap successor

    Merge detection: a new_apn is flagged as a merge target when ≥2 different
    old_apns each contribute ≥ threshold of their own area to it.
    """
    # ── per old_apn: sum overlap area by new_apn ──────────────────────────────
    by_old: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    old_area_map: dict[str, float] = {}
    change_year_map: dict[str, int] = {}

    for r in overlap_rows:
        by_old[r["old_apn"]][r["new_apn"]] += r["overlap_area"]
        old_area_map[r["old_apn"]]    = r["old_area"]
        change_year_map[r["old_apn"]] = r["change_year"]

    # ── merge detection: which new APNs receive significant area from >1 old ──
    # significant_contributions[new_apn] = list of old_apns contributing ≥ threshold
    sig_contrib: dict[str, list] = defaultdict(list)
    for old_apn, new_areas in by_old.items():
        old_area = old_area_map[old_apn]
        if old_area <= 0:
            continue
        for new_apn, ovlp in new_areas.items():
            if ovlp / old_area >= threshold:
                sig_contrib[new_apn].append(old_apn)

    merge_targets = {na for na, olds in sig_contrib.items() if len(olds) > 1}

    # ── build output records ──────────────────────────────────────────────────
    out_rows = []
    for old_apn, new_areas in by_old.items():
        old_area    = old_area_map[old_apn]
        change_year = change_year_map[old_apn]

        if old_area <= 0:
            continue

        # Filter to significant successors
        significant = {
            na: area
            for na, area in new_areas.items()
            if area / old_area >= threshold
        }
        if not significant:
            continue

        n_successors = len(significant)
        has_merge    = any(na in merge_targets for na in significant)

        if has_merge:
            change_type = "merge"
        elif n_successors == 1:
            ovlp_frac = list(significant.values())[0] / old_area
            change_type = "rename" if ovlp_frac >= 0.90 else "split"
        else:
            change_type = "split"

        # Rank successors by overlap (largest = is_primary)
        ranked = sorted(significant.items(), key=lambda x: x[1], reverse=True)
        for rank, (new_apn, ovlp_area) in enumerate(ranked):
            if _is_el_dorado_format_change(old_apn, new_apn):
                continue   # already handled by s02 El Dorado zero-pad fix
            out_rows.append({
                "old_apn"    : old_apn,
                "new_apn"    : new_apn,
                "change_year": change_year,
                "overlap_pct": round(ovlp_area / old_area, 4),
                "change_type": change_type,
                "is_primary" : 1 if rank == 0 else 0,
                "source"     : "SPATIAL",
            })

    return out_rows


# ── Chain detection ───────────────────────────────────────────────────────────

def _detect_chains(rows: list[dict]) -> list[dict]:
    """
    Walk the is_primary=1 successor graph to find multi-hop chains.
    e.g. A→B (2017) and B→C (2021) = depth-2 chain A→B→C.

    s02b handles chains correctly via iterative application (each hop is
    applied in turn), but this check flags them so analysts can verify
    every intermediate link is present in the genealogy data.

    Returns list of chain dicts sorted by depth descending.
    """
    successor: dict[str, tuple[str, int]] = {}
    for r in rows:
        if r["is_primary"] == 1:
            # later change_year wins if same old_apn appears twice (shouldn't happen)
            if r["old_apn"] not in successor or \
               r["change_year"] > successor[r["old_apn"]][1]:
                successor[r["old_apn"]] = (r["new_apn"], r["change_year"])

    chains     = []
    seen_start = set()

    for start_apn in list(successor.keys()):
        if start_apn in seen_start:
            continue

        chain = [start_apn]
        apn   = start_apn
        while apn in successor:
            nxt, _ = successor[apn]
            if nxt in chain:          # cycle guard
                break
            chain.append(nxt)
            apn = nxt

        seen_start.update(chain[:-1])

        if len(chain) < 3:            # depth-1 (A→B) is not a chain
            continue

        hops = []
        for i in range(len(chain) - 1):
            _, yr = successor[chain[i]]
            hops.append(f"{chain[i]}→{chain[i+1]}({yr})")
        chains.append({
            "Depth"    : len(chain) - 1,
            "Start_APN": chain[0],
            "End_APN"  : chain[-1],
            "Chain"    : " → ".join(chain),
            "Hops"     : ", ".join(hops),
        })

    return sorted(chains, key=lambda x: -x["Depth"])


# ── Split area conservation ────────────────────────────────────────────────────

def _check_split_conservation(rows: list[dict],
                               warn_threshold: float = 0.80) -> list[dict]:
    """
    For each old_apn involved in a split, sum overlap_pct across all successors.
    Flag cases where the sum is below warn_threshold — part of the original
    parcel area is unaccounted for (missing successor or geometry gap).
    """
    totals: dict[tuple, float] = defaultdict(float)
    change_types: dict[tuple, str] = {}

    for r in rows:
        if r["change_type"] == "split":
            key = (r["old_apn"], r["change_year"])
            totals[key] += r["overlap_pct"]
            change_types[key] = r["change_type"]

    flags = []
    for (old_apn, change_year), total in totals.items():
        if total < warn_threshold:
            flags.append({
                "Old_APN"         : old_apn,
                "Change_Year"     : change_year,
                "Total_Overlap_Pct": round(total, 4),
                "Missing_Pct"     : round(1.0 - total, 4),
            })

    return sorted(flags, key=lambda x: x["Total_Overlap_Pct"])


# ── QA table ──────────────────────────────────────────────────────────────────

def _write_qa_table(rows: list[dict]) -> None:
    if arcpy.Exists(QA_TABLE):
        arcpy.management.Delete(QA_TABLE)
    arcpy.management.CreateTable(GDB, "QA_Spatial_Genealogy")

    field_defs = [
        ("OLD_APN",     "TEXT",   50),
        ("NEW_APN",     "TEXT",   50),
        ("CHANGE_YEAR", "LONG",   None),
        ("OVERLAP_PCT", "DOUBLE", None),
        ("CHANGE_TYPE", "TEXT",   10),
        ("IS_PRIMARY",  "SHORT",  None),
        ("SOURCE",      "TEXT",   10),
    ]
    for fname, ftype, flen in field_defs:
        if flen:
            arcpy.management.AddField(QA_TABLE, fname, ftype, field_length=flen)
        else:
            arcpy.management.AddField(QA_TABLE, fname, ftype)

    with arcpy.da.InsertCursor(QA_TABLE, [
            "OLD_APN", "NEW_APN", "CHANGE_YEAR",
            "OVERLAP_PCT", "CHANGE_TYPE", "IS_PRIMARY", "SOURCE"]) as ic:
        for r in rows:
            ic.insertRow([
                r["old_apn"], r["new_apn"], r["change_year"],
                r["overlap_pct"], r["change_type"], r["is_primary"],
                r["source"],
            ])
    log.info("Written %d rows → %s", len(rows), QA_TABLE)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    t0    = time.time()
    years = sorted(CSV_YEARS)

    log.info("=== build_spatial_genealogy.py ===")
    log.info("Source FC  : %s", SOURCE_FC)
    log.info("Years      : %d – %d  (%d transitions)",
             years[0], years[-1], len(years) - 1)
    log.info("Threshold  : %.0f%% overlap", SPATIAL_GENEALOGY_OVERLAP_THRESHOLD * 100)

    sr         = arcpy.Describe(SOURCE_FC).spatialReference
    all_rows   = []

    # Cache each year's geometry so adjacent year pairs share reads
    # (year N read once as the "current" year, reused as "previous" next iteration)
    geom_cache: dict[int, dict] = {}

    for i in range(len(years) - 1):
        yr_n  = years[i]
        yr_n1 = years[i + 1]
        t_yr  = time.time()

        log.info("── %d → %d ──────────────────────────────────────────", yr_n, yr_n1)

        if yr_n not in geom_cache:
            geom_cache[yr_n]  = _read_apn_geometry(yr_n)
        if yr_n1 not in geom_cache:
            geom_cache[yr_n1] = _read_apn_geometry(yr_n1)

        geom_n  = geom_cache[yr_n]
        geom_n1 = geom_cache[yr_n1]

        apns_n  = set(geom_n.keys())
        apns_n1 = set(geom_n1.keys())

        disappeared = {a: geom_n[a]  for a in apns_n  - apns_n1}
        appeared    = {a: geom_n1[a] for a in apns_n1 - apns_n}

        log.info("  Disappeared : %d  |  Appeared : %d  |  Unchanged : %d",
                 len(disappeared), len(appeared),
                 len(apns_n & apns_n1))

        if not disappeared or not appeared:
            log.info("  One side is empty — no genealogy possible, skipping")
            # Release yr_n from cache; it won't be needed again
            geom_cache.pop(yr_n, None)
            continue

        overlap_rows = _identity_overlap(disappeared, appeared, yr_n, sr)
        log.info("  Identity pieces with overlap : %d", len(overlap_rows))

        year_rows = _classify(overlap_rows, SPATIAL_GENEALOGY_OVERLAP_THRESHOLD)

        # Per-type summary
        for ct in ("rename", "split", "merge"):
            events = sum(1 for r in year_rows if r["change_type"] == ct
                         and r["is_primary"] == 1)
            if events:
                log.info("    %-8s : %d events", ct, events)

        log.info("  Records this pair : %d  (%.1fs)", len(year_rows),
                 time.time() - t_yr)
        all_rows.extend(year_rows)

        # Release yr_n — no longer needed
        geom_cache.pop(yr_n, None)

    # ── Chain detection ───────────────────────────────────────────────────────
    chains = _detect_chains(all_rows)
    if chains:
        log.info("")
        log.info("  Chains (multi-hop) : %d", len(chains))
        for c in chains[:10]:
            log.info("    depth=%d  %s", c["Depth"], c["Chain"])
        if len(chains) > 10:
            log.info("    ... (%d more)", len(chains) - 10)
    else:
        log.info("  No multi-hop chains detected")

    # ── Split area conservation ────────────────────────────────────────────────
    conservation_flags = _check_split_conservation(all_rows)
    if conservation_flags:
        log.info("  Split conservation flags (<80%% area accounted): %d",
                 len(conservation_flags))
        for f in conservation_flags[:10]:
            log.info("    %s  year=%d  covered=%.0f%%",
                     f["Old_APN"], f["Change_Year"],
                     f["Total_Overlap_Pct"] * 100)
    else:
        log.info("  All splits account for ≥80%% of area")

    # ── Summary ───────────────────────────────────────────────────────────────
    log.info("")
    log.info("=== Summary ===")
    log.info("  Total records    : %d", len(all_rows))
    for ct in ("rename", "split", "merge"):
        n_events = sum(1 for r in all_rows
                       if r["change_type"] == ct and r["is_primary"] == 1)
        n_rows   = sum(1 for r in all_rows if r["change_type"] == ct)
        log.info("  %-8s : %d events  (%d rows total)", ct, n_events, n_rows)
    log.info("  Chains detected  : %d", len(chains))
    log.info("  Split conserv.   : %d flags", len(conservation_flags))

    # ── Write CSV ─────────────────────────────────────────────────────────────
    fieldnames = ["old_apn", "new_apn", "change_year", "overlap_pct",
                  "change_type", "is_primary", "source"]
    out_path = Path(GENEALOGY_SPATIAL)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    log.info("Written → %s", GENEALOGY_SPATIAL)

    # ── Write QA table ────────────────────────────────────────────────────────
    _write_qa_table(all_rows)

    elapsed = time.time() - t0
    mins, secs = divmod(int(elapsed), 60)
    log.info("Done.  (%dm %02ds)", mins, secs)


if __name__ == "__main__":
    main()
