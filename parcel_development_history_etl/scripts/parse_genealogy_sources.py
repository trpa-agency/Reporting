"""
Parse LTinfo and Accela Excel genealogy files into ETL-ready CSVs.

Outputs
-------
data/raw_data/apn_genealogy_accela.csv
    One row per (old_apn, new_apn) pair derived from Accela permit transactions.
    change_year is taken directly from REC_DATE.  All rows have is_primary=1.

data/raw_data/apn_genealogy_ltinfo.csv
    One row per (ParentAPN, ChildAPN) pair from LTinfo Sheet2.
    change_year is filled where a matching Accela transaction is found;
    unmatched rows have change_year blank and will be skipped by s02b until
    a year is provided.

Run once (or whenever the source Excel files are updated):
    C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe \\
        parcel_development_history_etl/parse_genealogy_sources.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1]))
from config import GENEALOGY_ACCELA, GENEALOGY_LTINFO

ROOT = Path(__file__).parents[2]
RAW  = ROOT / "data" / "raw_data"

# Source Excel files still live in raw_data; only outputs go to qa_data
LTINFO_XLSX  = RAW / "LTinfo_Parcel_Genealogy.xlsx"
ACCELA_XLSX  = RAW / "Accela_Genealogy_March2026.xlsx"
OUT_ACCELA   = Path(GENEALOGY_ACCELA)
OUT_LTINFO   = Path(GENEALOGY_LTINFO)


# ── Accela ────────────────────────────────────────────────────────────────────

def parse_accela() -> pd.DataFrame:
    """
    Convert Accela GENEALOGY sheet to (old_apn, new_apn, change_year) pairs.

    Encoding:
      GEN_STAGE_NBR = 2  →  parent / old APN (being replaced)
      GEN_STAGE_NBR = 1  →  child  / new APN (successor)
      GEN_TRAN_ID groups all APNs involved in one split/merge/rename event.
    """
    print("Reading Accela...")
    df = pd.read_excel(ACCELA_XLSX, sheet_name="GENEALOGY", dtype=str)
    df.columns = df.columns.str.strip()

    # Keep only PARCEL rows that are active
    df = df[df["OBJECT_TYPE"].str.strip() == "PARCEL"].copy()
    df = df[df["REC_STATUS"].str.strip() == "A"].copy()

    df["GEN_TRAN_ID"]    = pd.to_numeric(df["GEN_TRAN_ID"],    errors="coerce")
    df["GEN_STAGE_NBR"]  = pd.to_numeric(df["GEN_STAGE_NBR"],  errors="coerce")
    df["REC_DATE"]       = pd.to_datetime(df["REC_DATE"],       errors="coerce")
    df["OBJECT_NBR"]     = df["OBJECT_NBR"].str.strip()

    parents = df[df["GEN_STAGE_NBR"] == 2][["GEN_TRAN_ID", "OBJECT_NBR", "REC_DATE"]] \
                .rename(columns={"OBJECT_NBR": "old_apn"})
    children = df[df["GEN_STAGE_NBR"] == 1][["GEN_TRAN_ID", "OBJECT_NBR"]] \
                 .rename(columns={"OBJECT_NBR": "new_apn"})

    pairs = parents.merge(children, on="GEN_TRAN_ID", how="inner")

    # Derive change_type from transaction structure
    sizes = df.groupby("GEN_TRAN_ID")["GEN_STAGE_NBR"].value_counts().unstack(fill_value=0)
    sizes.columns = [f"stage_{int(c)}" for c in sizes.columns]
    sizes = sizes.reset_index()
    n_parents  = sizes.get("stage_2", pd.Series(0, index=sizes.index))
    n_children = sizes.get("stage_1", pd.Series(0, index=sizes.index))
    type_map = {}
    for _, row in sizes.iterrows():
        tid = row["GEN_TRAN_ID"]
        np_ = row.get("stage_2", 0)
        nc_ = row.get("stage_1", 0)
        if np_ == 1 and nc_ == 1:
            type_map[tid] = "rename"
        elif np_ == 1 and nc_ > 1:
            type_map[tid] = "split"
        elif np_ > 1 and nc_ == 1:
            type_map[tid] = "merge"
        else:
            type_map[tid] = "complex"
    pairs["change_type"] = pairs["GEN_TRAN_ID"].map(type_map)

    pairs["change_year"] = pairs["REC_DATE"].dt.year.astype("Int64")
    pairs["is_primary"]  = 1
    pairs["source"]      = "ACCELA"
    pairs["overlap_pct"] = ""

    # Remove self-loops and drop rows without a year
    pairs = pairs[pairs["old_apn"] != pairs["new_apn"]]
    pairs = pairs.dropna(subset=["change_year"])

    # Deduplicate — same pair can appear in multiple transactions
    pairs = pairs.sort_values("change_year").drop_duplicates(
        subset=["old_apn", "new_apn"], keep="first")

    out = pairs[["old_apn", "new_apn", "change_year", "overlap_pct",
                 "change_type", "is_primary", "source"]].copy()
    out["change_year"] = out["change_year"].astype(int)

    print(f"  Accela pairs: {len(out):,}")
    print(f"  change_type breakdown:\n{out['change_type'].value_counts().to_string()}")
    print(f"  change_year range: {out['change_year'].min()} – {out['change_year'].max()}")

    return out


# ── LTinfo ────────────────────────────────────────────────────────────────────

def parse_ltinfo(accela_pairs: pd.DataFrame) -> pd.DataFrame:
    """
    Convert LTinfo Sheet2 (ParentAPN → ChildAPN) to ETL format.
    Fills change_year from Accela where a matching pair exists.
    """
    print("Reading LTinfo...")
    df = pd.read_excel(LTINFO_XLSX, sheet_name="Sheet2", dtype=str)
    df.columns = df.columns.str.strip()
    df["ParentAPN"] = df["ParentAPN"].str.strip()
    df["ChildAPN"]  = df["ChildAPN"].str.strip()
    df = df.dropna(subset=["ParentAPN", "ChildAPN"])
    df = df[df["ParentAPN"] != df["ChildAPN"]]
    df = df.drop_duplicates(subset=["ParentAPN", "ChildAPN"])

    # Look up change_year from Accela pairs
    accela_lookup = accela_pairs.set_index(["old_apn", "new_apn"])["change_year"].to_dict()
    df["change_year"] = df.apply(
        lambda r: accela_lookup.get((r["ParentAPN"], r["ChildAPN"]), pd.NA), axis=1)

    matched   = df["change_year"].notna().sum()
    unmatched = df["change_year"].isna().sum()
    print(f"  LTinfo pairs: {len(df):,}  (matched year from Accela: {matched:,}, "
          f"unmatched / no year: {unmatched:,})")

    # Remove pairs already fully covered by Accela (same old+new+year)
    accela_set = set(zip(accela_pairs["old_apn"], accela_pairs["new_apn"]))
    ltinfo_only = df[~df.apply(
        lambda r: (r["ParentAPN"], r["ChildAPN"]) in accela_set, axis=1)].copy()
    print(f"  LTinfo-only (not already in Accela): {len(ltinfo_only):,}")

    ltinfo_only = ltinfo_only.rename(columns={"ParentAPN": "old_apn", "ChildAPN": "new_apn"})
    ltinfo_only["overlap_pct"] = ""
    ltinfo_only["change_type"] = ""
    ltinfo_only["is_primary"]  = 1
    ltinfo_only["source"]      = "LTINFO"

    out = ltinfo_only[["old_apn", "new_apn", "change_year", "overlap_pct",
                        "change_type", "is_primary", "source"]].copy()
    return out


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    accela = parse_accela()
    accela.to_csv(OUT_ACCELA, index=False)
    print(f"  Written -> {OUT_ACCELA}")

    print()
    ltinfo = parse_ltinfo(accela)
    ltinfo.to_csv(OUT_LTINFO, index=False)
    print(f"  Written -> {OUT_LTINFO}")

    print()
    print(f"Summary:")
    print(f"  Accela rows (with change_year, ready to apply): {len(accela):,}")
    has_year = ltinfo["change_year"].notna().sum()
    print(f"  LTinfo rows with change_year (ready to apply): {has_year:,}")
    no_year  = ltinfo["change_year"].isna().sum()
    print(f"  LTinfo rows WITHOUT change_year (skipped by s02b): {no_year:,}")


if __name__ == "__main__":
    main()
