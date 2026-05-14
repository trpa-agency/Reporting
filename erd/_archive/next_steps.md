# Cumulative Accounting - next steps

> **SUPERSEDED.** This proposed an earlier architecture. Current source of truth: system_of_record_roadmap.md plus the live Cumulative_Accounting service.

A 5-minute read ahead of a working session. Everything here is
proposal / direction; nothing is built in Corral or anywhere else yet.

## What we're building

A single SQL-backed **development-rights ledger** that produces the
annual cumulative accounting report, the allocation drawdown chart,
and a per-APN history view from one source. It anchors on the five
buckets from TRPA Code §16.8.2:

```
Max Regional Capacity  =  Existing + Banked + Remaining
where  Remaining  =  Allocated + Not Allocated + Not Released
```

Every event (allocation, assignment, transfer, conversion, banking,
retirement) moves commodity between those buckets. The ledger records
each movement as a signed-quantity row; reports are `SUM(Quantity)`
queries over the ledger filtered by year / jurisdiction / commodity.

## Where the data comes from

Three inputs, one destination:

1. **Corral (`sql24/Corral`)** - system of record for transactions,
   allocations, banked rights, pools, and parcels. We read it; we don't
   change its schema.
2. **GIS `Parcel_History_Attributed` feature class** - authoritative for
   existing development per parcel per year (residential units, TAU,
   CFA). Fills Corral's coverage gap for buildings that never triggered
   a permit-driven inventory update.
3. **`2025 Transactions and Allocations Details.xlsx`** - authoritative
   for the 10 columns Corral doesn't hold: year built, PM year built,
   TRPA/MOU project #, development type / detailed development type,
   local jurisdiction status + date, allocation number, supplemental
   notes. Keeps working as the authoring surface; a scheduled ETL pulls
   those columns into the ledger.

Destination: one flat ledger table (`LedgerEntry`) plus a small sidecar
for permit metadata (`LedgerEntryAnnotation`). Dashboards and reports
read from derived views, not from any of the three source systems
directly.

## What's already in flight

- **`notebooks/`** - reproducible diff between Corral and the 2025 XLSX.
  Confirms the 78% join rate, surfaces the columns Corral doesn't source,
  and produces the transition-table CSV that becomes the annotation
  loader.
- **`ledger_prototype/`** - CSV-only prototype of the full ledger. Pulls
  from live Corral, fans `dbo.TdrTransaction` + banking + annotations
  into signed-quantity ledger rows, runs the accounting-identity
  validator, and compares 2023 residential totals against the public
  cumulative accounting report. Proves the model works before we commit
  to SDE DDL.
- **`erd/target_schema.md`** - full ERD proposal for the SDE DB version:
  6 physical tables + 4 views. Stays in draft until the questions below
  are resolved.

## Questions we need to close before cutting DDL

Proposals in brackets - confirm, override, or flag if unclear.

1. **ECM Retirement** - what does "ECM" expand to? Best read from the
   docs is *Excess Coverage Mitigation*, consistent with the Threshold
   Attainment fund named the same thing.
   *[proposed: Excess Coverage Mitigation]*

2. **Pool sub-structure.** CSLT's three sub-pools (Single-Family,
   Multi-Family, Town Center) are well-documented. Are there other
   jurisdictions with similar sub-pools, or CFA area-plan sub-pools, not
   obvious from `dbo.CommodityPool` names?
   *[proposed: CSLT's three only; one pool per commodity elsewhere]*

3. **Max Regional Capacity source.** 2,600 residential units from the
   2013 Regional Plan is clear. What's the authoritative source for
   each other commodity's cap (TAU, CFA sq ft, RBU, PAOT pools)?
   *[proposed: pull each from the 2023 published cumulative accounting report]*

4. **ADU modeling.** Corral's `ResidentialAllocationUseType` has only
   Single-Family and Multi-Family. How do ADUs fit?
   *[options: (a) third use type; (b) flag on an allocation; (c) a new
   `Commodity` value]* - *[proposed: (c), since the annual report
   already breaks ADU counts out]*

5. **2012–2015 existing-development baseline.** Pre-2016 is outside
   Corral's AuditLog. The `ExistingResidential_2012_2025_unstacked.csv`
   is the candidate seed. Is it the right source to stand behind?
   *[proposed: yes - loaded with `SourceSystem='legacy_seed'` provenance]*

## Rough timeline

| When | What |
|---|---|
| Now | Ledger prototype runs end-to-end against live Corral; validator passes; 2023 delta captured as findings. |
| After questions close | Draft DDL for the 6 tables + 4 views. Review with DB admins before running. |
| Weeks 2–3 | Stand up the ledger in the SDE DB; wire the GIS feature-class reader. |
| Week 4 | Publish ESRI MapServer / FeatureServer layers over the views; point dashboards at them. |
| Later | Back-fill `TdrTransaction.AccelaCAPRecordID` into Corral from the ledger's permit joins. |

## What doesn't change for the XLSX workflow

The 2025 XLSX stays as the authoring surface. The scheduled ETL reads
it into the ledger. When the source system (county assessor, Accela
MOU tracker) is ready to feed the data directly, that reader swaps in
and the ETL retires - the schema doesn't change.

## Working session agenda (suggested)

1. Walk through the five questions above. 10 minutes each.
2. Review the prototype output (`ledger_prototype/views/v_cumulative_accounting.csv`)
   side-by-side with the 2023 public report. Pick the biggest delta and
   trace where it comes from.
3. Agree on a go / pause / refine decision before DDL.
