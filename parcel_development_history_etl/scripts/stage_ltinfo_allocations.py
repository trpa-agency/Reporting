"""
stage_ltinfo_allocations.py - the nightly LT Info to Enterprise GDB staging ETL.

Refreshes the LT Info-origin layers in the `Cumulative_Accounting` REST service
(`maps.trpa.org`) by pulling the live LT Info JSON services and writing into
staging tables in `STAGING_GDB`. The user's publish step pushes those into the
SDE source tables the service publishes from; when direct SDE write is wired,
repoint the target constants in `config.py` at SDE paths and the ETL writes
straight through.

Pipelines currently refreshed (each is independent - one failing does not
block the others; each stamps its own row in the refresh-log table):

  - layer 5 "Development Right Pool Balance Report"
        <- `GetDevelopmentRightPoolBalanceReport`
  - layer 6 "Development Right Transactions"
        <- `GetDevelopmentRightTransactions`  (the full transaction log:
           transfers, allocations, land-bank transfers, conversions,
           retirements, allocation assignments - all transaction types)
  - layer 7 "Banked Development Rights"
        <- `GetBankedDevelopmentRights`  (current bank state per APN)
  - layer 8 "Transacted and Banked Development Rights"
        <- `GetTransactedAndBankedDevelopmentRights`  (APN-transaction
           junction view: both sides of every transaction + banked commodities)

Pending (no LT Info endpoint yet):
  - layer 4 "Residential Allocations 2012 Regional Plan"
        <- (future) `GetResidentialAllocationGrid`
    The grid is the in-app `parcels.laketahoeinfo.org/ResidentialAllocation/Manage`
    table; LT Info has the backing query but no JSON service yet.

Run nightly via Task Scheduler. Exit codes:
  0  success - all pipelines OK
  1  LTINFO_API_KEY missing (fast exit, no pipelines run)
  3  at least one pipeline failed (check the refresh-log table for which)

Each pipeline's target table is configured in `config.py` (`LTINFO_*_TABLE`).
Defaults point at `STAGING_GDB` so the script runs end-to-end on the analyst's
workstation without an SDE connection. Repoint the constants at SDE paths
once direct SDE write is wired in.

Each refresh stamps a row in `LTINFO_REFRESH_LOG_TABLE` with the timestamp,
endpoint, target, row count, and status. Failures stamp status `ERROR` with
the message; the log is the single source of truth for freshness monitoring.

Conventions (`Reporting/CLAUDE.md`): `config.py` constants, `get_logger`,
`arcpy` (not geopandas) for SDE writes, no hardcoded paths, no em-dashes,
no staff names. Run with the full `arcgispro-py3` Python path:

    PYTHONIOENCODING=utf-8 \\
      "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" \\
      parcel_development_history_etl/scripts/stage_ltinfo_allocations.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# Repo-relative import: add parcel_development_history_etl/ to sys.path so
# `from config import ...` resolves regardless of where this script is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import arcpy  # noqa: E402  (must follow the sys.path manipulation above)

from config import (  # noqa: E402
    LTINFO_BASE_URL,
    # Endpoint names (used in URL construction + log messages)
    LTINFO_POOL_BALANCE_ENDPOINT,
    LTINFO_TRANSACTIONS_ENDPOINT,
    LTINFO_BANKED_ENDPOINT,
    LTINFO_TRANSACTED_BANKED_ENDPOINT,
    # Target staging tables
    LTINFO_POOL_BALANCE_TABLE,
    LTINFO_TRANSACTIONS_TABLE,
    LTINFO_BANKED_TABLE,
    LTINFO_TRANSACTED_BANKED_TABLE,
    LTINFO_REFRESH_LOG_TABLE,
)
from utils import get_logger  # noqa: E402

log = get_logger("stage_ltinfo")


# ─────────────────────────────────────────────────────────────────────────────
# FIELD-TUPLE ACCESSORS
# ─────────────────────────────────────────────────────────────────────────────
# Fields are tuples: (sde_field_name, ftype, flen) or
#                    (sde_field_name, ftype, flen, json_key)
# The 4th element is optional - defaults to sde_field_name. Provide it only
# when the JSON key differs from the SDE field name (e.g. "Record Type" with
# a space in the JSON maps to "RecordType" in SDE, which disallows spaces).

def f_name(f):     return f[0]
def f_type(f):     return f[1]
def f_len(f):      return f[2]
def f_json_key(f): return f[3] if len(f) >= 4 else f[0]


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMAS  (one list per LT Info endpoint, mirrors the JSON response)
# ─────────────────────────────────────────────────────────────────────────────

# GetDevelopmentRightPoolBalanceReport: 7 fields, pool-grain.
POOL_BALANCE_FIELDS = [
    ("DevelopmentRightPoolName",     "TEXT", 200),
    ("DevelopmentRight",             "TEXT", 100),
    ("Jurisdiction",                 "TEXT", 100),
    ("TotalDisbursements",           "LONG", None),
    ("ApprovedTransactionsQuantity", "LONG", None),
    ("PendingTransactionQuantity",   "LONG", None),
    ("BalanceRemaining",             "LONG", None),
]

# GetDevelopmentRightTransactions: 25 fields, transaction-grain.
# Profiled against the 2026-05 CSV export: 3,017 rows covering all transaction
# types (Allocation, Shorezone Allocation, Transfer, Land Bank Transfer,
# Conversion, Conversion With Transfer, Land Bank Acquisition, ECM Retirement,
# Allocation Assignment) and all statuses (Approved, Proposed, Draft, Expired,
# De-Allocated, Withdrawn). Date range 2014-04 to 2026-05.
TRANSACTIONS_FIELDS = [
    ("Transaction",                    "TEXT", 100),
    ("LandBankAcquisitionTransaction", "TEXT", 100),
    ("LeadAgency",                     "TEXT", 200),
    ("TransactionStatus",              "TEXT",  50),
    ("TransactionType",                "TEXT", 100),
    ("DevelopmentRight",               "TEXT", 100),
    ("Quantity",                       "LONG", None),
    ("FileOrCaseNumber",               "TEXT", 100),
    ("TransactionApprovalDate",        "TEXT",  50),
    ("TransactionExpirationDate",      "TEXT",  50),
    ("UpdatedBy",                      "TEXT", 100),
    ("UpdatedDate",                    "TEXT",  50),
    ("JurisdictionProjectNumber",      "TEXT", 100),
    ("ResidentialAllocationNumber",    "TEXT",  50),
    ("SendingParcel",                  "TEXT", 100),
    ("SendingJurisdiction",            "TEXT", 200),
    ("SendingLandCapability",          "TEXT",  50),
    ("SendingIPESScore",               "LONG", None),
    ("SendingAllocationPool",          "TEXT", 200),
    ("ReceivingParcel",                "TEXT", 100),
    ("ReceivingJurisdiction",          "TEXT", 200),
    ("ReceivingLandCapability",        "TEXT",  50),
    ("ReceivingIPESScore",             "LONG", None),
    ("ResidentialUse",                 "TEXT",  50),
    ("Comments",                       "TEXT", 1000),
]

# GetBankedDevelopmentRights: 11 fields, APN-grain (current bank snapshot).
BANKED_FIELDS = [
    ("APN",                     "TEXT", 100),
    ("Status",                  "TEXT",  50),
    ("DevelopmentRight",        "TEXT", 100),
    ("LandCapability",          "TEXT",  50),
    ("IPESScore",               "LONG", None),
    ("RemainingBankedQuantity", "LONG", None),
    ("Jurisdiction",            "TEXT", 200),
    ("LocalPlan",               "TEXT", 200),
    ("DateBankedOrApproved",    "TEXT",  50),
    ("HRA",                     "TEXT", 100),
    ("LastUpdated",             "TEXT",  50),
]

# GetTransactedAndBankedDevelopmentRights: 20 fields, APN-transaction grain.
# "Record Type" has a space in the JSON; SDE field names disallow spaces, so
# this column maps JSON "Record Type" -> SDE "RecordType" via the 4th tuple
# element.
TRANSACTED_BANKED_FIELDS = [
    ("APN",                      "TEXT", 100),
    ("RecordType",               "TEXT", 100, "Record Type"),
    ("DevelopmentRight",         "TEXT", 100),
    ("LandCapability",           "TEXT",  50),
    ("IPESScore",                "LONG", None),
    ("CumulativeBankedQuantity", "LONG", None),
    ("RemainingBankedQuantity",  "LONG", None),
    ("Jurisdiction",             "TEXT", 200),
    ("LocalPlan",                "TEXT", 200),
    ("DateBankedOrApproved",     "TEXT",  50),
    ("HRA",                      "TEXT", 100),
    ("LastUpdated",              "TEXT",  50),
    ("TransactionNumber",        "TEXT", 100),
    ("SendingParcel",            "TEXT", 100),
    ("ReceivingParcel",          "TEXT", 100),
    ("LandBank",                 "TEXT", 200),
    ("TransactionApprovalDate",  "TEXT",  50),
    ("AccelaID",                 "TEXT", 100),
    ("JurisdictionPermitNumber", "TEXT", 100),
    ("TransactionStatus",        "TEXT",  50),
]

REFRESH_LOG_FIELDS = [
    ("RefreshTime",  "DATE", None),
    ("Endpoint",     "TEXT", 100),
    ("TargetTable",  "TEXT", 250),
    ("RowsLoaded",   "LONG", None),
    ("Status",       "TEXT",  20),
    ("ErrorMessage", "TEXT", 500),
]


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE REGISTRY  (drives main())
# ─────────────────────────────────────────────────────────────────────────────
# Each entry: friendly name, LT Info endpoint, target staging table, schema.
# Order = run order. To add a pipeline: define schema above, add entry here.

PIPELINES = [
    {
        "name":     "Pool Balance Report",
        "endpoint": LTINFO_POOL_BALANCE_ENDPOINT,
        "target":   LTINFO_POOL_BALANCE_TABLE,
        "fields":   POOL_BALANCE_FIELDS,
    },
    {
        "name":     "Development Right Transactions",
        "endpoint": LTINFO_TRANSACTIONS_ENDPOINT,
        "target":   LTINFO_TRANSACTIONS_TABLE,
        "fields":   TRANSACTIONS_FIELDS,
    },
    {
        "name":     "Banked Development Rights",
        "endpoint": LTINFO_BANKED_ENDPOINT,
        "target":   LTINFO_BANKED_TABLE,
        "fields":   BANKED_FIELDS,
    },
    {
        "name":     "Transacted and Banked Development Rights",
        "endpoint": LTINFO_TRANSACTED_BANKED_ENDPOINT,
        "target":   LTINFO_TRANSACTED_BANKED_TABLE,
        "fields":   TRANSACTED_BANKED_FIELDS,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def get_api_key() -> str:
    """Read LTINFO_API_KEY from the environment, falling back to .env."""
    key = os.environ.get("LTINFO_API_KEY")
    if not key:
        repo_root = Path(__file__).resolve().parents[2]
        env_path = repo_root / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("LTINFO_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not key:
        log.error("LTINFO_API_KEY not found in environment or .env - cannot continue")
        sys.exit(1)
    return key


def fetch_endpoint(endpoint: str, api_key: str) -> list[dict]:
    """GET an LT Info JSON endpoint and parse the response.

    Raises RuntimeError on any HTTP / parse / shape problem so the caller
    (main()) can catch per-pipeline and continue with the others.
    """
    url = f"{LTINFO_BASE_URL.rstrip('/')}/{endpoint}/JSON/{api_key}"
    safe_url = url.replace(api_key, "<token>")  # never log the token
    log.info(f"GET {safe_url}")
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
        payload = json.loads(raw)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"URL error: {e.reason}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON decode error: {e}")
    if not isinstance(payload, list):
        raise RuntimeError(
            f"unexpected payload shape: expected list, got {type(payload).__name__}"
        )
    log.info(f"  fetched {len(payload):,} rows")
    return payload


def verify_schema(rows: list[dict], fields: list[tuple]) -> None:
    """Sanity check the response shape. Raises RuntimeError on hard mismatch."""
    if not rows:
        raise RuntimeError("0 rows in response - refusing to truncate target")
    expected = {f_json_key(f) for f in fields}
    actual = set(rows[0].keys())
    missing = expected - actual
    if missing:
        raise RuntimeError(f"response missing expected fields: {sorted(missing)}")
    unexpected = actual - expected
    if unexpected:
        log.warning(f"  ignoring extra fields in response: {sorted(unexpected)}")


def ensure_table(table_path: str, fields: list[tuple]) -> None:
    """Create the staging table if it does not exist."""
    if arcpy.Exists(table_path):
        return
    gdb, tname = os.path.split(table_path)
    log.info(f"  creating staging table {tname} in {gdb}")
    arcpy.management.CreateTable(gdb, tname)
    for f in fields:
        name, ftype, flen = f_name(f), f_type(f), f_len(f)
        if ftype == "TEXT" and flen:
            arcpy.management.AddField(table_path, name, "TEXT", field_length=flen)
        else:
            arcpy.management.AddField(table_path, name, ftype)


def coerce(val, ftype: str):
    """Type-coerce a JSON value to what arcpy InsertCursor expects."""
    if val is None or val == "":
        return None
    if ftype == "LONG":
        try:
            return int(val)
        except (ValueError, TypeError):
            return None
    if ftype == "DOUBLE":
        try:
            return float(val)
        except (ValueError, TypeError):
            return None
    return val  # TEXT / DATE / etc. pass through


def build_tuples(rows: list[dict], fields: list[tuple]) -> list[tuple]:
    """Build (value, ...) tuples matching field order, with JSON-key lookup
    and type coercion."""
    return [
        tuple(coerce(r.get(f_json_key(f)), f_type(f)) for f in fields)
        for r in rows
    ]


def truncate_and_insert(table_path: str, field_names: list[str],
                        tuples: list[tuple]) -> None:
    """Truncate the target table and bulk insert."""
    arcpy.management.TruncateTable(table_path)
    with arcpy.da.InsertCursor(table_path, field_names) as cur:
        for row in tuples:
            cur.insertRow(row)


def stamp_refresh_log(endpoint: str, target: str, rows_loaded: int,
                      status: str, error_msg: str = "") -> None:
    """Append one row to the refresh-log table. Creates the table if absent.
    Logging is best-effort - never crashes the ETL."""
    try:
        ensure_table(LTINFO_REFRESH_LOG_TABLE, REFRESH_LOG_FIELDS)
        names = [f_name(f) for f in REFRESH_LOG_FIELDS]
        with arcpy.da.InsertCursor(LTINFO_REFRESH_LOG_TABLE, names) as cur:
            cur.insertRow([
                datetime.now(), endpoint, target, rows_loaded, status, error_msg,
            ])
    except Exception as e:
        log.warning(f"could not stamp refresh log: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE RUNNER
# ─────────────────────────────────────────────────────────────────────────────
def stage(name: str, endpoint: str, target: str, fields: list[tuple],
          api_key: str) -> int:
    """Run one pipeline: fetch -> verify -> ensure -> truncate+insert -> stamp.
    Returns the row count on success, raises on failure (caller catches)."""
    log.info(f"--- {name} ---")
    rows = fetch_endpoint(endpoint, api_key)
    verify_schema(rows, fields)
    ensure_table(target, fields)
    tuples = build_tuples(rows, fields)
    sde_names = [f_name(f) for f in fields]
    try:
        truncate_and_insert(target, sde_names, tuples)
    except arcpy.ExecuteError:
        raise RuntimeError(f"arcpy error: {arcpy.GetMessages(2)}")
    log.info(f"  OK - wrote {len(rows):,} rows to {target}")
    stamp_refresh_log(endpoint, target, len(rows), "OK")
    return len(rows)


def stage_allocation_grid() -> None:
    """Stub: refresh layer 4 from a LT Info residential allocation grid endpoint.

    Gated on LT Info exposing the grid as a JSON service (working name
    `GetResidentialAllocationGrid`). The endpoint and field schema are
    documented in `erd/residential_allocation_grid_service.md`. Until then,
    the interim manual CSV load is the only data source for layer 4.
    """
    log.info("--- Allocation Grid (layer 4) ---")
    log.info("  skipped - LT Info grid endpoint not yet exposed")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    log.info("=== LT Info staging ETL start ===")
    t0 = time.time()
    api_key = get_api_key()

    failures = 0
    for p in PIPELINES:
        try:
            stage(p["name"], p["endpoint"], p["target"], p["fields"], api_key)
        except Exception as e:
            failures += 1
            msg = str(e)[:500]
            log.error(f"  FAILED {p['name']}: {msg}")
            stamp_refresh_log(p["endpoint"], p["target"], 0, "ERROR", msg)

    stage_allocation_grid()

    elapsed = time.time() - t0
    if failures:
        log.error(f"=== ETL done in {elapsed:.1f}s with {failures} failure(s) "
                  f"- check refresh log ===")
        return 3
    log.info(f"=== ETL done in {elapsed:.1f}s - all pipelines OK ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
