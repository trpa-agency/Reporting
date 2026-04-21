"""Render a standalone HTML ERD viewer with pan/zoom + tabs.

Tabs:
- Corral (SQL Server) — existing LTinfo backend
- LTinfo web services — live read layer
- Proposed — Reference
- Proposed — 5 buckets
- Proposed — Ledger
- Proposed — Permits & changes
- Proposed — Dashboard outputs

Zero external deps at build time; viewer loads mermaid + svg-pan-zoom from
CDNs at render time. Output: erd/development_rights_erd.html.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_erd import (  # noqa: E402
    build_corral_block,
    build_webservices_block,
)

ERD_DIR = Path(__file__).resolve().parent


def _strip_fence(block: str) -> str:
    lines = block.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines)


_ERD_HEADING = re.compile(r"^##\s+ERD\s*\u2014\s*(.+?)\s*$", re.MULTILINE)
_MERMAID = re.compile(r"```mermaid\s*\n(.+?)```", re.DOTALL)


def extract_proposed_blocks(md_path: Path) -> list[dict]:
    """Pull each `## ERD — <label>` + following ```mermaid block from a markdown file."""
    md = md_path.read_text(encoding="utf-8")
    blocks: list[dict] = []
    # Find each ERD heading and its index
    headings = [(m.start(), m.group(1).strip()) for m in _ERD_HEADING.finditer(md)]
    for i, (start, label) in enumerate(headings):
        end = headings[i + 1][0] if i + 1 < len(headings) else len(md)
        section = md[start:end]
        mm = _MERMAID.search(section)
        if not mm:
            continue
        key = "prop-" + re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
        blocks.append({
            "key": key,
            "label": "Proposed \u2014 " + label,
            "mermaid": mm.group(1).rstrip(),
        })
    return blocks


HTML_HEAD = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>TRPA Development-Rights ERD</title>
<style>
  :root {
    --bg: #0f1419;
    --panel: #161b22;
    --fg: #e6edf3;
    --muted: #8b949e;
    --accent: #58a6ff;
    --accent2: #3fb950;
    --border: #30363d;
  }
  html, body { margin: 0; padding: 0; height: 100%; background: var(--bg); color: var(--fg); font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }
  header { padding: 10px 16px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 16px; background: var(--panel); flex-wrap: wrap; }
  header h1 { font-size: 15px; margin: 0; font-weight: 600; white-space: nowrap; }
  header nav { display: flex; flex-wrap: wrap; gap: 4px 12px; }
  header nav a { color: var(--accent); text-decoration: none; font-size: 13px; white-space: nowrap; cursor: pointer; }
  header nav a.proposed { color: var(--accent2); }
  header nav a.active { color: var(--fg); font-weight: 600; }
  header .spacer { flex: 1; }
  header .controls button { background: var(--panel); color: var(--fg); border: 1px solid var(--border); padding: 4px 10px; margin-left: 4px; border-radius: 4px; cursor: pointer; font-size: 12px; }
  header .controls button:hover { border-color: var(--accent); }
  #stage { position: absolute; top: 84px; bottom: 0; left: 0; right: 0; overflow: hidden; background: #0b0f14; }
  @media (min-width: 1400px) { #stage { top: 46px; } }
  .view { display: none; width: 100%; height: 100%; }
  .view.active { display: block; }
  .view .mermaid { width: 100%; height: 100%; white-space: pre; font-family: ui-monospace, monospace; color: var(--muted); padding: 16px; box-sizing: border-box; overflow: auto; }
  .view svg { width: 100% !important; height: 100% !important; max-width: none !important; background: #0b0f14; display: block; }
  #status { position: absolute; bottom: 8px; left: 12px; color: var(--muted); font-size: 12px; font-family: ui-monospace, monospace; }
</style>
</head>
<body>
"""


HTML_TAIL_PRE_SCRIPT = r"""<div id="status">loading mermaid...</div>
"""


HTML_SCRIPTS = r"""
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/svg-pan-zoom@3.6.1/dist/svg-pan-zoom.min.js"></script>
<script>
  const panzooms = {};
  const status = document.getElementById('status');

  // Wire up click handlers on the server-rendered nav tabs.
  document.querySelectorAll('#nav a').forEach(a => {
    a.addEventListener('click', (e) => { e.preventDefault(); activate(a.dataset.view); });
  });

  if (typeof mermaid === 'undefined') {
    status.textContent = 'mermaid CDN failed to load; tabs still work but diagrams will not render';
  } else {
    mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      themeVariables: { darkMode: true, background: '#0b0f14' },
      er: { useMaxWidth: false },
      maxTextSize: 500000,
      securityLevel: 'loose'
    });
    renderAll();
  }

  const rendered = {};

  const rendered = {};

  async function renderAll() {
    const views = Array.from(document.querySelectorAll('.view'));
    for (const view of views) {
      const key = view.id.replace('view-', '');
      const host = view.querySelector('.mermaid');
      if (!host) continue;
      const src = host.textContent;
      try {
        status.textContent = 'rendering ' + key + '...';
        const { svg } = await mermaid.render('svg-' + key, src);
        host.innerHTML = svg;
        const svgEl = host.querySelector('svg');
        if (svgEl) {
          svgEl.removeAttribute('width');
          svgEl.removeAttribute('height');
          svgEl.removeAttribute('style');
          svgEl.style.width = '100%';
          svgEl.style.height = '100%';
          svgEl.style.maxWidth = 'none';
          svgEl.setAttribute('preserveAspectRatio', 'xMidYMid meet');
          host.style.whiteSpace = 'normal';
          host.style.padding = '0';
          rendered[key] = true;
        }
      } catch (e) {
        host.innerHTML = '<pre style="color:#f85149;padding:16px;white-space:pre-wrap">' + key + ':\n' + (e.message || e) + '</pre>';
      }
    }
    status.textContent = 'ready \u2014 click tabs, scroll to zoom, drag to pan';
    const first = document.querySelector('.view.active');
    if (first) initPanZoom(first.id.replace('view-', ''));
  }

  function initPanZoom(key) {
    if (panzooms[key] || !rendered[key]) return;
    if (typeof svgPanZoom === 'undefined') return;
    const svgEl = document.querySelector('#mm-' + key + ' svg');
    if (!svgEl) return;
    try {
      panzooms[key] = svgPanZoom(svgEl, {
        zoomEnabled: true, controlIconsEnabled: false, fit: true, center: true,
        contain: false, minZoom: 0.05, maxZoom: 30
      });
      requestAnimationFrame(() => {
        if (panzooms[key]) { panzooms[key].resize(); panzooms[key].fit(); panzooms[key].center(); }
      });
    } catch (e) {
      console.error('svgPanZoom failed for', key, e);
    }
  }

  function activate(key) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    const target = document.getElementById('view-' + key);
    if (target) target.classList.add('active');
    document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('active', a.dataset.view === key));
    if (!panzooms[key]) initPanZoom(key);
    if (panzooms[key]) {
      requestAnimationFrame(() => { panzooms[key].resize(); panzooms[key].fit(); panzooms[key].center(); });
    }
  }

  const active = () => {
    const el = document.querySelector('.view.active');
    return el ? el.id.replace('view-', '') : null;
  };
  const withPZ = (fn) => { const k = active(); if (k && panzooms[k]) fn(panzooms[k]); };
  document.getElementById('btn-fit').addEventListener('click', () => withPZ(p => { p.fit(); p.center(); }));
  document.getElementById('btn-reset').addEventListener('click', () => withPZ(p => { p.resetZoom(); p.center(); }));
  document.getElementById('btn-zoom-in').addEventListener('click', () => withPZ(p => p.zoomIn()));
  document.getElementById('btn-zoom-out').addEventListener('click', () => withPZ(p => p.zoomOut()));
  window.addEventListener('resize', () => Object.values(panzooms).forEach(p => { p.resize(); p.fit(); p.center(); }));
</script>
</body>
</html>
"""


def _render_nav(views: list[dict]) -> str:
    parts = ['<nav id="nav">']
    for i, v in enumerate(views):
        classes = []
        if v.get("proposed"):
            classes.append("proposed")
        if i == 0:
            classes.append("active")
        cls = f' class="{" ".join(classes)}"' if classes else ""
        parts.append(
            f'<a href="#{html.escape(v["key"])}" data-view="{html.escape(v["key"])}"{cls}>{html.escape(v["label"])}</a>'
        )
    parts.append("</nav>")
    return "\n".join(parts)


def _render_stage(views: list[dict]) -> str:
    parts = ['<div id="stage">']
    for i, v in enumerate(views):
        active = " active" if i == 0 else ""
        parts.append(f'<div class="view{active}" id="view-{html.escape(v["key"])}">')
        parts.append(f'<div class="mermaid" id="mm-{html.escape(v["key"])}">{html.escape(v["mermaid"])}</div>')
        parts.append("</div>")
    parts.append("</div>")
    return "\n".join(parts)


def main() -> None:
    schema = json.loads((ERD_DIR / "corral_schema.json").read_text(encoding="utf-8"))
    services = json.loads((ERD_DIR / "ltinfo_services.json").read_text(encoding="utf-8"))

    views = [
        {"key": "corral", "label": "Corral (SQL Server)", "mermaid": _strip_fence(build_corral_block(schema)), "proposed": False},
        {"key": "ltinfo", "label": "LTinfo web services",  "mermaid": _strip_fence(build_webservices_block(services)), "proposed": False},
    ]
    for b in extract_proposed_blocks(ERD_DIR / "target_schema.md"):
        views.append({**b, "proposed": True})

    header_html = (
        "<header>\n"
        '  <h1>TRPA Development-Rights ERD</h1>\n'
        f"  {_render_nav(views)}\n"
        '  <span class="spacer"></span>\n'
        '  <div class="controls">\n'
        '    <button id="btn-fit">Fit</button>\n'
        '    <button id="btn-reset">100%</button>\n'
        '    <button id="btn-zoom-in">+</button>\n'
        '    <button id="btn-zoom-out">&minus;</button>\n'
        '  </div>\n'
        "</header>\n"
    )

    out_html = (
        HTML_HEAD
        + header_html
        + _render_stage(views)
        + HTML_TAIL_PRE_SCRIPT
        + HTML_SCRIPTS
    )
    out = ERD_DIR / "development_rights_erd.html"
    out.write_text(out_html, encoding="utf-8")
    print(f"Wrote {out}  ({len(views)} views, server-rendered nav)")


if __name__ == "__main__":
    main()
