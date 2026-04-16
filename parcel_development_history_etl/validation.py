"""
Parcel Development History — Conflict Detection (validation.py)
===============================================================
Standalone post-ETL QA script.  Reads OUTPUT_FC (never modifies it),
queries external truth sources, and writes QA_Flag_Table to the same GDB.

Rules are specified in validation.md alongside this file.
To update rules: edit validation.md, then ask Claude to sync this file.

Usage
-----
  cd parcel_development_history_etl
  C:\\...\\arcgispro-py3\\python.exe validation.py                     # all checks
  C:\\...\\arcgispro-py3\\python.exe validation.py --flags PHANTOM DROPOUT
  C:\\...\\arcgispro-py3\\python.exe validation.py --apn 035-123-456   # debug one APN

Output
------
  ParcelHistory.gdb\\QA_Flag_Table   (APN x Year flag rows)

  Join to OUTPUT_FC on APN + YEAR in ArcGIS Pro, then filter
  QA_STATUS = 'Pending' to review flagged parcels on the map.

  SQL filter example:
    SELECT * FROM QA_Flag_Table
    WHERE APN LIKE '035%' AND FLAG_CODE = 'PHANTOM'
    ORDER BY YEAR DESC;
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import arcpy
import pandas as pd

from config import (
    OUTPUT_FC, FC_APN, FC_YEAR, FC_UNITS,
    CSV_YEARS,
    QA_UNITS_BY_YEAR, QA_GENEALOGY_APPLIED, QA_FLAG_TABLE,
    IMPERVIOUS_SVC, BMP_CERT_SVC, VHR_PERMIT_SVC,
    LTINFO_PERMITS,
)
from utils import get_logger, df_to_gdb_table

log = get_logger("validation")

# ── Schema ────────────────────────────────────────────────────────────────────
# QA_Flag_Table field text lengths (passed to df_to_gdb_table)
_TEXT_LENGTHS = {
    "APN"       : 50,
    "FLAG_CODE" : 50,
    "EVIDENCE"  : 500,
    "QA_STATUS" : 20,
}

ALL_FLAGS = {"PHANTOM", "DROPOUT", "GENEALOGY", "TOTALS_MISMATCH", "UNVERIFIED"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_fc() -> pd.DataFrame:
    """Read OUTPUT_FC into a DataFrame (APN, Year, Residential_Units)."""
    fields   = [FC_APN, FC_YEAR, FC_UNITS]
    existing = {f.name for f in arcpy.ListFields(OUTPUT_FC)}
    read     = [f for f in fields if f in existing]
    yr_list  = ", ".join(str(y) for y in CSV_YEARS)

    rows = []
    with arcpy.da.SearchCursor(
            OUTPUT_FC, read, f"{FC_YEAR} IN ({yr_list})") as cur:
        for row in cur:
            rows.append(dict(zip(read, row)))

    df = pd.DataFrame(rows).rename(columns={
        FC_APN: "APN", FC_YEAR: "Year", FC_UNITS: "Residential_Units"})
    df["APN"]              = df["APN"].astype(str).str.strip()
    df["Year"]             = df["Year"].astype(int)
    df["Residential_Units"]= df["Residential_Units"].fillna(0).astype(int)
    log.info("FC rows read: %d", len(df))
    return df


def _read_gdb_table(table_path: str) -> pd.DataFrame:
    """Read a standalone GDB table into a DataFrame (empty if not found)."""
    if not arcpy.Exists(table_path):
        log.warning("GDB table not found: %s", table_path)
        return pd.DataFrame()
    fields = [f.name for f in arcpy.ListFields(table_path)
              if f.type not in ("Geometry", "OID")]
    rows = [dict(zip(fields, row))
            for row in arcpy.da.SearchCursor(table_path, fields)]
    return pd.DataFrame(rows)


def _make_flag(apn: str, year: int, flag_code: str,
               csv_val: int, matrix_val: int, evidence: str) -> dict:
    return {
        "APN"       : apn,
        "YEAR"      : year,
        "FLAG_CODE" : flag_code,
        "CSV_VAL"   : csv_val,
        "MATRIX_VAL": matrix_val,
        "EVIDENCE"  : evidence,
    }


def _batch_query(svc_url: str, apns: list, out_apn_field: str = "APN",
                 batch: int = 500) -> dict:
    """
    Batch-query a TRPA FeatureServer/MapServer layer by APN.
    Returns {APN: attributes_dict}.
    Skips with a warning if svc_url is empty (stub not yet configured).
    """
    if not svc_url:
        log.warning("Service URL not configured — skipping query (set URL in config.py).")
        return {}

    try:
        from arcgis.features import FeatureLayer
    except ImportError:
        log.warning("arcgis package not available — skipping service query.")
        return {}

    fl      = FeatureLayer(svc_url)
    results = {}
    for i in range(0, len(apns), batch):
        chunk = apns[i : i + batch]
        where = "{} IN ({})".format(
            out_apn_field,
            ", ".join(f"'{a}'" for a in chunk))
        try:
            for feat in fl.query(where=where).features:
                results[str(feat.attributes.get(out_apn_field, "")).strip()] = feat.attributes
        except Exception as exc:
            log.warning("Service query error (batch %d): %s", i // batch, exc)
    log.debug("Service query returned %d records for %d APNs", len(results), len(apns))
    return results


# ── Check A: PHANTOM ─────────────────────────────────────────────────────────

def check_phantom(df_fc: pd.DataFrame,
                  impervious_lookup: dict,
                  permit_lookup: dict) -> list[dict]:
    """
    Flag parcels that appear developed but show 0 units.

    Condition: Residential_Units == 0 AND
               (impervious footprint detected OR permit finaled <= Year)

    Sources: IMPERVIOUS_SVC, LTINFO_PERMITS
    """
    zeros = df_fc[df_fc["Residential_Units"] == 0]
    flags = []
    for _, row in zeros.iterrows():
        apn, yr = row["APN"], int(row["Year"])
        evidence = []

        if impervious_lookup.get(apn):
            evidence.append("Impervious")

        permit_yr = permit_lookup.get(apn)
        if permit_yr is not None:
            try:
                if int(permit_yr) <= yr:
                    evidence.append(f"Permit:{permit_yr}")
            except (TypeError, ValueError):
                pass

        if evidence:
            flags.append(_make_flag(apn, yr, "PHANTOM", 0, 0,
                                    "; ".join(evidence)))
    log.info("PHANTOM: %d flags", len(flags))
    return flags


# ── Check B: DROPOUT ─────────────────────────────────────────────────────────

def check_dropout(df_fc: pd.DataFrame) -> list[dict]:
    """
    Flag year gaps where units temporarily drop to 0 between two non-zero years.

    Condition: units[Year-1] > 0 AND units[Year] == 0 AND units[Year+1] > 0

    No external service needed — pure in-memory check.
    """
    pivot = df_fc.pivot_table(
        index="APN", columns="Year",
        values="Residential_Units", fill_value=0,
    )
    years = sorted(pivot.columns)
    flags = []

    for i, yr in enumerate(years[1:-1]):   # skip first and last — no neighbours
        prev_yr = years[i]
        next_yr = years[i + 2]
        gap_mask = (
            (pivot[prev_yr] > 0) &
            (pivot[yr]      == 0) &
            (pivot[next_yr] > 0)
        )
        for apn in pivot.index[gap_mask]:
            evidence = (
                f"Units: {prev_yr}={int(pivot.loc[apn, prev_yr])}, "
                f"{yr}=0, "
                f"{next_yr}={int(pivot.loc[apn, next_yr])}"
            )
            flags.append(_make_flag(apn, yr, "DROPOUT", 0, 0, evidence))

    log.info("DROPOUT: %d flags", len(flags))
    return flags


# ── Check C: GENEALOGY ───────────────────────────────────────────────────────

def check_genealogy(df_fc: pd.DataFrame) -> list[dict]:
    """
    Flag genealogy substitutions where the successor APN has no units in FC
    after the event year — potential unit loss during a subdivision or rename.

    Condition: a record in QA_Genealogy_Applied has Total_Units_Moved > 0,
               but the New_APN has Residential_Units == 0 for years >= Change_Year.

    Source: QA_Genealogy_Applied GDB table (written by S02b during the ETL run).
    """
    gen = _read_gdb_table(QA_GENEALOGY_APPLIED)
    if gen.empty:
        log.info("GENEALOGY: QA_Genealogy_Applied not found — skipping.")
        return []

    # Build fast lookup: {(APN, Year): units}
    fc_lookup = df_fc.set_index(["APN", "Year"])["Residential_Units"].to_dict()

    flags = []
    for _, rec in gen.iterrows():
        old_apn     = str(rec.get("Old_APN", "")).strip()
        new_apn     = str(rec.get("New_APN", "")).strip()
        change_year = rec.get("Change_Year")
        units_moved = int(rec.get("Total_Units_Moved", 0))

        if not old_apn or not new_apn or units_moved == 0:
            continue

        try:
            change_year = int(change_year)
        except (TypeError, ValueError):
            continue

        affected_years = [y for y in CSV_YEARS if y >= change_year]
        missing_years  = [y for y in affected_years
                          if fc_lookup.get((new_apn, y), 0) == 0]

        if missing_years:
            evidence = (
                f"Old:{old_apn}→New:{new_apn}; "
                f"Units moved:{units_moved}; "
                f"New APN missing units for years:{missing_years}"
            )
            for yr in missing_years:
                flags.append(_make_flag(old_apn, yr, "GENEALOGY",
                                        0, units_moved, evidence))

    log.info("GENEALOGY: %d flags", len(flags))
    return flags


# ── Check D: TOTALS_MISMATCH ─────────────────────────────────────────────────

def check_totals_mismatch() -> list[dict]:
    """
    Compare FC unit totals to CSV totals from QA_Units_By_Year.

    Any year where FC_Total != CSV_Total gets a flag.  This is the primary
    signal that units were lost or duplicated during the ETL — no external
    services required.

    Source: QA_Units_By_Year GDB table (written by Step 6 during the ETL run).
    """
    qa = _read_gdb_table(QA_UNITS_BY_YEAR)
    if qa.empty:
        log.info("TOTALS_MISMATCH: QA_Units_By_Year not found — run ETL Step 6 first.")
        return []

    flags = []
    for _, row in qa.iterrows():
        year      = int(row.get("Year",       0))
        csv_total = int(row.get("CSV_Total",  0) or 0)
        fc_total  = int(row.get("FC_Total",   0) or 0)
        diff      = fc_total - csv_total
        if diff != 0:
            flags.append({
                "APN"       : "TOTAL",
                "YEAR"      : year,
                "FLAG_CODE" : "TOTALS_MISMATCH",
                "CSV_VAL"   : csv_total,
                "MATRIX_VAL": fc_total,
                "EVIDENCE"  : (
                    f"CSV_Total={csv_total:,}, FC_Total={fc_total:,}, "
                    f"Diff={diff:+,} ({'+' if diff > 0 else ''}{diff/csv_total*100:.1f}%)"
                    if csv_total else
                    f"CSV_Total={csv_total:,}, FC_Total={fc_total:,}, Diff={diff:+,}"
                ),
            })

    log.info("TOTALS_MISMATCH: %d year(s) with discrepancies", len(flags))
    return flags


# ── Check E: UNVERIFIED ───────────────────────────────────────────────────────

def check_unverified(df_fc: pd.DataFrame,
                     bmp_lookup: dict,
                     vhr_lookup: dict) -> list[dict]:
    """
    Flag parcels with 0 units but an active BMP certificate or VHR permit.

    Condition: Residential_Units == 0 AND
               (BMP certificate active in Year OR VHR permit active in Year)

    bmp_lookup : {APN: set[int]}  — years with active BMP certificate
    vhr_lookup : {APN: set[int]}  — years with active VHR permit

    Sources: BMP_CERT_SVC, VHR_PERMIT_SVC
    """
    zeros = df_fc[df_fc["Residential_Units"] == 0]
    flags = []
    for _, row in zeros.iterrows():
        apn, yr = row["APN"], int(row["Year"])
        evidence = []

        if yr in bmp_lookup.get(apn, set()):
            evidence.append("BMP")
        if yr in vhr_lookup.get(apn, set()):
            evidence.append("VHR")

        if evidence:
            flags.append(_make_flag(apn, yr, "UNVERIFIED", 0, 0,
                                    "; ".join(evidence)))

    log.info("UNVERIFIED: %d flags", len(flags))
    return flags


# ── Service fetchers ──────────────────────────────────────────────────────────

def _fetch_impervious(apns: list) -> dict:
    """Return {APN: bool} — True if impervious footprint detected."""
    raw = _batch_query(IMPERVIOUS_SVC, apns)
    return {apn: bool(attrs) for apn, attrs in raw.items()}


def _fetch_permits(apns: list) -> dict:
    """Return {APN: int} — earliest finaled permit year."""
    raw = _batch_query(LTINFO_PERMITS, apns)
    result = {}
    for apn, attrs in raw.items():
        # Expect a field like "FinalYear" or "FINAL_YEAR" — adapt as needed
        yr = attrs.get("FinalYear") or attrs.get("FINAL_YEAR")
        if yr is not None:
            try:
                result[apn] = int(yr)
            except (TypeError, ValueError):
                pass
    return result


def _fetch_bmp(apns: list) -> dict:
    """Return {APN: set[int]} — years with an active BMP certificate."""
    raw = _batch_query(BMP_CERT_SVC, apns)
    result: dict[str, set] = {}
    for apn, attrs in raw.items():
        # Expect fields "StartYear" / "EndYear" or similar — adapt as needed
        start = attrs.get("StartYear") or attrs.get("START_YEAR")
        end   = attrs.get("EndYear")   or attrs.get("END_YEAR")
        try:
            start, end = int(start), int(end)
            result.setdefault(apn, set()).update(range(start, end + 1))
        except (TypeError, ValueError):
            pass
    return result


def _fetch_vhr(apns: list) -> dict:
    """Return {APN: set[int]} — years with an active VHR permit."""
    raw = _batch_query(VHR_PERMIT_SVC, apns)
    result: dict[str, set] = {}
    for apn, attrs in raw.items():
        start = attrs.get("StartYear") or attrs.get("START_YEAR")
        end   = attrs.get("EndYear")   or attrs.get("END_YEAR")
        try:
            start, end = int(start), int(end)
            result.setdefault(apn, set()).update(range(start, end + 1))
        except (TypeError, ValueError):
            pass
    return result


# ── Aggregation ───────────────────────────────────────────────────────────────

def _aggregate_flags(all_flags: list[dict]) -> pd.DataFrame:
    """
    Collapse multiple flags per APN×Year into a single row.
    FLAG_CODE values are pipe-delimited; EVIDENCE strings are semicolon-joined.
    """
    df = pd.DataFrame(all_flags)
    grouped = (
        df.groupby(["APN", "YEAR"])
        .agg(
            FLAG_CODE  = ("FLAG_CODE",  lambda x: " | ".join(sorted(set(x)))),
            CSV_VAL    = ("CSV_VAL",    "first"),
            MATRIX_VAL = ("MATRIX_VAL", "max"),
            EVIDENCE   = ("EVIDENCE",   lambda x: " || ".join(x)),
        )
        .reset_index()
    )
    grouped["QA_STATUS"] = "Pending"
    return grouped


# ── Main ──────────────────────────────────────────────────────────────────────

def main(flags: set = None, apn: str = None) -> None:
    log.info("=" * 60)
    log.info("Parcel Development History — Conflict Detection")
    log.info("=" * 60)

    df_fc = _read_fc()

    if apn:
        df_fc = df_fc[df_fc["APN"] == apn.strip()].copy()
        log.info("Debug mode: APN=%s  (%d rows)", apn, len(df_fc))
        if df_fc.empty:
            log.warning("APN %s not found in OUTPUT_FC — nothing to check.", apn)
            return

    run_all      = not flags
    all_apns     = df_fc["APN"].unique().tolist()
    all_flag_rows: list[dict] = []

    # ── TOTALS_MISMATCH (no service — uses QA_Units_By_Year) ─────────────────
    if run_all or "TOTALS_MISMATCH" in flags:
        all_flag_rows += check_totals_mismatch()

    # ── DROPOUT (no service) ──────────────────────────────────────────────────
    if run_all or "DROPOUT" in flags:
        all_flag_rows += check_dropout(df_fc)

    # ── GENEALOGY (no service) ────────────────────────────────────────────────
    if run_all or "GENEALOGY" in flags:
        all_flag_rows += check_genealogy(df_fc)

    # ── PHANTOM (needs IMPERVIOUS_SVC + LTINFO_PERMITS) ───────────────────────
    if run_all or "PHANTOM" in flags:
        log.info("Fetching impervious surface data ...")
        impervious = _fetch_impervious(all_apns)
        log.info("Fetching permit data ...")
        permits    = _fetch_permits(all_apns)
        all_flag_rows += check_phantom(df_fc, impervious, permits)

    # ── UNVERIFIED (needs BMP_CERT_SVC + VHR_PERMIT_SVC) ─────────────────────
    if run_all or "UNVERIFIED" in flags:
        log.info("Fetching BMP certificate data ...")
        bmp = _fetch_bmp(all_apns)
        log.info("Fetching VHR permit data ...")
        vhr = _fetch_vhr(all_apns)
        all_flag_rows += check_unverified(df_fc, bmp, vhr)

    if not all_flag_rows:
        log.info("No conflicts detected.")
        return

    df_flags = _aggregate_flags(all_flag_rows)

    log.info("-" * 60)
    log.info("Total flag rows : %d  (%d unique APNs)",
             len(df_flags), df_flags["APN"].nunique())
    for code, grp in df_flags.groupby("FLAG_CODE"):
        log.info("  %-30s : %d rows", code, len(grp))

    df_to_gdb_table(df_flags, QA_FLAG_TABLE, text_lengths=_TEXT_LENGTHS)
    log.info("Written → %s", QA_FLAG_TABLE)
    log.info(
        "In ArcGIS Pro: join QA_Flag_Table to OUTPUT_FC on APN + YEAR, "
        "then filter QA_STATUS = 'Pending' to review on the map."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Parcel Development History — Conflict Detection")
    parser.add_argument(
        "--flags", nargs="+", metavar="FLAG",
        choices=sorted(ALL_FLAGS),
        help=f"Run only these checks (default: all). Choices: {sorted(ALL_FLAGS)}")
    parser.add_argument(
        "--apn", metavar="APN",
        help="Restrict to a single APN for debugging")
    args = parser.parse_args()

    main(
        flags=set(args.flags) if args.flags else None,
        apn=args.apn,
    )
