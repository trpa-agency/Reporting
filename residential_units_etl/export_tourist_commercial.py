"""
export_tourist_commercial.py — One-off extract.

Reads Parcel_History_Attributed and writes a CSV of all APN × Year rows
that have a non-zero TouristAccommodation_Units or CommericialFloorArea_sqft.

Output CSV columns:
  APN, Year, Tourist_Units, CommercialFloorArea_SqFt

Run from ArcGIS Pro Python:
  & "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" `
    "C:/Users/mbindl/Documents/GitHub/Reporting/residential_units_etl/export_tourist_commercial.py"
"""

import sys
import csv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import arcpy
from config import SOURCE_FC, FC_APN, FC_YEAR

OUT_CSV      = (r"C:\Users\mbindl\Documents\GitHub\Reporting"
                r"\data\raw_data\tourist_commercial_by_year.csv")
F_TOURIST    = "TouristAccommodation_Units"
F_COMMERCIAL = "CommercialFloorArea_SqFt"

import logging
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s",
                    datefmt="%H:%M:%S",
                    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger("export_tourist_commercial")


def main():
    log.info("Source FC : %s", SOURCE_FC)

    # Verify fields exist
    existing = {f.name for f in arcpy.ListFields(SOURCE_FC)}
    for f in [F_TOURIST, F_COMMERCIAL]:
        if f not in existing:
            log.error("Field not found in source FC: %s", f)
            log.error("Available fields: %s", sorted(existing))
            sys.exit(1)

    log.info("Reading rows with Tourist or Commercial values > 0 ...")
    fields = [FC_APN, FC_YEAR, F_TOURIST, F_COMMERCIAL]
    where  = (f"{F_TOURIST} > 0 OR {F_COMMERCIAL} > 0")

    rows = []
    with arcpy.da.SearchCursor(SOURCE_FC, fields, where) as cur:
        for apn, yr, tourist, commercial in cur:
            rows.append({
                "APN"                     : str(apn).strip() if apn else "",
                "Year"                    : int(yr) if yr else None,
                "Tourist_Units"           : tourist,
                "CommercialFloorArea_SqFt": commercial,
            })

    log.info("Rows found : %d", len(rows))

    rows.sort(key=lambda r: (r["APN"], r["Year"] or 0))

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["APN", "Year", "Tourist_Units", "CommercialFloorArea_SqFt"])
        writer.writeheader()
        writer.writerows(rows)

    log.info("Written → %s", OUT_CSV)


if __name__ == "__main__":
    main()
