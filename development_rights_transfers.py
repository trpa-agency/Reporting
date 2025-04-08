import pandas as pd
import os
import pathlib
import arcpy
from arcgis.features import FeatureLayer, GeoAccessor, GeoSeriesAccessor
from utils import *
from datetime import datetime
from time import strftime  
# set environement workspace to in memory 
arcpy.env.workspace = 'memory'
# overwrite true
arcpy.env.overwriteOutput = True
# Set spatial reference to NAD 1983 UTM Zone 10N
sr = arcpy.SpatialReference(26910)
arcpy.env.outputCoordinateSystem = sr

# current working directory
local_path = pathlib.Path().absolute()
# set data path as a subfolder of the current working directory TravelDemandModel\2022\
data_dir   = local_path.parents[0] / 'Reporting/data/raw_data'
# folder to save processed data
out_dir    = local_path.parents[0] / 'Reporting/data/processed_data'
# local geodatabase path
local_gdb = Path("C:\GIS\Scratch.gdb")
# network path to connection files
filePath = "F:/GIS/PARCELUPDATE/Workspace/"
# database file path 
sdeBase    = os.path.join(filePath, "Vector.sde")
sdeCollect = os.path.join(filePath, "Collection.sde")

# web service and database paths
# portal_ParcelMaster = 'https://maps.trpa.org/server/rest/services/Parcel_Master/FeatureServer/0'
sdeParcelMaster  = Path(sdeBase) / "sde.SDE.Parcels\\sde.SDE.Parcel_Master"
sdeParcelHistory = Path(sdeBase) / "sde.SDE.Parcels\\sde.SDE.Parcel_History"
# get spatially enabled dataframes
sdfParcels       = pd.DataFrame.spatial.from_featureclass(sdeParcelMaster)
sdfParcelHistory = pd.DataFrame.spatial.from_featureclass(sdeParcelHistory)
# Development Rights Transacted and Banked as a DataFrame
dfDevRightTransacted = pd.read_json("https://www.laketahoeinfo.org/WebServices/GetTransactedAndBankedDevelopmentRights/JSON/e17aeb86-85e3-4260-83fd-a2b32501c476")

# get a copy
df = dfDevRightTransacted[['APN',
                        'RecordType',
                        'DevelopmentRight',
                        'LandCapability',
                        'IPESScore',
                        'CumulativeBankedQuantity',
                        'RemainingBankedQuantity',
                        'LastUpdated',
                        'TransactionNumber',
                        'TransactionApprovalDate',
                        'SendingParcel',
                        'ReceivingParcel',
                        'AccelaID',
                        'JurisdictionPermitNumber']].copy()
# filter columns of copy
parcels = sdfParcels[['APN', 
                        'JURISDICTION',  
                        'PLAN_ID',
                        'PLAN_NAME',
                        'ZONING_ID',
                        'ZONING_DESCRIPTION',
                        'TOWN_CENTER',
                        'LOCATION_TO_TOWNCENTER',
                        'TAZ', 
                        'WITHIN_BONUSUNIT_BNDY', 
                        'WITHIN_TRPA_BNDY',
                        'LOCAL_PLAN_HYPERLINK',
                        'LTINFO_HYPERLINK',
                        'PARCEL_ACRES', 'PARCEL_SQFT', 'SHAPE']].copy()

# filter to only include the record types in the list
record_types = ['Conversion With Transfer Receiving Parcel',
                'Conversion With Transfer Sending Parcel',
                'Transfer Receiving Parcel', 
                'Transfer Sending Parcel']

# filter the dataframe to only include the record types in the list
df = df[df['RecordType'].isin(record_types)]
# # # if ApprovalData is not  then it is approved
df = df[df['TransactionApprovalDate'] != '']

# categorize bailey rating
landcap_dict = {'1b':'SEZ',
                '1a':'Sensitive',
                '1c':'Sensitive',
                '2':'Sensitive',
                '3':'Sensitive',
                '4':'Non-Sensitive',
                '5':'Non-Sensitive',
                '6':'Non-Sensitive',
                '7':'Non-Sensitive'}

# land capability class = strip -1 if string starts with Bailey
df.loc[df['LandCapability'].notnull() & df['LandCapability'].str.startswith('Bailey'), 
                                        'LandCapability'] = df['LandCapability'].str.strip('Bailey ')

# map the land capability class to the dictionary after filtering out 'IPES'
df.loc[df['LandCapability'].notnull() & df['LandCapability'] != 'IPES', 
                                        'LandCapabilityCategory'] = df['LandCapability'].map(landcap_dict)

# land capability category 
# if IPESScore class to 0 = SEZ, 1-725 = Sensitive, >725 = Non Sensitive
df.loc[df['IPESScore'] == 0, 'LandCapabilityCategory'] = 'SEZ'
df.loc[(df['IPESScore'] > 0) & (df['IPESScore'] <= 725), 'LandCapabilityCategory'] = 'Sensitive'
df.loc[df['IPESScore'] > 725, 'LandCapabilityCategory'] = 'Non-Sensitive'

# merge with parcels
df = pd.merge(df, parcels, left_on='APN', right_on='APN', how='left')

# export to feature class
df.spatial.to_featureclass(local_gdb / "Parcel_Transfers", sanitize_columns=False, overwrite=True)


