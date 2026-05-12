"""Extract textual copy from each TRPA dashboard for the Word doc review.

Pulls header, KPI labels/subs, section headings & descriptions, and footnote
text from each HTML file. Writes a JSON blob the docx builder consumes.
"""
import json
import re
from pathlib import Path

HTML_DIR = Path(__file__).resolve().parents[1] / "html"
OUT      = Path(__file__).parent / "dashboard_content.json"

# (slug, html_filename, friendly_title, audience, track, screenshot)
DASHBOARDS = [
    ("01_allocation-tracking",            "allocation-tracking.html",
     "Allocation Tracking",
     "Staff · daily ops",
     "Track 1 (Allocation tracking)",
     "01_allocation-tracking.png"),
    ("02_pool-balance-cards",             "pool-balance-cards.html",
     "Pool Balance Cards",
     "Staff · per-pool drilldown",
     "Track 1 (Allocation tracking)",
     "02_pool-balance-cards.png"),
    ("03_public-allocation-availability", "public-allocation-availability.html",
     "Residential Allocation Availability",
     "Public",
     "Track 1 (Allocation tracking)",
     "03_public-allocation-availability.png"),
    ("04_residential-additions-by-source", "residential-additions-by-source.html",
     "Residential Additions by Source",
     "Leadership · public",
     "Track 2 (Source of rights)",
     "04_residential-additions-by-source.png"),
    ("05_regional-capacity-dial",         "regional-capacity-dial.html",
     "Regional Plan Capacity Dial",
     "Executive · board",
     "Track 4 (Total development tracking)",
     "05_regional-capacity-dial.png"),
    ("06_development_history",            "development_history.html",
     "Development History — Buildings",
     "Planners · analysts",
     "Companion view",
     "06_development_history.png"),
    ("07_development_history_units",      "development_history_units.html",
     "Development History — Residential Units",
     "Housing analysts",
     "Companion view",
     "07_development_history_units.png"),
    ("08_qa-change-rationale",            "qa-change-rationale.html",
     "QA Change Rationale Audit Trail",
     "Ken · Dan · QA leads",
     "QA / audit",
     "08_qa-change-rationale.png"),
]

# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

ENTITY_MAP = {
    "&mdash;": "—", "&ndash;": "–", "&middot;": "·", "&rarr;": "→",
    "&le;": "≤", "&ge;": "≥", "&amp;": "&", "&quot;": '"', "&#039;": "'",
    "&rsquo;": "’", "&lsquo;": "‘", "&ldquo;": "“", "&rdquo;": "”",
    "&nbsp;": " ", "&hellip;": "…", "&times;": "×", "&percnt;": "%",
}

def clean(s: str | None) -> str:
    if s is None: return ""
    # strip tags
    s = re.sub(r"<[^>]+>", "", s)
    for k, v in ENTITY_MAP.items():
        s = s.replace(k, v)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def grab_first(pattern: str, html: str, flags=re.S | re.I) -> str:
    m = re.search(pattern, html, flags)
    return clean(m.group(1)) if m else ""

def grab_all(pattern: str, html: str, flags=re.S | re.I) -> list[str]:
    return [clean(m.group(1)) for m in re.finditer(pattern, html, flags)]


# ────────────────────────────────────────────────────────────────────
# Per-dashboard extraction
# ────────────────────────────────────────────────────────────────────

def extract(slug, fname):
    html = (HTML_DIR / fname).read_text(encoding="utf-8")

    eyebrow = grab_first(r'class="header-eyebrow"[^>]*>(.*?)</div>', html)
    h1      = grab_first(r'<h1[^>]*>(.*?)</h1>', html)
    sub     = grab_first(r'class="header-sub"[^>]*>(.*?)</div>', html)
    meta    = grab_first(r'class="header-meta"[^>]*>(.*?)</div>', html)

    # KPI cards — pull label + sub (skip the value since it's data, not copy)
    kpis = []
    for m in re.finditer(
        r'class="kpi-card"[^>]*>(.*?)</div>\s*</div>',
        html, re.S | re.I
    ):
        block = m.group(1)
        label = grab_first(r'class="kpi-label"[^>]*>(.*?)</div>', block)
        sub_t = grab_first(r'class="kpi-sub"[^>]*>(.*?)</div>', block)
        if label:
            kpis.append({"label": label, "sub": sub_t})

    # Section headings/descriptions (cards within sections)
    sections = []
    for m in re.finditer(
        r'class="card[^"]*"[^>]*>\s*<h3[^>]*>(.*?)</h3>\s*<p[^>]*>(.*?)</p>',
        html, re.S | re.I
    ):
        title = clean(m.group(1))
        desc  = clean(m.group(2))
        if title:
            sections.append({"title": title, "description": desc})

    # Top-level h3 in section/.card (no <p> right after) — also try
    for m in re.finditer(r'<h3[^>]*>(.*?)</h3>', html, re.S | re.I):
        title = clean(m.group(1))
        if title and not any(s["title"] == title for s in sections):
            sections.append({"title": title, "description": ""})

    # Footnote
    footnote = grab_first(r'class="footnote"[^>]*>(.*?)</div>', html)

    # Special: residential-additions-by-source has toggle buttons, capture mode labels
    toggles = grab_all(r'class="toggle-btn[^"]*"[^>]*>([^<]+)</button>', html)
    if not toggles:
        toggles = grab_all(r'class="type-btn[^"]*"[^>]*>([^<]+)</button>', html)
    if not toggles:
        toggles = grab_all(r'class="tab-btn[^"]*"[^>]*>([^<]+)</button>', html)
    if not toggles:
        toggles = grab_all(r'class="sort-btn[^"]*"[^>]*>([^<]+)</button>', html)

    return {
        "slug": slug,
        "html_file": fname,
        "eyebrow": eyebrow,
        "title": h1,
        "subtitle": sub,
        "meta": meta,
        "kpis": kpis,
        "sections": sections,
        "footnote": footnote,
        "controls": [t for t in toggles if t and len(t) < 80],
    }


def main():
    out = []
    for slug, fname, friendly, audience, track, shot in DASHBOARDS:
        rec = extract(slug, fname)
        rec.update({
            "friendly_title": friendly,
            "audience":       audience,
            "track":          track,
            "screenshot":     shot,
            "github_pages_url": f"https://trpa-agency.github.io/Reporting/html/{fname}",
        })
        out.append(rec)

    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"  {len(out)} dashboards, "
          f"{sum(len(d['kpis']) for d in out)} KPI cards, "
          f"{sum(len(d['sections']) for d in out)} section headings.")


if __name__ == "__main__":
    main()
