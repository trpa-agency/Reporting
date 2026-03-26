"""
deduplicate_source_fc.py — Remove duplicate APN × YEAR rows from
Parcel_History_Attributed, preferring the row with a Residential_Units value.

Tiebreak rules (applied in order):
  1. Row with Residential_Units > 0  → keep
  2. Row with Residential_Units not null (but 0) → keep over null
  3. Row with lower OID              → keep (arbitrary, logged as ambiguous)

A summary table QA_Duplicates_Removed is written to the GDB recording every
deleted row (OID, APN, YEAR, Residential_Units, KEEP_REASON).

Run from ArcGIS Pro Python:
  & "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" `
    "C:/Users/mbindl/Documents/GitHub/Reporting/parcel_development_history_etl/deduplicate_source_fc.py"
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import arcpy

from config import WORKING_FC as SOURCE_FC, GDB, FC_APN, FC_YEAR, FC_UNITS

OUTPUT_TABLE = GDB + r"\QA_Duplicates_Removed"

# ── Logging ───────────────────────────────────────────────────────────────────
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("deduplicate_source_fc")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _units_field_exists() -> bool:
    return FC_UNITS in {f.name for f in arcpy.ListFields(SOURCE_FC)}


def _find_duplicates(has_units_field: bool) -> dict:
    """
    Read source FC and return {(APN, YEAR): [row_dict, ...]} for groups
    with more than one row.

    row_dict keys: oid, apn, year, units
    """
    fields = ["OID@", FC_APN, FC_YEAR]
    if has_units_field:
        fields.append(FC_UNITS)

    log.info("Scanning source FC for duplicates ...")
    groups: dict[tuple, list] = defaultdict(list)

    with arcpy.da.SearchCursor(SOURCE_FC, fields) as cur:
        for row in cur:
            oid  = row[0]
            apn  = str(row[1]).strip() if row[1] else ""
            yr   = int(row[2]) if row[2] else None
            units = row[3] if has_units_field and len(row) > 3 else None
            if apn and yr:
                groups[(apn, yr)].append({"oid": oid, "apn": apn,
                                           "year": yr, "units": units})

    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    log.info("  Total unique APN × YEAR groups : %d", len(groups))
    log.info("  Groups with duplicates         : %d", len(dupes))
    log.info("  Total duplicate rows           : %d",
             sum(len(v) for v in dupes.values()))
    return dupes


def _pick_keeper(rows: list[dict]) -> tuple[dict, list[dict], str]:
    """
    Given a list of row dicts for the same APN × YEAR, return:
      (keeper_row, rows_to_delete, keep_reason)
    """
    def _unit_score(r):
        u = r["units"]
        if u is None:
            return 0    # null
        if u > 0:
            return 2    # has actual units
        return 1        # explicitly 0 (not null)

    scored = sorted(rows, key=lambda r: (_unit_score(r), -r["oid"]), reverse=True)
    keeper    = scored[0]
    to_delete = scored[1:]

    scores = [_unit_score(r) for r in rows]
    if scores.count(max(scores)) > 1:
        reason = "AMBIGUOUS_TIEBREAK_LOWER_OID"
    elif keeper["units"] and keeper["units"] > 0:
        reason = "HAS_RESIDENTIAL_UNITS"
    elif keeper["units"] == 0:
        reason = "HAS_EXPLICIT_ZERO"
    else:
        reason = "ALL_NULL_UNITS_LOWER_OID"

    return keeper, to_delete, reason


def _delete_rows(oids_to_delete: set) -> int:
    """Delete rows by OID using UpdateCursor.deleteRow()."""
    if not oids_to_delete:
        return 0

    deleted = 0
    # Process in batches to build a SQL filter
    oid_list  = sorted(oids_to_delete)
    batch_size = 500
    for i in range(0, len(oid_list), batch_size):
        chunk = oid_list[i : i + batch_size]
        where = f"OBJECTID IN ({','.join(str(o) for o in chunk)})"
        with arcpy.da.UpdateCursor(SOURCE_FC, ["OID@"], where) as cur:
            for _ in cur:
                cur.deleteRow()
                deleted += 1

    return deleted


def _write_qa_table(removed_rows: list[dict]) -> None:
    if arcpy.Exists(OUTPUT_TABLE):
        arcpy.management.Delete(OUTPUT_TABLE)

    arcpy.management.CreateTable(GDB, "QA_Duplicates_Removed")
    arcpy.management.AddField(OUTPUT_TABLE, "APN",                "TEXT", field_length=50)
    arcpy.management.AddField(OUTPUT_TABLE, "YEAR",               "LONG")
    arcpy.management.AddField(OUTPUT_TABLE, "DELETED_OID",        "LONG")
    arcpy.management.AddField(OUTPUT_TABLE, "KEPT_OID",           "LONG")
    arcpy.management.AddField(OUTPUT_TABLE, "DELETED_UNITS",      "DOUBLE")
    arcpy.management.AddField(OUTPUT_TABLE, "KEPT_UNITS",         "DOUBLE")
    arcpy.management.AddField(OUTPUT_TABLE, "KEEP_REASON",        "TEXT", field_length=40)

    with arcpy.da.InsertCursor(
            OUTPUT_TABLE,
            ["APN", "YEAR", "DELETED_OID", "KEPT_OID",
             "DELETED_UNITS", "KEPT_UNITS", "KEEP_REASON"]) as ic:
        for r in removed_rows:
            ic.insertRow([
                r["apn"], r["year"],
                r["deleted_oid"], r["kept_oid"],
                r["deleted_units"], r["kept_units"],
                r["keep_reason"],
            ])

    log.info("Written %d rows → %s", len(removed_rows), OUTPUT_TABLE)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    log.info("=== deduplicate_source_fc.py ===")
    log.info("Source FC : %s", SOURCE_FC)

    has_units = _units_field_exists()
    if not has_units:
        log.warning("Field '%s' not found in source FC — tiebreak will use OID only",
                    FC_UNITS)
    else:
        log.info("Field '%s' found — will prefer rows with units > 0", FC_UNITS)

    dupes = _find_duplicates(has_units)

    if not dupes:
        log.info("No duplicate APN × YEAR rows found — nothing to do.")
        return

    oids_to_delete = set()
    qa_rows        = []
    ambiguous      = 0

    for (apn, yr), rows in sorted(dupes.items()):
        keeper, to_delete, reason = _pick_keeper(rows)
        if reason == "AMBIGUOUS_TIEBREAK_LOWER_OID":
            ambiguous += 1
            log.debug("  Ambiguous: %s / %d — keeping OID %d (lowest), deleting %s",
                      apn, yr, keeper["oid"],
                      [r["oid"] for r in to_delete])

        for d in to_delete:
            oids_to_delete.add(d["oid"])
            qa_rows.append({
                "apn"          : apn,
                "year"         : yr,
                "deleted_oid"  : d["oid"],
                "kept_oid"     : keeper["oid"],
                "deleted_units": d["units"],
                "kept_units"   : keeper["units"],
                "keep_reason"  : reason,
            })

    log.info("Rows to delete : %d", len(oids_to_delete))
    if ambiguous:
        log.warning("  Ambiguous tiebreaks (both rows same unit status, kept lower OID): %d",
                    ambiguous)

    log.info("Deleting rows ...")
    deleted = _delete_rows(oids_to_delete)
    log.info("Deleted : %d rows", deleted)

    _write_qa_table(qa_rows)

    elapsed = time.time() - t0
    mins, secs = divmod(int(elapsed), 60)
    log.info("Done.  (%dm %02ds)", mins, secs)


if __name__ == "__main__":
    main()
