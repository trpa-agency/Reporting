---
name: trpa-brand
description: "TRPA (Tahoe Regional Planning Agency) brand guidelines for trpa.gov websites, tools, and applications. Use this skill whenever building any web page, dashboard, tool, report, or application that carries the TRPA identity — anything on trpa.gov, laketahoeinfo.org, or internal TRPA tools. Covers TRPA Blue, the full color palette, typography, logo usage, page layout, and tone. Trigger on any mention of: TRPA, Tahoe Regional Planning Agency, trpa.gov, laketahoeinfo.org, TRPA branding, TRPA colors, TRPA blue, or any request to build something for the agency. NOTE: This is the general TRPA agency brand. For EIP-specific (Environmental Improvement Program) projects, use the trpa-eip-brand skill instead or in addition."
---

# TRPA Brand Guidelines

Brand identity for the **Tahoe Regional Planning Agency (TRPA)** — the bi-state agency that oversees land use, transportation, and environmental planning for the Lake Tahoe Basin.

These guidelines apply to all tools, dashboards, and web pages built under the TRPA identity, including trpa.gov, laketahoeinfo.org subdomains, and internal agency applications.

---

## Color Palette

### Primary: TRPA Blue

TRPA Blue is the agency's signature color. It anchors the header, navigation, links, primary buttons, and any element that says "this is TRPA."

| Token           | Hex       | RGB             | Usage                                      |
|-----------------|-----------|-----------------|---------------------------------------------|
| `--trpa-blue`   | `#003E7E` | 0, 62, 126      | Headers, nav bars, primary buttons, links   |

This is a deep, authoritative blue — darker and more saturated than the EIP blue (`#007DC3`). It reflects the agency's regulatory and governmental role. When in doubt, use TRPA Blue.

### Full Palette

| Token                  | Hex       | RGB             | Role                                         |
|------------------------|-----------|-----------------|----------------------------------------------|
| `--trpa-blue`          | `#003E7E` | 0, 62, 126      | Primary brand, headers, nav, links           |
| `--trpa-blue-dark`     | `#002B56` | 0, 43, 86       | Hover states, footer background, dark UI     |
| `--trpa-blue-light`    | `#E8F1F8` | 232, 241, 248   | Light backgrounds, table row striping        |
| `--trpa-sky`           | `#4A90C4` | 74, 144, 196    | Secondary buttons, chart accent, info states |
| `--trpa-teal`          | `#2A7F62` | 42, 127, 98     | Success states, environmental/positive       |
| `--trpa-green`         | `#4CAF50` | 76, 175, 80     | Progress bars, on-track indicators           |
| `--trpa-amber`         | `#F5A623` | 245, 166, 35    | Warnings, caution, at-risk indicators        |
| `--trpa-red`           | `#D32F2F` | 211, 47, 47     | Errors, off-target, critical alerts          |
| `--trpa-gray-dark`     | `#333333` | 51, 51, 51      | Body text                                    |
| `--trpa-gray-medium`   | `#666666` | 102, 102, 102   | Secondary text, captions                     |
| `--trpa-gray-light`    | `#F5F5F5` | 245, 245, 245   | Page backgrounds, card backgrounds           |
| `--trpa-gray-border`   | `#DDDDDD` | 221, 221, 221   | Borders, dividers, table lines               |
| `--trpa-white`         | `#FFFFFF` | 255, 255, 255   | Card surfaces, content backgrounds           |

### Status color mapping

Use these consistently across all dashboards and tools:

- **On track / Achieved / Good** → `--trpa-green` (`#4CAF50`)
- **Caution / Somewhat off / Warning** → `--trpa-amber` (`#F5A623`)
- **Off track / Not achieved / Critical** → `--trpa-red` (`#D32F2F`)
- **Informational / Neutral / In progress** → `--trpa-sky` (`#4A90C4`)

### CSS variables

```css
:root {
  /* Primary */
  --trpa-blue:         #003E7E;
  --trpa-blue-dark:    #002B56;
  --trpa-blue-light:   #E8F1F8;
  --trpa-sky:          #4A90C4;

  /* Semantic */
  --trpa-teal:         #2A7F62;
  --trpa-green:        #4CAF50;
  --trpa-amber:        #F5A623;
  --trpa-red:          #D32F2F;

  /* Neutral */
  --trpa-gray-dark:    #333333;
  --trpa-gray-medium:  #666666;
  --trpa-gray-light:   #F5F5F5;
  --trpa-gray-border:  #DDDDDD;
  --trpa-white:        #FFFFFF;
}
```

---

## Typography

### Primary typeface: Open Sans

TRPA uses **Open Sans** across trpa.gov and its web tools. It is clean, highly legible, and available from Google Fonts.

```html
<link href="https://fonts.googleapis.com/css2?family=Open+Sans:wght@300;400;600;700&display=swap" rel="stylesheet" />
```

```css
body {
  font-family: 'Open Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-weight: 400;
  font-size: 15px;
  line-height: 1.6;
  color: var(--trpa-gray-dark);
}
```

### Type scale

| Element      | Weight | Size     | Usage                                    |
|-------------|--------|----------|------------------------------------------|
| Page title  | 700    | 1.75rem  | Dashboard/page main heading              |
| Section h2  | 600    | 1.35rem  | Section headings                         |
| Card h3     | 600    | 1.1rem   | Card titles, chart titles                |
| Body        | 400    | 0.9375rem (15px) | Default prose, table cells        |
| Caption     | 400    | 0.8rem   | Source notes, footnotes, timestamps      |
| KPI value   | 700    | 2rem     | Large metric numbers in summary cards    |
| KPI label   | 400    | 0.8rem   | Descriptor below KPI values              |

### When to use Lexend Deca

If the project is **EIP-specific**, pair this TRPA brand skill with the `trpa-eip-brand` skill and use **Lexend Deca Bold** for headings. For general TRPA agency work, stick with Open Sans.

---

## Logo

The TRPA logo is a horizontal wordmark featuring a stylized mountain/water icon followed by "Tahoe Regional Planning Agency" text. It exists in two variants:

- **Dark logo** (navy blue on light backgrounds): `https://www.trpa.gov/wp-content/uploads/2020/04/TRPA_logo.png`
- **White logo** (white on dark backgrounds): `https://www.trpa.gov/wp-content/uploads/2020/04/TRPA_logo_white.png`

### Logo placement rules

- Place the logo in the top-left of headers and navigation bars.
- On TRPA Blue or dark backgrounds, always use the white logo variant.
- On white or light backgrounds, use the dark logo variant.
- Maintain clear space around the logo — at minimum, the height of the icon portion on all sides.
- Do not stretch, recolor, add drop shadows, or place the logo on busy photographic backgrounds without a solid-color backing.
- Minimum display width: 160px for the full horizontal logo.

### Footer attribution

All TRPA tools should include a footer with TRPA attribution. For laketahoeinfo.org tools, include partner logos as appropriate. Minimal footer example:

```html
<footer style="background: var(--trpa-blue-dark); color: rgba(255,255,255,0.8); padding: 1.5rem 2rem; font-size: 0.8rem;">
  <img src="https://www.trpa.gov/wp-content/uploads/2020/04/TRPA_logo_white.png" 
       alt="TRPA" height="36" style="margin-bottom: 0.5rem;" />
  <div>Tahoe Regional Planning Agency · <a href="https://www.trpa.gov" style="color: rgba(255,255,255,0.9);">trpa.gov</a></div>
</footer>
```

---

## Page Layout Patterns

### Standard TRPA header

```css
.trpa-header {
  background: var(--trpa-blue);
  color: #fff;
  padding: 0.75rem 2rem;
  display: flex;
  align-items: center;
  gap: 1.5rem;
}
.trpa-header img { height: 40px; }
.trpa-header .page-title {
  font-size: 1.25rem;
  font-weight: 600;
}
```

```html
<header class="trpa-header">
  <img src="https://www.trpa.gov/wp-content/uploads/2020/04/TRPA_logo_white.png" alt="TRPA" />
  <span class="page-title">Tool or Page Title</span>
</header>
```

### Content cards

White cards with subtle shadow on light gray backgrounds:

```css
.card {
  background: var(--trpa-white);
  border-radius: 6px;
  padding: 1.25rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  margin-bottom: 1rem;
}
```

### KPI summary row

```css
.kpi-row {
  display: flex;
  gap: 1rem;
  padding: 1.5rem 2rem;
  flex-wrap: wrap;
}
.kpi-card {
  background: var(--trpa-white);
  border-radius: 6px;
  padding: 1.25rem 1.5rem;
  flex: 1;
  min-width: 160px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  border-left: 4px solid var(--trpa-blue);
}
```

Note: TRPA uses a **left border accent** on KPI cards (vs. the EIP brand which uses a top border). This is a subtle but intentional distinction.

---

## Chart & Data Visualization Colors

### Default chart color sequence

When building Plotly.js, Chart.js, or any visualization:

```javascript
const TRPA_COLORS = [
  '#003E7E',  // TRPA Blue (primary series)
  '#4A90C4',  // Sky (secondary)
  '#2A7F62',  // Teal
  '#F5A623',  // Amber
  '#D32F2F',  // Red
  '#7B8D97',  // Muted gray-blue
  '#5C6BC0',  // Indigo accent
  '#8D6E63',  // Warm brown
];
```

### Plotly.js default layout

```javascript
const TRPA_LAYOUT = {
  font: {
    family: 'Open Sans, system-ui, sans-serif',
    color: '#333333',
    size: 13
  },
  paper_bgcolor: 'transparent',
  plot_bgcolor: 'transparent',
  margin: { t: 30, r: 20, b: 40, l: 50 },
  xaxis: { gridcolor: '#e8e8e8', linecolor: '#DDDDDD' },
  yaxis: { gridcolor: '#e8e8e8', linecolor: '#DDDDDD' },
  colorway: ['#003E7E', '#4A90C4', '#2A7F62', '#F5A623', '#D32F2F', '#7B8D97'],
  hoverlabel: { font: { family: 'Open Sans, sans-serif' } }
};
```

### Threshold/status visualizations

Many TRPA dashboards display environmental threshold status. Always use this mapping:

| Status            | Color   | Hex       | Icon/symbol    |
|-------------------|---------|-----------|----------------|
| At or Above Target| Green   | `#4CAF50` | ● or ✓         |
| Somewhat Below    | Amber   | `#F5A623` | ◐ or ⚠         |
| Below Target      | Red     | `#D32F2F` | ○ or ✗         |
| Insufficient Data | Gray    | `#999999` | — or ?         |

---

## TRPA Ecosystem of Sites

When building tools, be aware of the broader TRPA web ecosystem:

| Site                         | Purpose                                    |
|------------------------------|--------------------------------------------|
| `trpa.gov`                   | Main agency website (WordPress)            |
| `laketahoeinfo.org`          | Data hub — dashboards and trackers         |
| `eip.laketahoeinfo.org`      | EIP Project Tracker                        |
| `thresholds.laketahoeinfo.org` | Threshold evaluation dashboard           |
| `parcels.laketahoeinfo.org`  | Parcel & permit records                    |
| `clarity.laketahoeinfo.org`  | Lake Clarity Tracker                       |
| `monitoring.laketahoeinfo.org`| Monitoring Dashboard                      |
| `transportation.laketahoeinfo.org` | Transportation Tracker              |
| `climate.laketahoeinfo.org`  | Climate Resilience Dashboard               |
| `stormwater.laketahoeinfo.org`| Stormwater Tools                          |
| `maps.trpa.org`              | ArcGIS Server (REST services)              |
| `gis.trpa.org`               | GIS web apps and map viewers               |

New tools should feel at home in this ecosystem. Match the visual language even if they're standalone HTML pages hosted on GitHub Pages.

---

## Tone & Voice

TRPA is a government planning agency. Written content in tools and dashboards should be:

- **Clear and factual** — no marketing language, no hype
- **Concise** — government audiences value brevity
- **Neutral and authoritative** — present data without editorializing
- **Accessible** — avoid jargon where possible; define acronyms on first use
- **Action-oriented** — label things by what they represent ("Units Allocated") not technical internals ("RES_UNITS_INT")

Field labels, chart titles, and KPI cards should use **sentence case** (e.g., "Allocated to development") not UPPER CASE or Title Case, except for proper nouns and acronyms.

---

## Relationship to EIP Brand

The **EIP (Environmental Improvement Program)** has its own distinct brand identity (green, blue, orange palette with Lexend Deca typography). When building:

- **General TRPA tools** → Use this `trpa-brand` skill (TRPA Blue, Open Sans)
- **EIP-specific tools** → Use the `trpa-eip-brand` skill (EIP colors, Lexend Deca)
- **Tools that span both** → Use TRPA brand as the structural shell (header, nav, footer) and EIP brand colors within the content area for EIP-specific data visualizations

Both skills can be loaded together. The EIP brand is a sub-brand within the TRPA family — it should feel related but visually distinct.
