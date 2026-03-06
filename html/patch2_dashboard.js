const fs = require('fs');
const path = 'c:/Users/mbindl/Documents/GitHub/Reporting/html/residential-allocations-dashboard.html';
let content = fs.readFileSync(path, 'utf8');

// ── 1. Replace embedded rawData array with a mutable empty placeholder
const rawDataStart = content.indexOf('const rawData = [');
const normalizeEnd = content.indexOf('\nrawData.forEach(') + content.slice(content.indexOf('\nrawData.forEach(')).indexOf('\n', 1) + 1;

// Sanity check
console.log('rawData start:', rawDataStart);
console.log('normalizeEnd:', normalizeEnd);
console.log('After normalizeEnd:', JSON.stringify(content.slice(normalizeEnd, normalizeEnd + 60)));

const newDataSection = 'let rawData = []; // populated by loadData()\n';
content = content.slice(0, rawDataStart) + newDataSection + content.slice(normalizeEnd);
console.log('Embedded rawData replaced. New file size:', Math.round(content.length / 1024) + ' KB');

// ── 2. Add a loading overlay to the body (just after <body>)
const loadingHTML = `<div id="loading-overlay" style="
  position:fixed;inset:0;background:rgba(11,31,65,0.82);
  display:flex;align-items:center;justify-content:center;
  z-index:9999;font-family:'Lexend Deca',sans-serif;">
  <div style="text-align:center;color:#fff;">
    <div style="font-size:1rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;margin-bottom:12px;">
      Loading data\u2026
    </div>
    <div style="width:180px;height:4px;background:rgba(255,255,255,0.15);border-radius:2px;overflow:hidden;">
      <div id="loading-bar" style="width:0%;height:100%;background:var(--green);border-radius:2px;transition:width 0.4s ease;"></div>
    </div>
  </div>
</div>
`;
content = content.replace('<body>', '<body>\n' + loadingHTML);
console.log('Loading overlay added');

// ── 3. Add loadData() async function + helpers before the INIT comment block
const loadDataFn = `
// ─────────────────────────────────────────
// DATA LOADING (CSV / future JSON service)
// ─────────────────────────────────────────
// To swap to a JSON web service, replace DATA_URL with the service endpoint
// and adjust the parse() function to match its response schema.
const DATA_URL = './data/raw_data/residentialAllocationGridExport.csv';

const POOL_TO_JURISDICTION = {
  'Residential Allocation - Douglas County':            'Douglas County',
  'Residential Allocation - El Dorado County':          'El Dorado County',
  'Residential Allocation - Placer County':             'Placer County',
  'Residential Allocation - City of South Lake Tahoe':  'City of South Lake Tahoe',
  'Residential Allocation - CSLT - Multi-Family Pool':  'City of South Lake Tahoe',
  'Residential Allocation - CSLT - Single-Family Pool': 'City of South Lake Tahoe',
  'Residential Allocation - CSLT - Town Center Pool':   'City of South Lake Tahoe',
  'Residential Allocation - TRPA Pool':                 'TRPA',
  'Residential Allocation - Washoe County':             'Washoe County',
};

function parseCSV(text) {
  const lines = text.trim().split(/\\r?\\n/);
  // Skip header row
  return lines.slice(1).filter(l => l.trim()).map(line => {
    // Split on commas — data has no quoted commas so a simple split is safe
    const c = line.split(',');
    let status = (c[5] || '').trim();
    // Normalize both known "without transaction" variants → Allocated
    if (status === 'Allocated w/out Transaction' || status === 'Allocated w/o Transaction') {
      status = 'Allocated';
    }
    const pool = (c[7] || '').trim();
    return {
      id:           (c[0] || '').trim(),
      year:         parseInt((c[2] || '').trim(), 10),
      jurisdiction: POOL_TO_JURISDICTION[pool] || pool,
      pool,
      status,
      transaction:  (c[6] || '').trim(),
      apn:          (c[9] || '').trim(),
    };
  });
}

async function loadData() {
  const bar = document.querySelector('#loading-bar');
  if (bar) bar.style.width = '30%';

  const resp = await fetch(DATA_URL);
  if (!resp.ok) throw new Error('Failed to load data: ' + resp.statusText);

  if (bar) bar.style.width = '70%';
  const text = await resp.text();
  rawData = parseCSV(text);
  if (bar) bar.style.width = '100%';
}

function showLoading(visible) {
  const el = document.querySelector('#loading-overlay');
  if (el) el.style.display = visible ? 'flex' : 'none';
}

`;

const initAnchor = '// ─────────────────────────────────────────\n// INIT';
if (content.includes(initAnchor)) {
  content = content.replace(initAnchor, loadDataFn + initAnchor);
  console.log('loadData() function added');
} else {
  console.log('ERROR: INIT anchor not found');
}

// ── 4. Update DOMContentLoaded to be async and await loadData
const oldInit = `document.addEventListener('DOMContentLoaded', () => {
  populateFilters();
  updateKPIs(rawData);
  renderCharts(rawData);
  initGrid();
});`;

const newInit = `document.addEventListener('DOMContentLoaded', async () => {
  showLoading(true);
  try {
    await loadData();
  } catch (err) {
    console.error(err);
    showLoading(false);
    document.querySelector('#loading-overlay').innerHTML =
      '<div style="color:#f16022;font-family:\\'Lexend Deca\\',sans-serif;padding:24px;text-align:center;">' +
      '<strong>Error loading data.</strong><br><small>' + err.message + '</small></div>';
    return;
  }
  showLoading(false);
  populateFilters();
  updateKPIs(rawData);
  renderCharts(rawData);
  initGrid();
});`;

if (content.includes(oldInit)) {
  content = content.replace(oldInit, newInit);
  console.log('DOMContentLoaded updated to async');
} else {
  console.log('ERROR: DOMContentLoaded old string not found');
}

fs.writeFileSync(path, content, 'utf8');
console.log('\nDone. Final file size:', Math.round(content.length / 1024) + ' KB');
