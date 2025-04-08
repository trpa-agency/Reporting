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

# fix issues with LOCATION_TO_TOWNCENTER values
parcels['LOCATION_TO_TOWNCENTER'] = parcels['LOCATION_TO_TOWNCENTER'].str.strip()
parcels['LOCATION_TO_TOWNCENTER'].replace({'Within Quarter Mile of Town Center': 'Quarter Mile Buffer',
                                            'Within Town Center': 'Town Center',
                                            'Further than Quarter Mile from Town Center': 'Outside Buffer'
                                            }, inplace=True)

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

# if IPESScore class to 0 = SEZ, 1-725 = Sensitive, >725 = Non Sensitive
df.loc[df['IPESScore'] == 0, 'LandCapabilityCategory'] = 'SEZ'
df.loc[(df['IPESScore'] > 0) & (df['IPESScore'] <= 725), 'LandCapabilityCategory'] = 'Sensitive'
df.loc[df['IPESScore'] > 725, 'LandCapabilityCategory'] = 'Non-Sensitive'

# merge with parcels
df = pd.merge(df, parcels, left_on='APN', right_on='APN', how='left')
def get_new_apn(old_apn, parcel_history):
    """
    Given an old APN, return the new APN(s) from the parcel history DataFrame.

    Parameters:
    - old_apn (str): The historical APN to look up.
    - parcel_history (pd.DataFrame): DataFrame with parcel history, containing APN, Status, APN_Current, and APNs_Current.

    Returns:
    - str | list | None: The new APN (str), list of APNs if split, or None if not found.
    """
    row = parcel_history[parcel_history['APN'] == old_apn]

    if row.empty:
        return None

    row = row.iloc[0]  # There should be only one match per old APN

    # Priority to APN_Current if it's a clean one-to-one mapping
    if pd.notna(row['APN_Current']):
        return row['APN_Current']

    # If there's a list in APNs_Current
    if pd.notna(row['APNs_Current']):
        apns = [apn.strip() for apn in row['APNs_Current'].split(',')]
        return apns if len(apns) > 1 else apns[0]

    return None

# example usage
get_new_apn('022-343-27', parcel_history)
# make a list of all APNs that didnt join to parcel master SHAPE is null
dfNoAPN = df[df['SHAPE'].isnull()]
# get the APNs that are not in the parcel master
dfNoAPN = dfNoAPN[['APN']]
# remove duplicates
dfNoAPN = dfNoAPN.drop_duplicates()
# get the APNs from the parcel history that are not in the parcel master
old_apns = dfNoAPN['APN'].tolist()

# next lets itterate through a list of APNs to return new APNs and create a column in the other dataframe for 'NewAPN'
def get_new_apns(df, old_apns parcel_history):
    """
    Given a DataFrame with APNs, return a new DataFrame with the new APNs.

    Parameters:
    - df (pd.DataFrame): DataFrame containing APNs.
    - parcel_history (pd.DataFrame): DataFrame with parcel history.

    Returns:
    - pd.DataFrame: DataFrame with original APNs and their corresponding new APNs.
    """
    df['NewAPN'] = df['APN'].apply(lambda x: get_new_apn(x, parcel_history))
    return df

### Transform functions ###
# SendingVsReceiving from RecordType
def classify_sending_receiving(record_type):
    if "Receiving Parcel" in record_type:
        return "Receiving"
    elif "Sending Parcel" in record_type:
        return "Sending"
    return "Unknown"

# get the sensitivity of the counterpart parcel
def get_counterpart_sensitivity(row):
    if row['SendingVsReceiving'] == 'Receiving':
        return apn_to_sensitivity.get(row['SendingParcel'], 'Unknown')
    elif row['SendingVsReceiving'] == 'Sending':
        return apn_to_sensitivity.get(row['ReceivingParcel'], 'Unknown')
    return 'Unknown'

# Build the From → To sensitivity string
def classify_sensitivity_transition(row):
    if row['SendingVsReceiving'] == 'Sending':
        return f"From {row['LandCapabilityCategory']} to {row['CounterpartSensitivity']}"
    elif row['SendingVsReceiving'] == 'Receiving':
        return f"From {row['CounterpartSensitivity']} to {row['LandCapabilityCategory']}"
    return 'Unknown'

# Look up counterparty Town Center classification
def get_counterpart_towncenter(row):
    if row['SendingVsReceiving'] == 'Receiving':
        return apn_to_towncenter.get(row['SendingParcel'], 'Unknown')
    elif row['SendingVsReceiving'] == 'Sending':
        return apn_to_towncenter.get(row['ReceivingParcel'], 'Unknown')
    return 'Unknown'

# Build the From → To Town Center transition string
def classify_towncenter_transition(row):
    if row['SendingVsReceiving'] == 'Sending':
        return f"From {row['LOCATION_TO_TOWNCENTER']} to {row['CounterpartTownCenter']}"
    elif row['SendingVsReceiving'] == 'Receiving':
        return f"From {row['CounterpartTownCenter']} to {row['LOCATION_TO_TOWNCENTER']}"
    return 'Unknown'

# Build combined category for land sensitivity and town center location
def build_land_towncenter_combo(row):
    sending_sens = row['LandCapabilityCategory']  # e.g. 'Sensitive' or 'Non-Sensitive'
    sending_loc = row['LOCATION_TO_TOWNCENTER']  # e.g. 'Town Center', 'Quarter Mile Buffer', 'Outside Buffer'
    receiving_sens = row['CounterpartSensitivity']  # e.g. 'Sensitive' or 'Non-Sensitive'
    receiving_loc = row['CounterpartTownCenter']  # e.g. 'Town Center', 'Quarter Mile Buffer', 'Outside Buffer'
    
    if pd.isna(sending_sens) or pd.isna(sending_loc) or pd.isna(receiving_sens) or pd.isna(receiving_loc):
        return 'Unknown'
    return f"Sending: {sending_sens} ({sending_loc}) → Receiving: {receiving_sens} ({receiving_loc})"

# classify sending vs receiving
df['SendingVsReceiving'] = df['RecordType'].apply(classify_sending_receiving)
# Create lookup from APN to LandCapabilityCategory
apn_to_sensitivity = df.set_index('APN')['LandCapabilityCategory'].to_dict()
df['CounterpartSensitivity'] = df.apply(get_counterpart_sensitivity, axis=1)
df['Sensitivity_Transition'] = df.apply(classify_sensitivity_transition, axis=1)
# Create a lookup from APN to LOCATION_TO_TOWNCENTER
apn_to_towncenter = df.set_index('APN')['LOCATION_TO_TOWNCENTER'].to_dict()
df['CounterpartTownCenter'] = df.apply(get_counterpart_towncenter, axis=1)
df['TownCenter_Transition'] = df.apply(classify_towncenter_transition, axis=1)

df['LandSensitivity_and_TownCenter_Transition'] = df.apply(build_land_towncenter_combo, axis=1)

# export to feature class
df.spatial.to_featureclass(local_gdb / "Parcel_Transfers", sanitize_columns=False, overwrite=True)