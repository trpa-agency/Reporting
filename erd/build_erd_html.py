"""Render a standalone HTML ERD viewer with pan/zoom.

Zero external dependencies at build time; viewer loads mermaid + svg-pan-zoom
from CDNs at render time. Output: erd/development_rights_erd.html.
"""
from __future__ import annotations

import json
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


HTML_TEMPLATE = r"""<!doctype html>
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
    --border: #30363d;
  }
  html, body { margin: 0; padding: 0; height: 100%; background: var(--bg); color: var(--fg); font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }
  header { padding: 10px 16px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 16px; background: var(--panel); }
  header h1 { font-size: 15px; margin: 0; font-weight: 600; }
  header nav a { color: var(--accent); text-decoration: none; margin-right: 12px; font-size: 13px; }
  header nav a.active { color: var(--fg); font-weight: 600; }
  header .spacer { flex: 1; }
  header .controls button { background: var(--panel); color: var(--fg); border: 1px solid var(--border); padding: 4px 10px; margin-left: 4px; border-radius: 4px; cursor: pointer; font-size: 12px; }
  header .controls button:hover { border-color: var(--accent); }
  #stage { position: absolute; top: 46px; bottom: 0; left: 0; right: 0; overflow: hidden; background: #0b0f14; }
  .view { display: none; width: 100%; height: 100%; }
  .view.active { display: block; }
  .view .mermaid { width: 100%; height: 100%; }
  .view svg { width: 100% !important; height: 100% !important; max-width: none !important; background: #0b0f14; display: block; }
  #status { position: absolute; bottom: 8px; left: 12px; color: var(--muted); font-size: 12px; font-family: ui-monospace, monospace; }
  .pre-mermaid { display: none; }
</style>
</head>
<body>
<header>
  <h1>TRPA Development-Rights ERD</h1>
  <nav>
    <a href="#" data-view="corral" class="active">Corral (SQL Server)</a>
    <a href="#" data-view="ltinfo">LTinfo web services</a>
  </nav>
  <span class="spacer"></span>
  <div class="controls">
    <button id="btn-fit">Fit</button>
    <button id="btn-reset">100%</button>
    <button id="btn-zoom-in">+</button>
    <button id="btn-zoom-out">&minus;</button>
  </div>
</header>

<div id="stage">
  <div class="view active" id="view-corral"><div class="mermaid" id="mm-corral">__CORRAL__</div></div>
  <div class="view"        id="view-ltinfo"><div class="mermaid" id="mm-ltinfo">__LTINFO__</div></div>
</div>

<div id="status">loading mermaid...</div>

<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/svg-pan-zoom@3.6.1/dist/svg-pan-zoom.min.js"></script>
<script>
  const panzooms = {};
  const status = document.getElementById('status');

  mermaid.initialize({
    startOnLoad: false,
    theme: 'dark',
    themeVariables: { darkMode: true, background: '#0b0f14' },
    er: { useMaxWidth: false },
    maxTextSize: 500000,
    securityLevel: 'loose'
  });

  async function renderAll() {
    for (const key of ['corral', 'ltinfo']) {
      const host = document.getElementById('mm-' + key);
      const src = host.textContent;
      try {
        status.textContent = 'rendering ' + key + '...';
        const { svg } = await mermaid.render('svg-' + key, src);
        host.innerHTML = svg;
        const svgEl = host.querySelector('svg');
        svgEl.removeAttribute('width');
        svgEl.removeAttribute('height');
        svgEl.removeAttribute('style');
        svgEl.style.width = '100%';
        svgEl.style.height = '100%';
        svgEl.style.maxWidth = 'none';
        svgEl.setAttribute('preserveAspectRatio', 'xMidYMid meet');
        panzooms[key] = svgPanZoom(svgEl, {
          zoomEnabled: true, controlIconsEnabled: false, fit: true, center: true,
          contain: false, minZoom: 0.05, maxZoom: 30
        });
        requestAnimationFrame(() => { panzooms[key].resize(); panzooms[key].fit(); panzooms[key].center(); });
      } catch (e) {
        host.innerHTML = '<pre style="color:#f85149;padding:16px;white-space:pre-wrap">' + e.message + '</pre>';
      }
    }
    status.textContent = 'ready \u2014 scroll to zoom, drag to pan';
    activate('corral');
  }

  function activate(key) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById('view-' + key).classList.add('active');
    document.querySelectorAll('header nav a').forEach(a => a.classList.toggle('active', a.dataset.view === key));
    if (panzooms[key]) { panzooms[key].resize(); panzooms[key].fit(); panzooms[key].center(); }
  }

  document.querySelectorAll('header nav a').forEach(a => {
    a.addEventListener('click', e => { e.preventDefault(); activate(a.dataset.view); });
  });
  const active = () => document.querySelector('.view.active').id.replace('view-', '');
  document.getElementById('btn-fit').addEventListener('click', () => { const p = panzooms[active()]; p && p.fit() && p.center(); });
  document.getElementById('btn-reset').addEventListener('click', () => { const p = panzooms[active()]; p && p.resetZoom() && p.center(); });
  document.getElementById('btn-zoom-in').addEventListener('click', () => panzooms[active()] && panzooms[active()].zoomIn());
  document.getElementById('btn-zoom-out').addEventListener('click', () => panzooms[active()] && panzooms[active()].zoomOut());
  window.addEventListener('resize', () => Object.values(panzooms).forEach(p => { p.resize(); p.fit(); p.center(); }));

  renderAll();
</script>
</body>
</html>
"""


def main() -> None:
    schema = json.loads((ERD_DIR / "corral_schema.json").read_text(encoding="utf-8"))
    services = json.loads((ERD_DIR / "ltinfo_services.json").read_text(encoding="utf-8"))

    corral = _strip_fence(build_corral_block(schema))
    ltinfo = _strip_fence(build_webservices_block(services))

    html = HTML_TEMPLATE.replace("__CORRAL__", corral).replace("__LTINFO__", ltinfo)
    out = ERD_DIR / "development_rights_erd.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
