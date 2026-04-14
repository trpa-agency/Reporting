"""
Shared utilities: logging setup, El Dorado APN helpers, and GDB table writer.
"""
import logging
import os
import re
from pathlib import Path

import arcpy
import numpy as np
import pandas as pd


# ── El Dorado APN pad / depad helpers ────────────────────────────────────────
# El Dorado County added a leading zero to the APN suffix starting in 2018.
# e.g. 080-155-11 → 080-155-011 (pad) and reverse (depad).
_EL_2D = re.compile(r"^(\d{3}-\d{2,3})-(\d{2})$")
_EL_3D = re.compile(r"^(\d{3}-\d{2,3})-0(\d{2})$")


def el_pad(apn: str) -> str:
    """Convert 2-digit El Dorado APN suffix to 3-digit (080-155-11 → 080-155-011)."""
    m = _EL_2D.match(apn)
    return f"{m.group(1)}-0{m.group(2)}" if m else apn


def el_depad(apn: str) -> str:
    """Convert 3-digit El Dorado APN suffix back to 2-digit (080-155-011 → 080-155-11)."""
    m = _EL_3D.match(apn)
    return f"{m.group(1)}-{m.group(2)}" if m else apn


# ── Logging ───────────────────────────────────────────────────────────────────

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    """Return a logger that writes to both console and a dated log file."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
                             datefmt="%Y-%m-%d %H:%M:%S")

    # Console
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File
    from datetime import date
    log_file = LOG_DIR / f"etl_{date.today():%Y%m%d}.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


# ── El Dorado APN fix — shared helpers ───────────────────────────────────────

def build_el_dorado_fix(output_fc: str, fc_apn: str) -> tuple[dict, dict]:
    """
    Query *output_fc* for COUNTY='EL' APNs and build pad/depad maps.

    Returns
    -------
    pad_map   : {2-digit APN → 3-digit APN}   apply when Year >= EL_PAD_YEAR
    depad_map : {3-digit APN → 2-digit APN}   apply when Year <  EL_PAD_YEAR
    """
    el_2d: set[str] = set()
    with arcpy.da.SearchCursor(output_fc, [fc_apn],
                               where_clause="COUNTY = 'EL'") as cur:
        for (apn,) in cur:
            if apn:
                a = str(apn).strip()
                if _EL_2D.match(a):
                    el_2d.add(a)

    pad_map   = {a: el_pad(a)   for a in el_2d}
    # depad_map keys are the 3-digit forms of known 2-digit APNs
    depad_map = {el_pad(a): el_depad(el_pad(a)) for a in el_2d
                 if _EL_3D.match(el_pad(a))}
    return pad_map, depad_map


def apply_el_dorado_fix(df: pd.DataFrame, pad_map: dict,
                        depad_map: dict, pad_year: int) -> pd.DataFrame:
    """
    Vectorized El Dorado APN suffix fix.

    Replaces row-wise ``df.apply(axis=1)`` with boolean-mask assignments —
    one pass per direction, no Python loop per row.

    Parameters
    ----------
    df        : DataFrame with columns "APN" and "Year"
    pad_map   : {2-digit APN → 3-digit APN}
    depad_map : {3-digit APN → 2-digit APN}
    pad_year  : year at which El Dorado switched to 3-digit suffixes

    Returns a copy of *df* with APN fixed.
    """
    df = df.copy()
    needs_pad   = df["APN"].isin(pad_map)   & (df["Year"] >= pad_year)
    needs_depad = df["APN"].isin(depad_map) & (df["Year"] <  pad_year)
    df.loc[needs_pad,   "APN"] = df.loc[needs_pad,   "APN"].map(pad_map)
    df.loc[needs_depad, "APN"] = df.loc[needs_depad, "APN"].map(depad_map)
    changed = int(needs_pad.sum() + needs_depad.sum())
    get_logger("utils.apply_el_dorado_fix").debug(
        "El Dorado fix: %d rows updated (%d pad, %d depad)",
        changed, int(needs_pad.sum()), int(needs_depad.sum()))
    return df


# ── GDB table writer ──────────────────────────────────────────────────────────

# Maps pandas dtype kinds to (arcpy field type, default length)
_DTYPE_MAP = {
    "i": ("LONG",   None),
    "u": ("LONG",   None),
    "f": ("DOUBLE", None),
    "b": ("SHORT",  None),
    "O": ("TEXT",   255),
    "U": ("TEXT",   255),
    "S": ("TEXT",   255),
    "M": ("DATE",   None),
}


def _safe_field_name(col: str) -> str:
    """Sanitise a DataFrame column name for use as a GDB field name."""
    import re
    name = re.sub(r"[^A-Za-z0-9_]", "_", str(col))
    if name and name[0].isdigit():
        name = "F_" + name
    return name[:64]


def df_to_gdb_table(df: pd.DataFrame, table_path: str,
                    text_lengths: dict = None) -> None:
    """
    Write *df* to a GDB stand-alone table at *table_path*.
    Drops and recreates the table if it already exists.

    Parameters
    ----------
    df          : DataFrame to write
    table_path  : Full path to the output table, e.g. r"C:\GIS\Foo.gdb\MyTable"
    text_lengths: Optional dict mapping column names to explicit TEXT lengths,
                  e.g. {"APN": 30, "NOTES": 500}
    """
    log = get_logger("utils.df_to_gdb_table")
    text_lengths = text_lengths or {}

    if arcpy.Exists(table_path):
        arcpy.management.Delete(table_path)
        log.debug("Deleted existing table: %s", table_path)

    gdb  = os.path.dirname(table_path)
    name = os.path.basename(table_path)
    arcpy.management.CreateTable(gdb, name)

    # Rename columns to safe GDB names
    col_map = {c: _safe_field_name(c) for c in df.columns}
    df = df.rename(columns=col_map)
    text_lengths = {_safe_field_name(k): v for k, v in text_lengths.items()}

    # Add fields
    for col in df.columns:
        dtype_kind = df[col].dtype.kind
        ftype, default_len = _DTYPE_MAP.get(dtype_kind, ("TEXT", 255))

        if ftype == "TEXT":
            non_null = df[col].dropna().astype(str)
            max_len  = int(non_null.str.len().max()) if len(non_null) else 50
            length   = text_lengths.get(col, max(max_len * 2, 50))
            length   = min(length, 8000)
            arcpy.management.AddField(table_path, col, "TEXT",
                                      field_length=length)
        else:
            arcpy.management.AddField(table_path, col, ftype)

    # Insert rows
    fields = list(df.columns)
    written = 0
    with arcpy.da.InsertCursor(table_path, fields) as cur:
        for row in df.itertuples(index=False, name=None):
            clean = tuple(
                None if (isinstance(v, float) and np.isnan(v)) else
                None if v is pd.NaT else v
                for v in row
            )
            cur.insertRow(clean)
            written += 1

    log.info("Wrote %d rows → %s", written, table_path)
