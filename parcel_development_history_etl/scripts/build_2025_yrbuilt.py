"""
build_2025_yrbuilt.py — Join PDH 2025 rows to Ken's original-year-built CSV.

Pulls all rows from Parcel_Development_History where YEAR=2025, joins them to
the per-APN OriginalYrBuilt lookup (data/raw_data/original_year_built.csv),
and falls back to the consolidated APN genealogy (apn_genealogy_tahoe.csv)
for any PDH APN that doesn't directly match — so recently split / merged /
renamed parcels still recover the original year built recorded under a
predecessor APN.

Also fetches county-source YEAR_BUILT from the Parcels FeatureService and
computes COMBINED_YEAR_BUILT = OriginalYrBuilt (primary) | CountyYearBuilt
(filler) so residual gaps from Ken's file are filled where the county has
the value.

Output: data/processed_data/PDH_2025_OriginalYrBuilt.csv

Run with ArcGIS Pro Python:
    PYTHONIOENCODING=utf-8 \\
    "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" \\
    parcel_development_history_etl/scripts/build_2025_yrbuilt.py
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# Make the parent package importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import arcpy
import pandas as pd

from config import (
    OUTPUT_FC,
    FC_APN, FC_YEAR, FC_UNITS, FC_TOURIST_UNITS, FC_COMMERCIAL_SQFT, FC_COUNTY,
    GENEALOGY_TAHOE,
    ORIGINAL_YR_BUILT_CSV, PDH_2025_YRBUILT_CSV,
    PARCELS_FS,
)
from utils import get_logger, canonical_apn

log = get_logger("build_2025_yrbuilt")

YEAR = 2025

# Optional FC fields — included in the output if they exist on OUTPUT_FC.
OPTIONAL_FIELDS = ["JURISDICTION", "PARCEL_ACRES", "Building_SqFt"]


def load_pdh_year(year: int) -> pd.DataFrame:
    """Pull all OUTPUT_FC rows where YEAR == *year*."""
    log.info("Loading PDH rows for YEAR=%d from %s", year, OUTPUT_FC)

    if not arcpy.Exists(OUTPUT_FC):
        raise SystemExit(f"OUTPUT_FC not found: {OUTPUT_FC}")

    fc_field_names = {f.name for f in arcpy.ListFields(OUTPUT_FC)}
    base_fields = [FC_APN, FC_YEAR, FC_UNITS, FC_TOURIST_UNITS,
                   FC_COMMERCIAL_SQFT, FC_COUNTY]
    optional = [f for f in OPTIONAL_FIELDS if f in fc_field_names]
    fields = base_fields + optional

    rows = []
    where = f"{FC_YEAR} = {year}"
    with arcpy.da.SearchCursor(OUTPUT_FC, fields, where_clause=where) as cur:
        for row in cur:
            rows.append(dict(zip(fields, row)))

    df = pd.DataFrame(rows)
    log.info("  %d rows loaded (%d columns)", len(df), len(df.columns))
    if df.empty:
        raise SystemExit(f"No rows returned for YEAR={year} — check OUTPUT_FC.")
    return df


def load_original_yr_built() -> pd.DataFrame:
    """Load original_year_built.csv (one row per APN, single int year)."""
    log.info("Loading OriginalYrBuilt: %s", ORIGINAL_YR_BUILT_CSV)
    df = pd.read_csv(ORIGINAL_YR_BUILT_CSV, dtype={"APN": str})
    df.columns = [c.strip() for c in df.columns]
    if "APN" not in df.columns or "OriginalYrBuilt" not in df.columns:
        raise SystemExit(
            f"original_year_built.csv missing expected columns; saw: {list(df.columns)}")
    df["APN"] = df["APN"].astype(str).str.strip()
    df["OriginalYrBuilt"] = pd.to_numeric(df["OriginalYrBuilt"],
                                          errors="coerce").astype("Int64")
    df = df.dropna(subset=["OriginalYrBuilt"]).copy()

    df["APN_canon"] = df["APN"].apply(canonical_apn)
    n_dup = int(df["APN_canon"].duplicated().sum())
    if n_dup:
        # Same canonical key from different raw forms — keep the oldest year.
        log.info("  %d duplicate canonical APNs after normalization — keeping min year", n_dup)
        df = (df.sort_values("OriginalYrBuilt")
                .drop_duplicates(subset=["APN_canon"], keep="first"))
    log.info("  %d unique canonical APNs", len(df))
    return df[["APN_canon", "APN", "OriginalYrBuilt"]].rename(
        columns={"APN": "OriginalYrBuilt_source_APN"})


def load_genealogy() -> pd.DataFrame:
    """Load apn_genealogy_tahoe.csv, filter, canonicalize."""
    log.info("Loading genealogy: %s", GENEALOGY_TAHOE)
    if not Path(GENEALOGY_TAHOE).exists():
        log.warning("  Genealogy not found — genealogy fallback disabled.")
        return pd.DataFrame(columns=["apn_old_canon", "apn_new_canon",
                                     "change_year", "source", "event_type"])

    g = pd.read_csv(GENEALOGY_TAHOE, dtype=str)
    g.columns = g.columns.str.strip()
    for col in ("is_primary", "in_fc_new", "source_priority"):
        if col in g.columns:
            g[col] = pd.to_numeric(g[col], errors="coerce").fillna(0).astype(int)
        else:
            g[col] = 0
    g["change_year"] = pd.to_numeric(g.get("change_year"), errors="coerce")

    g = g[(g["is_primary"] == 1)
          & (g["in_fc_new"] == 1)
          & g["change_year"].notna()].copy()
    g["change_year"] = g["change_year"].astype(int)
    g["apn_old_canon"] = g["apn_old"].apply(canonical_apn)
    g["apn_new_canon"] = g["apn_new"].apply(canonical_apn)
    g = g.dropna(subset=["apn_old_canon", "apn_new_canon"])
    g = g[g["apn_old_canon"] != g["apn_new_canon"]]
    g = g.sort_values(["source_priority", "change_year"]).reset_index(drop=True)

    log.info("  %d apply-ready genealogy rows (is_primary=1, in_fc_new=1)", len(g))
    return g


def load_county_year_built() -> pd.DataFrame:
    """
    Fetch APN + YEAR_BUILT from the Parcels FeatureService — county-source
    year built used to fill OriginalYrBuilt gaps. Paginated; ~43K non-null
    rows out of ~61K total.
    """
    log.info("Loading county YEAR_BUILT from %s", PARCELS_FS)

    base = f"{PARCELS_FS}/query"
    params_common = {
        "where": "YEAR_BUILT IS NOT NULL AND YEAR_BUILT > 0",
        "outFields": "APN,YEAR_BUILT",
        "returnGeometry": "false",
        "orderByFields": "OBJECTID ASC",
        "f": "json",
    }

    rows: list[dict] = []
    offset = 0
    page_size = 2000
    while True:
        params = {**params_common, "resultOffset": offset,
                  "resultRecordCount": page_size}
        url = f"{base}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = json.loads(resp.read())
        features = data.get("features", [])
        if not features:
            break
        for f in features:
            a = f["attributes"]
            rows.append({"APN": a.get("APN"), "YEAR_BUILT": a.get("YEAR_BUILT")})
        log.info("  page offset=%d: %d rows (running total %d)",
                 offset, len(features), len(rows))
        if not data.get("exceededTransferLimit") and len(features) < page_size:
            break
        offset += page_size

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["APN", "YEAR_BUILT"])
    df["APN"] = df["APN"].astype(str).str.strip()
    df["YEAR_BUILT"] = pd.to_numeric(df["YEAR_BUILT"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["YEAR_BUILT"])
    df["APN_canon"] = df["APN"].apply(canonical_apn)

    # If multiple raw forms canonicalize to the same APN (rare), keep the oldest.
    n_dup = int(df["APN_canon"].duplicated().sum())
    if n_dup:
        log.info("  %d duplicate canonical APNs in county data — keeping min year", n_dup)
        df = (df.sort_values("YEAR_BUILT")
                .drop_duplicates(subset=["APN_canon"], keep="first"))

    log.info("  %d unique canonical APNs with county YEAR_BUILT", len(df))
    return df[["APN_canon", "YEAR_BUILT"]].rename(columns={"YEAR_BUILT": "CountyYearBuilt"})


def build_genealogy_lookups(g: pd.DataFrame) -> tuple[dict, dict]:
    """Return ({apn_new → [apn_old, …]}, {apn_old → [apn_new, …]})."""
    new_to_old: dict[str, list[str]] = {}
    old_to_new: dict[str, list[str]] = {}
    for _, r in g.iterrows():
        old, new = r["apn_old_canon"], r["apn_new_canon"]
        new_to_old.setdefault(new, []).append(old)
        old_to_new.setdefault(old, []).append(new)
    return new_to_old, old_to_new


def resolve_via_genealogy(
    pdh_apn: str,
    yb_lookup: dict,
    new_to_old: dict,
    old_to_new: dict,
) -> tuple[int | None, str | None, str | None]:
    """
    Try to find an OriginalYrBuilt for an unmatched PDH APN by walking
    genealogy in both directions. Returns (year, source_apn, match_method)
    or (None, None, None).
    """
    # Direction 1 (typical): PDH APN is the current/new APN; its predecessor
    # holds the year-built record. Walk apn_new → apn_old.
    candidates: list[tuple[int, str]] = []
    for old in new_to_old.get(pdh_apn, []):
        if old in yb_lookup:
            yr, src = yb_lookup[old]
            candidates.append((yr, src))
    if candidates:
        # If multiple parents (merge), take min year — semantically "original".
        yr, src = min(candidates, key=lambda t: t[0])
        return yr, src, "genealogy_old_from_new"

    # Direction 2 (rarer): PDH APN appears as apn_old somewhere in the chain
    # (e.g. it was once the predecessor and Ken's file uses the post-rename APN).
    for new in old_to_new.get(pdh_apn, []):
        if new in yb_lookup:
            yr, src = yb_lookup[new]
            candidates.append((yr, src))
    if candidates:
        yr, src = min(candidates, key=lambda t: t[0])
        return yr, src, "genealogy_new_from_old"

    return None, None, None


def main() -> None:
    log.info("=" * 70)
    log.info("BUILD 2025 PDH × OriginalYrBuilt CSV")
    log.info("=" * 70)

    df_pdh = load_pdh_year(YEAR)
    df_yb = load_original_yr_built()
    g = load_genealogy()

    # Canonicalize PDH APN
    df_pdh["APN_canon"] = df_pdh[FC_APN].astype(str).str.strip().apply(canonical_apn)

    # Direct merge
    merged = df_pdh.merge(df_yb, on="APN_canon", how="left")
    direct = merged["OriginalYrBuilt"].notna()
    merged["match_method"] = pd.NA
    merged.loc[direct, "match_method"] = "direct"
    log.info("Direct matches: %d / %d (%.1f%%)",
             int(direct.sum()), len(merged), 100 * direct.mean())

    # Genealogy fallback for the remainder
    yb_lookup = {row.APN_canon: (int(row.OriginalYrBuilt),
                                  row.OriginalYrBuilt_source_APN)
                 for row in df_yb.itertuples(index=False)}
    new_to_old, old_to_new = build_genealogy_lookups(g)

    unmatched_idx = merged.index[~direct]
    g1 = g2 = 0
    for i in unmatched_idx:
        apn = merged.at[i, "APN_canon"]
        if not apn:
            continue
        yr, src, method = resolve_via_genealogy(
            apn, yb_lookup, new_to_old, old_to_new)
        if yr is not None:
            merged.at[i, "OriginalYrBuilt"] = yr
            merged.at[i, "OriginalYrBuilt_source_APN"] = src
            merged.at[i, "match_method"] = method
            if method == "genealogy_old_from_new":
                g1 += 1
            else:
                g2 += 1

    merged["match_method"] = merged["match_method"].fillna("unmatched")
    log.info("Genealogy old-from-new matches: %d", g1)
    log.info("Genealogy new-from-old matches: %d", g2)

    # ── County YEAR_BUILT filler ─────────────────────────────────────────────
    df_county = load_county_year_built()
    merged = merged.merge(df_county, on="APN_canon", how="left")

    # COMBINED = OriginalYrBuilt (primary) | CountyYearBuilt (filler)
    orig = pd.to_numeric(merged["OriginalYrBuilt"], errors="coerce").astype("Int64")
    county = pd.to_numeric(merged["CountyYearBuilt"], errors="coerce").astype("Int64")
    merged["COMBINED_YEAR_BUILT"] = orig.fillna(county)
    merged["combined_source"] = pd.Series(["none"] * len(merged), index=merged.index)
    merged.loc[orig.notna(), "combined_source"] = "original"
    merged.loc[orig.isna() & county.notna(), "combined_source"] = "county"

    # Final breakdown
    log.info("Match method breakdown (OriginalYrBuilt source):")
    for method, n in merged["match_method"].value_counts().items():
        log.info("  %-25s: %d (%.1f%%)", method, n, 100 * n / len(merged))

    log.info("COMBINED_YEAR_BUILT source breakdown:")
    for src, n in merged["combined_source"].value_counts().items():
        log.info("  %-10s: %d (%.1f%%)", src, n, 100 * n / len(merged))
    n_filled_by_county = int(((orig.isna()) & (county.notna())).sum())
    log.info("  (county filled %d gaps where OriginalYrBuilt was missing)",
             n_filled_by_county)

    # Order columns: PDH fields first, then year-built columns
    pdh_cols = [c for c in df_pdh.columns if c != "APN_canon"]
    out_cols = pdh_cols + ["APN_canon", "OriginalYrBuilt",
                           "OriginalYrBuilt_source_APN", "match_method",
                           "CountyYearBuilt",
                           "COMBINED_YEAR_BUILT", "combined_source"]
    out_cols = [c for c in out_cols if c in merged.columns]
    merged = merged[out_cols]

    # Cast year columns to nullable Int64 (for clean CSV output)
    for col in ("OriginalYrBuilt", "CountyYearBuilt", "COMBINED_YEAR_BUILT"):
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce").astype("Int64")

    # Ensure output directory exists
    out_path = Path(PDH_2025_YRBUILT_CSV)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_path, index=False)

    log.info("=" * 70)
    log.info("Wrote %d rows -> %s", len(merged), out_path)
    log.info("=" * 70)


if __name__ == "__main__":
    main()
