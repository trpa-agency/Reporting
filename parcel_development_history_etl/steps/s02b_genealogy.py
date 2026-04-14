"""
Step 2b — Apply parcel genealogy corrections to df_csv.

Preferred path (when apn_genealogy_tahoe.csv exists):
  Load the consolidated Tahoe master table, filter to:
    - is_primary == 1
    - change_year is set
    - in_fc_new == 1  (new APN exists in FC — ensures remap targets something real)
  Sort by (source_priority, change_year) and apply in a single vectorized pass.
  Sorting by change_year handles multi-chain events (A->B->C) correctly.
  Conflict-skip prevents double-counting for many-to-many events.

Fallback path (individual CSVs, used if master table not yet built):
  Four passes in priority order:
    1. apn_genealogy_master.csv  (hand-curated, authoritative)
    2. apn_genealogy_accela.csv  (Accela permit system, 2021-2025)
    3. apn_genealogy_ltinfo.csv  (LTinfo parcel pairs, no dates yet)
    4. apn_genealogy_spatial.csv (auto-detected spatial overlap)

For each applied record:
  - Rows in df_csv where APN == apn_old AND Year >= change_year have their
    APN replaced with apn_new.
  - Substitution is skipped if (apn_new, year) already exists in df_csv to
    avoid inflating unit counts.

This step runs AFTER the El Dorado APN fix and BEFORE csv_lookup is built.
The spatial crosswalk in s03 handles any remaining unresolved cases.

Writes QA_Genealogy_Applied to GDB.
"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))

from pathlib import Path

import pandas as pd

from config import (GENEALOGY_MASTER, GENEALOGY_ACCELA, GENEALOGY_LTINFO,
                    GENEALOGY_SPATIAL, GENEALOGY_TAHOE, QA_GENEALOGY_APPLIED)
from utils  import get_logger, df_to_gdb_table

log = get_logger("s02b_genealogy")


# ── Loaders ───────────────────────────────────────────────────────────────────

def _load_master_table(path: str) -> pd.DataFrame:
    """
    Load the consolidated Tahoe genealogy master (apn_genealogy_tahoe.csv).
    Filters to is_primary=1, change_year set, in_fc_new=1.
    Sorts by (source_priority, change_year) for correct multi-chain ordering.
    """
    if not Path(path).exists():
        return pd.DataFrame()

    try:
        df = pd.read_csv(path, dtype=str)
    except Exception as exc:
        log.error("Could not read master table: %s", exc)
        return pd.DataFrame()

    df.columns = df.columns.str.strip()
    required = {"apn_old", "apn_new", "change_year", "is_primary", "in_fc_new"}
    missing  = required - set(df.columns)
    if missing:
        log.error("Master table missing columns: %s — falling back to individual CSVs.", missing)
        return pd.DataFrame()

    df["apn_old"]     = df["apn_old"].str.strip()
    df["apn_new"]     = df["apn_new"].str.strip()
    df["is_primary"]  = pd.to_numeric(df["is_primary"],  errors="coerce").fillna(0).astype(int)
    df["in_fc_new"]   = pd.to_numeric(df["in_fc_new"],   errors="coerce").fillna(0).astype(int)
    df["source_priority"] = pd.to_numeric(
        df.get("source_priority", pd.Series("4", index=df.index)),
        errors="coerce").fillna(4).astype(int)

    df = df[(df["is_primary"] == 1) & (df["in_fc_new"] == 1)].copy()
    df["change_year"] = pd.to_numeric(df["change_year"], errors="coerce")

    skipped = df["change_year"].isna().sum()
    df = df.dropna(subset=["change_year"])
    df["change_year"] = df["change_year"].astype(int)

    if skipped:
        log.info("  %d rows skipped (no change_year)", skipped)

    df = df.sort_values(["source_priority", "change_year"]).reset_index(drop=True)

    log.info("Master table: %d apply-ready rows (is_primary=1, in_fc_new=1, change_year set)",
             len(df))
    if "source" in df.columns:
        for src, n in sorted(df.groupby("source").size().items()):
            log.info("  %-10s: %d rows", src, n)

    return df


def _load_csv(path: str, label: str) -> pd.DataFrame:
    """Load an individual genealogy CSV (fallback path)."""
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
        log.warning("  %d primary rows have no change_year — skipped.", skipped)

    return df


# ── Vectorized application ────────────────────────────────────────────────────

def _apply_vectorized(
    df: pd.DataFrame,
    records: pd.DataFrame,
    old_col: str = "apn_old",
    new_col: str = "apn_new",
    source_col: str = "source",
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Apply genealogy records to df using vectorized operations.

    Records must already be sorted by (source_priority, change_year) so that
    multi-chain events (A->B->C) resolve in the correct order.

    For each record:
      - Rows where APN == old AND Year >= change_year are candidates.
      - Candidates where (new, Year) already exists in df are conflict-skipped.
      - Remaining rows have APN set to new.

    Returns (updated_df, qa_rows).
    """
    df = df.copy()
    qa_rows = []
    remapped_old: set[str] = set()

    for _, rec in records.iterrows():
        old_apn     = rec[old_col]
        new_apn     = rec[new_col]
        change_year = int(rec["change_year"])
        change_type = str(rec.get("event_type", rec.get("change_type", ""))).strip()
        source      = str(rec.get(source_col, "")).strip()

        if old_apn == new_apn or old_apn in remapped_old:
            continue

        cand_mask = (df["APN"] == old_apn) & (df["Year"] >= change_year)
        if not cand_mask.any():
            continue

        # Conflict check: years where new_apn already exists in df
        existing_new = set(df.loc[df["APN"] == new_apn, "Year"])
        cand_years   = df.loc[cand_mask, "Year"]
        conflict_yrs = cand_years[cand_years.isin(existing_new)]
        safe_mask    = cand_mask & ~df["Year"].isin(conflict_yrs)

        if conflict_yrs.any():
            log.debug("  Conflict skip: %s -> %s years %s",
                      old_apn, new_apn, sorted(conflict_yrs.tolist()))

        if safe_mask.any():
            val_col = "Units_CSV" if "Units_CSV" in df.columns else (
                      "Value" if "Value" in df.columns else
                      next((c for c in df.columns if c not in ("APN", "Year")), None))
            units_moved = int(df.loc[safe_mask, val_col].sum()) if val_col else 0
            safe_years  = sorted(df.loc[safe_mask, "Year"].tolist())
            df.loc[safe_mask, "APN"] = new_apn
            remapped_old.add(old_apn)

            qa_rows.append({
                "Old_APN"          : old_apn,
                "New_APN"          : new_apn,
                "Change_Year"      : change_year,
                "Change_Type"      : change_type,
                "Years_Updated"    : len(safe_years),
                "Years_Conflicted" : len(conflict_yrs),
                "Total_Units_Moved": units_moved,
                "Source"           : source,
            })

    return df, qa_rows


def _apply_records(
    df: pd.DataFrame,
    records: pd.DataFrame,
    existing: set,
    source: str,
    already_remapped_old: set,
    old_col: str = "old_apn",
    new_col: str = "new_apn",
) -> tuple[pd.DataFrame, list[dict], set]:
    """Fallback row-by-row application for individual CSV sources."""
    qa_rows = []

    for _, rec in records.iterrows():
        old_apn     = rec[old_col]
        new_apn     = rec[new_col]
        change_year = int(rec["change_year"])
        change_type = str(rec.get("change_type", rec.get("event_type", ""))).strip()
        src         = str(rec.get("source", source)).strip() or source

        if old_apn == new_apn or old_apn in already_remapped_old:
            continue

        mask = (df["APN"] == old_apn) & (df["Year"] >= change_year)
        if not mask.any():
            continue

        years_all      = df.loc[mask, "Year"].tolist()
        conflict_years = [y for y in years_all if (new_apn, y) in existing]
        safe_years     = [y for y in years_all if (new_apn, y) not in existing]

        if conflict_years:
            log.debug("  Conflict skip: %s -> %s years %s", old_apn, new_apn, conflict_years)

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
                "Source"           : src,
            })

    return df, qa_rows, existing


# ── Public entry point ────────────────────────────────────────────────────────

def run(df_csv: pd.DataFrame) -> pd.DataFrame:
    log.info("=== Step 2b: Apply genealogy APN corrections ===")

    all_qa = []

    # ── Preferred path: consolidated master table ──────────────────────────────
    tahoe = _load_master_table(GENEALOGY_TAHOE)

    if not tahoe.empty:
        df, all_qa = _apply_vectorized(
            df_csv, tahoe,
            old_col="apn_old", new_col="apn_new", source_col="source",
        )

        by_src: dict = {}
        for r in all_qa:
            s = r["Source"]
            by_src.setdefault(s, {"subs": 0, "units": 0})
            by_src[s]["subs"]  += 1
            by_src[s]["units"] += r["Total_Units_Moved"]
        for src in sorted(by_src):
            log.info("  %-10s: %d substitutions / %d unit-years",
                     src, by_src[src]["subs"], by_src[src]["units"])
        log.info("Total:   %d APN substitutions  /  %d unit-years remapped",
                 len(all_qa), sum(r["Total_Units_Moved"] for r in all_qa))

    else:
        # ── Fallback path: individual CSVs ─────────────────────────────────────
        log.warning(
            "GENEALOGY: Master table not found at %s — falling back to 4 individual CSVs. "
            "Run build_genealogy_tahoe.py to rebuild the master table for reproducible results.",
            GENEALOGY_TAHOE,
        )
        master  = _load_csv(GENEALOGY_MASTER,  "Manual master CSV")
        accela  = _load_csv(GENEALOGY_ACCELA,  "Accela genealogy CSV")
        ltinfo  = _load_csv(GENEALOGY_LTINFO,  "LTinfo genealogy CSV")
        spatial = _load_csv(GENEALOGY_SPATIAL, "Spatial genealogy CSV")

        if master.empty and accela.empty and ltinfo.empty and spatial.empty:
            log.info("No genealogy corrections to apply.")
            return df_csv

        df       = df_csv.copy()
        existing = set(zip(df_csv["APN"], df_csv["Year"]))
        remapped_old: set = set()

        for records, label in [
            (master,  "Manual"),
            (accela,  "Accela"),
            (ltinfo,  "LTinfo"),
            (spatial, "Spatial"),
        ]:
            if records.empty:
                continue
            df, qa, existing = _apply_records(
                df, records, existing, source=label,
                already_remapped_old=remapped_old)
            log.info("%s: %d APN substitutions / %d unit-years remapped",
                     label, len(qa), sum(r["Total_Units_Moved"] for r in qa))
            all_qa.extend(qa)
            remapped_old |= set(records["old_apn"])

        log.info("Total:   %d APN substitutions  /  %d unit-years remapped",
                 len(all_qa), sum(r["Total_Units_Moved"] for r in all_qa))

    # ── Write QA table ────────────────────────────────────────────────────────
    if all_qa:
        df_qa = pd.DataFrame(all_qa)
        try:
            df_to_gdb_table(
                df_qa, QA_GENEALOGY_APPLIED,
                text_lengths={"Old_APN": 50, "New_APN": 50,
                              "Change_Type": 30, "Source": 10},
            )
            log.info("Written -> %s", QA_GENEALOGY_APPLIED)
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
