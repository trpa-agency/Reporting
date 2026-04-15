"""
qa_lost_apns_vs_new_genealogy.py
---------------------------------
Post-ETL QA script.  Run this after a full ETL run to:

  1. Summarise what's still lost (from QA_Lost_APNs in the GDB)
  2. Cross-reference lost APNs against two new genealogy files:
       - Accela genealogy from addresses.xlsx  (Washoe County format changes + renames)
       - Parcel Genealogy Lookups KK.xlsx      (mixed format normalization + renames)
  3. Report which lost APNs have a candidate mapping in the new files
     so an analyst can decide whether to promote them to the master table

Outputs
-------
  - Console summary
  - data/raw_data/qa_lost_vs_new_genealogy.csv  (review list)

Usage
-----
  cd parcel_development_history_etl
  & "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" scripts/qa_lost_apns_vs_new_genealogy.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import arcpy
import pandas as pd

from config import GDB, QA_LOST_APNS
from utils import get_logger, el_pad, el_depad, _EL_2D, _EL_3D

log = get_logger("qa_lost_vs_genealogy")

# ── Paths ─────────────────────────────────────────────────────────────────────
RAW = Path(__file__).resolve().parents[2] / "data" / "raw_data"
ACCELA_XL  = RAW / "Accela genealogy from addresses.xlsx"
KK_XL      = RAW / "Parcel Genealogy Lookups KK.xlsx"
TAHOE_CSV  = RAW / "apn_genealogy_tahoe.csv"
OUT_CSV    = RAW / "qa_lost_vs_new_genealogy.csv"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _norm(apn: str) -> str:
    """Normalise an APN for comparison: strip whitespace."""
    return str(apn).strip() if apn else ""


def _both_formats(apn: str) -> list[str]:
    """Return both El Dorado 2- and 3-digit forms of an APN (plus the original)."""
    apn = _norm(apn)
    forms = {apn}
    if _EL_2D.match(apn):
        forms.add(el_pad(apn))
    if _EL_3D.match(apn):
        forms.add(el_depad(apn))
    return list(forms)


# ── Step 1: Load QA_Lost_APNs ─────────────────────────────────────────────────

def load_lost_apns() -> pd.DataFrame:
    if not arcpy.Exists(QA_LOST_APNS):
        log.error("QA_Lost_APNs not found at %s — run the ETL first.", QA_LOST_APNS)
        sys.exit(1)

    rows = []
    fields = [f.name for f in arcpy.ListFields(QA_LOST_APNS)
              if f.name not in ("OBJECTID",)]
    with arcpy.da.SearchCursor(QA_LOST_APNS, fields) as cur:
        for row in cur:
            rows.append(dict(zip(fields, row)))
    df = pd.DataFrame(rows)
    df["APN"] = df["APN"].astype(str).str.strip()
    log.info("QA_Lost_APNs: %d rows", len(df))
    return df


# ── Step 2: Load new genealogy files ─────────────────────────────────────────

def load_accela() -> pd.DataFrame:
    if not ACCELA_XL.exists():
        log.warning("Accela file not found: %s", ACCELA_XL)
        return pd.DataFrame(columns=["old_apn", "new_apn"])
    df = pd.read_excel(ACCELA_XL, sheet_name="Sheet3")
    df.columns = ["old_apn", "new_apn", "old_dup"]
    df = df[["old_apn", "new_apn"]].copy()
    df["old_apn"] = df["old_apn"].astype(str).str.strip()
    df["new_apn"] = df["new_apn"].astype(str).str.strip()
    df = df[df["old_apn"] != df["new_apn"]].dropna()
    # Flag pairs where the segment count changes (e.g. 3-part → 4-part APN).
    # The cause is unknown — could be a county renumbering, a parcel event,
    # or a data artifact.  Label it for analyst review rather than assuming cause.
    df["is_segment_format_change"] = (
        df["old_apn"].str.count("-") != df["new_apn"].str.count("-"))
    log.info("Accela: %d pairs (%d segment-count change, %d same-format)",
             len(df), df["is_segment_format_change"].sum(),
             (~df["is_segment_format_change"]).sum())
    return df


def load_kk() -> pd.DataFrame:
    if not KK_XL.exists():
        log.warning("KK file not found: %s", KK_XL)
        return pd.DataFrame(columns=["old_apn", "new_apn"])
    df = pd.read_excel(KK_XL, sheet_name="Sheet1")
    df.columns = ["old_apn", "new_apn"]
    df["old_apn"] = df["old_apn"].astype(str).str.strip()
    df["new_apn"] = df["new_apn"].astype(str).str.strip()
    df = df[df["old_apn"] != df["new_apn"]].dropna()
    # Flag pure format normalization: same digits, just padding difference
    def _digits(apn):
        return apn.replace("-", "").lstrip("0")
    df["is_format_only"] = df.apply(
        lambda r: _digits(r["old_apn"]) == _digits(r["new_apn"]), axis=1)
    log.info("KK: %d pairs (%d format-only, %d actual renames)",
             len(df), df["is_format_only"].sum(),
             (~df["is_format_only"]).sum())
    return df


def load_existing_tahoe() -> set:
    if not TAHOE_CSV.exists():
        return set()
    df = pd.read_csv(TAHOE_CSV, dtype=str)
    return set(zip(df["apn_old"].str.strip(), df["apn_new"].str.strip()))


# ── Step 3: Cross-reference ───────────────────────────────────────────────────

def cross_reference(df_lost: pd.DataFrame,
                    df_accela: pd.DataFrame,
                    df_kk: pd.DataFrame,
                    existing_pairs: set) -> pd.DataFrame:
    # Build lookup: {apn_form -> [(source, old_apn, new_apn, flag)]}
    lookup: dict[str, list] = {}

    for _, row in df_accela.iterrows():
        flag = "segment_format_change" if row.get("is_segment_format_change") else "accela_rename"
        for form in _both_formats(row["old_apn"]):
            lookup.setdefault(form, []).append(
                ("ACCELA", row["old_apn"], row["new_apn"], flag))

    for _, row in df_kk.iterrows():
        flag = "format_only" if row.get("is_format_only") else "kk_rename"
        for form in _both_formats(row["old_apn"]):
            lookup.setdefault(form, []).append(
                ("KK", row["old_apn"], row["new_apn"], flag))

    results = []
    for _, lost_row in df_lost.iterrows():
        apn = lost_row["APN"]
        matches = []
        for form in _both_formats(apn):
            matches.extend(lookup.get(form, []))

        if not matches:
            results.append({
                "Lost_APN"          : apn,
                "Issue_Category"    : lost_row.get("Issue_Category", ""),
                "Years_Lost"        : lost_row.get("Years_Lost", ""),
                "Total_Units_CSV"   : lost_row.get("Total_Units_CSV", 0),
                "Match_Source"      : "NONE",
                "Candidate_New_APN" : "",
                "Match_Type"        : "",
                "Already_In_Tahoe"  : "",
                "Action"            : "no_candidate",
            })
        else:
            for source, old_raw, new_raw, flag in matches:
                already = (old_raw, new_raw) in existing_pairs
                results.append({
                    "Lost_APN"          : apn,
                    "Issue_Category"    : lost_row.get("Issue_Category", ""),
                    "Years_Lost"        : lost_row.get("Years_Lost", ""),
                    "Total_Units_CSV"   : lost_row.get("Total_Units_CSV", 0),
                    "Match_Source"      : source,
                    "Candidate_New_APN" : new_raw,
                    "Match_Type"        : flag,
                    "Already_In_Tahoe"  : "YES" if already else "NO",
                    "Action"            : (
                        "already_in_tahoe" if already else
                        "review_format_only" if flag in ("format_only", "segment_format_change") else
                        "NEEDS_CHANGE_YEAR"
                    ),
                })

    df_out = pd.DataFrame(results)
    df_out = df_out.sort_values(
        ["Action", "Issue_Category", "Total_Units_CSV"],
        ascending=[True, True, False]
    )
    return df_out


# ── Step 4: Summary ───────────────────────────────────────────────────────────

def print_summary(df_lost: pd.DataFrame, df_match: pd.DataFrame) -> None:
    log.info("")
    log.info("=" * 60)
    log.info("QA SUMMARY: Lost APNs vs New Genealogy Files")
    log.info("=" * 60)

    log.info("\nLost APNs by category:")
    for cat, grp in df_lost.groupby("Issue_Category"):
        log.info("  %-20s: %d APNs / %d units",
                 cat, len(grp), grp["Total_Units_CSV"].sum())

    has_match = df_match[df_match["Match_Source"] != "NONE"]
    no_match  = df_match[df_match["Match_Source"] == "NONE"]

    log.info("\nCross-reference results:")
    log.info("  Lost APNs with a candidate mapping : %d", has_match["Lost_APN"].nunique())
    log.info("  Lost APNs with NO candidate        : %d", no_match["Lost_APN"].nunique())

    log.info("\nCandidate breakdown (by Action):")
    for action, grp in has_match.groupby("Action"):
        units = df_lost[df_lost["APN"].isin(grp["Lost_APN"])]["Total_Units_CSV"].sum()
        log.info("  %-30s: %d APNs / ~%d units", action, grp["Lost_APN"].nunique(), units)

    log.info("\nTop lost APNs with NEEDS_CHANGE_YEAR candidates (highest units first):")
    needs_yr = has_match[has_match["Action"] == "NEEDS_CHANGE_YEAR"]
    top = (needs_yr.groupby(["Lost_APN", "Candidate_New_APN", "Match_Source", "Match_Type"])
           .first().reset_index()
           .sort_values("Total_Units_CSV", ascending=False)
           .head(20))
    if len(top):
        log.info("  %-20s  %-20s  %-8s  %-20s  %s",
                 "Lost_APN", "Candidate_New_APN", "Source", "Match_Type", "Units")
        for _, r in top.iterrows():
            log.info("  %-20s  %-20s  %-8s  %-20s  %d",
                     r["Lost_APN"], r["Candidate_New_APN"],
                     r["Match_Source"], r["Match_Type"], r["Total_Units_CSV"])
    else:
        log.info("  (none)")

    log.info("")
    log.info("Full review list written to: %s", OUT_CSV)
    log.info("Next steps:")
    log.info("  1. Open qa_lost_vs_new_genealogy.csv, filter Action = NEEDS_CHANGE_YEAR")
    log.info("     Verify each pair in ArcGIS Pro, then add change_year and promote")
    log.info("     to apn_genealogy_master.csv or apn_genealogy_accela.csv")
    log.info("  2. Filter Action = review_format_only (includes segment_format_change pairs)")
    log.info("     These may be handled as a county-wide lookup rather than genealogy")
    log.info("  3. Filter Action = no_candidate")
    log.info("     These need manual spatial investigation in ArcGIS Pro")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("Loading QA_Lost_APNs from GDB ...")
    df_lost = load_lost_apns()

    log.info("Loading new genealogy files ...")
    df_accela = load_accela()
    df_kk     = load_kk()
    existing  = load_existing_tahoe()
    log.info("Existing tahoe pairs: %d", len(existing))

    log.info("Cross-referencing ...")
    df_match = cross_reference(df_lost, df_accela, df_kk, existing)

    df_match.to_csv(OUT_CSV, index=False)

    print_summary(df_lost, df_match)


if __name__ == "__main__":
    main()
