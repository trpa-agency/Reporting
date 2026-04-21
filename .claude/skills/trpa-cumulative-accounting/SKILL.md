---
name: trpa-cumulative-accounting
description: "TRPA Cumulative Accounting — the code-mandated framework (TRPA Code of Ordinances §16.8.2) for annually tracking Units of Use, Resource Utilization, and Threshold Attainment & Maintenance in the Lake Tahoe Basin. Use this skill whenever work involves: the cumulative accounting report, development-rights accounting, existing/banked/allocated/transferred/converted development, the Existing + Banked + Remaining Allocations + Bonus Units + Unused Capacity equation, commodity pools and drawdowns, RES/TAU/CFA/PAOT unit-of-use totals, or the annual December-31 accounting snapshot. Trigger on any mention of: cumulative accounting, thresholds.laketahoeinfo.org, Subsection 16.8.2, units of use, banked development rights, development-right transfers, development-right conversions, residential allocation pools, RBU, ADU accounting, commercial floor area accounting, tourist accommodation units, PAOT, bonus units, incentive pool, community enhancement program, mitigation fund accounts, regional plan buildout capacity."
---

# TRPA Cumulative Accounting

The annual accounting framework that tracks regional plan implementation at
Lake Tahoe. Mandated by **TRPA Code of Ordinances §16.8.2**. Public report
at [thresholds.laketahoeinfo.org/CumulativeAccounting](https://thresholds.laketahoeinfo.org/CumulativeAccounting/Index/2023)
(yearly snapshot as of December 31).

## What Cumulative Accounting is

A bucket-based ledger of Tahoe's development envelope. For each commodity
(residential units, CFA, TAU, PAOT), the Regional Plan sets a **theoretical
maximum capacity**. That capacity is partitioned across fixed buckets:

```
Max Regional Capacity  =  Existing Development
                       +  Banked Development Rights
                       +  Allocated (not yet built)
                       +  Bonus Units
                       +  Unused Capacity (still in pool, not yet allocated)
```

Every event in the TRPA system moves commodity between these buckets.
Cumulative Accounting is the year-end snapshot of where everything sits.

**Design-mindset rule**: when thinking about a schema, dashboard, or report for
TRPA, anchor on these **five buckets per commodity per jurisdiction**, not on
allocation records. Allocations are one type of bucket-movement event.

## The three tracking categories

TRPA Code §16.8.2 requires annual reporting on three distinct things. Don't
conflate them.

### 1. Units of Use
Development capacity — what's built or can be built.

| Commodity | Short name | Tracks |
|---|---|---|
| Single-Family Residential Unit of Use | SFRUU | Detached single-family dwellings |
| Multi-Family Residential Unit of Use | MFRUU | Apartments, condos, townhomes |
| Potential Residential Unit of Use | PRUU | Subdivided lots not yet built |
| Residential Bonus Unit | RBU | Incentive-driven bonus residential entitlements |
| Accessory Dwelling Unit | ADU | Secondary units on single-family lots |
| Commercial Floor Area | CFA | Non-residential building area, sq ft |
| Tourist Accommodation Unit | TAU | Hotel rooms, motel units, time-shares |
| Residential Floor Area | RFA | Residential building area sq ft (support metric) |
| Tourist Floor Area | TFA | Tourist building area sq ft (support metric) |
| PAOT (People At One Time) | PAOT | Recreational capacity — overnight / summer day / winter day |

### 2. Resource Utilization
Environmental consumption driven by development.

- Vehicle Miles Traveled (VMT)
- Daily Vehicle Trip Ends (DVTE)
- Impervious coverage (hard / soft / potential)
- Water demand
- Sewage disposal capacity
- Stream Environment Zone (SEZ) disturbance

### 3. Threshold Attainment & Maintenance
Investment values in mitigation funds, not development rights.

| Fund | What it funds |
|---|---|
| Water Quality Mitigation | Water-quality treatments, bike/ped |
| Stream Zone Restoration | SEZ restoration, BMP implementation |
| Air Quality & Mobility | Trails, roads, street sweepers, transit |
| Operations & Maintenance | Street-sweeper operation, erosion control |
| Excess Land Coverage Mitigation | Land bank acquisitions |
| Shorezone Mitigation | Shorezone research, restoration |

## Development-rights movement types (bucket transitions)

There are seven canonical movement types. Each Cumulative Accounting event is
one of these.

| Movement | From bucket | To bucket | Notes |
|---|---|---|---|
| **Allocation release** | Unused Capacity | Allocated (not built) | Annual issuance by TRPA or jurisdiction; 130 residential/yr authorized through 2032 |
| **Allocation use** | Allocated | Existing | Permit issued + unit built |
| **Banking** | Existing | Banked | Legally existing development removed, restored, recorded |
| **Unbanking (onsite use)** | Banked | Existing | Previously banked unit rebuilt on same parcel |
| **Transfer** | Existing (parcel A) | Existing (parcel B) | Typically SEZ → less-sensitive lands |
| **Conversion** | One commodity type | Another | Uses fixed exchange ratios (see below) |
| **Retirement / expiration** | Any bucket | Out of system | Permanently removed |

Bonus Units work the same mechanically — they start in a "Bonus Unit pool"
(a separate Unused-Capacity bucket) and flow through Allocated → Existing.

### Conversion ratios (fixed)

```
600 CFA (sq ft)  =  2 TAUs  =  2 single-family units  =  3 multi-family units
```

Post-2018 net conversion trend: **+157 residential units, −65 TAUs, −30,500 sq ft CFA**.

## Pool structure

Pools are the **containers of Unused Capacity**. There are ~129 pools in
Corral (`dbo.CommodityPool`) spanning all commodity types.

### Residential pools (2013 Regional Plan framework)

- **Jurisdiction pools** — one per jurisdiction:
  - El Dorado County
  - Placer County
  - Douglas County
  - Washoe County
  - City of South Lake Tahoe (CSLT) — subdivided into three sub-pools:
    - CSLT Single-Family Pool
    - CSLT Multi-Family Pool
    - CSLT Town Center Pool
- **TRPA Incentive Pool** — 129 units reserved for sensitive-lot retirement
- **Bonus Unit pools** — separate, containing RBUs (1,445 remaining as of 2023)

### CFA pools
- Local jurisdiction Community Plan / Area Plan pools (many sub-pools per jurisdiction)
- TRPA bonus pools (environmental improvement projects)
- 1987 Regional Plan pools (legacy)
- 2012 Regional Plan allocations (200,000 sq ft)

### TAU pools
- Local jurisdiction allocations
- TRPA Incentive Pool (74 TAU bonus units)
- Community Enhancement Program reserved (138 units)
- Area/Community Plan pools (130 units)

### PAOT pools
- Summer day-use pool
- Winter day-use pool
- Overnight use pool

## Land categories

Pool draws and transfers interact with land sensitivity categories:

- **Stream Environment Zones (SEZ)** — most sensitive; development generally
  disallowed, transfers *out* are encouraged.
- **Town Centers** — walkable urban cores; development *in* is encouraged,
  lower mitigation burden.
- **Remote Areas** — > ¼-mile from town center; discouraged for new development.
- **Non-sensitive lands** — Bailey land capability classes 4–7; standard
  development treatment.

IPES (Index of Parcel Environmental Sensitivity) scores drive eligibility
at the parcel level within these categories.

## The accounting equation in practice (2023 snapshot)

### Residential (as of 2023-12-31)

| Bucket | Count | % of max capacity |
|---|---:|---:|
| Existing units | 48,891 | 92.5% |
| Banked | 512 | — |
| Released allocations 2012–2023 | 1,558 (52% assigned to projects) | — |
| Remaining allocations | 960 | ~6% |
| RBUs remaining | 1,445 | — |

### CFA

| Bucket | Amount |
|---|---:|
| Built | 6.48 million sq ft (88%) |
| Banked | 344,000 sq ft |
| Remaining allocation | ~530,880 sq ft (6%) |

### TAU

| Bucket | Count | % |
|---|---:|---:|
| Existing TAUs | 11,039 | 88% |
| Banked | 1,170 | — |
| Remaining allocation | ~342 | ~3% |

### PAOT

| Pool | Max | Assigned | Remaining |
|---|---:|---|---|
| Overnight | 6,114 | ~32% | 68% |
| Summer day-use | 6,761 | — | — |
| Winter day-use | 12,400 | — | — |

## Time dimension

**Cumulative across years**, reported as annual year-end (Dec 31) snapshots.
The current LTinfo report lets you select any year from the route
`/CumulativeAccounting/Index/{year}`. Snapshots carry:

- Running totals per bucket per commodity per jurisdiction
- That year's allocation releases
- That year's transfers, conversions, banking events
- Mitigation fund contributions + expenditures for the applicable period

## Major report sections (verbatim from the 2023 page)

- Cumulative Accounting Overview
- Relation to Prior Regional Analyses
- Units of Use
- Banked Development Rights
- Development Right Transfers
- Development Right Conversions
- Residential
  - Existing Units
  - Existing Units by Land Capability
  - Residential Allocations
  - Residential Bonus Units
  - ADUs
- Commercial Floor Area (CFA)
  - Existing CFA by Land Capability
  - CFA Allocations
- Tourist Accommodation Units (TAU)
  - Existing TAUs by Land Capability
- Recreation
- Resource Utilization
  - VMT
  - DVTE
  - Impervious Coverage
  - Water Demand
  - Sewage Disposal
- Threshold Attainment and Maintenance

## Vocabulary clarifications (avoid these pitfalls)

- **"Allocation"** is a specific concept — a unit drawn from Unused Capacity
  and granted to a jurisdiction or parcel. Do **not** use "allocation" as a
  generic term for "development right." The generic term is **commodity**.
- **"Bonus Unit"** (RBU) is not the same as an allocation — it's a separate
  bucket of reserved capacity granted for environmental benefits. A parcel
  may receive an RBU *in addition to* its regular allocation.
- **"Banked"** does not mean "in the bank." It means "legally existed but
  currently removed from the ground, reserved for onsite rebuild or transfer."
  Banked development is not new capacity.
- **"Converted"** means type-to-type exchange at fixed ratios — not moved
  between parcels (that's "transferred") and not moved between states (that's
  banking/unbanking).
- **"Existing"** means on-the-ground built, **not** permitted-but-not-built.
  Permitted-but-not-built is still in the "Allocated" bucket until final
  inspection / certificate of occupancy.
- **"Pool"** is the container, **"allocation"** is the drawdown event,
  **"commodity"** is the type. All three terms are load-bearing and distinct.

## How this skill should shape design and implementation work

When you're asked to build anything adjacent to cumulative accounting:

1. **Schema decisions**: anchor on the five-bucket model. Don't model
   allocations as the primary entity; model *pool ledger entries* that move
   commodities between buckets. Allocation release is one of seven movement
   types.
2. **Dashboard decisions**: reports must show bucket decomposition per
   commodity per jurisdiction per year. A stacked area chart of remaining
   capacity over time is the canonical allocation-drawdown view.
3. **Terminology**: match TRPA's vocabulary exactly. Don't invent synonyms.
   If building UIs for internal staff, governing board, developers, or
   jurisdictions — they all expect these specific terms.
4. **Time resolution**: default to annual (Dec 31) snapshots for public
   reporting. Drill-down to transaction-level is for internal use only.
5. **Conversion arithmetic**: if a report shows "net change in residential
   units since 2018 = +157," validate by adding allocation releases,
   subtracting retirements, and including the ±65 TAU conversion and
   ±30,500 CFA conversion at fixed ratios.

## Related systems & data sources

- **Corral SQL Server (sql24)** — LTinfo's backend. Source of truth for
  allocations, pools, TDR transactions. Tables of interest:
  `CommodityPool` (129), `ResidentialAllocation` (1,852),
  `TdrTransaction*` family, `ShorezoneAllocation` (374),
  `CommodityPoolDisbursement` (230).
- **LTinfo web services** — live read interface over Corral.
  `GetTransactedAndBankedDevelopmentRights`, `GetBankedDevelopmentRights`,
  `GetAllParcels` are the key endpoints.
- **GIS enterprise geodatabase (future; today `C:\GIS\Scratch.gdb\Parcel_History_Attributed`)**
  — APN × Year × Shape 2006–2023 (gap 2016–2017). Authoritative for
  **Existing Development** per parcel per year (`RES`, `TAU`, `CFA`,
  `Assessor_Units`, `YEAR_BUILT` columns).
- **Ken's spreadsheets** (`data/raw_data/`) — bridge data that stitches
  allocations to permit completion and existing-development changes. Loaded
  into the new integration DB as ETL input.
- **Accela** — permit workflow system of record; accessed via Corral's
  `AccelaCAPRecord` bridge (124K rows) or directly.

## References

- TRPA Code of Ordinances §16.8.2 — "Cumulative accounting of units of use,
  resource utilization, and threshold attainment and maintenance."
- Public report: [thresholds.laketahoeinfo.org/CumulativeAccounting/Index/{year}](https://thresholds.laketahoeinfo.org/CumulativeAccounting/Index/2023)
- 2013 Regional Plan — authorized 2,600 new homes (the "Max Regional Capacity"
  baseline for residential).
- Repo memory: [C:\Users\mbindl\.claude\projects\...\memory\MEMORY.md](../../../../memory/MEMORY.md) —
  notes the TRPA pool / Jurisdiction pool / Private pool distinction.
