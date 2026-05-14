/* =============================================================================
 * Genealogy Solver - client-side BFS over the pre-joined adjacency JSON.
 *
 * Sections:
 *   1. State + constants
 *   2. canonical_apn (JS port) + test vectors
 *   3. Data loader
 *   4. Graph walk (bidirectional BFS, with cycle defense)
 *   5. UI rendering: KPIs, xref panel, component grid, SVG diagram
 *   6. Single APN tab wiring
 *   7. Batch CSV tab wiring (drop zone, CSV parser, AG Grid)
 *   8. Tab switcher, helpers, toast
 *   9. Self-test under ?test=1
 * ============================================================================= */

// ─── 1. State + constants ───────────────────────────────────────────────────
const DATA_URL = './data/genealogy_solver.json';
const TRPA = {
  blue:   '#0072CE', navy: '#003B71', forest: '#4A6118', orange: '#E87722',
  brick:  '#9C3E27', earth: '#B47E00', purple: '#7B6A8A', ice: '#B4CBE8',
  olive:  '#B5A64C',
};

const state = {
  edges: [],            // raw edge array (compact short-key form)
  apns:  {},            // apn -> node {co, ju, ru, tu, cf, yb, ad, in, po, pi}
  meta:  null,
  currentSeed: null,    // canonical APN currently displayed
  batchRows: null,      // raw input rows of latest batch
  componentGrid: null,  // AG Grid instance for Single tab
  batchGrid: null,      // AG Grid instance for Batch tab
  map:    null,         // {map, view, layer} once ArcGIS init resolves
  mapModules: null,     // ArcGIS module cache
  mapInitPromise: null, // resolves when MapView is ready
};

// Event-type fanout collapse threshold for the SVG diagram
const FANOUT_COLLAPSE_AT = 8;

// AllParcels MapServer (layer 4 = Parcels - Active; polygon).
// Used as the primary geometry source for the lineage map. Soon to be
// replaced by a map service of Parcel_Development_History feature class.
// Note: AllParcels stores APNs in the pre-2018 unpadded form for many
// jurisdictions, so we query with both canonical and depadded variants.
const ALLPARCELS_BASE = 'https://maps.trpa.org/server/rest/services/AllParcels/MapServer';
const ALLPARCELS_ACTIVE_URL = ALLPARCELS_BASE + '/4';
// Per-year layer fallbacks for APNs not in the active layer.
//
// NOTE (2026-05-13): AllParcels MapServer's per-year layers (32, 31, 30, ...)
// do support Query but return null geometry for individual feature requests
// over REST - only the MapServer image-tile rendering paths get pixels.
// Until that changes (or a Parcel_Development_History FeatureServer is
// published), historical/renamed-out APNs won't appear on the map. The
// fallback walk is kept here so it lights up automatically if those layers
// ever start serving polygons; the empty geometry case is filtered in
// fetchParcelGeometries.
const ALLPARCELS_YEAR_LAYERS = [
  [2024, 32], [2023, 31], [2022, 30], [2021, 29], [2020, 27],
  [2019, 22], [2018, 20], [2017, 17], [2016, 18], [2015, 5],
  [2014, 6],  [2013, 7],  [2012, 8],
];

// Reverse of canonical_apn: strip the leading zero from a 3-digit third segment
// (NNN-NNN-0DD -> NNN-NNN-DD). Mirrors `el_depad` in utils.py.
// Returns null if no depadding is possible (i.e. already in 2-digit form, or
// a non-standard format like Douglas County's long-form APN).
const EL_3D_RE = /^(\d{3}-\d{2,3})-0(\d{2})$/;
function depadApn(canon) {
  if (!canon) return null;
  const m = EL_3D_RE.exec(canon);
  return m ? `${m[1]}-${m[2]}` : null;
}

// Map symbology per role. Seed parcel is the standout - solid fill + thick
// orange outline. Other lineage parcels are outline-only with role color so
// the seed always reads as the focal point.
const MAP_SYMBOL = {
  self:       { fill: [0, 59, 113, 0.70],  outline: [232, 119, 34, 1.0], width: 3.5 },  // navy fill, ORANGE outline (highlight)
  ancestor:   { fill: [0, 114, 206, 0.10], outline: [0, 114, 206, 1.0], width: 2 },     // blue outline, very light blue fill
  descendant: { fill: [232, 119, 34, 0.12], outline: [232, 119, 34, 1.0], width: 2 },   // orange outline, very light orange fill
};

// ─── 2. canonical_apn (JS port of utils.canonical_apn) ──────────────────────
// Python source: r"^(\d{3})-(\d{3})-(\d{2,3})$" then zfill(3) on segment 3.
// Other formats: pass through after .strip(). Empty/null -> null.
const STD_APN_RE = /^(\d{3})-(\d{3})-(\d{2,3})$/;
function canonicalApn(raw) {
  if (raw == null) return null;
  const s = String(raw).trim();
  if (!s) return null;
  const m = STD_APN_RE.exec(s);
  if (!m) return s;
  return `${m[1]}-${m[2]}-${m[3].padStart(3, '0')}`;
}

const CANONICAL_TEST_VECTORS = [
  ['015-331-04',      '015-331-004'],
  ['015-331-004',     '015-331-004'],
  ['007-011-23',      '007-011-023'],
  ['023-111-37',      '023-111-037'],
  ['048-041-15',      '048-041-015'],
  ['1418-03-301-010', '1418-03-301-010'],
  ['  132-231-10  ',  '132-231-010'],
  ['',                null],
  [null,              null],
];

// ─── 3. Data loader ─────────────────────────────────────────────────────────
async function loadData() {
  setLoadingStatus('Fetching JSON');
  const t0 = performance.now();
  const resp = await fetch(DATA_URL, { cache: 'no-cache' });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  setLoadingProgress(40);
  setLoadingStatus('Parsing');
  const json = await resp.json();
  setLoadingProgress(80);
  state.edges = json.edges;
  state.apns  = json.apns;
  state.meta  = json.meta;
  setLoadingProgress(100);
  setLoadingStatus(`${state.meta.n_nodes.toLocaleString()} APNs, ${state.meta.n_edges.toLocaleString()} edges`);
  const t1 = performance.now();
  console.info(`Loaded genealogy_solver.json in ${(t1 - t0).toFixed(0)} ms`);
  await sleep(150);
  hideLoading();
}

// ─── 4. Graph walk ─────────────────────────────────────────────────────────
/**
 * Bidirectional BFS from seed. Returns the full reachable component (treating
 * the graph as undirected for the union of ancestors + descendants), with
 * hop distance and the predecessor edge for each non-seed node.
 *
 * @param {string} seed canonical APN
 * @param {boolean} applyFilter when true, only edges with ab=1 are traversed
 * @returns {{found, seed, members, ancestors, descendants, edgeIdxs, maxUp, maxDn}}
 */
function walkGenealogy(seed, applyFilter) {
  const result = {
    found: false, seed, members: [], ancestors: [], descendants: [],
    edgeIdxs: new Set(), maxUp: 0, maxDn: 0,
  };
  const seedNode = state.apns[seed];
  // We can still "look up" an APN that's not in the graph - we'll show only the seed row.
  // Treat as "found" if either the node exists OR seed isn't bare-empty.
  result.found = !!seedNode;

  // Always include the seed row
  result.members.push({ apn: seed, role: 'self', hop: 0, viaEdge: null });

  if (!seedNode) return result;

  // Upstream BFS (incoming edges = ancestors)
  bfs(seed, 'in', applyFilter, result, 'ancestor');
  // Downstream BFS (outgoing edges = descendants)
  bfs(seed, 'out', applyFilter, result, 'descendant');

  // Sort: self, ancestors (oldest hop last), descendants
  result.members.sort((a, b) => {
    const roleOrder = { self: 0, ancestor: 1, descendant: 2 };
    if (a.role !== b.role) return roleOrder[a.role] - roleOrder[b.role];
    if (a.hop !== b.hop) return a.hop - b.hop;
    return a.apn.localeCompare(b.apn);
  });

  result.ancestors   = result.members.filter(m => m.role === 'ancestor');
  result.descendants = result.members.filter(m => m.role === 'descendant');
  result.maxUp = result.ancestors.reduce((m, x) => Math.max(m, x.hop), 0);
  result.maxDn = result.descendants.reduce((m, x) => Math.max(m, x.hop), 0);
  return result;
}

function bfs(seed, direction, applyFilter, result, role) {
  const visited = new Set([seed]);
  // queue items: {apn, hop, pathFromSeed: [apn, ...]}
  const queue = [{ apn: seed, hop: 0 }];
  while (queue.length) {
    const { apn, hop } = queue.shift();
    const node = state.apns[apn];
    if (!node) continue;
    const edgeIdxs = direction === 'in' ? (node.pi || []) : (node.po || []);
    for (const ei of edgeIdxs) {
      const edge = state.edges[ei];
      if (!edge) continue;
      if (applyFilter && !edge.ab) continue;
      const neighbor = direction === 'in' ? edge.o : edge.n;
      if (visited.has(neighbor)) continue;
      visited.add(neighbor);
      result.edgeIdxs.add(ei);
      result.members.push({
        apn: neighbor,
        role,
        hop: hop + 1,
        viaEdge: ei,
        viaApn: apn,
      });
      queue.push({ apn: neighbor, hop: hop + 1 });
    }
  }
}

/**
 * For batch mode: summarize a walk result into a single row of metrics.
 */
function summarizeWalk(rawApn, applyFilter) {
  const seed = canonicalApn(rawApn);
  if (!seed) {
    return { rawApn, seed: null, found: 'no', active: 'no', size: 0, up: 0, dn: 0,
             earliest: null, latest: null, types: '', leaves: '', units: 0,
             counties: '', jurisdictions: '' };
  }
  const w = walkGenealogy(seed, applyFilter);
  const seedNode = state.apns[seed];
  const active = seedNode && seedNode.in ? 'yes' : 'no';
  if (!w.found && !seedNode) {
    return { rawApn, seed, found: 'no', active, size: 0, up: 0, dn: 0,
             earliest: null, latest: null, types: '', leaves: '', units: 0,
             counties: '', jurisdictions: '' };
  }
  // Aggregates across the component
  let units = 0, earliest = null, latest = null;
  const types = new Set(), counties = new Set(), juris = new Set();
  const allApns = w.members.map(m => m.apn);
  for (const a of allApns) {
    const n = state.apns[a];
    if (!n) continue;
    if (n.ru) units += n.ru;
    if (n.co) counties.add(n.co);
    if (n.ju) juris.add(n.ju);
  }
  for (const ei of w.edgeIdxs) {
    const e = state.edges[ei];
    if (e.t) types.add(e.t);
    if (e.y != null) {
      if (earliest == null || e.y < earliest) earliest = e.y;
      if (latest   == null || e.y > latest)   latest   = e.y;
    }
  }
  // Terminal descendants = members whose outgoing applied edges are 0 in the walk's filter
  const leafSet = w.descendants.filter(m => {
    const n = state.apns[m.apn];
    if (!n || !n.po) return true;
    return !n.po.some(ei => {
      const e = state.edges[ei];
      return e && (!applyFilter || e.ab);
    });
  });
  return {
    rawApn, seed,
    found: w.found ? 'yes' : 'no',
    active,
    size: w.members.length,
    up: w.maxUp,
    dn: w.maxDn,
    earliest, latest,
    types: [...types].sort().join(', '),
    leaves: leafSet.slice(0, 8).map(m => m.apn).join('; ') + (leafSet.length > 8 ? ` (+${leafSet.length - 8})` : ''),
    units,
    counties: [...counties].sort().join(', '),
    jurisdictions: [...juris].sort().join(', '),
  };
}

// ─── 5. UI rendering ────────────────────────────────────────────────────────
function renderKPIs(walk) {
  const kApn       = document.getElementById('kpi-apn');
  const kApnSub    = document.getElementById('kpi-apn-sub');
  const kComp      = document.getElementById('kpi-component');
  const kCompSub   = document.getElementById('kpi-component-sub');
  const kDepth     = document.getElementById('kpi-depth');
  const kDepthSub  = document.getElementById('kpi-depth-sub');
  const kUnits     = document.getElementById('kpi-units');
  const kUnitsSub  = document.getElementById('kpi-units-sub');
  if (!walk) {
    [kApn, kComp, kDepth, kUnits].forEach(el => { el.textContent = '-'; el.classList.add('muted'); });
    kApnSub.textContent  = 'enter an APN to begin';
    kCompSub.textContent = 'APNs reachable from the seed';
    kDepthSub.textContent = 'max ancestor / descendant hops';
    kUnitsSub.textContent = 'sum across component';
    return;
  }
  const seedNode = state.apns[walk.seed];
  [kApn, kComp, kDepth, kUnits].forEach(el => el.classList.remove('muted'));
  kApn.textContent = walk.seed;
  kApnSub.textContent = seedNode && seedNode.in
    ? `Active in 2025${seedNode.co ? ' · ' + seedNode.co : ''}`
    : 'Not in 2025 PDH';
  kComp.textContent = walk.members.length.toLocaleString();
  kCompSub.textContent = walk.found
    ? `${walk.ancestors.length} ancestors · ${walk.descendants.length} descendants`
    : 'No genealogy events recorded';
  kDepth.textContent = `${walk.maxUp}↑ / ${walk.maxDn}↓`;
  kDepthSub.textContent = walk.maxUp + walk.maxDn === 0 ? 'isolated APN' : 'max hops in each direction';
  let units = 0, tau = 0;
  for (const m of walk.members) {
    const n = state.apns[m.apn];
    if (!n) continue;
    if (n.ru) units += n.ru;
    if (n.tu) tau += n.tu;
  }
  kUnits.textContent = units.toLocaleString();
  kUnitsSub.textContent = tau ? `+ ${tau.toLocaleString()} TAU` : 'residential units';
}

function renderXref(seed) {
  const node = state.apns[seed];
  const wrap = document.getElementById('xref-panel');
  if (!node) {
    wrap.innerHTML = `
      <table class="xref-table">
        <tr><th>APN</th><td class="apn">${escHtml(seed)}</td></tr>
        <tr><td colspan="2" style="color:var(--text-light); padding-top:14px">Not in the 2025 parcel index. May be a historical APN that has since split or been renamed.</td></tr>
      </table>
    `;
    return;
  }
  const rows = [
    ['APN',               `<span class="apn">${escHtml(seed)}</span>`],
    ['Active in 2025',    node.in ? 'Yes' : 'No'],
    ['County',            node.co || '—'],
    ['Jurisdiction',      node.ju || '—'],
    ['Residential units', node.ru != null ? node.ru : '—'],
    ['Tourist (TAU)',     node.tu != null ? node.tu : '—'],
    ['Commercial sqft',   node.cf != null ? node.cf.toLocaleString() : '—'],
    ['Year built',        node.yb != null ? node.yb : '—'],
    ['Address',           node.ad || '—'],
  ];
  wrap.innerHTML = '<table class="xref-table">'
    + rows.map(([k, v]) => `<tr><th>${k}</th><td>${v}</td></tr>`).join('')
    + '</table>';
}

// ─── 5b. Component AG Grid ──────────────────────────────────────────────────
function buildComponentGrid() {
  const div = document.getElementById('component-grid');
  div.innerHTML = '';
  const cols = [
    { headerName: 'Role',     field: 'role',  width: 110,
      cellRenderer: (p) => `<span class="role-badge role-${p.value}">${p.value}</span>` },
    { headerName: 'APN',      field: 'apn',   width: 130,
      cellStyle: { fontFamily: 'Consolas, monospace' } },
    { headerName: 'Hop',      field: 'hop',   width: 70,  type: 'numericColumn' },
    { headerName: 'Event',    field: 'event', width: 100,
      cellRenderer: (p) => p.value ? `<span class="event-badge event-${p.value}">${p.value}</span>` : '' },
    { headerName: 'Year',     field: 'year',  width: 80,  type: 'numericColumn' },
    { headerName: 'Source',   field: 'source',width: 95,
      cellRenderer: (p) => p.value ? `<span class="source-badge source-${p.value}">${p.value}</span>` : '' },
    { headerName: 'Applied',  field: 'applied', width: 90,
      cellRenderer: (p) => p.value === '✓'
        ? '<span class="applied-mark">✓</span>'
        : (p.value === '—' ? '<span class="applied-mark no">—</span>' : '') },
    { headerName: 'Res 2025', field: 'res',   width: 95,  type: 'numericColumn' },
    { headerName: 'TAU 2025', field: 'tau',   width: 95,  type: 'numericColumn' },
    { headerName: 'Year built', field: 'yb',  width: 105, type: 'numericColumn' },
    { headerName: 'County',   field: 'co',    width: 80 },
    { headerName: 'Jurisdiction', field: 'ju', width: 110 },
    { headerName: 'Active 2025', field: 'active', width: 105 },
    { headerName: 'Address',  field: 'ad',    flex: 1, minWidth: 200 },
  ];
  const opts = {
    columnDefs: cols,
    rowData: [],
    defaultColDef: { sortable: true, resizable: true, filter: true },
    rowSelection: 'single',
    onRowClicked: (ev) => {
      if (ev.data && ev.data.apn && ev.data.role !== 'self') {
        setSeedInput(ev.data.apn);
        lookupSingle();
      }
    },
  };
  state.componentGrid = agGrid.createGrid(div, opts);
}

function renderComponentGrid(walk, applyFilter) {
  if (!state.componentGrid) buildComponentGrid();
  const rows = walk.members.map((m) => {
    const node = state.apns[m.apn] || {};
    let event = '', year = '', source = '', applied = '';
    if (m.viaEdge != null) {
      const e = state.edges[m.viaEdge];
      event   = e.t || 'empty';
      year    = e.y != null ? e.y : '';
      source  = e.s || '';
      applied = e.ab ? '✓' : '—';
    }
    return {
      role:   m.role,
      apn:    m.apn,
      hop:    m.hop,
      event, year, source, applied,
      res:    node.ru != null ? node.ru : '',
      tau:    node.tu != null ? node.tu : '',
      yb:     node.yb != null ? node.yb : '',
      co:     node.co || '',
      ju:     node.ju || '',
      active: node.in ? 'yes' : 'no',
      ad:     node.ad || '',
    };
  });
  state.componentGrid.setGridOption('rowData', rows);
}

// ─── 5c. Vertical lineage diagram (custom SVG) ──────────────────────────────
function renderLineageDiagram(walk) {
  const wrap = document.getElementById('lineage-diagram');
  if (!walk.members.length) {
    wrap.innerHTML = `<div class="empty-state"><div class="glyph">&#x21CC;</div><div>Look up an APN to see its lineage.</div></div>`;
    return;
  }
  if (walk.members.length === 1) {
    const seedNode = state.apns[walk.seed] || {};
    wrap.innerHTML = `<div class="empty-state" style="text-align:left">
      <div><strong>${escHtml(walk.seed)}</strong> has no recorded genealogy events.</div>
      <div style="font-size:0.74rem; margin-top:6px">${seedNode.in ? 'Currently active in 2025.' : 'Not in 2025 PDH - possibly a historical APN or outside the index.'}</div>
    </div>`;
    return;
  }

  // Group by hop, separating ancestors (hop > 0, role=ancestor) and descendants
  const upByHop = {};   // hop -> [member]
  const dnByHop = {};
  walk.members.forEach((m) => {
    if (m.role === 'ancestor')   (upByHop[m.hop]   ??= []).push(m);
    if (m.role === 'descendant') (dnByHop[m.hop]   ??= []).push(m);
  });

  // Build rows: deepest ancestor first (top), descending hop, seed, then descendants
  const rows = [];
  const upHops = Object.keys(upByHop).map(Number).sort((a, b) => b - a);
  upHops.forEach(h => rows.push({ kind: 'ancestor',   hop: h, items: upByHop[h] }));
  rows.push({ kind: 'self', hop: 0, items: [{ apn: walk.seed, role: 'self', hop: 0 }] });
  const dnHops = Object.keys(dnByHop).map(Number).sort((a, b) => a - b);
  dnHops.forEach(h => rows.push({ kind: 'descendant', hop: h, items: dnByHop[h] }));

  // Layout constants
  const NODE_W = 130, NODE_H = 44;
  const ROW_GAP = 70, COL_GAP = 14;
  const PAD_X = 24, PAD_Y = 16;

  // Determine row widths (with fanout collapse)
  const rowLayouts = rows.map(r => {
    const collapsed = r.items.length > FANOUT_COLLAPSE_AT;
    const visible = collapsed ? r.items.slice(0, FANOUT_COLLAPSE_AT) : r.items;
    return { ...r, collapsed, hiddenCount: r.items.length - visible.length, visible };
  });
  const maxCols = Math.max(...rowLayouts.map(r => r.visible.length + (r.collapsed ? 1 : 0)));
  const innerW = maxCols * NODE_W + (maxCols - 1) * COL_GAP;
  const svgW = innerW + PAD_X * 2;
  const svgH = rowLayouts.length * NODE_H + (rowLayouts.length - 1) * ROW_GAP + PAD_Y * 2;

  // Position each node and remember its center for edge drawing
  const nodePos = {};  // apn -> {cx, cy}
  rowLayouts.forEach((row, ri) => {
    const totalCells = row.visible.length + (row.collapsed ? 1 : 0);
    const totalW = totalCells * NODE_W + (totalCells - 1) * COL_GAP;
    const startX = PAD_X + (innerW - totalW) / 2;
    const cy = PAD_Y + ri * (NODE_H + ROW_GAP) + NODE_H / 2;
    row.visible.forEach((m, i) => {
      const x = startX + i * (NODE_W + COL_GAP);
      m._x = x; m._y = cy - NODE_H / 2;
      m._cx = x + NODE_W / 2; m._cy = cy;
      nodePos[m.apn] = { cx: m._cx, cy: m._cy };
    });
    if (row.collapsed) {
      const x = startX + row.visible.length * (NODE_W + COL_GAP);
      row._collapseX = x;
      row._collapseY = cy - NODE_H / 2;
    }
  });

  // Build SVG
  const parts = [];
  parts.push(`<svg viewBox="0 0 ${svgW} ${svgH}" width="${svgW}" height="${svgH}">`);

  // Edges first (so nodes overlay)
  walk.edgeIdxs.forEach(ei => {
    const e = state.edges[ei];
    const a = nodePos[e.o], b = nodePos[e.n];
    if (!a || !b) return;   // collapsed endpoint - skip
    const y1 = a.cy + NODE_H / 2, y2 = b.cy - NODE_H / 2;
    const my = (y1 + y2) / 2;
    const d = `M ${a.cx} ${y1} C ${a.cx} ${my}, ${b.cx} ${my}, ${b.cx} ${y2}`;
    const cls = ['diagram-edge', `event-${e.t || 'empty'}`, e.ab ? '' : 'not-applied'].filter(Boolean).join(' ');
    parts.push(`<path class="${cls}" d="${d}"/>`);
    if (e.y != null || e.t) {
      const lx = (a.cx + b.cx) / 2;
      const ly = my - 4;
      const label = `${e.t || ''}${e.y != null ? ' · ' + e.y : ''}`;
      parts.push(`<text class="diagram-edge-label" x="${lx}" y="${ly}" text-anchor="middle">${escHtml(label)}</text>`);
    }
  });

  // Nodes
  rowLayouts.forEach(row => {
    row.visible.forEach(m => {
      const node = state.apns[m.apn] || {};
      const sub = m.role === 'self'
        ? (node.in ? `${node.ru || 0} units` : 'not in 2025')
        : `hop ${m.hop}`;
      parts.push(`<g class="diagram-node role-${m.role}" data-apn="${escHtml(m.apn)}" tabindex="0">`);
      parts.push(`  <rect x="${m._x}" y="${m._y}" width="${NODE_W}" height="${NODE_H}"/>`);
      parts.push(`  <text class="label-apn" x="${m._cx}" y="${m._y + 18}" text-anchor="middle">${escHtml(m.apn)}</text>`);
      parts.push(`  <text class="label-sub" x="${m._cx}" y="${m._y + 33}" text-anchor="middle">${escHtml(sub)}</text>`);
      parts.push(`</g>`);
    });
    if (row.collapsed) {
      const cx = row._collapseX + NODE_W / 2;
      const cy = row._collapseY + NODE_H / 2;
      parts.push(`<g class="diagram-node role-collapsed" data-hop="${row.hop}" data-kind="${row.kind}">`);
      parts.push(`  <rect x="${row._collapseX}" y="${row._collapseY}" width="${NODE_W}" height="${NODE_H}"/>`);
      parts.push(`  <text class="label-apn" x="${cx}" y="${row._collapseY + 20}" text-anchor="middle">+${row.hiddenCount} more</text>`);
      parts.push(`  <text class="label-sub" x="${cx}" y="${row._collapseY + 35}" text-anchor="middle">see table</text>`);
      parts.push(`</g>`);
    }
  });

  parts.push('</svg>');
  wrap.innerHTML = parts.join('');

  // Wire up click-to-reseed on nodes (not collapsed cells)
  wrap.querySelectorAll('.diagram-node[data-apn]').forEach(g => {
    g.addEventListener('click', () => {
      const apn = g.getAttribute('data-apn');
      if (apn && apn !== walk.seed) { setSeedInput(apn); lookupSingle(); }
    });
  });
}

// ─── 5d. ArcGIS map (parcel footprints colored by role) ─────────────────────
function initMap() {
  if (state.mapInitPromise) return state.mapInitPromise;
  state.mapInitPromise = new Promise((resolve, reject) => {
    if (typeof require !== 'function') {
      console.warn('ArcGIS SDK not loaded; map disabled');
      return resolve(null);
    }
    require([
      'esri/Map',
      'esri/views/MapView',
      'esri/layers/GraphicsLayer',
      'esri/Graphic',
      'esri/rest/query',
      'esri/rest/support/Query',
    ], function (Map, MapView, GraphicsLayer, Graphic, queryRest, Query) {
      state.mapModules = { Map, MapView, GraphicsLayer, Graphic, queryRest, Query };
      const map = new Map({ basemap: 'gray-vector' });
      const view = new MapView({
        container: 'genealogy-map',
        map,
        center: [-120.0, 39.0],   // Lake Tahoe Basin
        zoom: 9,
        constraints: { snapToZoom: false },
      });
      const layer = new GraphicsLayer();
      map.add(layer);
      state.map = { map, view, layer };
      view.when(() => {
        // Click on a parcel = re-seed the lookup
        view.on('click', (event) => {
          view.hitTest(event).then((response) => {
            const hit = response.results.find(r => r.graphic && r.graphic.attributes && r.graphic.attributes._apnCanon);
            if (hit) {
              const apn = hit.graphic.attributes._apnCanon;
              if (apn !== state.currentSeed) {
                setSeedInput(apn);
                lookupSingle();
              }
            }
          });
        });
        console.info('Map initialized');
        resolve(state.map);
      }, reject);
    });
  });
  return state.mapInitPromise;
}

/**
 * Fetch geometries for `apns` (canonical form) from a given layer URL via
 * the ArcGIS SDK's `queryFeatures` (handles CORS + reprojection cleanly).
 * Queries BOTH the canonical and pre-2018 depadded variants of each APN,
 * since AllParcels stores many in the unpadded form. Returns a
 * Map(canonical_apn -> Esri-Geometry).
 */
async function fetchParcelGeometries(layerUrl, apns) {
  if (!apns.length) return new Map();
  const { queryRest, Query } = state.mapModules;

  // Build expanded query list: canonical + depadded variants
  const queryVals = new Set();
  for (const a of apns) {
    queryVals.add(a);
    const d = depadApn(a);
    if (d) queryVals.add(d);
  }
  const queryList = [...queryVals];

  // Chunk to keep IN-list manageable
  const CHUNK = 80;
  const got = new Map();
  for (let i = 0; i < queryList.length; i += CHUNK) {
    const chunk = queryList.slice(i, i + CHUNK);
    const inList = chunk.map(a => `'${a.replace(/'/g, "''")}'`).join(',');
    const query = new Query({
      where: `APN IN (${inList})`,
      outFields: ['APN'],
      returnGeometry: true,
      outSpatialReference: { wkid: 4326 },
    });
    try {
      const result = await queryRest.executeQueryJSON(layerUrl, query);
      for (const feat of (result.features || [])) {
        const rawApn = feat.attributes && feat.attributes.APN;
        const apnCanon = canonicalApn(rawApn);
        if (!apnCanon || got.has(apnCanon)) continue;
        if (feat.geometry && feat.geometry.rings && feat.geometry.rings.length) {
          got.set(apnCanon, feat.geometry);
        }
      }
    } catch (err) {
      console.warn(`Parcel query failed for ${layerUrl}:`, err && err.message || err);
    }
  }
  return got;
}

async function renderMap(walk) {
  const statusEl = document.getElementById('map-status');
  statusEl.innerHTML = '<span>Loading parcel footprints&hellip;</span>';
  try {
    await initMap();
  } catch (e) {
    statusEl.innerHTML = `<span style="color:var(--trpa-brick)">Map failed to initialize: ${escHtml(e.message || String(e))}</span>`;
    return;
  }
  if (!state.map) return;
  const { Graphic } = state.mapModules;
  const { view, layer } = state.map;
  layer.removeAll();

  if (!walk.members.length) {
    statusEl.innerHTML = '<span>Enter an APN to load its parcels onto the map.</span>';
    return;
  }

  // Role lookup
  const roleByApn = new Map();
  walk.members.forEach(m => roleByApn.set(m.apn, m.role));
  const apnList = walk.members.map(m => m.apn);

  // 1. Active layer (primary source - only one that serves polygon geometry)
  let geoms = await fetchParcelGeometries(ALLPARCELS_ACTIVE_URL, apnList);

  // 2. Year-layer fallback for any misses (currently returns no geometry from
  //    the AllParcels MapServer per 2026-05 testing; kept for forward
  //    compatibility with a future Parcel_Development_History service)
  let missing = apnList.filter(a => !geoms.has(a));
  if (missing.length) {
    for (const [year, layerIdx] of ALLPARCELS_YEAR_LAYERS) {
      if (!missing.length) break;
      const yearUrl = `${ALLPARCELS_BASE}/${layerIdx}`;
      const got = await fetchParcelGeometries(yearUrl, missing);
      got.forEach((g, a) => geoms.set(a, g));
      missing = missing.filter(a => !geoms.has(a));
    }
  }

  // 3. Build graphics, render, zoom
  const graphics = [];
  // Sort so seed renders LAST (on top); ancestors/descendants underneath
  const orderedApns = [...geoms.keys()].sort((a, b) => {
    const ra = roleByApn.get(a), rb = roleByApn.get(b);
    if (ra === 'self') return 1;
    if (rb === 'self') return -1;
    return 0;
  });

  for (const apn of orderedApns) {
    const geom = geoms.get(apn);
    const role = roleByApn.get(apn) || 'descendant';
    const sym = MAP_SYMBOL[role];
    const node = state.apns[apn] || {};
    const g = new Graphic({
      geometry: {
        type: 'polygon',
        rings: geom.rings,
        spatialReference: geom.spatialReference || { wkid: 4326 },
      },
      symbol: {
        type: 'simple-fill',
        color: sym.fill,
        outline: { color: sym.outline, width: sym.width },
      },
      attributes: {
        APN: apn,
        _apnCanon: apn,
        Role: role,
        ResUnits: node.ru != null ? node.ru : '',
        YearBuilt: node.yb != null ? node.yb : '',
        Jurisdiction: node.ju || '',
      },
      popupTemplate: {
        title: '{APN}',
        content: [
          {
            type: 'fields',
            fieldInfos: [
              { fieldName: 'Role',          label: 'Role' },
              { fieldName: 'ResUnits',      label: 'Residential units (2025)' },
              { fieldName: 'YearBuilt',     label: 'Year built' },
              { fieldName: 'Jurisdiction',  label: 'Jurisdiction' },
            ],
          },
          { type: 'text', text: 'Click parcel to re-seed.' },
        ],
      },
    });
    layer.add(g);
    graphics.push(g);
  }

  // Zoom: pass the graphics array directly - the SDK computes the union
  // extent and reprojects to the view's SR for us. Pad ~20% so the parcels
  // don't kiss the card edges.
  if (graphics.length) {
    view.goTo({ target: graphics, padding: 40 }, { duration: 700 })
      .catch(err => console.warn('goTo failed:', err && err.message || err));
  } else {
    // No matches anywhere - fall back to the Tahoe Basin overview
    view.goTo({ center: [-120.0, 39.0], zoom: 10 }, { duration: 0 }).catch(() => {});
  }

  // Status row
  const n_found = geoms.size, n_total = apnList.length;
  const legend = `<span><span class="legend-swatch legend-self"></span>Seed (current)</span>`
    + `<span><span class="legend-swatch legend-ancestor"></span>Ancestor</span>`
    + `<span><span class="legend-swatch legend-descendant"></span>Descendant</span>`;
  const missingTxt = missing.length
    ? `<span><strong>${missing.length}</strong> not in AllParcels: <span class="map-missing-list">${missing.slice(0, 6).map(escHtml).join(', ')}${missing.length > 6 ? `, +${missing.length - 6} more` : ''}</span></span>`
    : '';
  statusEl.innerHTML = `<span>Mapped <strong>${n_found}</strong> of <strong>${n_total}</strong> APNs.</span>${legend}${missingTxt}`;
  console.info(`Map: ${n_found}/${n_total} parcels rendered`);
}

// ─── 6. Single APN tab wiring ───────────────────────────────────────────────
function setSeedInput(apn) {
  const el = document.getElementById('apn-input');
  el.value = apn;
  el.classList.remove('invalid');
}

function lookupSingle() {
  const raw = document.getElementById('apn-input').value;
  const applyFilter = document.getElementById('filter-toggle').checked;
  const seed = canonicalApn(raw);
  if (!seed) {
    toast('Enter an APN to look up.', 'warn');
    document.getElementById('apn-input').classList.add('invalid');
    return;
  }
  document.getElementById('apn-input').classList.remove('invalid');

  // Diagnostic flag if not in graph AND not in PDH
  const inGraph = !!state.apns[seed];
  if (!inGraph) {
    // Still render the seed-only state so the user gets feedback
    toast(`${seed} not found in 2025 parcel index or genealogy graph.`, 'warn');
  }

  const walk = walkGenealogy(seed, applyFilter);
  state.currentSeed = seed;
  renderKPIs(walk);
  renderXref(seed);
  renderLineageDiagram(walk);
  renderComponentGrid(walk, applyFilter);
  // Fire-and-forget; the map renders async (REST query to AllParcels)
  renderMap(walk).catch(err => console.warn('Map render failed:', err));
}

// ─── 7. Batch CSV tab wiring ────────────────────────────────────────────────
function buildBatchGrid() {
  const div = document.getElementById('batch-grid');
  div.innerHTML = '';
  const cols = [
    { headerName: 'Input APN',    field: 'rawApn', width: 130,
      cellStyle: { fontFamily: 'Consolas, monospace' } },
    { headerName: 'Canonical',    field: 'seed',   width: 130,
      cellStyle: { fontFamily: 'Consolas, monospace' } },
    { headerName: 'Found',        field: 'found',  width: 80 },
    { headerName: 'Active 2025',  field: 'active', width: 105 },
    { headerName: 'Component size', field: 'size', width: 130, type: 'numericColumn' },
    { headerName: 'Ancestor depth', field: 'up',   width: 130, type: 'numericColumn' },
    { headerName: 'Descendant depth', field: 'dn', width: 150, type: 'numericColumn' },
    { headerName: 'Earliest event', field: 'earliest', width: 130, type: 'numericColumn' },
    { headerName: 'Latest event',   field: 'latest',   width: 120, type: 'numericColumn' },
    { headerName: 'Event types', field: 'types',  width: 140 },
    { headerName: 'Sum units 2025', field: 'units', width: 130, type: 'numericColumn' },
    { headerName: 'Counties',    field: 'counties', width: 110 },
    { headerName: 'Jurisdictions', field: 'jurisdictions', width: 130 },
    { headerName: 'Leaf APNs',   field: 'leaves', flex: 1, minWidth: 200,
      cellStyle: { fontFamily: 'Consolas, monospace', fontSize: '0.75rem' } },
  ];
  const opts = {
    columnDefs: cols,
    rowData: [],
    defaultColDef: { sortable: true, resizable: true, filter: true },
    rowSelection: 'single',
    onRowClicked: (ev) => {
      if (ev.data && ev.data.seed) {
        switchTab('single', document.getElementById('btn-tab-single'));
        setSeedInput(ev.data.seed);
        lookupSingle();
      }
    },
  };
  state.batchGrid = agGrid.createGrid(div, opts);
}

function processBatch(rawApns) {
  if (!state.batchGrid) buildBatchGrid();
  const applyFilter = document.getElementById('filter-toggle-batch').checked;
  const total = rawApns.length;
  const summary = document.getElementById('batch-summary');
  const progress = document.getElementById('progress-wrap');
  const fill = document.getElementById('progress-fill');
  const rows = [];
  let i = 0;
  let hits = 0, misses = 0;
  progress.style.display = total > 100 ? 'block' : 'none';

  function chunk() {
    const start = performance.now();
    while (i < total && performance.now() - start < 30) {
      const row = summarizeWalk(rawApns[i], applyFilter);
      if (row.found === 'yes') hits++; else misses++;
      rows.push(row);
      i++;
    }
    fill.style.width = `${(i / total) * 100}%`;
    if (i < total) {
      summary.innerHTML = `<span>Processed <strong>${i.toLocaleString()}</strong> / ${total.toLocaleString()}</span>`;
      if (window.requestIdleCallback) requestIdleCallback(chunk, { timeout: 100 });
      else setTimeout(chunk, 0);
    } else {
      state.batchGrid.setGridOption('rowData', rows);
      state.batchRows = rows;
      progress.style.display = 'none';
      summary.innerHTML = `<span>Input rows: <strong>${total.toLocaleString()}</strong></span>
        <span>Hits in graph: <strong>${hits.toLocaleString()}</strong></span>
        <span>Misses: <strong>${misses.toLocaleString()}</strong></span>`;
      document.getElementById('btn-download').disabled = false;
    }
  }
  chunk();
}

function runPaste() {
  const text = document.getElementById('paste-area').value;
  const apns = text.split(/[\r\n,]+/).map(s => s.trim()).filter(Boolean);
  if (!apns.length) {
    toast('Paste some APNs first (one per line).', 'warn');
    return;
  }
  processBatch(apns);
  document.getElementById('paste-status').innerHTML = `Queued <strong>${apns.length}</strong> APN(s).`;
}

/** Minimal CSV parser (handles quoted fields with embedded commas). */
function parseCSV(text) {
  const rows = [];
  let i = 0, field = '', row = [], inQuote = false;
  while (i < text.length) {
    const c = text[i];
    if (inQuote) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i += 2; continue; }
        inQuote = false; i++; continue;
      }
      field += c; i++; continue;
    }
    if (c === '"') { inQuote = true; i++; continue; }
    if (c === ',') { row.push(field); field = ''; i++; continue; }
    if (c === '\n' || c === '\r') {
      if (field || row.length) { row.push(field); rows.push(row); row = []; field = ''; }
      if (c === '\r' && text[i + 1] === '\n') i++;
      i++; continue;
    }
    field += c; i++;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  return rows;
}

function detectApnColumn(headers) {
  const norm = headers.map(h => String(h || '').trim().toLowerCase());
  const preferred = ['apn', 'apn_canon', 'parcel', 'parcel_id', 'apn_raw'];
  for (const p of preferred) {
    const idx = norm.indexOf(p);
    if (idx >= 0) return idx;
  }
  return 0;   // fall back to first column
}

function handleFile(file) {
  if (!file) return;
  if (file.size > 50 * 1024 * 1024) {
    toast('File too large (>50MB).', 'warn');
    return;
  }
  const reader = new FileReader();
  reader.onload = (e) => {
    const text = e.target.result;
    const rows = parseCSV(text);
    if (!rows.length) { toast('Empty CSV.', 'warn'); return; }
    // Decide if first row is a header (heuristic: contains non-APN-looking strings)
    const first = rows[0];
    const firstLooksLikeApn = first.some(c => /^\d{3}-\d{3}-/.test(String(c).trim()));
    let apnColIdx = 0, dataRows = rows;
    if (!firstLooksLikeApn) {
      apnColIdx = detectApnColumn(first);
      dataRows = rows.slice(1);
    }
    const apns = dataRows.map(r => r[apnColIdx]).filter(Boolean);
    if (apns.length > 20000) {
      toast(`Truncated to first 20,000 of ${apns.length.toLocaleString()} rows.`, 'warn');
      apns.length = 20000;
    }
    if (!apns.length) { toast('No parseable APN values in the file.', 'warn'); return; }
    document.getElementById('paste-status').textContent = '';
    processBatch(apns);
  };
  reader.readAsText(file);
}

function downloadBatchCsv() {
  if (!state.batchRows || !state.batchRows.length) return;
  const headers = ['rawApn','seed','found','active','size','up','dn','earliest','latest','types','units','counties','jurisdictions','leaves'];
  const lines = [headers.join(',')];
  for (const r of state.batchRows) {
    const vals = headers.map(h => {
      const v = r[h];
      if (v == null) return '';
      const s = String(v);
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    });
    lines.push(vals.join(','));
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'genealogy_solver_results.csv';
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

// ─── 8. Tab switcher + helpers ──────────────────────────────────────────────
function switchTab(name, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
  // Lazy build the batch grid the first time the tab is opened
  if (name === 'batch' && !state.batchGrid) buildBatchGrid();
}

function escHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function setLoadingProgress(p) { document.getElementById('loading-bar-fill').style.width = p + '%'; }
function setLoadingStatus(s)   { document.getElementById('loading-status').textContent = s; }
function hideLoading()         { document.getElementById('loading-overlay').style.display = 'none'; }
let _toastTimer;
function toast(msg, kind) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.remove('warn');
  if (kind === 'warn') el.classList.add('warn');
  el.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), 2800);
}

// ─── 9. Self-test ───────────────────────────────────────────────────────────
function runSelfTests() {
  console.group('Genealogy Solver self-tests');
  let pass = 0, fail = 0;
  // canonical_apn test vectors
  for (const [inp, expected] of CANONICAL_TEST_VECTORS) {
    const actual = canonicalApn(inp);
    if (actual === expected) { pass++; }
    else { fail++; console.warn(`canonicalApn(${JSON.stringify(inp)}) = ${JSON.stringify(actual)}, expected ${JSON.stringify(expected)}`); }
  }
  // Functional checks against known APNs
  const checks = [
    ['048-041-03', false, 'no-event APN'],
    ['132-231-10', false, 'has events'],
    ['029-630-029', false, 'hub APN'],
    ['032-301-011', false, 'wide fanout'],
    ['1318-22-310-001', false, 'Douglas long-form'],
    ['015-331-04', false, 'pre-2018 El Dorado padding'],
  ];
  for (const [apn, isMissing, label] of checks) {
    const seed = canonicalApn(apn);
    const w = walkGenealogy(seed, false);
    const ok = isMissing ? !w.found : true;
    if (ok) { pass++; console.info(`  [PASS] ${label}: ${seed} -> ${w.members.length} APNs, ${w.maxUp}up/${w.maxDn}dn`); }
    else    { fail++; console.warn(`  [FAIL] ${label}: ${seed}`); }
  }
  console.info(`Self-tests: ${pass} passed, ${fail} failed`);
  console.groupEnd();
  return { pass, fail };
}

// ─── Bootstrap ──────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  // Component grid is built lazily on first lookup; Batch grid lazily on tab switch.
  // Drop zone wiring
  const dz = document.getElementById('drop-zone');
  const fi = document.getElementById('file-input');
  dz.addEventListener('click', () => fi.click());
  fi.addEventListener('change', (e) => { handleFile(e.target.files[0]); });
  dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('drag-active'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('drag-active'));
  dz.addEventListener('drop', (e) => {
    e.preventDefault(); dz.classList.remove('drag-active');
    if (e.dataTransfer.files && e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
  });
  document.getElementById('btn-download').addEventListener('click', downloadBatchCsv);

  // Example pills
  document.querySelectorAll('#example-pills .example-pill').forEach(el => {
    el.addEventListener('click', () => {
      setSeedInput(el.getAttribute('data-apn'));
      lookupSingle();
    });
  });
  // Enter key in input triggers lookup
  document.getElementById('apn-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); lookupSingle(); }
  });
  // Toggle re-runs current query if one is set
  document.getElementById('filter-toggle').addEventListener('change', () => {
    if (state.currentSeed) lookupSingle();
  });

  try {
    await loadData();
    buildComponentGrid();
    // Kick off the map init in parallel; the first lookup awaits it
    initMap().catch(err => console.warn('Map init failed:', err));
    // Run self-tests under ?test=1
    if (new URLSearchParams(location.search).get('test') === '1') runSelfTests();
  } catch (err) {
    console.error('Failed to load data:', err);
    setLoadingStatus(`Error: ${err.message}`);
    toast('Failed to load genealogy data. See console.', 'warn');
  }
});
