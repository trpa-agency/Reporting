# Dashboard explainer content

Markdown narrative for the editorial layer of each dashboard. Page content, not data.

## Convention

```
content/explainers/<dashboard-slug>/<commodity-or-section>.md
```

One subfolder per dashboard. Filename matches the dashboard's internal key for the section the explainer describes (e.g., `residential_bonus_units.md` matches the commodity key `residential_bonus_units` in `pool-balance-cards.html`).

## Loading

Dashboards fetch the markdown at runtime and render via [marked](https://github.com/markedjs/marked) (CDN). Standard h3/p/a output styles automatically against the existing `.explainer` CSS.

## Editing

These files are intentionally easy to edit without touching JS. The analyst or any content owner can update the markdown directly and the dashboard picks it up on next load (no rebuild). Avoid em-dashes per repo convention.

## Current set

| Dashboard | Folder | Sections |
|---|---|---|
| pool-balance-cards.html | `pool-balance-cards/` | `residential.md` (full) + 3 placeholders (`residential_bonus_units.md`, `commercial_floor_area.md`, `tourist_accommodation_units.md`) awaiting analyst-authored content |
