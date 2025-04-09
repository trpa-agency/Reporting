import pandas as pd
import pathlib
import arcpy
from arcgis.features import FeatureLayer, GeoAccessor

# Set up environment
arcpy.env.workspace = 'memory'
arcpy.env.overwriteOutput = True
arcpy.env.outputCoordinateSystem = arcpy.SpatialReference(26910)

# Paths
# local_path = pathlib.Path().absolute()
# data_dir   = local_path.parents[0] / 'Reporting/data/raw_data'
# out_dir    = local_path.parents[0] / 'Reporting/data/processed_data'
local_gdb = pathlib.Path(r"C:\GIS\Scratch.gdb")
# sdeBase   = pathlib.Path(r"F:\GIS\DB_CONNECT\Vector.sde")
# Feature class paths
# sdeParcelMaster  = pathlib.Path(sdeBase) / "sde.SDE.Parcels\\sde.SDE.Parcel_Master"
# sdeParcelHistory = pathlib.Path(sdeBase) / "sde.SDE.Parcels\\sde.SDE.Parcel_History"

# feature service urls
parcel_master  = "https://maps.trpa.org/server/rest/services/Parcels/FeatureServer/0"
parcel_history = "https://maps.trpa.org/server/rest/services/AllParcels/MapServer/3"

## Functions ##

# Gets spatially enabled dataframe from TRPA server
def get_sdf_from_feature_layer(url: str, where: str = "1=1", out_fields: str = "*", spatial_reference: int = 26910):
    try:
        fl = FeatureLayer(url)
        features = fl.query(where=where, out_fields=out_fields, out_sr=spatial_reference, return_geometry=True)
        return features.sdf
    except Exception as e:
        print(f"Error fetching data from feature layer: {e}")
        return pd.DataFrame()

# sending recieving field
def classify_sending_receiving(record_type):
    if "Receiving Parcel" in record_type:
        return "Receiving"
    elif "Sending Parcel" in record_type:
        return "Sending"
    return "Unknown"

# Define APN update logic
def get_new_apn(old_apn, parcel_history):
    row = parcel_history[parcel_history['APN'] == old_apn]
    if row.empty:
        return None
    row = row.iloc[0]
    if pd.notna(row['APN_Current']):
        return row['APN_Current']
    if pd.notna(row['APNs_Current']):
        apns = [apn.strip() for apn in row['APNs_Current'].split(',')]
        return apns if len(apns) > 1 else apns[0]
    return None

def get_new_apns(df, parcel_history):
    df['NewAPN'] = df['APN'].apply(lambda x: get_new_apn(x, parcel_history))
    return df
def get_counterpart_sensitivity(row):
    if row['SendingVsReceiving'] == 'Receiving':
        return apn_to_sensitivity.get(row['SendingParcel'], 'Unknown')
    elif row['SendingVsReceiving'] == 'Sending':
        return apn_to_sensitivity.get(row['ReceivingParcel'], 'Unknown')
    return 'Unknown'

def classify_sensitivity_transition(row):
    if row['SendingVsReceiving'] == 'Sending':
        return f"From {row['LandCapabilityCategory']} to {row['CounterpartSensitivity']}"
    elif row['SendingVsReceiving'] == 'Receiving':
        return f"From {row['CounterpartSensitivity']} to {row['LandCapabilityCategory']}"
    return 'Unknown'

def get_counterpart_towncenter(row):
    if row['SendingVsReceiving'] == 'Receiving':
        return apn_to_towncenter.get(row['SendingParcel'], 'Unknown')
    elif row['SendingVsReceiving'] == 'Sending':
        return apn_to_towncenter.get(row['ReceivingParcel'], 'Unknown')
    return 'Unknown'

def classify_towncenter_transition(row):
    if row['SendingVsReceiving'] == 'Sending':
        return f"From {row['LOCATION_TO_TOWNCENTER']} to {row['CounterpartTownCenter']}"
    elif row['SendingVsReceiving'] == 'Receiving':
        return f"From {row['CounterpartTownCenter']} to {row['LOCATION_TO_TOWNCENTER']}"
    return 'Unknown'

def build_land_towncenter_combo(row):
    sending_sens = row['LandCapabilityCategory']
    sending_loc = row['LOCATION_TO_TOWNCENTER']
    receiving_sens = row['CounterpartSensitivity']
    receiving_loc = row['CounterpartTownCenter']
    if pd.isna(sending_sens) or pd.isna(sending_loc) or pd.isna(receiving_sens) or pd.isna(receiving_loc):
        return 'Unknown'
    return f"Sending: {sending_sens} ({sending_loc}) → Receiving: {receiving_sens} ({receiving_loc})"

# Load data to dataframes
sdfParcels           = get_sdf_from_feature_layer(parcel_master)
sdfParcelHistory     = get_sdf_from_feature_layer(parcel_history)
dfDevRightTransacted = pd.read_json("https://www.laketahoeinfo.org/WebServices/GetTransactedAndBankedDevelopmentRights/JSON/e17aeb86-85e3-4260-83fd-a2b32501c476")

# dataframe of development rights transactions
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

# Clean and filter parcel data
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

parcels['LOCATION_TO_TOWNCENTER'] = parcels['LOCATION_TO_TOWNCENTER'].str.strip()
parcels['LOCATION_TO_TOWNCENTER'].replace({'Within Quarter Mile of Town Center': 'Quarter Mile Buffer',
                                           'Within Town Center': 'Town Center',
                                           'Further than Quarter Mile from Town Center': 'Outside Buffer'}, inplace=True)

record_types = ['Conversion With Transfer Receiving Parcel',
                'Conversion With Transfer Sending Parcel',
                'Transfer Receiving Parcel', 
                'Transfer Sending Parcel']

df = df[df['RecordType'].isin(record_types)]
df = df[df['TransactionApprovalDate'] != '']

# Land capability categorization
landcap_dict = {'1b':'SEZ', '1a':'Sensitive', '1c':'Sensitive', '2':'Sensitive',
                '3':'Sensitive', '4':'Non-Sensitive', '5':'Non-Sensitive',
                '6':'Non-Sensitive', '7':'Non-Sensitive'}

df.loc[df['LandCapability'].notnull() & df['LandCapability'].str.startswith('Bailey'), 'LandCapability'] = df['LandCapability'].str.strip('Bailey ')
df.loc[df['LandCapability'].notnull() & df['LandCapability'] != 'IPES', 'LandCapabilityCategory'] = df['LandCapability'].map(landcap_dict)
df.loc[df['IPESScore'] == 0, 'LandCapabilityCategory'] = 'SEZ'
df.loc[(df['IPESScore'] > 0) & (df['IPESScore'] <= 725), 'LandCapabilityCategory'] = 'Sensitive'
df.loc[df['IPESScore'] > 725, 'LandCapabilityCategory'] = 'Non-Sensitive'

# Merge with parcels
df = pd.merge(df, parcels, on='APN', how='left')

# Apply to missing parcel matches
dfNoAPN = df[df['SHAPE'].isnull()][['APN']].drop_duplicates()
dfNoAPN = get_new_apns(dfNoAPN, sdfParcelHistory)

# Merge back into main df to replace missing shapes
df = pd.merge(df, dfNoAPN[['APN', 'NewAPN']], on='APN', how='left')
df.loc[df['SHAPE'].isnull() & df['NewAPN'].notnull(), 'APN'] = df['NewAPN']
df.drop(columns='NewAPN', inplace=True)

# Re-merge to add missing parcel info again using new APN
df = pd.merge(df, parcels, on='APN', how='left', suffixes=('', '_fixed'))
df.update(df.filter(like='_fixed'))
df.drop(columns=df.filter(like='_fixed').columns, inplace=True)

# classify sending and receiving parcels in new field
df['SendingVsReceiving'] = df['RecordType'].apply(classify_sending_receiving)

apn_to_sensitivity = df.set_index('APN')['LandCapabilityCategory'].to_dict()
apn_to_towncenter  = df.set_index('APN')['LOCATION_TO_TOWNCENTER'].to_dict()

# apply transformations to get sensitivity and town center values
df['CounterpartSensitivity'] = df.apply(get_counterpart_sensitivity, axis=1)
df['Sensitivity_Transition'] = df.apply(classify_sensitivity_transition, axis=1)
df['CounterpartTownCenter']  = df.apply(get_counterpart_towncenter, axis=1)
df['TownCenter_Transition']  = df.apply(classify_towncenter_transition, axis=1)
df['LandSensitivity_and_TownCenter_Transition'] = df.apply(build_land_towncenter_combo, axis=1)

# Export to feature class
df.spatial.to_featureclass(local_gdb / "Parcel_Transfers", sanitize_columns=False, overwrite=True)
