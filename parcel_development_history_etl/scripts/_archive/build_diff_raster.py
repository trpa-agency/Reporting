"""
Standalone script: build a residential units diff raster.

Rasterizes Residential_Units for two year-slices of the output FC, then
subtracts them (end_year - start_year) to produce a change surface.  Cell
values are net unit change per cell; positive = gain, negative = loss.

Because the raster operates on grid cells rather than APN identities, parcel
genealogy (splits, merges, renames) does not affect the result — a cell that
contained a unit in 2012 and still contains one in 2025 reads as zero change
regardless of whether the APN changed.

Output rasters written to GDB:
  ResUnits_<start>         rasterized units for start year
  ResUnits_<end>           rasterized units for end year
  ResUnits_Diff_<s>_<e>    end - start  (saved as the primary product)

Usage
-----
    & "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" `
        parcel_development_history_etl/scripts/build_diff_raster.py

Optional flags
--------------
  --start YEAR       Start year  (default: first in CSV_YEARS)
  --end   YEAR       End year    (default: last  in CSV_YEARS)
  --cell-size METERS Cell size in meters  (default: 10)
  --keep-inputs      Keep the per-year input rasters in the GDB (deleted by default)

Symbology note
--------------
Load ResUnits_Diff_* in ArcGIS Pro and apply a diverging color ramp
(e.g. Red-White-Green) centered on 0.  Set the stretch type to "Minimum
Maximum" so the full gain/loss range is visible.
"""
import argparse
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1]))

import arcpy

from config import OUTPUT_FC, FC_APN, FC_YEAR, FC_UNITS, CSV_YEARS, GDB
from utils  import get_logger

log = get_logger("build_diff_raster")


def _rasterize_year(year: int, cell_size: float) -> str:
    """
    Extract the year-slice from OUTPUT_FC, rasterize Residential_Units,
    and return the output raster path in the GDB.
    """
    out_name = f"ResUnits_{year}"
    out_path = f"{GDB}/{out_name}"

    if arcpy.Exists(out_path):
        arcpy.management.Delete(out_path)

    lyr = f"diff_lyr_{year}"
    if arcpy.Exists(lyr):
        arcpy.management.Delete(lyr)

    arcpy.management.MakeFeatureLayer(OUTPUT_FC, lyr, f"{FC_YEAR} = {year}")
    n = int(arcpy.management.GetCount(lyr).getOutput(0))
    log.info("  Year %d: %d parcels", year, n)

    if n == 0:
        arcpy.management.Delete(lyr)
        log.error("  No parcels found for year %d — check FC and year range", year)
        sys.exit(1)

    # PolygonToRaster: each cell gets the Residential_Units value of the
    # polygon whose centroid falls in that cell (CELL_CENTER assignment).
    # Cells not covered by any parcel are NoData.
    arcpy.conversion.PolygonToRaster(
        lyr, FC_UNITS, out_path,
        cell_assignment="CELL_CENTER",
        cellsize=cell_size,
    )
    arcpy.management.Delete(lyr)

    n_cells = int(arcpy.management.GetRasterProperties(out_path, "COLUMNCOUNT")[0]) * \
              int(arcpy.management.GetRasterProperties(out_path, "ROWCOUNT")[0])
    log.info("  Raster %s: %d total cells", out_name, n_cells)
    return out_path


def build(start_year: int, end_year: int,
          cell_size: float = 10.0, keep_inputs: bool = False) -> None:

    log.info("=== build_diff_raster ===")
    log.info("Start: %d  End: %d  Cell size: %gm", start_year, end_year, cell_size)
    log.info("Output GDB: %s", GDB)

    arcpy.env.overwriteOutput = True
    arcpy.CheckOutExtension("Spatial")

    # -- Rasterize each year --------------------------------------------------
    log.info("Rasterizing year %d ...", start_year)
    raster_start = _rasterize_year(start_year, cell_size)

    log.info("Rasterizing year %d ...", end_year)
    raster_end   = _rasterize_year(end_year, cell_size)

    # -- Map algebra: diff = end - start --------------------------------------
    diff_name = f"ResUnits_Diff_{start_year}_{end_year}"
    diff_path = f"{GDB}/{diff_name}"
    if arcpy.Exists(diff_path):
        arcpy.management.Delete(diff_path)

    log.info("Computing diff raster (%d - %d) ...", end_year, start_year)
    from arcpy.sa import Raster
    diff = Raster(raster_end) - Raster(raster_start)
    diff.save(diff_path)

    # -- Report value range ---------------------------------------------------
    mn = float(arcpy.management.GetRasterProperties(diff_path, "MINIMUM")[0])
    mx = float(arcpy.management.GetRasterProperties(diff_path, "MAXIMUM")[0])
    log.info("  Diff raster value range: %.0f  to  +%.0f", mn, mx)
    log.info("  Saved: %s", diff_path)

    # -- Optionally clean up inputs -------------------------------------------
    if not keep_inputs:
        for r in [raster_start, raster_end]:
            if arcpy.Exists(r):
                arcpy.management.Delete(r)
        log.info("  Input rasters removed (use --keep-inputs to retain)")

    arcpy.CheckInExtension("Spatial")
    log.info("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build residential units diff raster")
    parser.add_argument("--start",      type=int,   default=min(CSV_YEARS),
                        help="Start year (default: %(default)s)")
    parser.add_argument("--end",        type=int,   default=max(CSV_YEARS),
                        help="End year   (default: %(default)s)")
    parser.add_argument("--cell-size",  type=float, default=10.0,
                        help="Cell size in meters (default: %(default)s)")
    parser.add_argument("--keep-inputs", action="store_true",
                        help="Keep per-year input rasters in GDB")
    args = parser.parse_args()
    build(args.start, args.end, args.cell_size, args.keep_inputs)
