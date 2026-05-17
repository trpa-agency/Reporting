# html/_archive/

Dashboards that were once active and have since been superseded, replaced, or
rejected in favor of a different layout. Kept here for reference - not the
canonical answer to any of the questions on [index.html](../index.html).

## What's in here

### Legacy / pre-restructure dashboards

| File | Why it's here |
|---|---|
| `residential-allocations-dashboard.html` | Earlier per-jurisdiction allocation overview; superseded by today's `allocation-tracking.html` + `pool-balance-cards.html`. |
| `allocation_drawdown.html` | Stacked-area drawdown prototype - the first stack + TRPA-brand proof that became `pool-balance-cards.html`. |
| `public-allocation-availability.html` | Public-facing 5-jurisdiction allocation balance map. Dan's 2026-05 "Why would I look?" review answered "I don't know" - parked here pending a clearer framing. |
| `development_history_buildings.html` | Tahoe Basin building footprints by construction era with year-slider playback. Spatial-first view; the units-first `development_history.html` is the canonical Trends entry. |
| `development_history_units.html` | Residential unit completions joined to building footprints by APN. Same spatial / unit-split tradeoff as the buildings version. |

### Rejected variants from the Option A/B/C process

| File | Why it's here |
|---|---|
| `tahoe-development-tracker_option1.html` | 3-tile commodity-first layout with stacked-bar pipelines + ice accent. Rejected (2026-05) in favor of Option C, which adds an explicit Banked Development Rights 4-card section below the tiles. |

As more dashboards complete their Option A/B (/C) cycles, the not-chosen
variants will land here too.

## Conventions for archived files

- **Cross-link prefixes:** Files in this folder use `../` to reach sibling
  dashboards in `html/`. The shared explainer markdown lives at
  `content/explainers/pool-balance-cards/*.md` from the repo root, so its
  fetch path is `../../content/explainers/...` from here (one extra level up
  compared to active dashboards).
- **Eyebrow labeling:** Archived files mark themselves with an italic
  "archived layout" tag in the header eyebrow + link out to the active
  options so a viewer landing here knows it's not the canonical version.
- **Footnote layer naming:** Archived files keep their original footer link
  text - we're not back-porting the "layer name as link text" convention to
  archived pages.

## Adding a new entry

1. Move the rejected variant into this folder.
2. Update the file's relative paths:
   - Eyebrow links to active dashboards: `../<file>.html`
   - Related-views links: `../<file>.html`
   - Explainer markdown URLs: `../../content/explainers/...`
3. Add an italic "archived layout" tag to the eyebrow.
4. Add an `archive-card` entry in [index.html](../index.html) so it's
   discoverable from the home page.
5. Add a row in the table above.
6. Update the eyebrows in the remaining active variants to drop the link
   to the now-archived option.
