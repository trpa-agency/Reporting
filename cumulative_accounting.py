# data engineering for cumulative accounting

import pandas as pd
from arcgis.features import FeatureLayer
from utils import read_file, read_excel, get_fs_data, get_fs_data_query, get_fs_data_spatial, get_fs_data_spatial_query, convert_to_utc

# get parcel history data
parcelHistory = "https://maps.trpa.org/server/rest/services/AllParcels/MapServer/3"
dfHistory = get_fs_data(parcelHistory)

# get parcel development data
parcelDevelopment = "https://maps.trpa.org/server/rest/services/Existing_Development/MapServer/2"
dfDevelopment = get_fs_data(parcelDevelopment)

# trpa permit table
permitTable = "https://maps.trpa.org/server/rest/services/Permit_Records/MapServer/1"
dfPermit = get_fs_data(permitTable)

# trpa Parcel_Master
parcelMaster = "https://maps.trpa.org/server/rest/services/Parcels/FeatureServer/0"
sdfParcel = get_fs_data_spatial(parcelMaster)

# get Transacted development rights data
dfDRTrans  = pd.read_json("https://laketahoeinfo.org/WebServices/GetTransactedAndBankedDevelopmentRights/JSON/e17aeb86-85e3-4260-83fd-a2b32501c476")

# get Banked development rights data
dfDRBank   = pd.read_json("https://laketahoeinfo.org/WebServices/GetBankedDevelopmentRights/JSON/e17aeb86-85e3-4260-83fd-a2b32501c476")

dfPlacerPermit = read_file("data\PermitData_Placer_040124.csv")
dfCSLTPermit   = read_file("data\PermitData_CSLT_040224.csv")
dfElDoPermit   = read_file("data\PermitData_CSLT_040224.csv")

# get transaction data with inactive APNs
dfTransaction = read_file("data\Transactions_InactiveParcels.csv")

# get allocation data
dfAllocation = read_excel("data\Allocation Tracking.xlsx", 0)

# create new table with APN, _APN, Percent_Overlap
# create geneology matrix
# get current Parcel APN 
# inactive APN spatial join 
# inactive parcel to active parcel 