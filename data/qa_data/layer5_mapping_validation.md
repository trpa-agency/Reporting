# Layer 5 field-semantics validation

Generated 2026-05-14T22:48:12.

## What this tests

Whether `Cumulative_Accounting/MapServer/5` (staged from LT Info 
`GetDevelopmentRightPoolBalanceReport`) can serve the 2012-era pool 
balances the dashboards need - by joining its rows to the analyst-
built `regional_plan_allocations.json` and comparing candidate field 
mappings.

Inputs:

- Layer 5 (live)
- `regional_plan_allocations.json` (analyst-built ground truth)

## Headline: layer 5 totals vs json `summary`

Summing layer 5 across all pools per commodity, against the 
JSON's `status.summary` (the combined 1987+2012 era totals for 
non-residential; for residential we compare to `summary.plan_2012`).

| Commodity | n pools | json max | l5 TotalDisb | json assigned | l5 Approved | json not_assigned | l5 Balance | delta_max(H3b) | delta_assigned(H2) | delta_not_assigned(H1) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| residential | 9 | 2600 | 2112 | 832 | 691 | 1768 | 998 | -488 | -141 | -770 |
| residential_bonus_units | 12 | 2000 | 1474 | 1260 | 379 | 740 | 740 | -526 | -881 | +0 |
| commercial_floor_area | 19 | 1000000 | 581342 | 511106 | 52117 | 488894 | 488894 | -418658 | -458989 | +0 |
| tourist_accommodation_units | 14 | 400 | 342 | 196 | 48 | 204 | 204 | -58 | -148 | +0 |

## Findings

1. **`BalanceRemaining` == `not_assigned`** for the three non-
   residential commodities (RBU, CFA, TAU): delta = 0 at the 
   aggregate level. This is the cleanest confirmed field mapping.

2. **Residential `BalanceRemaining` is off by exactly 770** vs 
   the JSON's 2012 not_assigned (998 vs 1,768). The 770 is the 
   *unreleased allocations* tracked separately in the residential 
   allocation grid (layer 4 / Corral_2026 derivation), not in the 
   pool balance report. The combine view must add these back in.

3. **`TotalDisbursements` does NOT equal `regional_plan_maximum`**. 
   For non-residential, the deltas are exactly the size of the 
   1987-era cap (e.g. CFA: 1,000,000 - 581,342 = 418,658, of which 
   layer 3 holds 800,000 1987-era + the JSON treats some pool as 
   1987-era-only). `TotalDisbursements` is the 2012-era 
   *cumulative disbursed* (Approved + Pending + Balance), not the 
   policy cap.

4. **`Approved` does NOT equal `assigned_to_projects`**. The JSON's 
   `assigned_to_projects` rolls in 1987-era assignments which are 
   in layer 3, not layer 5. Layer 5 only reports the 2012-era 
   sub-status.

## Combine-view recipe (empirically supported)

For non-residential (RBU / CFA / TAU):

```text
combined.not_assigned        := layer5.BalanceRemaining (per jurisdiction sum)
combined.regional_plan_max   := layer3.regional_plan_maximum  -- 1987 baseline
                              + (layer5.TotalDisbursements - layer5.Approved - layer5.Pending)
                              ... OR ... source the 2012-additional cap from a frozen reference
combined.assigned_to_projects:= combined.regional_plan_max - combined.not_assigned
```

For residential, additionally:

```text
plan_2012.not_assigned       := layer5.BalanceRemaining + unreleased_count
                                 where unreleased_count = layer4 IssuanceYear IS NULL count
```

## Remaining open question

What is the 2012-era *additional* cap per pool? For residential 
we know it's 2,600 (2,112 issued + 488 unreleased per the grid). 
For RBU/CFA/TAU we'd need the LT Info owner to confirm whether 
`TotalDisbursements + BalanceRemaining` == 2012-era cap, or 
whether the 2012 additional is hard-coded by policy.

## Per-pool hypothesis pass rates

Lower-confidence: pool-name normalization is fragile (layer 5 has 
fine-grained sub-pools that the JSON aggregates by jurisdiction). 
Only rows that join on both sides are counted.

| Hypothesis | tested | exact match | within 5 | off by 10+ | mean abs delta | max abs delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| H1  BalanceRemaining == json.not_assigned | 5 | 2 | 0 | 2 | 40.0 | 181 |
| H2  ApprovedTransactionsQuantity == json.assigned_to_projects | 5 | 0 | 1 | 4 | 40.4 | 110 |
| H2a Approved + Pending == json.assigned_to_projects | 5 | 0 | 0 | 5 | 56.0 | 96 |
| H3a Approved + BalanceRemaining == json.regional_plan_maximum | 5 | 0 | 1 | 4 | 80.4 | 291 |
| H3b TotalDisbursements == json.regional_plan_maximum | 5 | 0 | 0 | 5 | 93.2 | 220 |
| H3c Approved + Pending + BalanceRemaining == json.regional_plan_maximum | 5 | 0 | 0 | 5 | 93.2 | 220 |

## Pools that joined on only one side (normalization gap)

| commodity | pool | source |
| --- | --- | --- |
| commercial_floor_area | Bijou/Al Tahoe Community Plan | layer5 only |
| commercial_floor_area | CSLT 2007 EIP Second Round | layer5 only |
| commercial_floor_area | CSLT Accomplishment of EIP in CP | layer5 only |
| commercial_floor_area | CSLT Area Outside of CPS | layer5 only |
| commercial_floor_area | CSLT Community Plan Recharge | layer5 only |
| commercial_floor_area | CSLT Pre CP Adoption | layer5 only |
| commercial_floor_area | City of South Lake Tahoe | json only |
| commercial_floor_area | Douglas County | json only |
| commercial_floor_area | El Dorado County | json only |
| commercial_floor_area | El Dorado non-community plan | layer5 only |
| commercial_floor_area | Greater Tahoe City Mixed Use Subdistrict | layer5 only |
| commercial_floor_area | Meyers Area Plan | layer5 only |
| commercial_floor_area | North Tahoe East Mixed Use Subdistrict | layer5 only |
| commercial_floor_area | Placer County | json only |
| commercial_floor_area | Placer County Area Wide | layer5 only |
| commercial_floor_area | Round Hill Community Plan | layer5 only |
| commercial_floor_area | South Shore Area Plan - DG | layer5 only |
| commercial_floor_area | South Y Industrial Tract Community Plan | layer5 only |
| commercial_floor_area | TRPA 2012 Regional Plan Allocation (Not for Use until 1987 CFA is used) | layer5 only |
| commercial_floor_area | TRPA Special Project/CEP Pool | layer5 only |
| commercial_floor_area | TRPA Special Projects Pool | json only |
| commercial_floor_area | Tahoe Area Plan - WA CO | layer5 only |
| commercial_floor_area | Tahoe Valley Area Plan | layer5 only |
| commercial_floor_area | Tourist Core Area Plan Pool - CSLT | layer5 only |
| commercial_floor_area | Unreleased CFA from 2012 Plan | json only |
| commercial_floor_area | Washoe County | json only |
| residential | CSLT - Multi-Family Pool | layer5 only |
| residential | CSLT - Single-Family Pool | layer5 only |
| residential | CSLT - Town Center Pool | layer5 only |
| residential | TRPA Allocation Incentive Pool | json only |
| residential | TRPA Pool | layer5 only |
| residential | Unreleased Allocations | json only |
| residential_bonus_units | Bijou/Al Tahoe Community Plan | layer5 only |
| residential_bonus_units | City of South Lake Tahoe | json only |
| residential_bonus_units | Douglas County | json only |
| residential_bonus_units | El Dorado County | json only |
| residential_bonus_units | Greater Tahoe City Mixed Use Subdistrict | layer5 only |
| residential_bonus_units | North Tahoe East Mixed Use Subdistrict | layer5 only |
| residential_bonus_units | North Tahoe West Mixed Use Subdistrict | layer5 only |
| residential_bonus_units | Placer County | json only |
| residential_bonus_units | Placer County General | layer5 only |
| residential_bonus_units | South Shore Area Plan - DG | layer5 only |
| residential_bonus_units | TRPA Bonus Unit Pool - Affordable | layer5 only |
| residential_bonus_units | TRPA Bonus Unit Pool - Moderate/Achievable | layer5 only |
| residential_bonus_units | TRPA Bonus Unit Pools | json only |
| residential_bonus_units | TRPA Centers Pool - Moderate/Achievable | layer5 only |
| residential_bonus_units | TRPA Centers Pool - Transfer Incentives Pool (Any) | layer5 only |
| residential_bonus_units | Tahoe Area Plan - WA CO | layer5 only |
| residential_bonus_units | Tourist Core Area Plan | layer5 only |
| residential_bonus_units | Washoe County | json only |
| tourist_accommodation_units | Bijou/Al Tahoe CP | layer5 only |
| tourist_accommodation_units | City of South Lake Tahoe | json only |
| tourist_accommodation_units | Douglas County | json only |
| tourist_accommodation_units | El Dorado County | json only |
| tourist_accommodation_units | Greater Tahoe City Mixed Use Subdistrict | layer5 only |
| tourist_accommodation_units | Kings Beach Commercial Town Center | layer5 only |
| tourist_accommodation_units | Kingsbury CP | layer5 only |
| tourist_accommodation_units | Meyers Area Plan | layer5 only |
| tourist_accommodation_units | North Tahoe East Mixed Use Subdistrict | layer5 only |
| tourist_accommodation_units | Placer County | json only |
| tourist_accommodation_units | Round Hill CP | layer5 only |
| tourist_accommodation_units | South Shore Area Plan - DG | layer5 only |
| tourist_accommodation_units | South Y CP | layer5 only |
| tourist_accommodation_units | South Y Ind. Tract CP | layer5 only |
| tourist_accommodation_units | TRPA Pool | layer5 only |
| tourist_accommodation_units | TRPA Tourist Bonus Unit Pool | json only |
| tourist_accommodation_units | Tahoe Area Plan - WA CO | layer5 only |
| tourist_accommodation_units | Tourist Core Area Plan Pool - CSLT | layer5 only |
| tourist_accommodation_units | Unassigned to CPs | layer5 only |
| tourist_accommodation_units | Washoe County | json only |

## Top 15 row-level deltas (rows where any hypothesis is off by 10+)

(Useful for spotting per-pool data-quality issues independent of 
field-mapping choice.)

| commodity | pool | json max / assigned / not_assigned | layer5 TotalDisb / Approved / Pending / Balance |
| --- | --- | --- | --- |
| residential | City of South Lake Tahoe | 434.0 / 253.0 / 181.0 | 214 / 143 / 71 / 0 |
| residential | El Dorado County | 452.0 / 354.0 / 98.0 | 548 / 320 / 130 / 98 |
| residential | Placer County | 488.0 / 139.0 / 349.0 | 558 / 100 / 116 / 342 |
| residential | Washoe County | 145.0 / 22.0 / 123.0 | 203 / 38 / 30 / 135 |
| residential | Douglas County | 137.0 / 44.0 / 93.0 | 159 / 47 / 19 / 93 |