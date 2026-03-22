"""
Step 6 — QA checks.  Writes results as GDB tables for review in ArcGIS Pro.

Tables written
--------------
QA_Units_By_Year        CSV vs FC totals, diff, status per year
QA_Lost_APNs            APNs with units in CSV but 0 in FC (categorised)
QA_Duplicate_APN_Year   Duplicate APN x Year rows in FC
QA_Spatial_Completeness Null spatial attr counts (TRPA boundary rows only)
"""
import re
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))

import arcpy
import pandas as pd

from config import (
    OUTPUT_FC, FC_APN, FC_YEAR, FC_UNITS, FC_COUNTY,
    SPATIAL_FIELDS, CSV_YEARS,
    QA_UNITS_BY_YEAR, QA_LOST_APNS,
    QA_DUPLICATE_APN_YEAR, QA_SPATIAL_COMPLETENESS,
)
from utils import get_logger, df_to_gdb_table

log = get_logger("s06_qa")

_2D = re.compile(r"^\d{3}-\d{2,3}-\d{2}$")
_3D = re.compile(r"^\d{3}-\d{2,3}-0\d{2}$")


def _read_fc() -> pd.DataFrame:
    """Read the output FC into a DataFrame."""
    qa_fields = [FC_APN, FC_YEAR, FC_UNITS, FC_COUNTY,
                 "WITHIN_TRPA_BNDY"] + SPATIAL_FIELDS
    existing  = {f.name for f in arcpy.ListFields(OUTPUT_FC)}
    read      = [f for f in qa_fields if f in existing]
    missing   = set(qa_fields) - existing
    if missing:
        log.warning("Fields not in FC (skipped): %s", sorted(missing))

    yr_list = ", ".join(str(y) for y in CSV_YEARS)
    rows = []
    with arcpy.da.SearchCursor(
            OUTPUT_FC, read, f"{FC_YEAR} IN ({yr_list})") as cur:
        for row in cur:
            rows.append(dict(zip(read, row)))

    df = pd.DataFrame(rows).rename(columns={
        FC_APN: "APN", FC_YEAR: "Year",
        FC_UNITS: "FC_Units", FC_COUNTY: "COUNTY"})
    df["FC_Units"] = df["FC_Units"].fillna(0)
    log.info("FC rows read: %d", len(df))
    return df


def _categorise_lost(apn: str, yrs_lost: list, yrs_in_fc: set) -> tuple[str, str]:
    """
    Assign an issue category and suggested action to a lost APN.

    Returns (ISSUE_CATEGORY, SUGGESTED_ACTION)
    """
    all_years = set(CSV_YEARS)
    yrs_present = yrs_in_fc  # years where this APN appears in the FC

    if not yrs_present:
        return (
            "PARCEL_NEW",
            "APN never found in FC for any year. "
            "Verify parcel exists in AllParcels service. "
            "May need geometry fetch or CSV correction."
        )

    first_missing = min(yrs_lost)
    last_present  = max(yrs_present) if yrs_present else None

    if last_present and last_present < first_missing:
        return (
            "PARCEL_SPLIT",
            f"APN present in FC through {last_present}, then disappears. "
            "Parcel was likely split or re-numbered. "
            "Update CSV to reference successor APNs for years after split."
        )

    if min(yrs_lost) > min(all_years) and yrs_present:
        return (
            "PARCEL_SPLIT",
            f"APN present in FC for some years but missing for: {sorted(yrs_lost)}. "
            "Likely a parcel split or APN renaming event. "
            "Update CSV to reference successor APNs for affected years."
        )

    return (
        "UNKNOWN",
        "APN appears in FC for some years but unit value is 0 for listed years. "
        "Manual investigation required."
    )


def run(df_csv: pd.DataFrame) -> None:
    log.info("=== Step 6: QA checks ===")

    df_fc = _read_fc()

    # ── Check 1: Units by year ─────────────────────────────────────────────
    log.info("Check 1: Units by year ...")
    fc_tot  = df_fc.groupby("Year")["FC_Units"].sum().rename("FC_Total")
    csv_tot = df_csv.groupby("Year")["Units_CSV"].sum().rename("CSV_Total")
    df_yr   = pd.concat([csv_tot, fc_tot], axis=1).loc[sorted(CSV_YEARS)].fillna(0)
    df_yr["Diff"]   = (df_yr["FC_Total"] - df_yr["CSV_Total"]).astype(int)
    df_yr["Status"] = df_yr["Diff"].apply(lambda d: "OK" if d == 0 else "FLAG")
    df_yr = df_yr.reset_index()
    df_yr.columns = ["Year", "CSV_Total", "FC_Total", "Diff", "Status"]
    df_yr[["CSV_Total","FC_Total"]] = df_yr[["CSV_Total","FC_Total"]].astype(int)

    log.info("\n  %-6s  %-10s  %-10s  %-8s  %s",
             "Year", "CSV_Total", "FC_Total", "Diff", "Status")
    for _, r in df_yr.iterrows():
        log.info("  %-6d  %-10d  %-10d  %-+8d  %s",
                 r.Year, r.CSV_Total, r.FC_Total, r.Diff, r.Status)

    df_to_gdb_table(df_yr, QA_UNITS_BY_YEAR)

    # ── Check 2: Lost APNs ────────────────────────────────────────────────
    log.info("Check 2: Lost APNs ...")

    # Merge CSV (units > 0) onto FC to find FC_Units = 0
    df_csv_pos = df_csv[df_csv["Units_CSV"] > 0].copy()
    df_merged  = df_csv_pos.merge(
        df_fc[["APN", "Year", "FC_Units", "COUNTY"]],
        on=["APN","Year"], how="left")
    df_lost = df_merged[df_merged["FC_Units"].fillna(0) == 0].copy()
    df_lost["FC_Units"] = df_lost["FC_Units"].fillna(0).astype(int)

    # For each lost APN, determine which years it's present in the FC
    fc_apn_years = df_fc.groupby("APN")["Year"].apply(set).to_dict()

    # Categorise
    lost_records = []
    for apn, grp in df_lost.groupby("APN"):
        yrs_lost    = sorted(grp["Year"].tolist())
        yrs_in_fc   = fc_apn_years.get(apn, set())
        county      = grp["COUNTY"].dropna().iloc[0] if grp["COUNTY"].notna().any() else ""
        total_units = grp["Units_CSV"].sum()
        cat, action = _categorise_lost(apn, yrs_lost, yrs_in_fc)

        lost_records.append({
            "APN"              : apn,
            "COUNTY"           : str(county),
            "Years_Lost"       : str(yrs_lost),
            "Num_Years_Lost"   : len(yrs_lost),
            "Total_Units_CSV"  : int(total_units),
            "Years_In_FC"      : str(sorted(yrs_in_fc)) if yrs_in_fc else "NEVER",
            "Issue_Category"   : cat,
            "Suggested_Action" : action,
        })

    df_lost_out = pd.DataFrame(lost_records).sort_values(
        ["Issue_Category","Total_Units_CSV"], ascending=[True, False])

    log.info("  Lost APNs total     : %d", len(df_lost_out))
    log.info("  By category:")
    for cat, grp in df_lost_out.groupby("Issue_Category"):
        log.info("    %-20s : %d APNs  /  %d units",
                 cat, len(grp), grp["Total_Units_CSV"].sum())
    log.info("  Lost units by year:")
    for yr, grp in df_lost.groupby("Year"):
        log.info("    %d : %d APNs  /  %.0f units",
                 yr, grp["APN"].nunique(), grp["Units_CSV"].sum())

    df_to_gdb_table(df_lost_out, QA_LOST_APNS,
                    text_lengths={"APN": 50, "Years_Lost": 200,
                                  "Years_In_FC": 200, "Suggested_Action": 500})

    # ── Check 3: Duplicate APN x Year ─────────────────────────────────────
    log.info("Check 3: Duplicate APN x Year ...")
    dup_mask = df_fc.duplicated(subset=["APN","Year"], keep=False)
    df_dups  = df_fc[dup_mask][["APN","Year","FC_Units","COUNTY"]].copy()
    log.info("  Duplicate rows: %d", len(df_dups))
    if len(df_dups):
        df_to_gdb_table(df_dups, QA_DUPLICATE_APN_YEAR,
                        text_lengths={"APN": 50, "COUNTY": 10})
    elif arcpy.Exists(QA_DUPLICATE_APN_YEAR):
        arcpy.management.Delete(QA_DUPLICATE_APN_YEAR)

    # ── Check 4: Spatial completeness (TRPA boundary only) ────────────────
    log.info("Check 4: Spatial completeness (WITHIN_TRPA_BNDY = 1 only) ...")
    df_trpa = df_fc[df_fc.get("WITHIN_TRPA_BNDY", pd.Series(dtype=int)) == 1]
    if "WITHIN_TRPA_BNDY" not in df_fc.columns or len(df_trpa) == 0:
        log.warning("  WITHIN_TRPA_BNDY not available — skipping spatial completeness")
    else:
        sp_rows = []
        check_fields = [f for f in SPATIAL_FIELDS if f in df_trpa.columns]
        for field in check_fields:
            col = df_trpa[field]
            if col.dtype == object:
                bad = col.isna() | (col.astype(str).str.strip().isin(["", "None"]))
            else:
                bad = col.isna()
            n_bad = int(bad.sum())
            pct   = round(100 * n_bad / len(df_trpa), 2) if len(df_trpa) else 0
            sp_rows.append({
                "Field"      : field,
                "Null_Count" : n_bad,
                "Pct_Null"   : pct,
                "TRPA_Rows"  : len(df_trpa),
                "Status"     : "OK" if n_bad == 0 else "FLAG",
            })
            log.info("  %-35s : %d null  (%.1f%%)  %s",
                     field, n_bad, pct, "OK" if n_bad == 0 else "FLAG")

        df_sp = pd.DataFrame(sp_rows)
        df_to_gdb_table(df_sp, QA_SPATIAL_COMPLETENESS,
                        text_lengths={"Field": 50, "Status": 10})

    log.info("Step 6 complete.  QA tables written to %s",
             __import__('config').GDB)


if __name__ == "__main__":
    import s02_load_csv as s02
    df_csv, _ = s02.run()
    run(df_csv)
