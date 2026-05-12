"""
Step 2b — Apply parcel genealogy corrections to df_csv.

Reads the consolidated Tahoe master table at GENEALOGY_TAHOE, filtered to:
  - is_primary == 1
  - change_year is set
  - in_fc_new == 1   (new APN exists in FC — ensures remap targets something real)

Sorts by (source_priority, change_year) and applies in a single vectorized
pass. Sorting by change_year handles multi-chain events (A->B->C) correctly.
Conflict-skip prevents double-counting for many-to-many events.

For each applied record:
  - Rows in df_csv where APN == apn_old AND Year >= change_year have their
    APN replaced with apn_new.
  - Substitution is skipped if (apn_new, year) already has non-zero units —
    avoids double-counting on many-to-many events.

This step runs AFTER the El Dorado APN fix and BEFORE csv_lookup is built.
The spatial crosswalk in s03 handles any remaining unresolved cases.

The consolidated master table is the single source of truth — re-run
`scripts/build_genealogy_tahoe.py` whenever upstream sources change (manual
master / Accela / LTinfo / spatial). The four individual CSVs are inputs to
that builder, not consumed here.

Writes QA_Genealogy_Applied to GDB.
"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))

from pathlib import Path

import pandas as pd

from config import GENEALOGY_TAHOE, QA_GENEALOGY_APPLIED
from utils  import get_logger, write_qa_table

log = get_logger("s02b_genealogy")


# ── Loader ────────────────────────────────────────────────────────────────────

def _load_master_table(path: str) -> pd.DataFrame:
    """
    Load the consolidated Tahoe genealogy master (apn_genealogy_tahoe.csv).
    Filters to is_primary=1, change_year set, in_fc_new=1.
    Sorts by (source_priority, change_year) for correct multi-chain ordering.
    """
    if not Path(path).exists():
        raise FileNotFoundError(
            f"Genealogy master table not found: {path}\n"
            f"Run scripts/build_genealogy_tahoe.py first to build it from the "
            f"four upstream sources (manual master, Accela, LTinfo, spatial)."
        )

    df = pd.read_csv(path, dtype=str)
    df.columns = df.columns.str.strip()

    required = {"apn_old", "apn_new", "change_year", "is_primary", "in_fc_new"}
    missing  = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Genealogy master table missing required columns: {missing}\n"
            f"Re-run scripts/build_genealogy_tahoe.py."
        )

    df["apn_old"]     = df["apn_old"].str.strip()
    df["apn_new"]     = df["apn_new"].str.strip()
    df["is_primary"]  = pd.to_numeric(df["is_primary"], errors="coerce").fillna(0).astype(int)
    df["in_fc_new"]   = pd.to_numeric(df["in_fc_new"],  errors="coerce").fillna(0).astype(int)
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


# ── Vectorized application ────────────────────────────────────────────────────

def _apply_vectorized(
    df: pd.DataFrame,
    records: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Apply genealogy records to df using vectorized operations.

    Records must already be sorted by (source_priority, change_year) so that
    multi-chain events (A->B->C) resolve in the correct order.

    For each record:
      - Rows where APN == apn_old AND Year >= change_year are candidates.
      - Candidates where (apn_new, Year) already has non-zero units are
        conflict-skipped (prevents double-counting for many-to-many events).
      - Remaining rows have APN set to apn_new.

    Returns (updated_df, qa_rows).
    """
    df = df.copy()
    qa_rows: list[dict] = []
    remapped_old: set[str] = set()

    # Pick the value column once (Units_CSV / Value / first non-APN/Year col)
    val_col = "Units_CSV" if "Units_CSV" in df.columns else (
              "Value" if "Value" in df.columns else
              next((c for c in df.columns if c not in ("APN", "Year")), None))

    for _, rec in records.iterrows():
        old_apn     = rec["apn_old"]
        new_apn     = rec["apn_new"]
        change_year = int(rec["change_year"])
        change_type = str(rec.get("event_type", "")).strip()
        source      = str(rec.get("source", "")).strip()

        if old_apn == new_apn or old_apn in remapped_old:
            continue

        cand_mask = (df["APN"] == old_apn) & (df["Year"] >= change_year)
        if not cand_mask.any():
            continue

        # Conflict check: years where new_apn already has NON-ZERO units.
        # Using zero-value rows as conflicts was too strict — it blocked
        # remapping of split-parcel successors that have 0 units in early
        # years, causing those historical units to be silently dropped.
        if val_col:
            existing_new = set(
                df.loc[(df["APN"] == new_apn) & (df[val_col] > 0), "Year"])
        else:
            existing_new = set(df.loc[df["APN"] == new_apn, "Year"])
        cand_years   = df.loc[cand_mask, "Year"]
        conflict_yrs = cand_years[cand_years.isin(existing_new)]
        safe_mask    = cand_mask & ~df["Year"].isin(conflict_yrs)

        if conflict_yrs.any():
            log.debug("  Conflict skip: %s -> %s years %s",
                      old_apn, new_apn, sorted(conflict_yrs.tolist()))

        if safe_mask.any():
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


# ── Public entry point ────────────────────────────────────────────────────────

def run(df_csv: pd.DataFrame) -> pd.DataFrame:
    log.info("=== Step 2b: Apply genealogy APN corrections ===")

    tahoe = _load_master_table(GENEALOGY_TAHOE)
    df, all_qa = _apply_vectorized(df_csv, tahoe)

    # Summary by source
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

    # Write QA table
    if all_qa:
        df_qa = pd.DataFrame(all_qa)
        try:
            write_qa_table(
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
