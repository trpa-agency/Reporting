---
name: tahoe-living-brand
description: "Tahoe Living / Cultivating Community, Conserving the Basin brand guidelines. Use this skill when building any web page, dashboard, tool, or visualization for the Tahoe Living housing initiative, the Cultivating Community project, or any TRPA housing-related work. This brand has a warm, community-focused, equity-centered visual identity — distinct from the institutional TRPA blue. Trigger on any mention of: Tahoe Living, Cultivating Community, Conserving the Basin, tahoeliving.org, TRPA housing, housing assessment, growth management, workforce housing, affordable housing at Tahoe, community engagement housing, or housing equity Tahoe."
---

# Tahoe Living — Cultivating Community, Conserving the Basin

Brand guidelines for **Tahoe Living**, TRPA's community-facing housing and growth management initiative. The site lives at [tahoeliving.org](https://www.tahoeliving.org/) and represents a warmer, more approachable identity than the institutional TRPA brand — designed to welcome community members, renters, workers, and historically underrepresented groups into the planning conversation.

This brand is used for housing dashboards, community engagement tools, survey results, housing needs data, growth management visualizations, and the Environmental Impact Statement materials.

---

## Brand Personality

Tahoe Living's visual identity is **warm, grounded, and inclusive**. Where the TRPA agency brand says "government authority," this brand says "your neighbor who cares about your housing situation." It uses earth tones, soft greens, and natural textures to evoke mountain community, environmental stewardship, and approachability.

Key qualities:
- **Welcoming** — not institutional; designed for community audiences, not regulators
- **Equity-centered** — visuals and language are inclusive of BIPOC communities, renters, and low-income households
- **Environmental** — grounded in the land; colors come from the Tahoe landscape (pine, sage, earth, sky)
- **Hopeful** — this is about solutions, not just problems

---

## Color Palette

### Primary Colors

| Token                    | Hex       | RGB             | Usage                                          |
|--------------------------|-----------|-----------------|------------------------------------------------|
| `--tl-sage`              | `#5B7B6B` | 91, 123, 107    | Primary brand, nav bar, headers, links         |
| `--tl-forest`            | `#2D5A3D` | 45, 90, 61      | Dark accent, hover states, footer background   |
| `--tl-cream`             | `#F7F3ED` | 247, 243, 237   | Page background, warm white                    |
| `--tl-warm-white`        | `#FFFFFF` | 255, 255, 255   | Card surfaces, content areas                   |

### Accent Colors

| Token                    | Hex       | RGB             | Usage                                          |
|--------------------------|-----------|-----------------|------------------------------------------------|
| `--tl-terracotta`        | `#C4704B` | 196, 112, 75    | CTAs, accent buttons, highlights, warm pop     |
| `--tl-gold`              | `#D4A843` | 212, 168, 67    | Secondary accent, badges, callout borders      |
| `--tl-sky`               | `#6BA3BE` | 107, 163, 190   | Info states, water/lake references, links       |
| `--tl-pine`              | `#3D6B4E` | 61, 107, 78     | Environmental indicators, positive/nature       |

### Neutral Colors

| Token                    | Hex       | RGB             | Usage                                          |
|--------------------------|-----------|-----------------|------------------------------------------------|
| `--tl-text-primary`      | `#2C2C2C` | 44, 44, 44      | Body text, headings                            |
| `--tl-text-secondary`    | `#5A5A5A` | 90, 90, 90      | Captions, secondary info, timestamps           |
| `--tl-text-muted`        | `#8A8A8A` | 138, 138, 138   | Placeholder text, disabled states              |
| `--tl-border`            | `#E0DDD7` | 224, 221, 215   | Borders, dividers (warm-tinted, not pure gray) |
| `--tl-bg-section`        | `#EDE9E1` | 237, 233, 225   | Alternating section backgrounds                |

### CSS variables

```css
:root {
  /* Primary */
  --tl-sage:          #5B7B6B;
  --tl-forest:        #2D5A3D;
  --tl-cream:         #F7F3ED;
  --tl-warm-white:    #FFFFFF;

  /* Accents */
  --tl-terracotta:    #C4704B;
  --tl-gold:          #D4A843;
  --tl-sky:           #6BA3BE;
  --tl-pine:          #3D6B4E;

  /* Neutrals */
  --tl-text-primary:  #2C2C2C;
  --tl-text-secondary:#5A5A5A;
  --tl-text-muted:    #8A8A8A;
  --tl-border:        #E0DDD7;
  --tl-bg-section:    #EDE9E1;
}
```

### Important: No pure grays

This brand avoids cold, pure grays (`#ccc`, `#999`, `#f5f5f5`). All neutrals should have a **warm undertone** — tinted toward cream/sand. The background is `--tl-cream` (`#F7F3ED`), not `#F5F5F5`. Borders are `--tl-border` (`#E0DDD7`), not `#DDDDDD`. This warmth is a core part of the brand's welcoming feel.

---

## Typography

### Primary typeface: Montserrat

Tahoe Living uses **Montserrat** — a geometric sans-serif that is modern, clean, and more characterful than Open Sans. It conveys approachability and contemporary civic design.

```html
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700&display=swap" rel="stylesheet" />
```

```css
body {
  font-family: 'Montserrat', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-weight: 400;
  font-size: 16px;
  line-height: 1.7;
  color: var(--tl-text-primary);
  background: var(--tl-cream);
}
```

### Type scale

| Element         | Weight | Size      | Notes                                    |
|-----------------|--------|-----------|------------------------------------------|
| Hero heading    | 700    | 2.5rem    | Large section openers, page titles       |
| Section h2      | 600    | 1.75rem   | Section headings                         |
| Card h3         | 600    | 1.2rem    | Card titles, chart titles                |
| Overline/label  | 500    | 0.75rem   | Section labels ("WHO WE ARE"), uppercase  |
| Body            | 400    | 1rem      | Default prose                            |
| Caption         | 400    | 0.85rem   | Source notes, footnotes                  |
| KPI value       | 700    | 2.25rem   | Large metric numbers                     |
| KPI label       | 400    | 0.85rem   | Descriptor below KPI values              |

### Overline pattern

Tahoe Living uses small uppercase labels above section headings to provide context. This is a signature pattern:

```css
.overline {
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--tl-sage);
  margin-bottom: 0.5rem;
}
```

```html
<p class="overline">Who we are</p>
<h2>What is "Cultivating Community, Conserving the Basin?"</h2>
```

---

## Logo

Tahoe Living uses a custom wordmark logo — a stylized outline of Lake Tahoe (the lake shape) rendered as a continuous line, paired with "Tahoe Living" text.

**Logo placement:**
- Top-left of navigation, linking to tahoeliving.org homepage
- The logo is an SVG line-drawing style — it is not the TRPA institutional logo
- On sage/forest/dark backgrounds, use a white version
- On cream/light backgrounds, use the dark (forest green) version

**TRPA co-branding:**
- The TRPA full logo appears in the **footer only**, not in the header
- Tahoe Living is the lead brand in the header; TRPA is the authority in the footer
- This deliberate separation keeps the community-facing feel in the navigation while maintaining institutional credibility at the page bottom

---

## Page Layout Patterns

### Header / Navigation

Tahoe Living uses a clean, minimal sticky nav with the logo on the left and horizontal nav links.

```css
.tl-nav {
  background: var(--tl-warm-white);
  border-bottom: 1px solid var(--tl-border);
  padding: 0.75rem 2rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 100;
}
.tl-nav a {
  color: var(--tl-text-primary);
  text-decoration: none;
  font-weight: 500;
  font-size: 0.9rem;
}
.tl-nav a:hover {
  color: var(--tl-sage);
}
```

### Hero sections

Full-width hero sections with landscape photography and overlaid text are a core pattern:

```css
.tl-hero {
  position: relative;
  background-size: cover;
  background-position: center;
  min-height: 400px;
  display: flex;
  align-items: flex-end;
  padding: 3rem 2rem;
}
.tl-hero::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(to top, rgba(45,90,61,0.8) 0%, transparent 60%);
}
.tl-hero h1 {
  position: relative;
  z-index: 1;
  color: #fff;
  font-size: 2.5rem;
  font-weight: 700;
  max-width: 700px;
}
```

### Content sections with alternating backgrounds

Alternate between `--tl-cream` and `--tl-bg-section` to visually separate content blocks:

```css
.section { padding: 4rem 2rem; }
.section--cream { background: var(--tl-cream); }
.section--sand { background: var(--tl-bg-section); }
```

### Cards

Warm white cards with rounded corners and subtle warm shadow:

```css
.tl-card {
  background: var(--tl-warm-white);
  border-radius: 12px;
  padding: 1.5rem;
  box-shadow: 0 2px 8px rgba(44,44,44,0.06);
  border: 1px solid var(--tl-border);
}
```

Note: Border radius is `12px` (softer/rounder than TRPA's `6px`). This contributes to the warmer, less institutional feel.

### KPI cards

```css
.tl-kpi {
  background: var(--tl-warm-white);
  border-radius: 12px;
  padding: 1.5rem;
  border-left: 4px solid var(--tl-sage);
  box-shadow: 0 2px 8px rgba(44,44,44,0.06);
}
.tl-kpi .value {
  font-size: 2.25rem;
  font-weight: 700;
  color: var(--tl-forest);
}
.tl-kpi .label {
  font-size: 0.85rem;
  color: var(--tl-text-secondary);
  margin-top: 0.25rem;
}
```

### Buttons

```css
/* Primary — terracotta CTA */
.tl-btn-primary {
  background: var(--tl-terracotta);
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 0.75rem 1.5rem;
  font-family: 'Montserrat', sans-serif;
  font-weight: 600;
  font-size: 0.9rem;
  cursor: pointer;
  transition: background 0.2s;
}
.tl-btn-primary:hover { background: #A85D3D; }

/* Secondary — outlined sage */
.tl-btn-secondary {
  background: transparent;
  color: var(--tl-sage);
  border: 2px solid var(--tl-sage);
  border-radius: 8px;
  padding: 0.65rem 1.5rem;
  font-family: 'Montserrat', sans-serif;
  font-weight: 600;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.2s;
}
.tl-btn-secondary:hover {
  background: var(--tl-sage);
  color: #fff;
}
```

### Footer

```css
.tl-footer {
  background: var(--tl-forest);
  color: rgba(255,255,255,0.85);
  padding: 2.5rem 2rem;
  font-size: 0.85rem;
}
.tl-footer a { color: rgba(255,255,255,0.9); }
```

The footer includes the TRPA logo (white variant), mailing address, social media links, and partner attribution.

---

## Chart & Data Visualization Colors

### Default chart color sequence

```javascript
const TL_COLORS = [
  '#5B7B6B',  // Sage (primary series)
  '#C4704B',  // Terracotta (contrast/accent)
  '#6BA3BE',  // Sky
  '#D4A843',  // Gold
  '#3D6B4E',  // Pine
  '#8B6F5E',  // Warm brown
  '#7B8E9A',  // Muted blue-gray
  '#2D5A3D',  // Forest (use sparingly — very dark)
];
```

### Plotly.js layout for Tahoe Living

```javascript
const TL_LAYOUT = {
  font: {
    family: 'Montserrat, system-ui, sans-serif',
    color: '#2C2C2C',
    size: 13
  },
  paper_bgcolor: 'transparent',
  plot_bgcolor: 'transparent',
  margin: { t: 30, r: 20, b: 40, l: 50 },
  xaxis: { gridcolor: '#E0DDD7', linecolor: '#E0DDD7' },
  yaxis: { gridcolor: '#E0DDD7', linecolor: '#E0DDD7' },
  colorway: ['#5B7B6B', '#C4704B', '#6BA3BE', '#D4A843', '#3D6B4E', '#8B6F5E'],
  hoverlabel: { font: { family: 'Montserrat, sans-serif' } }
};
```

### Housing-specific data patterns

Housing dashboards frequently display income-level and equity data. Use these semantic mappings:

| Category                   | Color           | Hex       |
|---------------------------|-----------------|-----------|
| Very low income (≤30% AMI) | Terracotta      | `#C4704B` |
| Low income (30–50% AMI)   | Gold            | `#D4A843` |
| Moderate income (50–80% AMI)| Sky            | `#6BA3BE` |
| Above moderate (80–120% AMI)| Sage           | `#5B7B6B` |
| Market rate (>120% AMI)   | Muted gray      | `#8A8A8A` |

For housing type breakdowns:

| Type                | Color      | Hex       |
|--------------------|------------|-----------|
| Single-family      | Sage       | `#5B7B6B` |
| Multi-family       | Sky        | `#6BA3BE` |
| ADU                | Gold       | `#D4A843` |
| Tourist/Seasonal   | Muted gray | `#8A8A8A` |
| Affordable/Deed-restricted | Pine | `#3D6B4E` |

---

## Photography & Imagery

Tahoe Living uses warm, people-centered photography showing:

- Diverse community members (families, workers, neighbors)
- Tahoe neighborhoods and streetscapes (not pristine wilderness — this is about *living* in Tahoe)
- Construction and housing (new builds, ADUs, multi-family)
- Community meetings and engagement events

Photography is typically displayed full-bleed or in large rounded containers, with the forest-green gradient overlay for text readability.

**Avoid:** Stock-photo-looking imagery, exclusively lakefront/tourism shots (this is a housing project, not a tourism site), images that only show affluent settings.

---

## Bilingual / Accessibility Notes

Tahoe Living content is produced in **English and Spanish**. When building tools:

- Include language toggle or bilingual labels where appropriate
- Ensure all chart labels and data table headers can accommodate Spanish translations (which tend to be ~20% longer than English)
- Use ARIA labels on interactive elements
- Ensure color contrast meets WCAG AA standards — the warm palette can trend light, so test body text against cream backgrounds carefully

---

## Tone & Voice

Tahoe Living's written tone is:

- **Conversational and direct** — not bureaucratic; "we" and "you" language
- **Community-oriented** — speak to people as neighbors, not as permit applicants
- **Equity-aware** — acknowledge housing disparities without being clinical about them
- **Action-oriented** — emphasize participation: "Get involved," "Sign up," "Share your experience"
- **Bilingual-friendly** — keep sentences clear and translatable; avoid idioms

Example labels:
- ✓ "Housing units needed" (clear, direct)
- ✗ "Projected residential unit demand allocation" (too institutional)
- ✓ "People who rent" (human)
- ✗ "Renter-occupied households" (census-speak)

---

## Relationship to Other TRPA Brands

| Context                          | Brand to use          |
|----------------------------------|-----------------------|
| General TRPA agency tools        | `trpa-brand`          |
| EIP environmental projects       | `trpa-eip-brand`      |
| Housing / Tahoe Living / community engagement | **`tahoe-living-brand`** (this skill) |
| Dashboard tech stack (always)    | `trpa-dashboard-stack` |

Tahoe Living is a **sub-brand** of TRPA. The TRPA logo appears in the footer for credibility, but the header, colors, and feel are entirely Tahoe Living. When building dashboards for housing data that will live on tahoeliving.org or be embedded in Tahoe Living materials, use this brand. When building the same housing data for an internal TRPA report or trpa.gov page, use `trpa-brand` instead.
