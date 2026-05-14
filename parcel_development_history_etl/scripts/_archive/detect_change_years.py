"""
detect_change_years.py  —  Auto-detect change_year for NEEDS_CHANGE_YEAR genealogy pairs.

Reads qa_lost_vs_new_genealogy.csv (filter: Action == NEEDS_CHANGE_YEAR) and
queries the OUTPUT_FC to find:
  - last_year_old  : last year the old (lost) APN exists in the FC
  - first_year_new : first year the candidate new APN exists in the FC

Suggested change_year = last_year_old + 1  (year after the old APN disappears).
Validated against first_year_new when available.

Output: data/raw_data/change_year_candidates.csv
  Sorted by Total_Units_CSV descending — highest-impact pairs first.
  Includes a Promote_Ready flag (YES/NO) for rows that are high-confidence
  and can be copied directly into apn_genealogy_master.csv.

Run with ArcGIS Pro Python:
  "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" detect_change_years.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import arcpy
import pandas as pd

from config import OUTPUT_FC, SOURCE_FC, FC_APN, FC_YEAR, CSV_YEARS
from utils import get_logger, el_pad, el_depad, _EL_2D, _EL_3D

log = get_logger("detect_change_years")

QA_CSV   = Path(__file__).resolve().parents[2] / "data" / "raw_data" / "qa_lost_vs_new_genealogy.csv"
OUT_CSV  = Path(__file__).resolve().parents[2] / "data" / "raw_data" / "change_year_candidates.csv"

CSV_YEARS_SET = set(CSV_YEARS)   # 2012–2025


# ── Step 1: Load & deduplicate NEEDS_CHANGE_YEAR pairs ───────────────────────

def _is_el_format_pair(old: str, new: str) -> bool:
    """True if old and new are El Dorado 2-digit/3-digit variants of the same parcel."""
    if _EL_3D.match(old) and el_depad(old) == new:
        return True
    if _EL_2D.match(old) and el_pad(old) == new:
        return True
    return False


def load_pairs() -> pd.DataFrame:
    log.info("Loading %s ...", QA_CSV)
    df = pd.read_csv(QA_CSV, dtype=str)
    df = df[df["Action"].str.strip() == "NEEDS_CHANGE_YEAR"].copy()
    log.info("  NEEDS_CHANGE_YEAR rows: %d", len(df))

    df["Total_Units_CSV"] = pd.to_numeric(df["Total_Units_CSV"], errors="coerce").fillna(0).astype(int)

    # Drop El Dorado format-only pairs (2-digit ↔ 3-digit suffix variants).
    # These are already handled by the S2 El Dorado fix — adding them to
    # genealogy would create duplicate substitutions.
    el_mask = df.apply(lambda r: _is_el_format_pair(r["Lost_APN"], r["Candidate_New_APN"]), axis=1)
    if el_mask.any():
        log.info("  Dropping %d El Dorado format-only pairs (handled by S2 EL fix)", el_mask.sum())
    df = df[~el_mask].copy()

    # Keep one row per (Lost_APN, Candidate_New_APN) — highest unit count wins
    df = (df.sort_values("Total_Units_CSV", ascending=False)
            .drop_duplicates(subset=["Lost_APN", "Candidate_New_APN"])
            .reset_index(drop=True))

    log.info("  Unique (old, new) pairs after EL filter: %d", len(df))
    return df


# ── Step 2: Build APN → years-present lookup from OUTPUT_FC ──────────────────

def build_apn_years(apns: set) -> dict[str, set[int]]:
    """
    Return {apn: {year, year, ...}} for all APNs in *apns* found in OUTPUT_FC.
    Also checks El Dorado 2-digit / 3-digit variants and maps them back to the
    canonical form supplied in *apns*.
    """
    # Expand El Dorado variants
    depad_lookup: dict[str, str] = {}   # 2d_form -> canonical
    pad_lookup:   dict[str, str] = {}   # 3d_form -> canonical
    expanded: set[str] = set(apns)

    for apn in apns:
        if _EL_3D.match(apn):
            two_d = el_depad(apn)
            depad_lookup[two_d] = apn
            expanded.add(two_d)
        elif _EL_2D.match(apn):
            three_d = el_pad(apn)
            pad_lookup[three_d] = apn
            expanded.add(three_d)

    result: dict[str, set[int]] = {a: set() for a in apns}
    expanded_list = sorted(expanded)
    batch_size = 500

    for fc in [OUTPUT_FC, SOURCE_FC]:
        if not arcpy.Exists(fc):
            log.warning("FC not found, skipping: %s", fc)
            continue
        log.info("  Querying %s for %d APNs ...", fc.split("\\")[-1], len(expanded_list))

        for i in range(0, len(expanded_list), batch_size):
            chunk = expanded_list[i : i + batch_size]
            sql = " OR ".join(f"{FC_APN} = '{a}'" for a in chunk)
            try:
                with arcpy.da.SearchCursor(fc, [FC_APN, FC_YEAR], sql) as cur:
                    for raw_apn, yr in cur:
                        if not raw_apn or yr is None:
                            continue
                        a = str(raw_apn).strip()
                        yr = int(yr)
                        # Resolve to canonical form
                        canonical = depad_lookup.get(a) or pad_lookup.get(a) or a
                        if canonical in result:
                            result[canonical].add(yr)
            except Exception as exc:
                log.warning("Query failed on %s chunk %d: %s", fc.split("\\")[-1], i, exc)

    found = sum(1 for v in result.values() if v)
    log.info("  APNs found in FC: %d / %d", found, len(apns))
    return result


# ── Step 3: Compute suggested change_year ────────────────────────────────────

def suggest_change_year(old_years: set[int], new_years: set[int]
                        ) -> tuple[int | None, str]:
    """
    Returns (suggested_change_year, confidence).

    Logic:
      - last_old = max year old APN appears in FC (within CSV_YEARS)
      - first_new = min year new APN appears in FC (within CSV_YEARS)
      - Ideal: last_old + 1 == first_new  → HIGH confidence
      - Only old available: last_old + 1   → MEDIUM
      - Only new available: first_new      → MEDIUM
      - Neither:                           → LOW / None
      - Old appears in ALL years (2012-2025): likely a format-only rename → MEDIUM,
        use first_new if available else flag for manual review
    """
    old_fc = {y for y in old_years if y in CSV_YEARS_SET}
    new_fc = {y for y in new_years if y in CSV_YEARS_SET}

    last_old  = max(old_fc)  if old_fc  else None
    first_new = min(new_fc)  if new_fc  else None

    all_years_present = old_fc == CSV_YEARS_SET  # old APN never disappeared

    if all_years_present:
        # Old APN still in FC for all years — may be a format rename or ongoing APN
        if first_new is not None:
            return first_new, "MEDIUM_FORMAT"
        return None, "LOW_PERSISTENT"

    if last_old is not None and first_new is not None:
        from_old  = last_old + 1
        if from_old == first_new:
            return from_old, "HIGH"
        # Off by one year: still useful, note discrepancy
        if abs(from_old - first_new) == 1:
            return min(from_old, first_new), "MEDIUM_OFFBYONE"
        # Larger gap: trust the first appearance of new APN
        return first_new, "MEDIUM_GAP"

    if last_old is not None:
        return last_old + 1, "MEDIUM_OLD_ONLY"

    if first_new is not None:
        return first_new, "MEDIUM_NEW_ONLY"

    return None, "LOW"


# ── Step 4: Assemble output CSV ───────────────────────────────────────────────

def run():
    log.info("=== detect_change_years: finding change_year for NEEDS_CHANGE_YEAR pairs ===")

    pairs = load_pairs()

    all_apns = set(pairs["Lost_APN"]) | set(pairs["Candidate_New_APN"])
    log.info("Unique APNs to look up: %d", len(all_apns))

    apn_years = build_apn_years(all_apns)

    rows = []
    for _, pair in pairs.iterrows():
        old_apn = pair["Lost_APN"]
        new_apn = pair["Candidate_New_APN"]

        old_years = apn_years.get(old_apn, set())
        new_years = apn_years.get(new_apn, set())

        last_old  = max((y for y in old_years if y in CSV_YEARS_SET), default=None)
        first_new = min((y for y in new_years if y in CSV_YEARS_SET), default=None)

        suggested, confidence = suggest_change_year(old_years, new_years)

        in_fc_old = 1 if old_years else 0
        in_fc_new = 1 if new_years else 0

        # Promote-ready: HIGH confidence, new APN exists in FC
        promote = (
            "YES" if confidence in ("HIGH", "MEDIUM_OFFBYONE") and in_fc_new == 1
            else "NO"
        )

        rows.append({
            "Lost_APN"           : old_apn,
            "Candidate_New_APN"  : new_apn,
            "Issue_Category"     : pair["Issue_Category"],
            "Match_Source"       : pair["Match_Source"],
            "Match_Type"         : pair["Match_Type"],
            "Total_Units_CSV"    : pair["Total_Units_CSV"],
            "FC_Last_Year_Old"   : last_old,
            "FC_First_Year_New"  : first_new,
            "Suggested_Change_Year": suggested,
            "Confidence"         : confidence,
            "In_FC_Old"          : in_fc_old,
            "In_FC_New"          : in_fc_new,
            "Promote_Ready"      : promote,
            # Pre-filled columns matching apn_genealogy_master.csv schema
            "old_apn"            : old_apn,
            "new_apn"            : new_apn,
            "change_year"        : suggested,
            "change_type"        : pair["Match_Type"].replace("kk_rename", "rename")
                                                     .replace("accela_rename", "rename")
                                                     .replace("_rename", "rename"),
            "is_primary"         : 1,
            "year_source"        : "fc_last_old+1" if confidence.startswith("HIGH") else "fc_first_new",
            "source"             : pair["Match_Source"],
            "fc_last_year"       : last_old,
            "fc_new_first"       : first_new,
        })

    df_out = pd.DataFrame(rows).sort_values(
        ["Promote_Ready", "Total_Units_CSV"], ascending=[False, False]
    ).reset_index(drop=True)

    # Summary
    log.info("")
    log.info("=== SUMMARY ===")
    for conf, grp in df_out.groupby("Confidence"):
        log.info("  %-25s : %d pairs  /  %d units",
                 conf, len(grp), grp["Total_Units_CSV"].sum())
    log.info("")
    promote_df = df_out[df_out["Promote_Ready"] == "YES"]
    log.info("Promote_Ready = YES : %d pairs / %d units",
             len(promote_df), promote_df["Total_Units_CSV"].sum())
    log.info("Promote_Ready = NO  : %d pairs", len(df_out) - len(promote_df))
    log.info("")

    log.info("Top 20 promote-ready pairs (highest units):")
    top = promote_df.head(20)[["Lost_APN", "Candidate_New_APN", "Suggested_Change_Year",
                                "Confidence", "Total_Units_CSV"]]
    log.info("\n%s", top.to_string(index=False))

    df_out.to_csv(OUT_CSV, index=False)
    log.info("")
    log.info("Written: %s  (%d rows)", OUT_CSV, len(df_out))
    log.info("")
    log.info("Next steps:")
    log.info("  1. Open change_year_candidates.csv")
    log.info("  2. Filter Promote_Ready = YES — review Suggested_Change_Year in ArcGIS Pro")
    log.info("     (check that old APN disappears / new APN appears in the right year)")
    log.info("  3. Copy confirmed rows (old_apn, new_apn, change_year, ...) into")
    log.info("     apn_genealogy_master.csv")
    log.info("  4. Re-run build_genealogy_tahoe.py then re-run ETL")
    log.info("  5. For Promote_Ready = NO, use ArcGIS Pro to manually determine change_year")

    return df_out


if __name__ == "__main__":
    run()
