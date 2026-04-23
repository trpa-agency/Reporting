"""Full exhaustive enumeration of every column's domain in the 2025 XLSX.

Print EVERY distinct value with counts, for every column where the domain
is small enough to be informative. For free-text columns, print patterns
and counts of structural markers.
"""
from __future__ import annotations
import io
import re
import sys
from pathlib import Path
from collections import Counter

import pandas as pd

# Force UTF-8 stdout so the \u2010 hyphen and other non-CP1252 chars print.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

XLSX = Path(r"C:\Users\mbindl\Documents\GitHub\Reporting\data\raw_data\2025 Transactions and Allocations Details.xlsx")

df = pd.read_excel(XLSX, sheet_name="Sheet1")
print(f"Rows: {len(df):,}  Cols: {len(df.columns)}\n")


def full_domain(col: str) -> None:
    vc = df[col].value_counts(dropna=False)
    print(f"========== {col!r}  ({vc.shape[0]} distinct, {df[col].isna().sum()} nulls) ==========")
    for val, cnt in vc.items():
        s = repr(val)
        print(f"  {cnt:>5}  {s}")
    print()


# Enumeration-like columns — show full domain
ENUMS = [
    "Transaction Type",
    "Jurisdiction",
    "Development Right",
    "Development Type",
    "TRPA Status",
    "Local Status",
    "Status Jan 2026",
]
for col in ENUMS:
    full_domain(col)

# Detailed Development Type: full domain, sorted by count
print(f"========== Detailed Development Type  ({df['Detailed Development Type'].nunique()} distinct) ==========")
vc = df["Detailed Development Type"].value_counts(dropna=False)
for val, cnt in vc.items():
    print(f"  {cnt:>5}  {val!r}")
print()

# Notes: pattern-only
print("========== Notes (free-text) ==========")
notes = df["Notes"].dropna().astype(str)
print(f"  Non-null: {len(notes)}")
print(f"  Avg length: {notes.str.len().mean():.0f}")
print(f"  Max length: {notes.str.len().max()}")
date_pat = r"\d{1,2}/\d{1,2}/\d{2,4}"
accela_pat = r"ERSP\d{4}"
print(f"  Contains date pattern (M/D/YYYY): {notes.str.contains(date_pat, regex=True).sum()}")
print(f"  Contains CSLT/Accela-like IDs: {notes.str.contains(accela_pat, regex=True).sum()}")
print(f"  Contains 'ADU' mention: {notes.str.contains(r'ADU', case=False, regex=True).sum()}")
print(f"  Contains 'bank' keyword: {notes.str.contains(r'bank', case=False, regex=True).sum()}")
print(f"  Contains 'convert' keyword: {notes.str.contains(r'convert', case=False, regex=True).sum()}")
print(f"  Contains 'expire' keyword: {notes.str.contains(r'expire', case=False, regex=True).sum()}")
print(f"  Sample (15 random):")
for s in notes.sample(15, random_state=42):
    short = s[:180]
    print(f"    > {short}")
print()

# Allocation Number patterns
print("========== Allocation Number patterns ==========")
alloc = df["Allocation Number"].dropna().astype(str)
print(f"  Non-null: {len(alloc)}, unique: {alloc.nunique()}")
# Pattern shape
shape = alloc.str.replace(r"\d", "#", regex=True).str.replace(r"[A-Z]", "A", regex=True)
for v, c in shape.value_counts().head(20).items():
    print(f"  {c:>5}  {v}")
print(f"  Full first-part domain: {dict(alloc.str.split('-').str[0].value_counts().head(20))}")
print()

# TransactionID special cases (5-part ones)
print("========== TransactionID 5-part special cases ==========")
tid = df["TransactionID"].dropna().astype(str)
five_part = tid[tid.str.split("-").apply(len) == 5]
print(f"  Count: {len(five_part)}")
for v in five_part.unique()[:20]:
    print(f"    > {v}")
print()

# Transaction Record ID patterns
print("========== Transaction Record ID patterns ==========")
tri = df["Transaction Record ID"].dropna().astype(str)
print(f"  Non-null: {len(tri)}, unique: {tri.nunique()}")
shape = tri.str.replace(r"\d", "#", regex=True)
for v, c in shape.value_counts().head(15).items():
    print(f"  {c:>5}  {v}")
print()

# TRPA/MOU Project # patterns
print("========== TRPA/MOU Project # patterns ==========")
tmp = df["TRPA/MOU Project #"].dropna().astype(str)
print(f"  Non-null: {len(tmp)}, unique: {tmp.nunique()}")
# Count structural markers
print(f"  Contains ' plus ': {tmp.str.contains(' plus ', case=False).sum()}")
print(f"  Contains ' revisions': {tmp.str.contains('revisions?', case=False, regex=True).sum()}")
print(f"  Contains '(Withdrawn)': {tmp.str.contains('Withdrawn', case=False).sum()}")
print(f"  Contains '(Expired)': {tmp.str.contains('Expired', case=False).sum()}")
print(f"  Contains '/': {tmp.str.contains('/', regex=False).sum()}")
print(f"  Contains ';': {tmp.str.contains(';', regex=False).sum()}")
print(f"  Starts with 'ERSP': {tmp.str.startswith('ERSP').sum()}")
print(f"  Starts with 'MOU': {tmp.str.startswith('MOU').sum()}")
shape = tmp.str.replace(r"\d", "#", regex=True)
for v, c in shape.value_counts().head(15).items():
    print(f"  {c:>5}  {v[:80]}")
print()

# Local Jurisdiction Project # patterns
print("========== Local Jurisdiction Project # patterns ==========")
lj = df["Local Jurisdiction Project #"].dropna().astype(str)
print(f"  Non-null: {len(lj)}, unique: {lj.nunique()}")
shape = lj.str.replace(r"\d", "#", regex=True)
for v, c in shape.value_counts().head(20).items():
    print(f"  {c:>5}  {v[:80]}")
print()

# Year Built and PM Year Built stats
print("========== Year Built / PM Year Built stats ==========")
for col in ["Year Built", "PM Year Built"]:
    s = df[col].dropna()
    print(f"  {col}: count={len(s)}, min={s.min()}, max={s.max()}, unique={s.nunique()}")
    print(f"    distinct values sorted: {sorted(s.unique().astype(int))[:10]} ... {sorted(s.unique().astype(int))[-5:]}")
print()

# Year Built vs PM Year Built divergence
both = df[df["Year Built"].notna() & df["PM Year Built"].notna()]
diff = both[both["Year Built"] != both["PM Year Built"]]
print(f"  Both present: {len(both)}; Year Built != PM Year Built: {len(diff)}")
print(f"  Examples of divergence:")
for _, row in diff.head(10).iterrows():
    print(f"    APN={row['APN']}  YB={row['Year Built']}  PM={row['PM Year Built']}")
print()

# Quantity domain
print("========== Quantity domain ==========")
q = df["Quantity"].dropna()
print(f"  count={len(q)}, unique={q.nunique()}")
print(f"  value_counts top 15:")
for v, c in q.value_counts().head(15).items():
    print(f"    {c:>5}  {v}")
print()

# APN format samples for each format pattern
print("========== APN format patterns ==========")
apn = df["APN"].dropna().astype(str)
fmts = apn.str.replace(r"\d", "#", regex=True)
for v, c in fmts.value_counts().head(15).items():
    print(f"  {c:>5}  {v}")
print()

# Date column date-range stats
print("========== Date column ranges ==========")
for col in ["Transaction Created Date", "Transaction Acknowledged Date",
            "TRPA Status Date", "Local Status Date"]:
    s = pd.to_datetime(df[col], errors="coerce").dropna()
    if len(s) == 0:
        continue
    print(f"  {col}: count={len(s)}, min={s.min().date()}, max={s.max().date()}, unique_dates={s.dt.date.nunique()}")
print()

# Rows with Quantity > 1 (suspicious — are there really multi-unit rows?)
print("========== Rows with Quantity > 1 ==========")
multi = df[df["Quantity"] > 1]
print(f"  Count: {len(multi)}")
for _, row in multi.head(15).iterrows():
    print(f"    APN={row['APN']:<18}  qty={row['Quantity']:<6}  dev_right={row['Development Right']!r:<55}  dev_type={row['Development Type']!r}")
print()

# Rows with Quantity null
print(f"Quantity null rows: {df['Quantity'].isna().sum()}")
print(f"Transaction Type null rows: {df['Transaction Type'].isna().sum()}")
print(f"TransactionID null rows: {df['TransactionID'].isna().sum()}")

# Cross-check: when TransactionID is null, what's populated?
print("\n========== Profile of rows with no TransactionID (n=405) ==========")
no_tid = df[df["TransactionID"].isna()]
print(f"  Transaction Type values: {dict(no_tid['Transaction Type'].value_counts(dropna=False))}")
print(f"  Development Right values (top 10): {dict(no_tid['Development Right'].value_counts(dropna=False).head(10))}")
print(f"  Status Jan 2026: {dict(no_tid['Status Jan 2026'].value_counts(dropna=False))}")
print(f"  Development Type: {dict(no_tid['Development Type'].value_counts(dropna=False))}")
