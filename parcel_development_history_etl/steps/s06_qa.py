"""
Step 6 — QA checks.  Writes results as GDB tables for review in ArcGIS Pro.

Tables written
--------------
QA_Units_By_Year        CSV vs FC totals, diff, status per year
QA_Lost_APNs            APNs with units in CSV but 0 in FC (categorised)
QA_Duplicate_APN_Year   Duplicate APN x Year rows in FC
QA_Spatial_Completeness Null spatial attr counts (TRPA boundary rows only)
QA_FC_Units_Not_In_CSV  FC units > 0 where raw CSV has no entry for that APN x Year
                        (categorised: EL_DORADO_FORMAT, GENEALOGY_REMAP,
                         CROSSWALK_REMAP, UNKNOWN)
"""
import re
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))

import arcpy
import pandas as pd

from config import (
    OUTPUT_FC, FC_APN, FC_YEAR, FC_UNITS, FC_COUNTY,
    SPATIAL_FIELDS, CSV_YEARS, CSV_PATH, EL_PAD_YEAR,
    FC_NATIVE_YEARS,
    QA_UNITS_BY_YEAR, QA_LOST_APNS,
    QA_DUPLICATE_APN_YEAR, QA_SPATIAL_COMPLETENESS,
    QA_GENEALOGY_APPLIED, QA_APN_CROSSWALK, QA_FC_NOT_IN_CSV,
    QA_UNIT_RECONCILIATION,
)
from utils import get_logger, write_qa_table

log = get_logger("s06_qa")

_2D = re.compile(r"^\d{3}-\d{2,3}-\d{2}$")
_3D = re.compile(r"^\d{3}-\d{2,3}-0\d{2}$")


def _read_fc() -> pd.DataFrame:
    """Read the output FC into a DataFrame."""
    qa_fields = [FC_APN, FC_YEAR, FC_UNITS, FC_COUNTY,
                 "WITHIN_TRPA_BNDY", "FC_Native_Units", "Unit_Source"] + SPATIAL_FIELDS
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


def _raw_csv_positive_set() -> set:
    """
    Read the raw input CSV (no APN transformations) and return the set of
    (APN, Year) pairs where Units > 0.  Used by Check 5.
    """
    df = pd.read_csv(CSV_PATH, dtype=str)
    year_cols = [c for c in df.columns if "Final" in c]
    df_long = df.melt(id_vars="APN", value_vars=year_cols,
                      var_name="Year_Label", value_name="Units")
    df_long["Year"]  = df_long["Year_Label"].str.extract(r"(\d{4})").astype(int)
    df_long["Units"] = pd.to_numeric(df_long["Units"], errors="coerce").fillna(0)
    df_long["APN"]   = df_long["APN"].astype(str).str.strip()
    df_long = df_long[df_long["Year"].isin(CSV_YEARS)]
    return set(zip(df_long.loc[df_long["Units"] > 0, "APN"],
                   df_long.loc[df_long["Units"] > 0, "Year"]))


def _read_remap_sets() -> tuple[set, set]:
    """
    Return (genealogy_new_apns, crosswalk_fc_apns) — APNs that received units
    via genealogy substitution or spatial crosswalk respectively.
    Used by Check 5 to categorise why the FC APN doesn't appear in the raw CSV.
    """
    genealogy_apns = set()
    crosswalk_apns = set()

    if arcpy.Exists(QA_GENEALOGY_APPLIED):
        with arcpy.da.SearchCursor(QA_GENEALOGY_APPLIED, ["New_APN"]) as cur:
            for (apn,) in cur:
                if apn:
                    genealogy_apns.add(str(apn).strip())

    if arcpy.Exists(QA_APN_CROSSWALK):
        with arcpy.da.SearchCursor(QA_APN_CROSSWALK, ["FC_APN"]) as cur:
            for (apn,) in cur:
                if apn:
                    crosswalk_apns.add(str(apn).strip())

    return genealogy_apns, crosswalk_apns


_PRIORITY = {"DISAGREE": 1, "FC_NATIVE": 2, "CSV_ONLY": 3}


def _check_unit_reconciliation(df_fc: pd.DataFrame) -> None:
    """
    Compare CSV-derived units against FC native units for years where the
    FC has its own curated unit data (FC_NATIVE_YEARS).

    Categories written to QA_Unit_Reconciliation:
      DISAGREE   Both sources have units but different values — needs human judgment
      FC_NATIVE  FC has units, CSV has none — units being captured from FC not in CSV
      CSV_ONLY   CSV has units, FC native = 0 — existing deficit for FC-native years

    2013–2017 rows are excluded: FC has no native data for those years so
    CSV_ONLY there is expected and already covered by QA_Lost_APNs (Check 2).

    Sorted by Priority (DISAGREE first), then Unit_Diff descending so the
    largest discrepancies appear at the top for review in ArcGIS Pro.
    """
    if "Unit_Source" not in df_fc.columns or "FC_Native_Units" not in df_fc.columns:
        log.warning("  Unit_Source / FC_Native_Units fields not in FC — "
                    "run main.py to populate them (S4 adds these fields)")
        return

    # Restrict to years where FC has native data
    df_native_yrs = df_fc[df_fc["Year"].isin(FC_NATIVE_YEARS)].copy()
    df_native_yrs["FC_Native_Units"] = df_native_yrs["FC_Native_Units"].fillna(0).astype(int)

    records = []

    for _, row in df_native_yrs.iterrows():
        source   = str(row.get("Unit_Source", "")).strip()
        csv_val  = int(row.get("FC_Units", 0))        # merged (CSV-wins) value
        fc_val   = int(row.get("FC_Native_Units", 0))
        apn      = str(row["APN"]).strip()
        year     = int(row["Year"])

        if source == "DISAGREE":
            category = "DISAGREE"
            diff     = abs(csv_val - fc_val)
        elif source == "FC_NATIVE":
            category = "FC_NATIVE"
            diff     = fc_val           # CSV had 0; diff = what FC adds
        elif source == "CSV" and csv_val > 0 and fc_val == 0:
            category = "CSV_ONLY"
            diff     = csv_val
        else:
            continue                   # BOTH_AGREE or both zero — no action needed

        records.append({
            "APN"            : apn,
            "Year"           : year,
            "CSV_Units"      : csv_val,
            "FC_Native_Units": fc_val,
            "Unit_Diff"      : diff,
            "Category"       : category,
            "Priority"       : _PRIORITY.get(category, 9),
            "Review_Note"    : _reconciliation_note(category, csv_val, fc_val),
        })

    if not records:
        log.info("  No reconciliation discrepancies found.")
        return

    df_recon = (pd.DataFrame(records)
                .sort_values(["Priority", "Unit_Diff"], ascending=[True, False])
                .reset_index(drop=True))

    log.info("  Reconciliation rows: %d", len(df_recon))
    for cat, grp in df_recon.groupby("Category"):
        log.info("    %-12s : %d APN×Year pairs  /  %d total unit diff",
                 cat, len(grp), grp["Unit_Diff"].sum())

    write_qa_table(
        df_recon, QA_UNIT_RECONCILIATION,
        text_lengths={"APN": 50, "Category": 15, "Review_Note": 300},
    )
    log.info("  Written → %s", QA_UNIT_RECONCILIATION)
    log.info("  Open in ArcGIS Pro: join to OUTPUT_FC on APN + Year, "
             "filter by Category to review on map.")


def _reconciliation_note(category: str, csv_val: int, fc_val: int) -> str:
    if category == "DISAGREE":
        return (f"CSV={csv_val}, FC={fc_val} (diff={abs(csv_val - fc_val)}). "
                "Both sources have units but disagree. "
                "Review parcel on map — determine which count is correct "
                "and update the CSV or FC native value.")
    if category == "FC_NATIVE":
        return (f"FC={fc_val}, CSV=0. "
                "FC has units not in CSV. "
                "Review parcel on map — if units are real, add to CSV.")
    if category == "CSV_ONLY":
        return (f"CSV={csv_val}, FC=0. "
                "CSV has units but FC native is 0 for a year with FC data. "
                "Review parcel on map — may be a split, remap needed, "
                "or FC native data is missing.")
    return ""


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

    write_qa_table(df_yr, QA_UNITS_BY_YEAR)

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

    write_qa_table(df_lost_out, QA_LOST_APNS,
                    text_lengths={"APN": 50, "Years_Lost": 200,
                                  "Years_In_FC": 200, "Suggested_Action": 500})

    # ── Check 3: Duplicate APN x Year ─────────────────────────────────────
    log.info("Check 3: Duplicate APN x Year ...")
    dup_mask = df_fc.duplicated(subset=["APN","Year"], keep=False)
    df_dups  = df_fc[dup_mask][["APN","Year","FC_Units","COUNTY"]].copy()
    log.info("  Duplicate rows: %d", len(df_dups))
    if len(df_dups):
        write_qa_table(df_dups, QA_DUPLICATE_APN_YEAR,
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
        write_qa_table(df_sp, QA_SPATIAL_COMPLETENESS,
                        text_lengths={"Field": 50, "Status": 10})

    # ── Check 5: FC units with no raw-CSV match ────────────────────────────
    log.info("Check 5: FC units not in raw CSV (APN x Year) ...")
    raw_pos                       = _raw_csv_positive_set()
    genealogy_new_apns, xwalk_apns = _read_remap_sets()

    df_fc_pos = df_fc[df_fc["FC_Units"] > 0][["APN","Year","FC_Units","COUNTY"]].copy()
    df_no_raw = df_fc_pos[~df_fc_pos.apply(
        lambda r: (r["APN"], int(r["Year"])) in raw_pos, axis=1)].copy()

    def _categorise_fc(row) -> str:
        apn    = str(row["APN"]).strip()
        yr     = int(row["Year"])
        county = str(row.get("COUNTY", "")).strip().upper()
        # El Dorado format: 3-digit suffix APN, county = EL, year >= EL_PAD_YEAR
        if county == "EL" and yr >= EL_PAD_YEAR and _3D.match(apn):
            return "EL_DORADO_FORMAT"
        if apn in genealogy_new_apns:
            return "GENEALOGY_REMAP"
        if apn in xwalk_apns:
            return "CROSSWALK_REMAP"
        return "UNKNOWN"

    df_no_raw["Category"] = df_no_raw.apply(_categorise_fc, axis=1)

    log.info("  FC units with no raw CSV match : %d rows  (%d unique APNs)",
             len(df_no_raw), df_no_raw["APN"].nunique())
    log.info("  By category:")
    for cat, grp in df_no_raw.groupby("Category"):
        log.info("    %-22s : %d rows  /  %d APNs  /  %d units",
                 cat, len(grp), grp["APN"].nunique(), grp["FC_Units"].sum())

    write_qa_table(df_no_raw.sort_values(["Category","APN","Year"]),
                    QA_FC_NOT_IN_CSV,
                    text_lengths={"APN": 50, "COUNTY": 10, "Category": 30})
    log.info("  Written → %s", QA_FC_NOT_IN_CSV)

    # ── Check 6: Unit reconciliation — CSV vs FC native ───────────────────
    log.info("Check 6: Unit reconciliation (CSV vs FC native) ...")

    _check_unit_reconciliation(df_fc)

    log.info("Step 6 complete.  QA tables written to %s",
             __import__('config').GDB)


if __name__ == "__main__":
    import s02_load_csv as s02
    df_csv, _ = s02.run()
    run(df_csv)
