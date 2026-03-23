---
name: trpa-eip-brand
description: "Lake Tahoe EIP (Environmental Improvement Program) brand guidelines. Use this skill whenever building any UI, web app, dashboard, report, presentation, or visual output for TRPA's EIP program or its sub-programs (Forest Health, Aquatic Invasive Species, Stormwater). Apply these colors, fonts, and styling rules to all EIP-related artifacts. Trigger on any mention of EIP, Lake Tahoe EIP, Environmental Improvement Program, Forest Health, TRPA branding for environmental projects, or when the user asks to style something in EIP brand colors."
---

# Lake Tahoe EIP — Brand Guidelines

Official brand guidelines for the **Lake Tahoe Environmental Improvement Program (EIP)**, sourced from the TRPA/BLKDOG brand guidelines.

---

## Color Palette

Four brand colors defined by Pantone. Use the hex values for all web/app work.

| Name       | Role      | Pantone  | CMYK         | RGB           | Hex       |
|------------|-----------|----------|--------------|---------------|-----------|
| EIP Green  | Primary   | P 802 C  | 61-0-100-0   | 110, 190, 68  | `#6EBE44` |
| EIP Blue   | Primary   | P 285 C  | 89-43-0-0    | 0, 125, 195   | `#007DC3` |
| EIP Orange | Accent    | P 1505 C | 0-77-100-0   | 241, 96, 34   | `#F16022` |
| EIP Navy   | Dark/Text | P 282 C  | 100-88-41-50 | 11, 31, 65    | `#0B1F41` |

**Note:** EIP Blue (PMS 285 / `#007DC3`) and TRPA Blue (PMS 285C / `#0072CE`) are variants of the same Pantone swatch. Use `#007DC3` in EIP contexts and `#0072CE` in agency contexts — the difference is subtle and intentional.

### Usage guidance

- **EIP Green (`#6EBE44`)** — Positive indicators, success states, environmental/nature themes, primary CTAs.
- **EIP Blue (`#007DC3`)** — Links, interactive elements, headers, water/lake data visualizations.
- **EIP Orange (`#F16022`)** — Sparingly as accent for highlights, warnings, callouts, secondary CTAs.
- **EIP Navy (`#0B1F41`)** — Body text, dark backgrounds, navigation bars, footers. Prefer over pure black.

### CSS variables

```css
:root {
  --eip-green:  #6EBE44;
  --eip-blue:   #007DC3;
  --eip-orange: #F16022;
  --eip-navy:   #0B1F41;

  /* Derived tints for UI use */
  --eip-green-light:  #E8F5E0;
  --eip-blue-light:   #E0F0FA;
  --eip-orange-light: #FDE8DC;
  --eip-navy-light:   #E6E8EC;
}
```

---

## Typography

| Role               | Typeface             | Usage                                    |
|--------------------|----------------------|------------------------------------------|
| Primary typeface   | **Lexend Deca Bold** | Headings, titles, hero text, display type |
| Secondary typeface | **Calder Dark**      | Labels, section headers in all-caps      |

### Web font loading

```html
<link href="https://fonts.googleapis.com/css2?family=Lexend+Deca:wght@400;700&display=swap" rel="stylesheet">
```

Calder Dark is a commercial font (Letters from Sweden). If unavailable, substitute **Montserrat Bold** or **Raleway Bold** in all-caps with `letter-spacing: 0.1em`.

### Font stack

```css
/* Primary — headings */
font-family: 'Lexend Deca', 'Lexend', system-ui, sans-serif;

/* Secondary — labels, section markers */
font-family: 'Calder Dark', 'Montserrat', 'Raleway', sans-serif;
text-transform: uppercase;
letter-spacing: 0.05em;
```

---

## Logo System

The EIP logo features a stylized mountain-and-water icon with layered peaks (navy mountains, blue water, orange chevron) plus "Lake Tahoe" and "Environmental Improvement Program" text.

### Available variants (in `logos/` folder)

| File | Description | Use when |
|------|-------------|----------|
| `EIP-Primary-Horizontal.png` | Full color, horizontal layout | Default — headers, wide spaces |
| `EIP-Primary-Stacked.png` | Full color, stacked/centered | Square spaces, mobile, centered layouts |
| `EIP-Tertiary-Print.png` | Text-only "Lake Tahoe EIP" | Tight spaces, inline references |
| `ForestHealth_Primary-Horizontal.png` | Forest Health sub-brand, horizontal | Forest health-specific dashboards |
| `ForestHealth_Primary-Stacked.png` | Forest Health sub-brand, stacked | Forest health-specific, square |
| `ForestHealth_White-Horizontal.png` | Forest Health, white on dark | Dark backgrounds |
| `ForestHealth_Black-Horizontal.png` | Forest Health, all black | 1-color print |
| `ForestHealth_Blue-Horizontal.png` | Forest Health, all navy | 1-color navy |
| `ForestHealth_Secondary-Horizontal.png` | Forest Health, secondary colors | Alternate color treatment |

### Logo color breakdown

In the primary logo:
- **"Lake"** text → EIP Navy (`#0B1F41`)
- **"Tahoe"** text → EIP Blue (`#007DC3`)
- **"Environmental Improvement Program"** subtext → EIP Blue (`#007DC3`)
- **Mountain peaks** in icon → EIP Navy
- **Water band** in icon → EIP Blue
- **Chevron** in icon → EIP Orange (`#F16022`)

### Logo rules

- Maintain clear space around the logo equal to the height of the icon mark.
- Do not stretch, rotate, recolor, or add effects.
- On dark backgrounds, use white variant logos.
- Sub-program logos (Forest Health, etc.) follow the same layout with the sub-program name replacing "Environmental Improvement Program."

---

## Sub-Program Branding

The EIP has sub-programs that share the logo system but substitute the subtitle:

- **Forest Health** — "Lake Tahoe / Forest Health" (logos included)
- **Aquatic Invasive Species** — follows same pattern
- **Stormwater & BMPs** — follows same pattern

All sub-programs use the same 4-color palette and mountain/water icon. Only the subtitle text changes.

---

## Chart & Visualization Colors

### Default sequence

```javascript
const EIP_COLORS = ['#007DC3', '#6EBE44', '#F16022', '#0B1F41'];
```

- **Blue → Green → Orange → Navy** for categorical data.
- For sequential palettes, use tints of Blue or Green.
- For diverging palettes, use Green (positive) to Orange (negative) with Blue as neutral.

---

## Applying the Brand in Code

1. **Set EIP Navy (`#0B1F41`) as default text color** — not black.
2. **Use EIP Blue for chart primary series**, Green for secondary, Orange for highlights.
3. **Headers: Lexend Deca Bold.**
4. **Section labels/nav:** Calder Dark (or substitute) in uppercase.
5. **Backgrounds:** White or light tints. Navy for dark-mode/footer.
6. **Avoid pure black and pure gray** — tint grays toward navy.
7. **Charts:** Cycle Blue → Green → Orange → Navy.

---

## Relationship to TRPA Agency Brand

| Element | TRPA Agency | EIP |
|---------|-------------|-----|
| Primary blue | PMS 285C / `#0072CE` | PMS 285 / `#007DC3` |
| Dark color | PMS 541 / `#003B71` | PMS 282 / `#0B1F41` |
| Accent | PMS 138 Orange / `#E87722` | PMS 1505 Orange / `#F16022` |
| Green | PMS 378 / `#4A6118` | P 802 / `#6EBE44` |
| Primary font (web) | Open Sans | Lexend Deca |
| Logo | Lake silhouette | Mountain/water icon |

Both brands share the PMS 285 blue family as their connecting thread. When building tools that span both brands, use TRPA brand for the structural shell and EIP colors within the content area.
