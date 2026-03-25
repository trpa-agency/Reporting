"""
Step 2b — Apply parcel genealogy corrections to df_csv.

Two sources applied in priority order:

  1. apn_genealogy_master.csv  (hand-curated, analyst-reviewed — authoritative)
  2. apn_genealogy_spatial.csv (auto-detected by build_spatial_genealogy.py — fills gaps)

For each record where change_year is populated and is_primary == 1:
  - Rows in df_csv where APN == old_apn AND Year >= change_year have their
    APN replaced with new_apn.
  - Substitution is skipped if (new_apn, year) already exists in df_csv to
    avoid inflating unit counts.
  - Spatial records are skipped for any old_apn already handled by the manual master.

This step runs AFTER the El Dorado APN fix and BEFORE csv_lookup is built,
so the lookup already references the correct current APN for each year when
the FC join happens.  The spatial crosswalk in s03 handles any remaining
unresolved cases.

Writes QA_Genealogy_Applied to GDB (includes a Source column: MANUAL / SPATIAL).
"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))

from pathlib import Path

import pandas as pd

from config import GENEALOGY_MASTER, GENEALOGY_SPATIAL, QA_GENEALOGY_APPLIED
from utils  import get_logger, df_to_gdb_table

log = get_logger("s02b_genealogy")


# ── Loaders ───────────────────────────────────────────────────────────────────

def _load_csv(path: str, label: str) -> pd.DataFrame:
    """
    Load a genealogy CSV and return primary, apply-ready rows.
    Returns empty DataFrame if file is missing or malformed.
    """
    if not Path(path).exists():
        log.warning("%s not found at %s — skipping.", label, path)
        return pd.DataFrame()

    try:
        df = pd.read_csv(path, dtype=str)
    except Exception as exc:
        log.error("Could not read %s: %s", label, exc)
        return pd.DataFrame()

    df.columns = df.columns.str.strip()
    required   = {"old_apn", "new_apn", "change_year", "is_primary"}
    missing    = required - set(df.columns)
    if missing:
        log.error("%s missing columns: %s — skipping.", label, missing)
        return pd.DataFrame()

    df["old_apn"]    = df["old_apn"].str.strip()
    df["new_apn"]    = df["new_apn"].str.strip()
    df["is_primary"] = pd.to_numeric(df["is_primary"], errors="coerce").fillna(0).astype(int)

    df = df[df["is_primary"] == 1].copy()
    df["change_year"] = pd.to_numeric(df["change_year"], errors="coerce")

    skipped = df["change_year"].isna().sum()
    df = df.dropna(subset=["change_year"])
    df["change_year"] = df["change_year"].astype(int)

    log.info("%s: %d apply-ready rows (is_primary=1, change_year set)", label, len(df))
    if skipped:
        log.warning(
            "  %d primary rows have no change_year — skipped. "
            "Fill in change_year to include them.", skipped)

    return df


# ── Application logic ─────────────────────────────────────────────────────────

def _apply_records(
    df: pd.DataFrame,
    records: pd.DataFrame,
    existing: set,
    source: str,
    already_remapped_old: set,
) -> tuple[pd.DataFrame, list[dict], set]:
    """
    Apply genealogy records to df.

    Parameters
    ----------
    df                  : long-format CSV DataFrame (APN, Year, Units_CSV)
    records             : genealogy rows to apply (old_apn, new_apn, change_year, ...)
    existing            : set of (APN, Year) combos currently in df — updated in place
    source              : "MANUAL" or "SPATIAL" — written to QA output
    already_remapped_old: old APNs already handled by a prior source — skipped here

    Returns
    -------
    (updated_df, qa_rows, updated_existing)
    """
    qa_rows = []

    for _, rec in records.iterrows():
        old_apn     = rec["old_apn"]
        new_apn     = rec["new_apn"]
        change_year = int(rec["change_year"])
        change_type = str(rec.get("change_type", "")).strip()

        if old_apn == new_apn:
            continue
        if old_apn in already_remapped_old:
            continue   # manual record already handled this APN

        mask = (df["APN"] == old_apn) & (df["Year"] >= change_year)
        if not mask.any():
            continue

        years_all       = df.loc[mask, "Year"].tolist()
        conflict_years  = [y for y in years_all if (new_apn, y) in existing]
        safe_years      = [y for y in years_all if (new_apn, y) not in existing]

        if conflict_years:
            log.debug(
                "  Conflict skip: %s → %s already in df for years %s",
                old_apn, new_apn, conflict_years,
            )

        if safe_years:
            safe_mask   = mask & df["Year"].isin(safe_years)
            units_moved = int(df.loc[safe_mask, "Units_CSV"].sum())
            df.loc[safe_mask, "APN"] = new_apn

            for y in safe_years:
                existing.add((new_apn, y))
                existing.discard((old_apn, y))

            qa_rows.append({
                "Old_APN"          : old_apn,
                "New_APN"          : new_apn,
                "Change_Year"      : change_year,
                "Change_Type"      : change_type,
                "Years_Updated"    : len(safe_years),
                "Years_Conflicted" : len(conflict_years),
                "Total_Units_Moved": units_moved,
                "Source"           : source,
            })

    return df, qa_rows, existing


# ── Public entry point ────────────────────────────────────────────────────────

def run(df_csv: pd.DataFrame) -> pd.DataFrame:
    log.info("=== Step 2b: Apply genealogy APN corrections ===")

    master  = _load_csv(GENEALOGY_MASTER,  "Manual master CSV")
    spatial = _load_csv(GENEALOGY_SPATIAL, "Spatial genealogy CSV")

    if master.empty and spatial.empty:
        log.info("No genealogy corrections to apply.")
        return df_csv

    existing = set(zip(df_csv["APN"], df_csv["Year"]))
    df       = df_csv.copy()
    all_qa   = []

    # ── Pass 1: manual master (authoritative) ─────────────────────────────────
    if not master.empty:
        df, qa_manual, existing = _apply_records(
            df, master, existing, source="MANUAL",
            already_remapped_old=set())
        log.info("Manual:  %d APN substitutions  /  %d unit-years remapped",
                 len(qa_manual),
                 sum(r["Total_Units_Moved"] for r in qa_manual))
        all_qa.extend(qa_manual)

    # ── Pass 2: spatial CSV (fills gaps not covered by manual) ────────────────
    if not spatial.empty:
        manual_old_apns = set(master["old_apn"]) if not master.empty else set()
        df, qa_spatial, existing = _apply_records(
            df, spatial, existing, source="SPATIAL",
            already_remapped_old=manual_old_apns)
        log.info("Spatial: %d APN substitutions  /  %d unit-years remapped",
                 len(qa_spatial),
                 sum(r["Total_Units_Moved"] for r in qa_spatial))
        all_qa.extend(qa_spatial)

    log.info("Total:   %d APN substitutions  /  %d unit-years remapped",
             len(all_qa),
             sum(r["Total_Units_Moved"] for r in all_qa))

    # ── Write QA table ────────────────────────────────────────────────────────
    if all_qa:
        df_qa = pd.DataFrame(all_qa)
        try:
            df_to_gdb_table(
                df_qa, QA_GENEALOGY_APPLIED,
                text_lengths={"Old_APN": 50, "New_APN": 50,
                              "Change_Type": 30, "Source": 10},
            )
            log.info("Written → %s", QA_GENEALOGY_APPLIED)
        except Exception as exc:
            log.warning("Could not write QA_Genealogy_Applied: %s", exc)

    log.info("Step 2b complete.")
    return df


if __name__ == "__main__":
    import s02_load_csv as s02
    df_csv, _ = s02.run()
    df_fixed  = run(df_csv)
    changed   = (df_fixed["APN"] != df_csv["APN"]).sum()
    print(f"Rows with APN changed: {changed:,}")
