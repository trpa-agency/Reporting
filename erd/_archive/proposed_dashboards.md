# Proposed data visualizations

> **Status: draft proposal, ready for team review.**
> **Audience: TRPA dev team, Dan, stakeholder leads (governing board, partner jurisdictions, developers, public).**
> **Buildability review**: every entry below is marked ✅ (buildable at v1 with the current target_schema.md), 🟡 (buildable v1 with a caveat), or 🟥 (not buildable v1 — missing upstream data or a schema feature deferred to v2).

The allocation drawdown prototype at [html/allocation_drawdown.html](../html/allocation_drawdown.html)
proves the stack works: Plotly.js + the TRPA dashboard brand, pulling from
the new schema tables + Corral + the enterprise GIS service. This doc
proposes the next set of dashboards to build.

Each visualization is scored on:

- **Audience** — who it's for.
- **Priority** — v1 (build with the schema), v2 (after v1 lands), stretch.
- **Data sources** — what tables/views feed it.
- **Complexity** — rough build cost (S / M / L).

See [cumulative_accounting_reference.md](./cumulative_accounting_reference.md)
for vocabulary, and [target_schema.md](./target_schema.md) for the tables
these visualizations would read from.

---

## Already committed (3 dashboards drive the v1 schema)

| # | Dashboard | Status |
|---|---|---|
| 0.1 | **Cumulative Accounting Report** — annual XLSX replacement. 5-bucket decomposition per commodity × jurisdiction × year. | v1, driven by `CumulativeAccountingSnapshot` |
| 0.2 | **Allocation Drawdown** — stacked area chart: pool × year → remaining balance. | v1, driven by `PoolDrawdownYearly`. Prototype at [html/allocation_drawdown.html](../html/allocation_drawdown.html) |
| 0.3 | **Parcel History Lookup** — per-APN timeline with change-rationale detail. | v1, driven by `ParcelHistoryView` + `ParcelDevelopmentChangeEvent` |

Everything below is **new**, in addition to those three.

---

## Cluster A — Regional capacity + buildout

For Dan, the governing board, partner agencies. Communicates "where is
Tahoe overall" in a single glance.

### A1. Regional Capacity Dial ✅ (v1 — built)

- **What it shows**: 4 Plotly indicator gauges in a 2×2 grid — one per
  commodity (Residential Allocations, Residential Bonus Units, Tourist
  Bonus Units, Commercial Floor Area) showing `% built` against the
  since-1987 cumulative Regional Plan max. Below: a stacked horizontal
  bar showing all 4 capacities side-by-side (constructed in TRPA brand
  color + remaining in ice). A framing strip distinguishes the 8,687
  since-1987 cumulative max from the 2,600 2012-Plan additional Board
  authorization.
- **Audience**: Governing board, press, annual reporting. The single
  page that answers "where is Tahoe overall."
- **Data**: inlined today from Ken's 2026 PPTX slide 8 (5 numbers ×
  4 commodities). Eventually backed by `CumulativeAccountingSnapshot`
  aggregated to Regional totals.
- **Complexity**: S. Built as
  [`html/regional-capacity-dial.html`](../html/regional-capacity-dial.html)
  — single-file Plotly + TRPA brand. No fetch, no state, no filters —
  pure headline dashboard.
- **Track context:** see [allocation_track.md](./allocation_track.md)
  for the broader Track B picture.

### A2. Buildout Projection (v2)

- **What it shows**: Line chart of existing development 2012→present, with
  projected buildout under current drawdown rates. Marks years remaining
  until full buildout per commodity.
- **Audience**: Planning staff, governing board, scenario analysis.
- **Data**: `CumulativeAccountingSnapshot` historical + trend extrapolation.
- **Complexity**: M. Needs a simple linear/exponential fit per commodity.
- **Open question**: Which projection model does TRPA prefer? Linear,
  S-curve, seasonal-adjusted? *Needs input from planning.*

### A3. Jurisdiction Scorecard (v1)

- **What it shows**: Small-multiples grid — one card per jurisdiction ×
  commodity showing `% of its own capacity used`, plus a sparkline of the
  drawdown trend.
- **Audience**: Partner jurisdictions (self-service), Dan for cross-jurisdiction
  comparisons.
- **Data**: `CumulativeAccountingSnapshot` + `PoolDrawdownYearly`.
- **Complexity**: M. 4 jurisdictions × 3 commodities = 12 cards in a grid.

### A4. Residential Additions by Source ✅ (v1 — built)

- **What it shows**: Multi-line chart by year tracking five sources of
  added residential units — **Allocations, Bonus Units, Transfers,
  Conversions, Banked**. Toggle between counts (lines), stacked area, and
  stacked percent. Sidebar of major completed projects per year (Sugar
  Pine, LTCC Dorms, Beach Club, etc.) anchors the inflections in narrative.
- **Audience**: Governing board, Dan, planning staff. The "where did the
  units come from" story that the cumulative accounting report
  (PPTX slide 4) tells in static form. Surfaces the 2024–25 bonus surge
  (Sugar Pine 70 + LTCC 85 = 155 affordable units) as the dominant
  recent driver.
- **Data**: realized today from
  [`from_ken/FINAL RES SUMMARY 2012 to 2025.xlsx`](../from_ken/FINAL%20RES%20SUMMARY%202012%20to%202025.xlsx)
  Summary sheet (the categorical "Added Residential Units from {Source}"
  rows). Eventually backed by `vCommodityLedger` filtered to residential
  commodities, grouped by year and movement type.
- **Complexity**: S. Built as
  [`html/residential-additions-by-source.html`](../html/residential-additions-by-source.html)
  — single-file Plotly + TRPA brand, ~13×6 dataset inlined.
- **Reverse-engineering**: see [dashboards_to_schema_trace.md](./dashboards_to_schema_trace.md)
  §"A4 reverse engineering" for the SQL shape against `vCommodityLedger`
  and the corresponding LT Info endpoint candidate.
- **Why it matters**: PPTX slide 3 calls out *"Bonus Units became the #1
  source of 2024 and 2025 additions"* — A4 is that finding made
  interactive. Pairs naturally with A1 (Regional Capacity Dial) for
  board-meeting use: A1 says "where are we", A4 says "how did we get here."

---

## Cluster B — Pool + allocation tracking

For internal TRPA staff doing allocation accounting. Extends the existing
drawdown prototype.

### B1. Pool Balance Cards ✅ (v1 — built; B2 trajectory included)

- **What it shows**: Grid of 9 cards, one per residential allocation pool
  (8 jurisdiction + sub-pool + 1 TRPA-central). Each card: current
  remaining (big number), initial capacity, % remaining bar (TRPA brand
  color per pool), drawn-down count, low/exhausted status flag. Click a
  card to populate the detail panel below with the pool's year-by-year
  trajectory (2013–26) as a Plotly area chart. KPI strip up top: total
  remaining, drawn down since 2013, pools exhausted, unreleased held
  centrally.
- **Audience**: TRPA allocation staff (daily-use), jurisdictions checking
  "what's left in our pool."
- **Data**: remaining counts inlined from Ken's
  `from_ken/Additional Development as of April2026.xlsx` LT Info Pools
  sheet (with the TRPA Pool 144→154 correction applied). Trajectory
  inlined from `html/allocation_drawdown.html`'s embedded series.
  Eventually backed by `PoolDrawdownYearly` most-recent row +
  `dbo.CommodityPool`.
- **Complexity**: M. Built as
  [`html/pool-balance-cards.html`](../html/pool-balance-cards.html) —
  single-file Plotly + TRPA brand, no fetch.
- **Sort options**: by remaining (default), by % used, by name.
- **Track context:** see [allocation_track.md](./allocation_track.md).
- **B2 status**: trajectory line (year-by-year remaining) covers the
  high-level B2 ask. The fuller B2 — per-event ledger drill-down with
  movement-type filtering — needs `vCommodityLedger` which is still
  schema-side. Marked 🟡 partial below.

### B2. Pool Detail Drill-down 🟡 (v1 partial — trajectory in B1, per-event detail pending vCommodityLedger)

- **What it shows**: For a selected pool: timeline of every ledger entry
  (allocations released, used, banked, transferred). Filter by year / by
  movement type.
- **Audience**: Staff auditing a specific pool's history.
- **Data**: `vCommodityLedger` filtered by `FromPoolID` or `ToPoolID`.
- **Complexity**: M. Timeline + filterable table.

### B3. Allocation Pipeline Funnel 🟡 (v1 with caveat)

- **What it shows**: Funnel chart showing allocation lifecycle — Released →
  Assigned → InPermit → Used → Expired. Counts and conversion rates between
  stages, per jurisdiction and per year.
- **Audience**: Staff answering "how many allocations we release actually
  get built?"
- **Data**: `dbo.ResidentialAllocation` joined to `dbo.ParcelPermit` via
  `vPermitAllocation`; status transitions from `vCommodityLedger`.
- **Complexity**: M.
- **🟡 Caveat**: `vPermitAllocation` Phase 1 has ~32% AccelaID coverage. The
  "InPermit → Used" stage shows 32% of reality. Ship v1 **with a prominent
  "confidence: Phase 1 coverage ~32%" badge**; coverage improves when
  Phase 2 back-fills `dbo.TdrTransaction.AccelaCAPRecordID` from Ken's XLSX
  (see Q7 in target_schema.md).

### B4. Expired Allocation Heatmap (v2)

- **What it shows**: Heatmap — rows = pools, columns = issuance years, cell
  color = % of that cohort that expired unbuilt. Identifies pools / years
  where capacity was "wasted".
- **Audience**: Planning staff looking for policy levers.
- **Data**: `dbo.ResidentialAllocation` + `PermitCompletion`.
- **Complexity**: M.

---

## Cluster C — Transfers + conversions

For staff tracking where development rights are *moving*. The 2013 Regional
Plan's whole point is to shift units out of SEZ into town centers — this is
where we visualize that.

### C1. TDR Transfer Flow Map (v1)

- **What it shows**: Parcel polygons with arrows from sending to receiving
  parcels. Time slider or year filter. Color = commodity type.
- **Audience**: Staff + public. "Where are development rights moving
  geographically?"
- **Data**: `vCommodityLedger WHERE MovementType='TRF'` joined to
  `dbo.Parcel` geometry for sending + receiving.
- **Complexity**: L. Requires ArcGIS Maps SDK + geometric arrow rendering.
- **Why it matters**: The existing `Parcel_Transfers` FC in `Scratch.gdb`
  already has this data pre-computed; we're productionizing it.

### C2. SEZ-Out / Town-Center-In Tracker ✅ (v1)

- **What it shows**: Running counters: "cumulative RES / TAU / CFA moved out
  of SEZ since 2013" and "moved into town centers since 2013." Year
  breakdowns as small bar charts.
- **Audience**: Governing board, annual reporting (this is a 2013 RP success
  metric).
- **Data**: `vCommodityLedger` + `ParcelSpatialAttribute` for `WithinSEZ`
  and `TownCenter` flags at both sending + receiving parcels.
- **Complexity**: M.
- **Prerequisite addressed**: `WithinSEZ` is now explicitly a column in
  `ParcelSpatialAttribute` (derived at load from Bailey rating 1a/1b/1c).

### C3. Commodity Conversion Sankey ✅ (v1)

- **What it shows**: Sankey diagram of conversions: left side = source
  commodities, right side = target commodities. Flow thickness = total units
  converted. Filter by year / jurisdiction.
- **Audience**: Planning staff tracking type-balance shifts (from the skill:
  post-2018 net is +157 RES / −65 TAU / −30,500 CFA).
- **Data**: `vCommodityLedger WHERE MovementType IN ('CONV','CONVTRF')`
  grouped by `PairingKey` (now exposed by the view; see target_schema.md).
- **Complexity**: M.

---

## Cluster D — Permit + completion pipeline

For staff tracking permit workflow and construction cadence.

### D1. Permit Pipeline Dashboard (v1)

- **What it shows**: Stacked bar chart by year — Applied / Issued / Under
  Construction / Finaled / Expired. Per-jurisdiction breakout. Percentage
  completion rate trend.
- **Audience**: Staff, jurisdictions self-monitoring their permit throughput.
- **Data**: `dbo.ParcelPermit` + `PermitCompletion`.
- **Complexity**: M.

### D2. Year-Built Lag Histogram (v2)

- **What it shows**: Distribution of time between `IssuedDate` and `YearBuilt`
  (or CO date). Per-jurisdiction comparison. Identifies slow-to-build
  jurisdictions or eras.
- **Audience**: Planning staff, jurisdiction benchmarking.
- **Data**: `dbo.ParcelPermit.IssuedDate` + `PermitCompletion.YearBuilt`.
- **Complexity**: S.

### D3. Active Construction Map 🟥 (v2 — needs live Accela)

- **What it shows**: Parcels with permits in "Under Construction" status,
  colored by permit age. Hover for permit detail. Staff can see what's
  currently in progress.
- **Audience**: Field inspection staff, project managers.
- **Data**: `PermitCompletion.CompletionStatusEnriched='UnderConstruction'`
  joined to parcel geometry.
- **Complexity**: M.
- **🟥 Blocker for v1**: Ken's XLSX carries permit status as a static
  snapshot (`Status Jan 2026`) — not live. "Under Construction" status needs
  a direct Accela feed to be trustworthy in real time. Defer until Accela
  integration lands.

---

## Cluster E — Change-rationale + QA

Directly serves Dan's ask for "a separate database of change rationale."

### E1. Change Rationale Audit Trail ✅ (v1 — built)

- **What it shows**: Filterable AG Grid table of every QA change event
  with APN (raw + canonical), reporting year, sweep campaign, quantity
  delta, correction category, rationale, recorded-by. Filters: reporting
  year, sweep campaign, vocab-canonicality (canonical vs noncanonical),
  free-text search across APN/rationale/category. Sidebar bar chart
  showing top 12 correction categories color-coded by canonicality.
- **Audience**: Dan + any staff auditing the 2023 and 2026 residential
  big-sweep corrections.
- **Data**: realized today from
  [`data/qa_data/qa_change_events.csv`](../data/qa_data/qa_change_events.csv)
  + [`qa_correction_detail.csv`](../data/qa_data/qa_correction_detail.csv)
  (5,925 events, joined client-side on `ChangeEventID`). Outputs of
  [`notebooks/04_load_ca_changes.ipynb`](../notebooks/04_load_ca_changes.ipynb)
  (Track C). Eventually backed by `ParcelDevelopmentChangeEvent` +
  `QaCorrectionDetail` once the DB load happens.
- **Complexity**: S. Built as
  [`html/qa-change-rationale.html`](../html/qa-change-rationale.html) —
  single-file Plotly + AG Grid + TRPA brand. KPIs surface the 30%
  canonical-vocab match as a "needs Ken's triage" signal.
- **Track context**: see [qa_corrections_track.md](./qa_corrections_track.md)
  for the full data flow + open issues.

### E2. Changes By Source Dashboard (v1)

- **What it shows**: Pie / bar of `ChangeSource` distribution — what % of
  changes are development-rights-use vs QA corrections vs genealogy
  restatements. Trend over time.
- **Audience**: Dan, Ken, anyone asking "are we spending more time on QA or
  on real events?"
- **Data**: `ParcelDevelopmentChangeEvent` aggregated.
- **Complexity**: S.

### E3. Recently Changed Parcels Map (v1)

- **What it shows**: Map of parcels whose `ParcelExistingDevelopment`
  changed in the last N days, colored by `ChangeSource`. Click parcel →
  full change log (E1).
- **Audience**: Staff monitoring data health in real time.
- **Data**: `ParcelDevelopmentChangeEvent` + parcel geometry.
- **Complexity**: M.

### E4. QA Checklist Progress (v2 — depends on QA workflow tables)

- **What it shows**: For each "locked 2025 data" parcel flagged for QA, how
  many checklist items are complete. Progress bar per parcel.
- **Audience**: QA reviewers.
- **Data**: v2+ `QaChecklist` + `QaChecklistResponse` tables.
- **Complexity**: M.

---

## Cluster F — Banked rights

### F1. Banked Rights Inventory (v1)

- **What it shows**: Table + map of all active banked rights (Corral's
  `dbo.ParcelPermitBankedDevelopmentRight` where not yet unbanked). Age
  breakdown: how long has each been banked?
- **Audience**: Staff tracking dormant capacity.
- **Data**: `dbo.ParcelPermitBankedDevelopmentRight` + `dbo.ParcelPermit` +
  parcel geometry.
- **Complexity**: S.

### F2. Banked → Rebuilt Conversion Rate ✅ (v1)

- **What it shows**: Of all rights banked in year Y, what fraction have been
  unbanked/rebuilt vs still sitting? Cohort analysis.
- **Audience**: Policy analysis.
- **Data**: `vCommodityLedger WHERE MovementType IN ('Banking','Unbanking')`.
- **Complexity**: M.
- **Prerequisite addressed**: `Unbanking` is now a first-class MovementType
  in `vCommodityLedger` and a column in `PoolDrawdownYearly`.

---

## Cluster G — Public-facing

### G1. Public Allocation Availability ✅ (v1 — built)

- **What it shows**: 6 large jurisdiction tiles, each showing residential
  allocations remaining as a big number with a TRPA brand-colored
  progress bar and a usage caption ("X of Y initial used"). Above the
  tiles: a total-strip summarizing basin-wide remaining + the 770
  unreleased-to-jurisdiction count + the 8,687 cumulative cap context.
  Below: an "What's a residential allocation?" plain-language explainer
  for the public audience, with a pointer to parcels.laketahoeinfo.org
  for per-APN detail.
- **Audience**: Developers, general public, partner jurisdictions
  checking "what's left in my pool."
- **Data**: same source as B1 Pool Balance Cards — Ken's
  `from_ken/Additional Development as of April2026.xlsx` LT Info Pools
  Balances, with the TRPA Pool 144→154 correction. The 3 CSLT
  sub-pools roll up into a single CSLT row for the public view.
  Eventually backed by `PoolDrawdownYearly` most-recent.
- **Complexity**: S. Built as
  [`html/public-allocation-availability.html`](../html/public-allocation-availability.html)
  — single-file HTML/CSS, no Plotly (just CSS), no fetch. Deliberately
  no filters, no map, no detail panel — public-facing means lowest-
  cognitive-load.
- **Pairs with B1**: B1 (`pool-balance-cards.html`) is the staff view
  showing all 9 pools including CSLT sub-pools; G1 is the public view
  rolling sub-pools up. Same data, different framing.

### G2. Parcel Development Rights Lookup (public) (v1)

- **What it shows**: Given an APN, what commodities does the parcel have?
  Any banked rights? Any existing deed restrictions? Read-only public view.
- **Audience**: Developers doing site due diligence, real estate agents,
  residents.
- **Data**: `ParcelExistingDevelopment` + `dbo.ParcelPermitBankedDevelopmentRight`
  + v2 `DeedRestriction` join.
- **Complexity**: M.

### G3. Transfer Market Listings (stretch)

- **What it shows**: Public-facing list of active `dbo.TdrListing` rows —
  "development rights for sale" marketplace view.
- **Audience**: Developers looking to acquire rights.
- **Data**: `dbo.TdrListing` (exists in Corral with 1 row today — growth
  pending).
- **Complexity**: M.

---

## Cluster H — ADU (if Q1 resolves ADU as a use type)

### H1. ADU Growth Map (v1 or v2 depending on Q1)

- **What it shows**: Parcels that gained an ADU over time. Time slider.
- **Audience**: Housing staff, Tahoe Living initiative (per `tahoe-living-brand` skill).
- **Data**: `ParcelExistingDevelopment` WHERE commodity maps to ADU.
- **Complexity**: M.

### H2. ADU Pipeline (v1 or v2)

- **What it shows**: Permits tagged `UseType='ADU'` by status — Applied /
  Issued / Built. Per-jurisdiction.
- **Audience**: Housing staff, jurisdictions tracking their ADU programs.
- **Data**: `dbo.ParcelPermit` + `PermitCompletion` + `dbo.ResidentialAllocationUseType`.
- **Complexity**: S.

---

## Questions for the team

1. **Stakeholder priorities.** Which 5 visualizations from above would have
   the highest impact for your primary audience? Please pick the top 5 and
   rank them.
2. **Governing board must-haves.** For the next board meeting, which of
   these visualizations would actually change the conversation? (A1 Regional
   Capacity Dial and C2 SEZ-Out Tracker are my guesses — confirm?)
3. **Partner jurisdiction self-service.** If jurisdictions can only access
   one page, is it A3 Jurisdiction Scorecard, B1 Pool Balance Cards, or G1
   Public Allocation Availability?
4. **Developer self-service.** G2 Parcel Development Rights Lookup —
   genuinely useful, or does it create too many questions for staff to
   answer?
5. **Tech stack confirmation.** Per the `trpa-dashboard-stack` skill:
   Plotly.js for charts, Calcite for UI, ArcGIS Maps SDK for maps, AG Grid
   for tables. All dashboards above assume this stack. Any overrides?
6. **Hosting.** Where do these get deployed? `html/` in this repo today;
   eventually published behind `trpa.gov` or `laketahoeinfo.org`?
7. **Refresh cadence.** Can we commit to the dashboard backends
   (`CumulativeAccountingSnapshot`, `PoolDrawdownYearly`) recomputing
   nightly? That drives the "freshness" label on every chart.
8. **Public vs internal.** Which dashboards are public and which are
   staff-only? Cluster G is deliberately public; all of E is staff-only;
   others are in between.
9. **Mobile support.** Do any of these need to work on phones /
   tablets for field staff?

---

## My opinion — what to build first

If I had to pick 5 for a v1 dashboards shelf:

1. **A1 Regional Capacity Dial** — communication to board + press. Biggest
   "one-glance" value.
2. **B1 Pool Balance Cards + B2 Pool Detail** — the daily-use tool for
   allocation staff. Pair these.
3. **E1 Change Rationale Audit Trail** — Dan's explicit ask. Delivers that
   on day one.
4. **G1 Public Allocation Availability** — developer self-service. Takes a
   lot of phone-call traffic off staff.
5. **D1 Permit Pipeline Dashboard** — the most-asked-about view from
   jurisdictions.

That's 5. Everything else can come in v2 or on-demand.
