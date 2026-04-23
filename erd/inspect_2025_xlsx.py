"""Inspect the 2025 Transactions and Allocations Details XLSX.

One-shot read-only exploration: sheets, columns, row counts, dtypes,
sample rows, and basic summary stats per transaction-type / status field.
"""
from __future__ import annotations
from pathlib import Path

import pandas as pd

XLSX = Path(r"C:\Users\mbindl\Documents\GitHub\Reporting\data\raw_data\2025 Transactions and Allocations Details.xlsx")

print(f"File: {XLSX.name}")
print(f"Size: {XLSX.stat().st_size:,} bytes\n")

xls = pd.ExcelFile(XLSX)
print(f"Sheets: {xls.sheet_names}\n")

for sheet in xls.sheet_names:
    df = pd.read_excel(XLSX, sheet_name=sheet)
    print(f"=== Sheet: {sheet} ===")
    print(f"  Rows: {len(df):,}")
    print(f"  Cols: {len(df.columns)}")
    print(f"  Columns:")
    for i, col in enumerate(df.columns, 1):
        nonnull = df[col].notna().sum()
        dtype = str(df[col].dtype)
        print(f"    {i:>3}. {col!r:<50} dtype={dtype:<12} nonnull={nonnull:>5}/{len(df):<5}")
    # Show first 3 rows (truncated)
    if len(df) > 0:
        print(f"  First 3 rows (truncated to 200 chars each):")
        for i, row in df.head(3).iterrows():
            s = row.to_dict()
            s_str = str(s)
            if len(s_str) > 200:
                s_str = s_str[:200] + "..."
            print(f"    [{i}] {s_str}")
    print()
