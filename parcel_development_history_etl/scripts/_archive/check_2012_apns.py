"""Quick check: compare 2012 El Dorado APN format between new FC and old FC."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

import arcpy

fc  = r"C:\GIS\ParcelHistory.gdb\Parcel_Development_History"
old = r"C:\GIS\ParcelHistory.gdb\Parcel_History_Attributed"

print("=== New FC 2012 - sample 080-xxx APNs ===")
with arcpy.da.SearchCursor(fc, ["APN"], "YEAR = 2012 AND APN LIKE '080-%'") as cur:
    for i, (a,) in enumerate(cur):
        print(a)
        if i >= 10:
            break

print()
print("=== Old FC 2012 - sample 080-xxx APNs ===")
with arcpy.da.SearchCursor(old, ["APN"], "YEAR = 2012 AND APN LIKE '080-%'") as cur:
    for i, (a,) in enumerate(cur):
        print(a)
        if i >= 10:
            break
