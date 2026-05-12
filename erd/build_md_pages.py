"""Convert erd/*.md to erd/*.html for GitHub Pages.

For each markdown doc in erd/ (except the ones with existing .html siblings),
produce a browser-renderable HTML page with:

- Dark theme matching development_rights_erd.html
- GitHub-like typography and table styling
- Mermaid diagrams rendered via mermaid.js CDN (client-side, on page load)
- Top nav linking all generated pages + the interactive ERD viewer
- Internal .md links rewritten to .html

Run: python erd/build_md_pages.py
"""
from __future__ import annotations

import html as html_lib
import re
from pathlib import Path

import markdown as md_lib

ERD = Path(__file__).resolve().parent

# .md files whose .html sibling is already generated elsewhere (don't clobber).
SKIP = {"development_rights_erd.md"}

# Pretty labels for the nav (fallback: stem).
NAV_LABELS = {
    "README": "README",
    "target_schema": "Target Schema",
    "tracks_status": "Tracks Status (A / B / C)",
    "dashboards_to_schema_trace": "Dashboards \u2192 Schema Trace",
    "inventory_tables_erd": "Inventory Tables ERD",
    "next_steps": "Next Steps",
    "xlsx_decomposition": "XLSX Decomposition",
    "raw_data_vs_corral": "raw_data vs Corral",
    "validation_findings": "Validation Findings",
    "corral_tables": "Corral Tables",
}

# Docs in their preferred nav order.
NAV_ORDER = [
    "README",
    "target_schema",
    "tracks_status",
    "dashboards_to_schema_trace",
    "inventory_tables_erd",
    "next_steps",
    "raw_data_vs_corral",
    "validation_findings",
    "xlsx_decomposition",
    "corral_tables",
]


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} \u2014 TRPA Development-Rights ERD</title>
<style>
  :root {{
    --bg: #0d1117;
    --panel: #161b22;
    --fg: #c9d1d9;
    --muted: #8b949e;
    --accent: #58a6ff;
    --accent2: #3fb950;
    --border: #30363d;
    --code-bg: #161b22;
  }}
  html, body {{ background: var(--bg); color: var(--fg); font-family: -apple-system, "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif; margin: 0; padding: 0; line-height: 1.6; }}
  header.docnav {{ background: var(--panel); padding: 10px 20px; border-bottom: 1px solid var(--border); font-size: 13px; position: sticky; top: 0; z-index: 10; display: flex; flex-wrap: wrap; gap: 12px 16px; align-items: center; }}
  header.docnav .brand {{ font-weight: 600; color: var(--fg); }}
  header.docnav a {{ color: var(--accent); text-decoration: none; white-space: nowrap; }}
  header.docnav a.active {{ color: var(--fg); font-weight: 600; }}
  header.docnav a.viewer {{ color: var(--accent2); }}
  header.docnav a:hover {{ text-decoration: underline; }}
  main.content {{ max-width: 920px; margin: 0 auto; padding: 32px 24px 96px; }}
  h1, h2, h3, h4 {{ color: var(--fg); margin-top: 1.6em; margin-bottom: 0.6em; line-height: 1.25; }}
  h1 {{ border-bottom: 1px solid var(--border); padding-bottom: 10px; margin-top: 0.5em; }}
  h2 {{ border-bottom: 1px solid var(--border); padding-bottom: 6px; }}
  p {{ margin: 0.8em 0; }}
  a {{ color: var(--accent); }}
  a:hover {{ text-decoration: underline; }}
  code {{ background: var(--code-bg); padding: 2px 6px; border-radius: 3px; font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 88%; color: #c9d1d9; }}
  pre {{ background: var(--code-bg); padding: 16px; border-radius: 6px; overflow-x: auto; border: 1px solid var(--border); }}
  pre code {{ background: none; padding: 0; font-size: 90%; line-height: 1.5; }}
  blockquote {{ border-left: 3px solid var(--accent); color: var(--muted); margin: 16px 0; padding: 4px 16px; background: rgba(88, 166, 255, 0.04); }}
  blockquote p {{ margin: 0.4em 0; }}
  table {{ border-collapse: collapse; margin: 16px 0; display: block; overflow-x: auto; }}
  th, td {{ border: 1px solid var(--border); padding: 6px 13px; text-align: left; vertical-align: top; }}
  th {{ background: var(--panel); font-weight: 600; }}
  tr:nth-child(even) {{ background: rgba(255,255,255,0.02); }}
  ul, ol {{ padding-left: 28px; }}
  li {{ margin: 4px 0; }}
  hr {{ border: 0; border-top: 1px solid var(--border); margin: 32px 0; }}
  .mermaid {{ background: #0b0f14; padding: 20px; border-radius: 6px; border: 1px solid var(--border); margin: 16px 0; overflow-x: auto; text-align: center; }}
  img {{ max-width: 100%; }}
</style>
</head>
<body>
<header class="docnav">
  <span class="brand">TRPA ERD</span>
  {nav}
</header>
<main class="content">
{body}
</main>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>
  if (typeof mermaid !== 'undefined') {{
    mermaid.initialize({{
      startOnLoad: true,
      theme: 'dark',
      themeVariables: {{ darkMode: true, background: '#0b0f14' }},
      er: {{ useMaxWidth: true }},
      maxTextSize: 500000,
      securityLevel: 'loose'
    }});
  }}
</script>
</body>
</html>
"""


def build_nav(current_stem: str, stems: list[str]) -> str:
    links = []
    for stem in stems:
        label = NAV_LABELS.get(stem, stem)
        active = ' class="active"' if stem == current_stem else ""
        links.append(f'<a href="{stem}.html"{active}>{label}</a>')
    links.append(
        '<a class="viewer" href="development_rights_erd.html">Interactive ERD \u2192</a>'
    )
    return "\n  ".join(links)


def preprocess(text: str, erd_md_names: set[str]) -> str:
    # Replace ```mermaid blocks with <div class="mermaid"> so mermaid.js picks them up.
    # (Otherwise Python-markdown's fenced_code would wrap them in <pre><code>.)
    def mermaid_block(m: re.Match) -> str:
        src = m.group(1)
        return f'\n<div class="mermaid">\n{html_lib.escape(src)}\n</div>\n'

    text = re.sub(r"```mermaid\s*\n(.*?)\n```", mermaid_block, text, flags=re.DOTALL)

    # Rewrite relative .md links to .html for siblings we're generating.
    def replace_link(m: re.Match) -> str:
        prefix = m.group(1) or ""
        name = m.group(2)
        anchor = m.group(3) or ""
        md_name = f"{name}.md"
        if md_name in erd_md_names and md_name not in SKIP:
            return f"]({prefix}{name}.html{anchor})"
        return m.group(0)

    text = re.sub(
        r"\]\((\./)?([A-Za-z0-9_\-]+)\.md(#[^)]*)?\)",
        replace_link,
        text,
    )
    return text


def convert(md_path: Path, stems_in_nav: list[str], erd_md_names: set[str]) -> Path:
    raw = md_path.read_text(encoding="utf-8")
    processed = preprocess(raw, erd_md_names)
    body = md_lib.markdown(
        processed,
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
        extension_configs={"toc": {"permalink": False}},
    )
    nav = build_nav(md_path.stem, stems_in_nav)
    title = NAV_LABELS.get(md_path.stem, md_path.stem)
    html_out = HTML_TEMPLATE.format(title=title, body=body, nav=nav)
    out = md_path.with_suffix(".html")
    out.write_text(html_out, encoding="utf-8")
    return out


def main() -> None:
    all_md = sorted(ERD.glob("*.md"))
    renderable = [p for p in all_md if p.name not in SKIP]
    erd_md_names = {p.name for p in all_md}

    # Nav order: explicit ordering first, then any leftovers alphabetically.
    ordered_stems = [s for s in NAV_ORDER if (ERD / f"{s}.md") in renderable]
    leftover = sorted(
        [p.stem for p in renderable if p.stem not in ordered_stems]
    )
    nav_stems = ordered_stems + leftover

    for md in renderable:
        out = convert(md, nav_stems, erd_md_names)
        print(f"Wrote {out.name}")
    print(f"\n{len(renderable)} pages rendered.")


if __name__ == "__main__":
    main()
