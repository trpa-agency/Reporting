# TRPA Reporting Repo

## Data Sources

#### "F:\Research and Analysis\Reporting\Annual Reports\2022 Annual Report\2022 Annual Report Data\2022 Transfer Analysis.xlsx"

#### Reports to add to the Batch Engine
* ReviewCompleteness_30Day_V1
* DetailHistory_Reporting

## Tasks to do.

### Cumulative Accounting of Residential Units, Tourist Accomodation Units, and Commercial Floor Area 

*
*
*

### Inactive Parcels to Current APN

### Count of Permit by Category
*  Get Accela Permits data summarized by count of Reporting Category 
	 - Delete TMP files
	 - Establish Reporting Category
		- Summary of Record Types
			- Get lookup list for Reporting Category by Recor Type
			
		- Filter out Plan Revision
			- A second lookup of the ID without -01 at the end and lookup list against the other File Number Record Type
			
	- Count of Files by Reporting Category
		- Just for current year

### Tree Permits 
* setup Tree Permit Activity report in Batch Engine workflow
    - filter by year
    - merge with the main Accela permit csv by File Number
    - Tree Total
    - CHECKED in a column is the reason the tree was removed 
    - Tree Total is the count of trees that are approved to be removed
    - Application is APPROVED
- How many trees removed apps by year
- Total trees approved by permit
- Get Tree Total by Reason
- just for current year
- what % of applications have x reason CHECKED
- Created By BBARR are the Fire Districts creating a permit on our behalf
    - to look at the ones we've processed filter out the BBARR ones
        - we just want to report on TRPA actions not the Fire district issued permits

### Banked Development Rights Analysis
* All Banked development rights by type, land capability, location and jurisdiction
* Current Banked development rights by type, land capability, location and jurisdiction
    * group by High Capability, Low Capability, and SEZ
    * By location to town center
    * banked before and after 12/12/12

* Remove things that have been banked in the past year from Existing Development on the ground (TAU, RES, CFA)
- quanity that was removed should be subtracted from existing development
- newly built allocations (comes from transacted data in LTinfo) 
    - this falls apart when we dont have current data from the jurisdictions on allocated development
- opportunity to get data from GIS service....

- IPES Score of 0 = SEZ, IPES 1-725 = Low Capability, and IPES>726 = High Capability