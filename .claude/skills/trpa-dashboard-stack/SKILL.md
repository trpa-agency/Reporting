---
name: trpa-dashboard-stack
description: "TRPA dashboard and web application tech stack. Use this skill whenever building a dashboard, web app, data visualization, map, interactive report, or any browser-based tool for TRPA. This skill defines the required libraries (Plotly.js, Calcite Design System, ArcGIS Maps SDK for JavaScript, AG Grid), CDN loading, page structure, and coding patterns. Always use this skill together with the appropriate brand skill (trpa-brand, trpa-eip-brand, or tahoe-living-brand) for colors and typography. Trigger on any mention of: dashboard, web app, HTML page, data viz, map view, interactive report, allocation tracker, parcel viewer, or any request to build something for the browser."
---

# TRPA Dashboard Tech Stack

All TRPA dashboards and web applications are built as **single-file HTML pages** that load libraries from CDN. No build tools, no bundlers, no node_modules. One `.html` file that can be opened directly or served from GitHub Pages.

This skill defines the required tech stack and patterns. **Always pair with the appropriate brand skill** for colors, fonts, and visual identity:

- **General TRPA tools** → `trpa-brand` (TRPA Blue `#0072CE`, Open Sans)
- **EIP projects** → `trpa-eip-brand` (EIP palette, Lexend Deca)
- **Housing / Tahoe Living** → `tahoe-living-brand` (sage/terracotta, Montserrat)

---

## Required Libraries

Every dashboard must use these four libraries. Load them in this order.

### 1. Calcite Design System (UI shell and components)

Calcite provides the page layout, panels, buttons, dropdowns, tabs, loaders, modals, and all structural UI. It is the design system — do not use Bootstrap, Tailwind, or other CSS frameworks alongside it.

```html
<!-- Calcite Design System v5.0 -->
<script type="module" src="https://js.arcgis.com/calcite-components/5.0"></script>
<link rel="stylesheet" type="text/css" href="https://js.arcgis.com/calcite-components/5.0/calcite.css" />
```

### 2. ArcGIS Maps SDK for JavaScript (maps and spatial)

Use for any map view, spatial query, feature layer, or location-based visualization. If the dashboard has no map, this can be omitted — but most TRPA dashboards will have one.

```html
<!-- ArcGIS Maps SDK for JavaScript -->
<link rel="stylesheet" href="https://js.arcgis.com/4.31/esri/themes/light/main.css" />
<script src="https://js.arcgis.com/4.31/"></script>
```

When using ArcGIS with Calcite, load modules via `require()`:

```javascript
require([
  "esri/Map",
  "esri/views/MapView",
  "esri/layers/FeatureLayer",
  "esri/widgets/Legend",
  "esri/widgets/Home"
], function(Map, MapView, FeatureLayer, Legend, Home) {
  // Map code here
});
```

### 3. Plotly.js (charts and data visualization)

Plotly is the charting library. Use it for all bar charts, line charts, stacked charts, pie/donut charts, sankey diagrams, scatter plots, and any non-map visualization. Do NOT use Chart.js, D3 directly, or other charting libraries.

```html
<!-- Plotly.js -->
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
```

### 4. AG Grid Community (data tables)

AG Grid is the table/grid library. Use it for any tabular data display with sorting, filtering, pagination, and CSV export. Do NOT use plain HTML tables for data — always use AG Grid.

```html
<!-- AG Grid Community -->
<script src="https://cdn.jsdelivr.net/npm/ag-grid-community/dist/ag-grid-community.min.js"></script>
```

---

## Brand-Specific Color Constants

Use the correct color set based on which brand skill is active. These are the official Plotly colorway arrays and font settings for each brand:

### TRPA Agency (trpa-brand)

```javascript
const BRAND_COLORS = ['#0072CE', '#003B71', '#E87722', '#4A6118', '#9C3E27', '#B5A64C', '#7B6A8A', '#B4CBE8'];
const BRAND_FONT = 'Open Sans, system-ui, sans-serif';
const BRAND_TEXT = '#003B71';  // PMS 541 Navy
```

### EIP (trpa-eip-brand)

```javascript
const BRAND_COLORS = ['#007DC3', '#6EBE44', '#F16022', '#0B1F41'];
const BRAND_FONT = 'Lexend Deca, system-ui, sans-serif';
const BRAND_TEXT = '#0B1F41';  // EIP Navy
```

### Tahoe Living (tahoe-living-brand)

```javascript
const BRAND_COLORS = ['#5B7B6B', '#C4704B', '#6BA3BE', '#D4A843', '#3D6B4E', '#8B6F5E'];
const BRAND_FONT = 'Montserrat, system-ui, sans-serif';
const BRAND_TEXT = '#2C2C2C';
```

---

## Page Template

Every dashboard follows this structure. The template below uses EIP brand tokens as the default — swap in the appropriate CSS variables and font link from the active brand skill.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>TITLE — TRPA</title>

  <!-- Calcite -->
  <script type="module" src="https://js.arcgis.com/calcite-components/5.0"></script>
  <link rel="stylesheet" type="text/css" href="https://js.arcgis.com/calcite-components/5.0/calcite.css" />

  <!-- ArcGIS Maps SDK (include if dashboard has a map) -->
  <link rel="stylesheet" href="https://js.arcgis.com/4.31/esri/themes/light/main.css" />
  <script src="https://js.arcgis.com/4.31/"></script>

  <!-- Plotly.js -->
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>

  <!-- AG Grid Community -->
  <script src="https://cdn.jsdelivr.net/npm/ag-grid-community/dist/ag-grid-community.min.js"></script>

  <!-- Google Fonts — swap per brand:
       EIP:          Lexend Deca
       TRPA Agency:  Open Sans
       Tahoe Living: Montserrat
  -->
  <link href="https://fonts.googleapis.com/css2?family=Lexend+Deca:wght@300;400;500;600;700&display=swap" rel="stylesheet" />

  <style>
    /* ── Brand Tokens — replace with active brand ── */
    :root {
      /* EIP defaults (swap for trpa-brand or tahoe-living-brand) */
      --brand-primary:    #007DC3;
      --brand-secondary:  #6EBE44;
      --brand-accent:     #F16022;
      --brand-dark:       #0B1F41;
      --brand-light:      #E0F0FA;

      /* TRPA Agency alternative:
      --brand-primary:    #0072CE;
      --brand-secondary:  #003B71;
      --brand-accent:     #E87722;
      --brand-dark:       #003B71;
      --brand-light:      #E8F1F8;
      */
    }

    html, body {
      margin: 0;
      padding: 0;
      font-family: 'Lexend Deca', system-ui, sans-serif;
      color: var(--brand-dark);
      background: #f8f9fa;
    }

    /* Page header bar */
    .dashboard-header {
      background: var(--brand-dark);
      color: #fff;
      padding: 1rem 2rem;
      display: flex;
      align-items: center;
      gap: 1rem;
    }
    .dashboard-header h1 {
      font-size: 1.5rem;
      font-weight: 700;
      margin: 0;
    }
    .dashboard-header .subtitle {
      font-size: 0.85rem;
      opacity: 0.75;
    }

    /* KPI summary cards row */
    .kpi-row {
      display: flex;
      gap: 1rem;
      padding: 1.5rem 2rem;
      flex-wrap: wrap;
    }
    .kpi-card {
      background: #fff;
      border-radius: 8px;
      padding: 1.25rem 1.5rem;
      flex: 1;
      min-width: 180px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
      border-top: 3px solid var(--brand-primary);
    }
    .kpi-card .kpi-value {
      font-size: 2rem;
      font-weight: 700;
      color: var(--brand-dark);
    }
    .kpi-card .kpi-label {
      font-size: 0.8rem;
      color: #5a6577;
      margin-top: 0.25rem;
    }

    /* Content area */
    .dashboard-content {
      padding: 0 2rem 2rem;
    }

    /* Chart containers */
    .chart-container {
      background: #fff;
      border-radius: 8px;
      padding: 1.25rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
      margin-bottom: 1rem;
    }
    .chart-container h3 {
      margin: 0 0 0.75rem 0;
      font-size: 1rem;
      font-weight: 600;
    }

    /* AG Grid container */
    .grid-container {
      background: #fff;
      border-radius: 8px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
      overflow: hidden;
    }

    /* Map container */
    #map-view {
      width: 100%;
      height: 450px;
      border-radius: 8px;
      overflow: hidden;
    }
  </style>
</head>
<body>

  <!-- ── HEADER ── -->
  <div class="dashboard-header">
    <div>
      <div class="subtitle">Tahoe Regional Planning Agency</div>
      <h1>Dashboard Title</h1>
    </div>
  </div>

  <!-- ── KPI CARDS ── -->
  <div class="kpi-row">
    <div class="kpi-card">
      <div class="kpi-value" id="kpi-1">—</div>
      <div class="kpi-label">Label 1</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-value" id="kpi-2">—</div>
      <div class="kpi-label">Label 2</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-value" id="kpi-3">—</div>
      <div class="kpi-label">Label 3</div>
    </div>
  </div>

  <!-- ── FILTERS (Calcite) ── -->
  <div class="dashboard-content">
    <calcite-label layout="inline">
      Filter
      <calcite-select id="filter-select">
        <calcite-option value="all" selected>All</calcite-option>
      </calcite-select>
    </calcite-label>

    <!-- ── TABS: Charts / Map / Table ── -->
    <calcite-tabs>
      <calcite-tab-nav slot="title-group">
        <calcite-tab-title selected>Charts</calcite-tab-title>
        <calcite-tab-title>Map</calcite-tab-title>
        <calcite-tab-title>Data Table</calcite-tab-title>
      </calcite-tab-nav>

      <!-- Charts tab -->
      <calcite-tab selected>
        <div class="chart-container">
          <h3>Chart Title</h3>
          <div id="plotly-chart"></div>
        </div>
      </calcite-tab>

      <!-- Map tab -->
      <calcite-tab>
        <div id="map-view"></div>
      </calcite-tab>

      <!-- Table tab -->
      <calcite-tab>
        <div class="grid-container">
          <div id="data-grid" style="height: 500px; width: 100%;"></div>
        </div>
      </calcite-tab>
    </calcite-tabs>
  </div>

  <script>
    // ── DATA LOADING ──
    // Fetch from TRPA ArcGIS REST services, CSV, or JSON
    async function fetchData(url, where = '1=1') {
      const params = new URLSearchParams({
        where,
        outFields: '*',
        f: 'json',
        returnGeometry: false
      });
      const resp = await fetch(`${url}/query?${params}`);
      const json = await resp.json();
      return json.features.map(f => f.attributes);
    }

    // ── PLOTLY CHARTS ──
    // Read BRAND_COLORS from the active brand skill
    const BRAND_COLORS = ['#007DC3', '#6EBE44', '#F16022', '#0B1F41'];
    // TRPA Agency: ['#0072CE', '#003B71', '#E87722', '#4A6118', '#9C3E27', '#B5A64C', '#7B6A8A', '#B4CBE8']
    // Tahoe Living: ['#5B7B6B', '#C4704B', '#6BA3BE', '#D4A843', '#3D6B4E', '#8B6F5E']

    function buildChart(data) {
      const trace = {
        x: data.map(d => d.category),
        y: data.map(d => d.value),
        type: 'bar',
        marker: { color: BRAND_COLORS[0] }
      };
      const layout = {
        font: { family: 'Lexend Deca, system-ui, sans-serif', color: '#0B1F41' },
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        margin: { t: 20, r: 20, b: 40, l: 50 },
        xaxis: { gridcolor: '#e8e8e8' },
        yaxis: { gridcolor: '#e8e8e8' },
        colorway: BRAND_COLORS
      };
      Plotly.newPlot('plotly-chart', [trace], layout, {
        responsive: true,
        displayModeBar: false
      });
    }

    // ── AG GRID ──
    function buildGrid(data, columns) {
      const gridOptions = {
        columnDefs: columns,
        rowData: data,
        defaultColDef: {
          sortable: true,
          filter: true,
          resizable: true
        },
        pagination: true,
        paginationPageSize: 25,
        domLayout: 'autoHeight'
      };
      const gridDiv = document.querySelector('#data-grid');
      agGrid.createGrid(gridDiv, gridOptions);
    }

    // ── ARCGIS MAP ──
    function buildMap() {
      require([
        "esri/Map",
        "esri/views/MapView",
        "esri/layers/FeatureLayer"
      ], function(Map, MapView, FeatureLayer) {
        const map = new Map({ basemap: "gray-vector" });
        const view = new MapView({
          container: "map-view",
          map: map,
          center: [-120.04, 39.09],  // Lake Tahoe center
          zoom: 10
        });
        // Add feature layers as needed
      });
    }

    // ── INIT ──
    document.addEventListener('DOMContentLoaded', async () => {
      // buildMap();
      // const data = await fetchData('SERVICE_URL/FeatureServer/0');
      // buildChart(data);
      // buildGrid(data, columnDefs);
    });
  </script>

</body>
</html>
```

---

## Coding Patterns

### Plotly.js conventions

- **Always set `displayModeBar: false`** — the floating toolbar clutters the dashboard.
- **Always set `responsive: true`** — charts must resize with the container.
- **Use `paper_bgcolor: 'transparent'` and `plot_bgcolor: 'transparent'`** — the chart container provides the white background.
- **Font:** Set `font.family` and `font.color` from the active brand skill.
- **Color cycle:** Use `colorway` from the active brand skill's color array. For sequential data, use tints of the brand primary. For categorical data, cycle through the full brand palette.
- **Number formatting:** Use `Plotly.d3.format` for consistent number display. Comma-separate thousands. No unnecessary decimals.
- **Symbols in charts:** Per TRPA style guide, symbols (%, $, °) are acceptable in charts and tables even though they should be spelled out in body text.
- **Annotations and titles:** Prefer chart section headings (via `<h3>` above the chart div) over Plotly's built-in title, which is harder to style consistently.

### AG Grid conventions

- **Always enable** `sortable`, `filter`, and `resizable` on all columns via `defaultColDef`.
- **Always enable pagination** with `paginationPageSize: 25`.
- **Use `domLayout: 'autoHeight'`** when the grid is inside a tab or scrollable container. Use a fixed-height div (`style="height: 500px"`) when the grid is the main content.
- **Include a CSV export button** using Calcite:
  ```html
  <calcite-button id="csv-export" icon-start="download" appearance="outline" scale="s">
    CSV
  </calcite-button>
  ```
  ```javascript
  document.getElementById('csv-export').addEventListener('click', () => {
    gridApi.exportDataAsCsv();
  });
  ```
- **Number columns:** Use `valueFormatter` to format numbers consistently:
  ```javascript
  { field: 'units', headerName: 'Units', valueFormatter: p => p.value?.toLocaleString() ?? '—' }
  ```

### Calcite component conventions

- **Page layout:** Use `calcite-shell` and `calcite-panel` for complex layouts, or the simple header/content pattern from the template for single-page dashboards.
- **Tabs:** Use `calcite-tabs` / `calcite-tab-nav` / `calcite-tab-title` / `calcite-tab` for switching between Charts, Map, and Data Table views.
- **Filters:** Use `calcite-select` for dropdowns, `calcite-slider` for ranges, `calcite-switch` for toggles.
- **Loading states:** Use `calcite-loader` while data is being fetched:
  ```html
  <calcite-loader id="loader" label="Loading data"></calcite-loader>
  ```
- **Alerts and notices:** Use `calcite-notice` for data source notes, update timestamps, and caveats:
  ```html
  <calcite-notice icon="information" scale="s" open>
    <span slot="message">Source: TRPA Permit System · Updated monthly</span>
  </calcite-notice>
  ```

### ArcGIS Maps conventions

- **Default basemap:** `"gray-vector"` for light mode. Use `"dark-gray-vector"` if the dashboard has a dark theme.
- **Default center:** `[-120.04, 39.09]` (Lake Tahoe center), zoom `10`.
- **Feature layers:** Load from TRPA ArcGIS Server REST endpoints. Always set a renderer with brand colors from the active brand skill.
- **Popups:** Configure popup templates on feature layers for click-to-inspect.
- **Legend and Home widgets:** Always include a `Legend` widget and a `Home` button for map resets.

### Data fetching patterns

Most TRPA data comes from ArcGIS REST services. Use this pattern for paginated queries:

```javascript
async function queryFeatureService(url, where = '1=1', outFields = '*') {
  const allFeatures = [];
  let offset = 0;
  const batchSize = 2000;
  
  while (true) {
    const params = new URLSearchParams({
      where,
      outFields,
      f: 'json',
      returnGeometry: false,
      resultOffset: offset,
      resultRecordCount: batchSize
    });
    const resp = await fetch(`${url}/query?${params}`);
    const json = await resp.json();
    if (!json.features || json.features.length === 0) break;
    allFeatures.push(...json.features.map(f => f.attributes));
    if (json.features.length < batchSize) break;
    offset += batchSize;
  }
  return allFeatures;
}
```

This handles pagination for services that limit results per query (typically 1,000 or 2,000 records).

---

## Reference: Common TRPA Service URLs

When building TRPA dashboards, spatial data is typically sourced from these ArcGIS Server endpoints:

- **Boundaries:** `https://maps.trpa.org/server/rest/services/Boundaries`
- **Planning:** `https://maps.trpa.org/server/rest/services/Planning`
- **Zoning:** `https://maps.trpa.org/server/rest/services/Zoning`
- **Transportation:** `https://maps.trpa.org/server/rest/services/Transportation_Planning`
- **Parcels:** `https://maps.trpa.org/server/rest/services/LocalPlan`

Always verify the specific FeatureServer/MapServer index for the layer you need.

---

## What NOT to Use

- **No Bootstrap, Tailwind, or Material UI** — Calcite is the design system.
- **No Chart.js, D3.js (directly), or Highcharts** — Plotly.js is the charting library.
- **No plain HTML `<table>` for data** — AG Grid handles all tabular display.
- **No Leaflet or Mapbox** — ArcGIS Maps SDK is the mapping library.
- **No React, Vue, or Angular** — dashboards are vanilla JS single-file HTML.
- **No npm, webpack, or build tools** — everything loads from CDN.

---

## Example: Allocation Tracking Dashboard

The Allocation Tracking dashboard at `trpa-agency.github.io/Reporting/html/allocation-tracking.html` is the reference implementation. It demonstrates:

- Dark header bar with TRPA branding and subtitle
- KPI summary cards (Total Authorized, Allocated, Available, Unassigned)
- Calcite tabs switching between Charts, Map, and Data Table views
- Calcite dropdowns for filtering by type, jurisdiction, and year
- Plotly.js stacked/grouped bar charts with brand colors
- ArcGIS MapView centered on Lake Tahoe with feature layer symbology
- AG Grid with sorting, filtering, pagination, and CSV export
- Live data fetched from TRPA ArcGIS REST services
- `calcite-notice` for data source attribution
- Responsive layout that works on desktop and tablet
