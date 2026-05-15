# Banked Development Rights Reconciliation

Generated 2026-05-14T22:38:04.

## Inputs

- Layer 7 (Cumulative_Accounting MapServer/7), staged from LT Info `GetBankedDevelopmentRights`
- Corral_2026.ParcelCommodityInventory (`BankedQuantity` + `RemainingBankedQuantityAdjustment`)
- Corral_2026.vTransactedAndBankedCommodities (TDR transaction history)

Output: `data/qa_data/banked_reconciliation_findings.csv`

## Flag taxonomy

| Flag | Meaning |
| --- | --- |
| `LAYER7_ONLY` | row exists in layer 7 but not in `ParcelCommodityInventory.BankedQuantity` |
| `PCI_ONLY` | `ParcelCommodityInventory.BankedQuantity > 0` but no row in layer 7 (JSON service dropping it) |
| `LAYER7_VS_PCI_DELTA` | layer 7 qty does not match `pci.BankedQuantity + adjustment` |
| `INACTIVE_BUT_REMAINING` | layer 7 Status='Inactive' yet RemainingBankedQuantity > 0 |
| `STALE_LASTUPDATED` | `pci.LastUpdateDate` older than 5 years with banked > 0 |
| `NET_NEGATIVE` | TDR withdrawals exceed deposits+receipts (impossible) |
| `RESALL_BANKED` | banked Residential Allocation (residential allocations don't bank per policy) |

## Per-commodity totals

| Commodity | n | layer7 | pci_net | delta | flagged |
| --- | ---: | ---: | ---: | ---: | ---: |
| CoverageHard | 784 | 1993522 | 2166182 | -172660 | 408 |
| PotentialResidentialUnitOfUse | 419 | 497 | 478 | +19 | 360 |
| SingleFamilyResidentialUnitOfUse | 316 | 514 | 349 | +165 | 259 |
| CoveragePotential | 159 | 167007 | 19021 | +147986 | 156 |
| CommercialFloorArea | 136 | 389028 | 409430 | -20402 | 111 |
| TouristAccommodationUnit | 76 | 1536 | 1682 | -146 | 65 |
| CoverageSoft | 120 | 626577 | 715321 | -88744 | 64 |
| MultiFamilyResidentialUnitOfUse | 23 | 127 | 18 | +109 | 20 |
| RestorationCredit | 16 | 191786 | 199984 | -8198 | 16 |
| ResidentialFloorArea | 5 | 8678 | 11558 | -2880 | 4 |
| ResidentialAllocation | 2 | 6 | 6 | +0 | 2 |
| PersonsAtOneTime | 1 | 124 | 124 | +0 | 1 |
| ResidentialBonusUnit | 3 | 24 | 4 | +20 | 1 |
| TouristFloorArea | 1 | 10326 | 10326 | +0 | 0 |

## Flag counts

| Flag | Count |
| --- | ---: |
| `STALE_LASTUPDATED` | 868 |
| `LAYER7_ONLY` | 451 |
| `LAYER7_VS_PCI_DELTA` | 269 |
| `INACTIVE_BUT_REMAINING` | 88 |
| `NET_NEGATIVE` | 7 |
| `RESALL_BANKED` | 2 |