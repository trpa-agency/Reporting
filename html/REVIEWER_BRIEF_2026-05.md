# TRPA Cumulative Accounting Dashboards · Reviewer Brief

**For:** Communications reviewer
**Review window:** Monday (1 - 1.5 hours)
**Target publish:** Wednesday
**Deliverable from you:** edits with track-changes in the feedback doc + a GO / GO-WITH-EDITS / NO-GO recommendation per dashboard

---

## What you're reviewing

A 7-dashboard ecosystem that answers the Cumulative Accounting questions TRPA reports on annually. The dashboards are color-coded by audience:

- **Executive** (navy) - board-meeting headline view
- **Operations** (blue) - per-commodity / per-pool detail for daily staff use
- **Trends** (forest) - year-over-year change + source breakdown
- **Audit** (orange) - per-APN lineage + correction history

The entry point is the decision-tree home page (`index.html` once we rename). Each card is one question with the dashboard that answers it.

---

## Recommended viewing order

| # | Dashboard | Time | What to look for |
|---|---|---|---|
| 1 | **index.html / index.html** (the decision tree home) | 5 min | Does the framing land for each audience tier? Are the seven questions the right questions to lead with? |
| 2 | **Tahoe Development Tracker** (try Option A and Option C) | 10 min | Board-meeting-ready? Does the "how much built / how much more can be built" story come through in <30 seconds? |
| 3 | **Allocation Tracking** (try Option A and Option B) | 10 min | Operations-staff view. Too jargon-heavy for a non-staff visitor? |
| 4 | **Pool Balance Cards** (try Option A and Option B) | 10 min | Per-pool drilldown. Is the by-jurisdiction breakdown clear? Are the commodity toggles (Residential Allocations / Residential Bonus Units / Commercial Floor Area / Tourist Bonus Units) self-explanatory? |
| 5 | **Residential Additions by Source** (try Option A and Option B) | 10 min | The five source categories - clear? The 2024-25 bonus surge story - lands? |
| 6 | **Development History** (try Option A and Option B) | 8 min | Year-over-year change. Negative bars are brick-colored - does that read as "removal" or as "error/problem"? |
| 7 | **QA Change Rationale** | 5 min | Internal audit log. Is this even appropriate for the public site, or staff-only? |
| 8 | **Genealogy Solver** | 5 min | APN lineage tool. Public-facing or internal-only? |

Each dashboard with variants carries a "switch to Option X layout" link in the header eyebrow - flip between them in place.

---

## Five focus questions

Please leave comments against each:

### 1. Audience match
Does each card on the home page land for the audience tag it claims? In particular - does the **Executive** card read like something you'd put in front of the governing board, and does the **Operations** card read like something a staff person would use for daily work?

### 2. Jargon audit
Flag any term we use without explanation that a board member or local-jurisdiction staffer wouldn't recognize. Top candidates:

- **MFRUU / SFRUU** (Multi-Family / Single-Family Residential Units of Use)
- **CFA** (Commercial Floor Area)
- **TAU** (Tourist Accommodation Unit)
- **RBU** (Residential Bonus Unit)
- **"allocation pool"** vs **"jurisdiction pool"** vs **"TRPA pool"**
- **"banked"** development rights
- **"since-1987 cap"** / **"2012 Regional Plan grid"**
- **"reserved, not constructed"**

If you flag any, we can either rewrite to plain language OR add a small glossary `?` icon next to the term that explains it on hover. The hover pattern is already in place on every dashboard.

### 3. Messaging risks
Anything that might read wrong publicly?

- TRPA shown "near cap" on any commodity - is that the message we want, or framing we should soften?
- Banked totals - any chance of misinterpretation? (banked rights are NOT the same as allocations; the dashboards distinguish them explicitly but is the framing clear?)
- The pre-1987 vs post-1987 totals - we surface both; could this read as "TRPA changed the rules"?
- Carson City context - we exclude Carson from per-jurisdiction filters because Carson doesn't receive Regional Plan allocations; is the way we explain that diplomatic?

### 4. TRPA brand voice
- Tone consistent with `trpa.gov`?
- Per our convention, we say "the analyst" / "the agency" / "TRPA leadership" and never name specific staff. Did we slip anywhere?
- Em-dashes (—) are forbidden in this repo per convention. Did any creep in?
- Anything else from the TRPA style guide we should clean up?

### 5. Calls to action / external links
Each dashboard's footer links out to:
- The Cumulative_Accounting REST service (technical endpoint)
- The LT Info Pool Balance Report
- The TRPA Development Rights Dashboard (ArcGIS)

For the public-facing version:
- Should we keep all three?
- Should we hide the REST endpoint links?
- Are there pages on `trpa.gov/development-rights/` we should link to that we don't yet?

---

## What you do NOT need to review

- Visual design (colors, layout, chart type) - already iterated through UX review
- Data accuracy - that's the analyst's signoff, separately
- Browser compatibility / edge cases - dev side
- The `reference.html` page (the technical reference) - that's for data engineers / analysts; not part of the public surface unless you want it linked

---

## Two prep items before Monday

I'd like your read on these before the deep dive:

1. **Public vs internal scope.** My current draft makes these public on the home page:
   - Tracker
   - Allocation Tracking
   - Pool Balance Cards
   - Residential Additions by Source
   - Development History

   And keeps these staff-only (still on the home page but in a separate row, or moved off entirely):
   - QA Change Rationale
   - Genealogy Solver

   Does that split land? Or do you want a different cut for the public site?

2. **Glossary pattern.** Want to commit to adding glossary hovers (one-click reveal) for all the acronyms above, OR keep them inline-defined in plain text, OR leave them as-is and assume the audience knows?

---

## How to leave feedback

- **Per-dashboard comments:** in the shared Google Doc, one section per dashboard
- **Per-card-text edits:** track-changes in that doc against the card descriptions
- **Per-dashboard recommendation:** GO / GO-WITH-EDITS / NO-GO at the top of each section
- **Anything urgent (i.e., a phrasing risk):** flag with `🚨 BLOCKER` in your comment so I can act before publish

---

## Wednesday publish timeline

- **Mon AM:** you review
- **Mon PM:** I integrate your edits, push to staging
- **Tue AM:** quick re-check on changes (15-30 min)
- **Tue PM:** deploy to production
- **Wed:** website team links from `trpa.gov` and/or `laketahoeinfo.org`

If you need more than Monday for the review, push the publish to Thursday rather than rush the integration.

---

## Quick navigation

Staging URLs (use these, not localhost):
- Home: `https://trpa-agency.github.io/Reporting/html/` (or `/index.html`)
- Reference (data architecture, not for public copy review): `https://trpa-agency.github.io/Reporting/html/reference.html`

Each dashboard:
- `tahoe-development-tracker.html` (+ `_option2.html`)
- `allocation-tracking.html` (+ `_option1.html`)
- `pool-balance-cards.html` (+ `_option1.html`)
- `residential-additions-by-source.html` (+ `_option1.html`)
- `development_history.html` (+ `_option1.html`)
- `qa-change-rationale.html`
- `genealogy_solver/`

Thanks!
