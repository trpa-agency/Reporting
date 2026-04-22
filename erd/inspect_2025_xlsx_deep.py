"""Deep inspection of 2025 XLSX — concatenation patterns, value domains, join targets in Corral.

Looking for:
- Columns where a single cell encodes multiple values (e.g., "X plus Revisions")
- Columns that look derived from Corral (TransactionID pattern, etc.)
- Fields where the domain is an enumeration (Transaction Type, TRPA Status, ...)
- Relationships between columns (e.g., does TRPA Status always map 1:1 to Local Status?)
"""
from __future__ import annotations
import re
from pathlib import Path
from collections import Counter

import pandas as pd

XLSX = Path(r"C:\Users\mbindl\Documents\GitHub\Reporting\data\raw_data\2025 Transactions and Allocations Details.xlsx")

df = pd.read_excel(XLSX, sheet_name="Sheet1")
print(f"Rows: {len(df):,}  Cols: {len(df.columns)}\n")


def show_domain(col: str, top_n: int = 15) -> None:
    print(f"--- Domain of {col!r} ({df[col].nunique()} unique) ---")
    vc = df[col].value_counts(dropna=False).head(top_n)
    for val, cnt in vc.items():
        s = str(val)
        if len(s) > 80:
            s = s[:80] + "..."
        print(f"  {cnt:>5}  {s}")
    print()


# Enumeration-like columns
for col in ["Transaction Type", "Jurisdiction", "Development Right", "Development Type",
            "Detailed Development Type", "TRPA Status", "Local Status", "Status Jan 2026"]:
    show_domain(col)

# Multi-value detection in specific free-text / project# columns
def scan_multivalue(col: str, patterns: list[str]) -> None:
    print(f"--- Multi-value scan for {col!r} ---")
    series = df[col].dropna().astype(str)
    hits = {}
    for pat in patterns:
        matches = series.str.contains(pat, case=False, regex=True, na=False)
        hits[pat] = matches.sum()
    for pat, n in hits.items():
        print(f"  /{pat}/  hits={n}")
    # Show up to 10 non-simple examples (contain delimiter chars)
    delim = series.str.contains(r"[;,/]|\s(plus|and)\s|revisions?|\(|\)", case=False, regex=True, na=False)
    print(f"  Cells containing delimiter/noise chars: {delim.sum()}")
    for s in series[delim].head(8):
        print(f"    > {s[:120]}")
    print()


scan_multivalue("TRPA/MOU Project #",
                [r"plus", r"revisions?", r";", r",", r" and ", r"\(", r"\d+\s*\d+"])
scan_multivalue("Transaction Record ID", [r"plus", r";", r",", r" and ", r"\("])
scan_multivalue("Local Jurisdiction Project #", [r"plus", r";", r",", r" and "])
scan_multivalue("Notes", [r";", r",", r" and "])

# TransactionID pattern analysis
print("--- TransactionID patterns ---")
tid = df["TransactionID"].dropna().astype(str)
print(f"  Non-null count: {len(tid)}")
print(f"  Unique: {tid.nunique()}")
pat_split = tid.str.split("-", expand=False)
arities = pat_split.apply(len).value_counts()
print(f"  Number of dash-separated parts: {dict(arities)}")
# Show the prefix domain (Lead Agency Abbreviation)
first_part = tid.str.split("-").str[0]
print(f"  First-segment domain (lead agency): {dict(first_part.value_counts().head(15))}")
second_part = tid.str.split("-").str[1]
print(f"  Second-segment domain (transaction type code): {dict(second_part.value_counts().head(15))}")
last_is_int = tid.str.split("-").str[-1].str.match(r"^\d+$", na=False)
print(f"  Last segment numeric: {last_is_int.sum()}/{len(tid)}")
print()

# Date-field inspection
print("--- Date-field inspection ---")
for col in ["Transaction Created Date", "Transaction Acknowledged Date",
            "TRPA Status Date", "Local Status Date"]:
    s = df[col].dropna()
    print(f"  {col}: dtype={s.dtype}, non-null={len(s)}")
    if len(s) > 0:
        print(f"    First 3 raw: {list(s.head(3))}")
    print()

# Dev Right text analysis (jurisdiction suffix concatenated)
print("--- Development Right: jurisdiction suffix concatenation ---")
dr = df["Development Right"].dropna().astype(str)
with_suffix = dr.str.contains(r" - ", regex=True, na=False)
print(f"  With ' - ' separator: {with_suffix.sum()}/{len(dr)}")
# Extract commodity vs suffix
split = dr.str.split(" - ", n=1, expand=True)
print(f"  Unique commodity parts: {split[0].nunique()}")
print(f"  Unique suffix parts: {split[1].nunique()}")
print(f"  Top commodity parts:")
for v, c in split[0].value_counts().head(8).items():
    print(f"    {c:>5}  {v}")
print(f"  Top suffix parts:")
for v, c in split[1].value_counts().head(8).items():
    print(f"    {c:>5}  {v}")
print()

# Status Jan 2026 domain (proof it's a stale snapshot)
print("--- Status Jan 2026 vs TRPA Status vs Local Status ---")
status_combos = df[["Status Jan 2026", "TRPA Status", "Local Status"]].fillna("<null>")
combo_counts = status_combos.value_counts().head(15)
for (sjan, trpa, local), cnt in combo_counts.items():
    print(f"  {cnt:>5}  SJan={sjan!r:<20} TRPA={trpa!r:<15} Local={local!r}")
print()

# Detailed Development Type text patterns (look for concatenated keywords)
print("--- Detailed Development Type patterns ---")
ddt = df["Detailed Development Type"].dropna().astype(str)
print(f"  Non-null: {len(ddt)}, unique: {ddt.nunique()}")
# How many contain "from" (suggesting source-fact concatenated)
contains_from = ddt.str.contains(r"\bfrom\b", case=False, regex=True, na=False)
print(f"  Contains 'from' (suggesting source-bucket encoded): {contains_from.sum()}")
# Show top 10
for v, c in ddt.value_counts().head(10).items():
    print(f"  {c:>5}  {v[:100]}")
print()

# Transaction Type × Development Type cross-tab
print("--- Transaction Type × Development Type (top cells) ---")
ct = pd.crosstab(df["Transaction Type"].fillna("<null>"), df["Development Type"].fillna("<null>"))
print(ct.to_string())
print()

# APN format diversity
print("--- APN format diversity ---")
apn = df["APN"].dropna().astype(str)
fmts = apn.str.replace(r"\d", "#", regex=True)
for v, c in fmts.value_counts().head(10).items():
    print(f"  {c:>5}  {v}")
print()
