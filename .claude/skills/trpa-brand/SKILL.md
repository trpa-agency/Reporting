---
name: trpa-brand
description: "TRPA (Tahoe Regional Planning Agency) brand guidelines for trpa.gov websites, tools, and applications. Use this skill whenever building any web page, dashboard, tool, report, or application that carries the TRPA identity — anything on trpa.gov, laketahoeinfo.org, or internal TRPA tools. Covers TRPA Blue, the full agency color palette, typography, logo usage, page layout, writing style, and tone. Trigger on any mention of: TRPA, Tahoe Regional Planning Agency, trpa.gov, laketahoeinfo.org, TRPA branding, TRPA colors, TRPA blue, or any request to build something for the agency. NOTE: For EIP-specific (Environmental Improvement Program) projects, use the trpa-eip-brand skill instead or in addition."
---

# TRPA Brand Guidelines

Brand identity for the **Tahoe Regional Planning Agency (TRPA)** — the bi-state agency that oversees land use, transportation, and environmental planning for the Lake Tahoe Basin.

---

## Color Palette

### TRPA Blue (Primary Brand Color)

Both the TRPA agency logo and the EIP logo share the same blue: **PMS 285C**.

| Token         | Pantone  | Hex       | RGB            | CMYK              |
|---------------|----------|-----------|----------------|--------------------|
| `--trpa-blue` | PMS 285C | `#0072CE` | 0, 114, 206    | 100%, 45%, 0%, 19% |

This is the definitive TRPA blue. Use it for headers, nav bars, primary buttons, links, and any element that says "this is TRPA."

### Agency Color Palette

TRPA has an 8-color Pantone palette for use across agency materials. Approximate hex conversions:

| Token                  | Pantone  | Hex       | RGB             | Role                                      |
|------------------------|----------|-----------|-----------------|--------------------------------------------|
| `--trpa-blue`          | PMS 285C | `#0072CE` | 0, 114, 206     | Primary brand, headers, links, logo        |
| `--trpa-navy`          | PMS 541  | `#003B71` | 0, 59, 113      | Dark blue, text on light, deep headers     |
| `--trpa-earth`         | PMS 1395 | `#B47E00` | 180, 126, 0     | Earth/land, warm accent                    |
| `--trpa-forest`        | PMS 378  | `#4A6118` | 74, 97, 24      | Forest/vegetation, environmental data      |
| `--trpa-brick`         | PMS 484  | `#9C3E27` | 156, 62, 39     | Soil/earth, alert accent                   |
| `--trpa-olive`         | PMS 618  | `#B5A64C` | 181, 166, 76    | Muted warm, secondary backgrounds          |
| `--trpa-orange`        | PMS 138  | `#E87722` | 232, 119, 34    | Highlight, energy, call-to-action          |
| `--trpa-purple`        | PMS 667  | `#7B6A8A` | 123, 106, 138   | Tertiary, data category, diversity         |
| `--trpa-ice`           | PMS 2708 | `#B4CBE8` | 180, 203, 232   | Light accent, backgrounds, frost/water     |

### Usage guidance

- **TRPA Blue (`#0072CE`)** is the primary interactive color — links, buttons, active states, chart primary series.
- **PMS 541 Navy (`#003B71`)** is the dark anchor — use for body text, dark headers/footers, and as an alternative to black. Prefer this over pure `#000000`.
- **The earth tones (PMS 1395, 378, 484, 618)** reflect the Tahoe landscape and are used for thematic data categories (land, forest, soil, grassland) and secondary UI elements.
- **PMS 138 Orange** is the high-energy accent — use for warnings, highlights, and CTAs when blue isn't enough contrast.
- **PMS 667 Purple and PMS 2708 Ice** are tertiary — use sparingly in charts and data viz when you need more categories beyond the core palette.

### CSS variables

```css
:root {
  /* Primary */
  --trpa-blue:    #0072CE;
  --trpa-navy:    #003B71;

  /* Agency earth palette */
  --trpa-earth:   #B47E00;
  --trpa-forest:  #4A6118;
  --trpa-brick:   #9C3E27;
  --trpa-olive:   #B5A64C;
  --trpa-orange:  #E87722;
  --trpa-purple:  #7B6A8A;
  --trpa-ice:     #B4CBE8;

  /* Functional neutrals */
  --trpa-gray-dark:   #333333;
  --trpa-gray-medium: #666666;
  --trpa-gray-light:  #F5F5F5;
  --trpa-gray-border: #DDDDDD;
  --trpa-white:       #FFFFFF;
}
```

---

## Typography

### Agency documents: Calibri

Per the TRPA Style Guide (Feb 2025), all agency documents use:

- **Calibri, 11pt** — public documents, plans, reports (spacing 1.15, left-justified)
- **Calibri, 11pt** — staff summaries, presentations, letters (spacing 1.0, left-justified)
- **One space between sentences** — never double-space after a period

### Maps: Syntax

Maps use the **Syntax** font family for labels and annotation.

### Web: Open Sans

For web applications and dashboards, use **Open Sans** (the closest widely available web font to Calibri's proportions):

```html
<link href="https://fonts.googleapis.com/css2?family=Open+Sans:wght@300;400;600;700&display=swap" rel="stylesheet" />
```

```css
body {
  font-family: 'Open Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-weight: 400;
  font-size: 15px;
  line-height: 1.6;
  color: var(--trpa-navy);
}
```

---

## Logo

TRPA has **two distinct logo systems**:

### 1. TRPA Agency Logo (Lake silhouette)

A blue silhouette of Lake Tahoe with "TAHOE REGIONAL PLANNING AGENCY" stacked text. Available in `logos/` folder:

- `TRPALogo_COLOR.png` — Blue lake silhouette + dark text (for light backgrounds)
- `TRPALogo_WHITE.png` — All white (for dark/blue backgrounds)

The lake silhouette is rendered in **TRPA Blue (PMS 285C / `#0072CE`)**.

**Use this logo for:** trpa.gov pages, internal tools, agency reports, regulatory documents, and any context where TRPA acts in its governmental capacity.

### 2. EIP Logo (Mountain/water icon)

The "Lake Tahoe Environmental Improvement Program" logo with the mountain/water/chevron icon. Multiple variants available in `trpa-eip-brand/logos/`:

- **Primary:** Horizontal and Stacked, full color (navy "Lake" + blue "Tahoe" + mountain icon)
- **Tertiary (print):** Text-only "Lake Tahoe EIP"
- **Forest Health:** Sub-program logo with "Forest Health" subtitle

**Use the EIP logo for:** Environmental improvement dashboards, project trackers, and EIP-specific outreach. See `trpa-eip-brand` skill for details.

### Logo placement rules

- Place the logo in the top-left of headers and navigation bars.
- On TRPA Blue or dark backgrounds, always use the white variant.
- On white or light backgrounds, use the color variant.
- Do not stretch, recolor, add drop shadows, or place on busy photographic backgrounds.
- TRPA logo on maps: bottom-right corner (per style guide).

---

## Writing Style (from TRPA Style Guide, Feb 2025)

### Formatting rules

- **Oxford comma:** Always use it. "Red, blue, and green."
- **One space** between sentences. One space after colons. No spaces around em dashes.
- **Punctuation inside quotes:** "It is a fresh start."
- **No symbols in body text:** Write "50 percent" not "50%", "5 feet" not "5'" — symbols are OK in charts, graphs, and tables.
- **Bullets:** Periods at the end of complete sentences. No periods for fragments/lists.
- **Spell out 1–9**, use numerals for 10+. Spell out numbers at start of sentence.
- **Percentages:** Always figures, spell out "percent": "1 percent", "52 percent". Repeat with each figure.
- **Dollars:** Numerals with $ sign: "$150" not "150 dollars".
- **Dates:** Abbreviate Jan., Feb., Aug., Sept., Oct., Nov., Dec. with specific dates. No ordinal suffixes: "Jan. 1, 2026" not "January 1st."
- **Avoid unnecessary capitals.** Capitalize formal titles before names only.
- **Use gender-neutral language:** "they/them" over "he/she", "person" over "man", "human-made" over "man-made".

### Commonly used terms (correct forms)

- Lake Tahoe, the lake
- Lake Tahoe Basin, Tahoe Basin, the basin
- Lake Tahoe Region, Tahoe Region, the region
- North Shore, South Shore, East Shore, West Shore
- Sierra Nevada (the Sierra, not "Sierras")
- Environmental Improvement Program (EIP)
- best management practices (BMPs)
- Bi-State Compact
- stream environment zone (SEZ)
- vehicle miles traveled (VMT)
- residential unit, commercial floor area (CFA), tourist accommodation unit (TAU)
- Regional Plan, Regional Transportation Plan (capitalize formal plan names)
- town center (lowercase), area plan (lowercase unless formal name)

---

## Chart & Visualization Colors

### Default chart color sequence

```javascript
const TRPA_COLORS = [
  '#0072CE',  // TRPA Blue (primary)
  '#003B71',  // Navy
  '#E87722',  // Orange
  '#4A6118',  // Forest
  '#9C3E27',  // Brick
  '#B5A64C',  // Olive
  '#7B6A8A',  // Purple
  '#B4CBE8',  // Ice
];
```

### Plotly.js default layout

```javascript
const TRPA_LAYOUT = {
  font: {
    family: 'Open Sans, system-ui, sans-serif',
    color: '#003B71',
    size: 13
  },
  paper_bgcolor: 'transparent',
  plot_bgcolor: 'transparent',
  margin: { t: 30, r: 20, b: 40, l: 50 },
  xaxis: { gridcolor: '#e8e8e8', linecolor: '#DDDDDD' },
  yaxis: { gridcolor: '#e8e8e8', linecolor: '#DDDDDD' },
  colorway: ['#0072CE', '#003B71', '#E87722', '#4A6118', '#9C3E27', '#B5A64C', '#7B6A8A', '#B4CBE8'],
  hoverlabel: { font: { family: 'Open Sans, sans-serif' } }
};
```

---

## TRPA Ecosystem of Sites

| Site                               | Purpose                              |
|------------------------------------|--------------------------------------|
| `trpa.gov`                         | Main agency website (WordPress)      |
| `laketahoeinfo.org`                | Data hub — dashboards and trackers   |
| `eip.laketahoeinfo.org`            | EIP Project Tracker                  |
| `thresholds.laketahoeinfo.org`     | Threshold evaluation dashboard       |
| `parcels.laketahoeinfo.org`        | Parcel & permit records              |
| `clarity.laketahoeinfo.org`        | Lake Clarity Tracker                 |
| `monitoring.laketahoeinfo.org`     | Monitoring Dashboard                 |
| `transportation.laketahoeinfo.org` | Transportation Tracker               |
| `climate.laketahoeinfo.org`        | Climate Resilience Dashboard         |
| `stormwater.laketahoeinfo.org`     | Stormwater Tools                     |
| `maps.trpa.org`                    | ArcGIS Server (REST services)        |
| `gis.trpa.org`                     | GIS web apps and map viewers         |
| `tahoeliving.org`                  | Cultivating Community housing project|

---

## Relationship to Sub-Brands

| Context                                  | Brand skill to use        |
|------------------------------------------|---------------------------|
| General TRPA agency tools                | **`trpa-brand`** (this)   |
| EIP environmental projects               | `trpa-eip-brand`          |
| Housing / Tahoe Living / Cultivating Community | `tahoe-living-brand` |
| Dashboard tech stack (always pair with)  | `trpa-dashboard-stack`    |

All sub-brands share **TRPA Blue (PMS 285C / `#0072CE`)** as a connecting thread.
