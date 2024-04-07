## A set of utility functions to help with the data processing and analysis
from pathlib import Path
import pandas as pd
import plotly.express as px
from arcgis.features import FeatureLayer
import arcpy
import pytz
from datetime import datetime
from time import strftime 

# Reads in csv file
def read_file(path_file):
    p = Path(path_file)
    p.expanduser()
    data = pd.read_csv(p)
    return data

# Reads in excel file with sheet index
def read_excel(path_file, sheet_index=0):
    p = Path(path_file)
    p.expanduser()
    data = pd.read_excel(p, sheet_name=sheet_index)
    return data

# Gets feature service data as dataframe with query option
def get_fs_data_query(service_url, query_params):
    feature_layer = FeatureLayer(service_url)
    query_result = feature_layer.query(query_params)
    # Convert the query result to a list of dictionaries
    feature_list = query_result.features
    # Create a pandas DataFrame from the list of dictionaries
    all_data = pd.DataFrame([feature.attributes for feature in feature_list])
    # return data frame
    return all_data

# Gets feature service data as dataframe
def get_fs_data(service_url):
    feature_layer = FeatureLayer(service_url)
    query_result = feature_layer.query()
    # Convert the query result to a list of dictionaries
    feature_list = query_result.features
    # Create a pandas DataFrame from the list of dictionaries
    all_data = pd.DataFrame([feature.attributes for feature in feature_list])
    # return data frame
    return all_data

# Gets feature service data as spatially enabled dataframe
def get_fs_data_spatial(service_url):
    feature_layer = FeatureLayer(service_url)
    query_result = feature_layer.query().sdf
    return query_result

# Gets feature service as spatially enabled dataframe with query
def get_fs_data_spatial_query(service_url, query_params):
    feature_layer = FeatureLayer(service_url)
    query_result = feature_layer.query(query_params).sdf
    return query_result

# rename columns in a dataframe
def renamecolumns(df, column_mapping,drop_columns):
    if drop_columns:
        df = df.rename(columns=column_mapping).drop(columns=[col for col in df.columns if col not in column_mapping])
    else:
        df = df.rename(columns=column_mapping) 
    return df

# get geodatabase table as dataframe
def import_table_from_fgb(tablename):
    data = []
    # Use SearchCursor to iterate through the feature class
    fields = [field.name for field in arcpy.ListFields(tablename)]
    with arcpy.da.SearchCursor(tablename, fields) as cursor:
        for row in cursor:
            data.append(row)
    # Convert the list of tuples to a Pandas DataFrame
    df = pd.DataFrame(data, columns=fields)
    return df

# build a dictionary from a csv file of lookup values
def import_lookup_dictionary(lookup_csv, key_column, value_column, filter_column_1, filter_condition_1,filter_column_2, filter_condition_2):
    df = pd.read_csv(lookup_csv)
    filtered_df = df[(df[filter_column_1] == filter_condition_1)&(df[filter_column_2] == filter_condition_2)]
    dictionary = filtered_df.set_index(key_column)[value_column].to_dict()
    return dictionary

# update a field based on lookup value
def update_field_from_dictionary(df, df_lookup, field_name,filter_column_1,filter_condition_1,key_column, value_column, exact_match):
    filtered_lookup = df_lookup[(df_lookup[filter_column_1] == filter_condition_1)&
                                (df_lookup['Field_Name'] == field_name)]
    dictionary = filtered_lookup.set_index(key_column)[value_column].to_dict()
    if exact_match:
        df[field_name]=df[field_name].map(dictionary)
    else:
        df = update_if_contains(df, field_name,dictionary)
    return df

# update a field based on lookup value if it contains a key
def update_if_contains(df, column_to_update, lookup_dictionary):
    for key, value in lookup_dictionary.items():
        df.loc[df[column_to_update].str.contains(key), column_to_update] = value
    return df

# update a field inplace on lookup value if it contains a key
def update_if_contains_inplace(df, column_to_update, lookup_dictionary):
    for key, value in lookup_dictionary.items():
        df.loc[df[column_to_update].str.contains(key), column_to_update] = value

# update a feature class field based on another feature class field with the same key
def fieldJoinCalc(updateFC, updateFieldsList, sourceFC, sourceFieldsList):
    print ("Started data transfer: " + strftime("%Y-%m-%d %H:%M:%S"))
    # Use list comprehension to build a dictionary from arcpy SearchCursor  
    valueDict = {r[0]:(r[1:]) for r in arcpy.da.SearchCursor(sourceFC, sourceFieldsList)}  
    with arcpy.da.UpdateCursor(updateFC, updateFieldsList) as updateRows:  
        for updateRow in updateRows:  
            # store the Join value of the row being updated in a keyValue variable  
            keyValue = updateRow[0]  
            # verify that the keyValue is in the Dictionary  
            if keyValue in valueDict:  
                # transfer the value stored under the keyValue from the dictionary to the updated field.  
                updateRow[1] = valueDict[keyValue][0]  
                updateRows.updateRow(updateRow)    
    del valueDict  
    print ("Finished data transfer: " + strftime("%Y-%m-%d %H:%M:%S"))

# convert Unix timestamp to UTC datetime
def convert_to_utc(timestamp):
    return datetime.utcfromtimestamp(timestamp // 1000).replace(tzinfo=pytz.utc)

# function to merge dataframes and filter to records only in the left dataframe
def merge_dataframes(left_df, right_df, left_key, right_key):
    merged_df = pd.merge(left_df, right_df, how='left', left_on=left_key, right_on=right_key)
    return merged_df

# function to merge dataframe with outer join and indicator and keep rows where indicator is left_only
def merge_dataframes_left_only(left_df, right_df, left_key, right_key):
    merged_df = pd.merge(left_df, right_df, how='outer', left_on=left_key, right_on=right_key, indicator=True)
    return merged_df[merged_df['_merge'] == 'left_only']

# function to merge dataframe with outer join and indicator and keep rows where indicator is right_only
def merge_dataframes_right_only(left_df, right_df, left_key, right_key):
    merged_df = pd.merge(left_df, right_df, how='outer', left_on=left_key, right_on=right_key, indicator=True)
    return merged_df[merged_df['_merge'] == 'right_only']

# function to merge dataframe with outer join and indicator and keep rows where indicator is both
def merge_dataframes_both(left_df, right_df, left_key, right_key):
    merged_df = pd.merge(left_df, right_df, how='outer', left_on=left_key, right_on=right_key, indicator=True)
    return merged_df[merged_df['_merge'] == 'both']

# Helper function to transform regular data to sankey format
# Returns data and layout as dictionary
def genSankey(df,category_cols=[],value_cols='',title='Sankey Diagram'):
    # maximum of 6 value cols -> 6 colors
    colorPalette = ['#4B8BBE','#306998','#FFE873','#FFD43B','#646464']
    labelList = []
    colorNumList = []
    for catCol in category_cols:
        labelListTemp =  list(set(df[catCol].values))
        colorNumList.append(len(labelListTemp))
        labelList = labelList + labelListTemp
        
    # remove duplicates from labelList
    labelList = list(dict.fromkeys(labelList))
    
    # define colors based on number of levels We probab
    colorList = []
    for idx, colorNum in enumerate(colorNumList):
        colorList = colorList + [colorPalette[idx]]*colorNum
        
    # transform df into a source-target pair
    for i in range(len(category_cols)-1):
        if i==0:
            sourceTargetDf = df[[category_cols[i],category_cols[i+1],value_cols]]
            sourceTargetDf.columns = ['source','target','count']
        else:
            tempDf = df[[category_cols[i],category_cols[i+1],value_cols]]
            tempDf.columns = ['source','target','count']
            sourceTargetDf = pd.concat([sourceTargetDf,tempDf])
        sourceTargetDf = sourceTargetDf.groupby(['source','target']).agg({'count':'sum'}).reset_index()
        
    # add index for source-target pair
    sourceTargetDf['sourceID'] = sourceTargetDf['source'].apply(lambda x: labelList.index(x))
    sourceTargetDf['targetID'] = sourceTargetDf['target'].apply(lambda x: labelList.index(x))
    
    # creating the sankey diagram
    data = dict(
        type='sankey',
        node = dict(
          pad = 15,
          thickness = 20,
          line = dict(
            color = "black",
            width = 0.5
          ),
          label = labelList,
          color = colorList
        ),
        link = dict(
          source = sourceTargetDf['sourceID'],
          target = sourceTargetDf['targetID'],
          value = sourceTargetDf['count']
        )
      )
    
    layout =  dict(
        title = title,
        font = dict(
          size = 10
        )
    )
       
    fig = dict(data=[data], layout=layout)
    return fig