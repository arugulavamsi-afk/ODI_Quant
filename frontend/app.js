/* ── ODI Quant Dashboard ─────────────────────────────────────────────────── */
'use strict';

// Use Render backend URL when running on a different origin (e.g. Netlify),
// otherwise fall back to same-origin (local dev or Render itself).
const API = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? ''
  : 'https://odi-quant.onrender.com';
let allStocks = [];       // Full dataset
let currentFilter = 'ALL';
let sortKey = 'rank';
let sortAsc = true;
let autoRefreshTimer = null;

// ── Bootstrap ────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadLatestResults();
  scheduleAutoRefresh();
});

function scheduleAutoRefresh() {
  clearInterval(autoRefreshTimer);
  autoRefreshTimer = setInterval(() => {
    if (!document.getElementById('loaderOverlay').style.display ||
        document.getElementById('loaderOverlay').style.display === 'none') {
      loadLatestResults(true);   // silent refresh
    }
  }, 30000);
}

// ── Data Loading ─────────────────────────────────────────────────────────────
async function loadLatestResults(silent = false) {
  try {
    const res = await fetch(`${API}/api/results/latest`);
    if (res.status === 404) return; // No data yet – that's fine
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderAll(data);
  } catch (e) {
    if (!silent) console.warn('Could not load latest results:', e);
  }
}

async function runPipeline() {
  const btn = document.getElementById('runBtn');
  showLoader('Fetching global market data...');
  btn.disabled = true;
  btn.classList.add('loading');
  btn.innerHTML = '<span class="btn-icon">⏳</span> Running...';

  // Cycle loader messages to give feedback
  const msgs = [
    'Fetching NSE stock data...',
    'Computing indicators...',
    'Generating trade signals...',
    'Scoring setups...',
    'Applying global sentiment...',
    'Ranking opportunities...',
  ];
  let mi = 0;
  const msgTimer = setInterval(() => {
    document.getElementById('loaderText').textContent = msgs[mi++ % msgs.length];
  }, 8000);

  try {
    const res = await fetch(`${API}/api/run`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    renderAll(data);
    showToast('Analysis complete!', 'success');
  } catch (e) {
    showToast(`Pipeline error: ${e.message}`, 'error');
    console.error(e);
  } finally {
    clearInterval(msgTimer);
    hideLoader();
    btn.disabled = false;
    btn.classList.remove('loading');
    btn.innerHTML = '<span class="btn-icon">▶</span> Run Analysis';
  }
}

// ── Rendering ─────────────────────────────────────────────────────────────────
function renderAll(data) {
  allStocks = data.stocks || [];
  renderSentiment(data.global_sentiment);
  renderSummary(data.summary);
  updateLastRun(data.run_date);
  applyFilters();
}

function renderSentiment(gs) {
  if (!gs) return;

  const score = gs.score ?? 0;
  const cls = gs.classification || 'NEUTRAL';

  const scoreEl = document.getElementById('sentimentScore');
  const badgeEl = document.getElementById('sentimentBadge');
  scoreEl.textContent = (score > 0 ? '+' : '') + score.toFixed(1);
  scoreEl.style.color = score > 0 ? 'var(--green)' : score < 0 ? 'var(--red)' : 'var(--text)';

  badgeEl.textContent = cls.replace('_', ' ');
  badgeEl.className = 'sentiment-badge ' + cls;

  // Global index chips
  const components = gs.components || {};
  const indicesEl = document.getElementById('sentimentIndices');
  const SHOW = ['^GSPC', '^IXIC', '^N225', '^HSI', 'CL=F', 'GC=F', 'DX-Y.NYB', '^NSEI'];
  const html = SHOW.map(sym => {
    const c = components[sym];
    if (!c) return '';
    const ch = c.change_pct ?? 0;
    const cls2 = ch > 0.1 ? 'up' : ch < -0.1 ? 'down' : 'flat';
    const prefix = ch > 0 ? '+' : '';
    return `<div class="si-chip">
      <span class="si-name">${c.name || sym}</span>
      <span class="si-val ${cls2}">${prefix}${ch.toFixed(2)}%</span>
    </div>`;
  }).join('');
  indicesEl.innerHTML = html;
}

function renderSummary(summary) {
  if (!summary) return;
  document.getElementById('totalCount').textContent = summary.total ?? 0;
  document.getElementById('longCount').textContent = summary.high_prob_long ?? 0;
  document.getElementById('shortCount').textContent = summary.high_prob_short ?? 0;
  document.getElementById('watchCount').textContent = summary.watchlist ?? 0;
}

function updateLastRun(date) {
  if (!date) return;
  const now = new Date();
  document.getElementById('lastRunTime').textContent = `Last run: ${date} at ${now.toLocaleTimeString()}`;
}

// ── Filters & Sort ────────────────────────────────────────────────────────────
function setFilter(el, filter) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  currentFilter = filter;
  applyFilters();
}

function applyFilters() {
  const search = document.getElementById('searchBox').value.toLowerCase().trim();
  let filtered = allStocks;

  if (currentFilter !== 'ALL') {
    filtered = filtered.filter(s => s.category === currentFilter);
  }

  if (search) {
    filtered = filtered.filter(s =>
      (s.symbol || '').toLowerCase().includes(search) ||
      (s.sector || '').toLowerCase().includes(search) ||
      (s.name || '').toLowerCase().includes(search)
    );
  }

  // Sort
  filtered = [...filtered].sort((a, b) => {
    let va = a[sortKey], vb = b[sortKey];
    if (typeof va === 'string') va = va.toLowerCase();
    if (typeof vb === 'string') vb = vb.toLowerCase();
    if (va == null) return 1;
    if (vb == null) return -1;
    return sortAsc ? (va < vb ? -1 : va > vb ? 1 : 0) : (va > vb ? -1 : va < vb ? 1 : 0);
  });

  renderTable(filtered);
}

function sortBy(key) {
  if (sortKey === key) {
    sortAsc = !sortAsc;
  } else {
    sortKey = key;
    sortAsc = key === 'rank';
  }
  applyFilters();
}

// ── Table Rendering ───────────────────────────────────────────────────────────
function renderTable(stocks) {
  const tbody = document.getElementById('stockTableBody');

  if (!stocks.length) {
    tbody.innerHTML = `<tr class="placeholder-row"><td colspan="12">
      <div class="placeholder-msg">
        <span class="ph-icon">🔍</span>
        <p>No stocks match the current filter.</p>
      </div>
    </td></tr>`;
    return;
  }

  tbody.innerHTML = stocks.map((s, idx) => buildRow(s, idx)).join('');

  // Re-open any rows that were expanded before the re-render (survives auto-refresh)
  expandedRows.forEach(rowId => {
    const dr = document.getElementById(`${rowId}-detail`);
    const mr = document.getElementById(rowId);
    if (dr) dr.classList.add('visible');
    if (mr) mr.classList.add('expanded');
  });
}

function buildRow(s, idx) {
  const id = `row-${s.symbol?.replace(/[^a-zA-Z0-9]/g, '_')}`;

  // CMP
  const cmp = s.cmp ?? s.entry ?? 0;
  const cmpHtml = `<span class="cmp-val">₹${fmt(cmp)}</span>`;

  // Trend
  const trend = s.trend_bias || 'NEUTRAL';
  const trendHtml = `<span class="trend-badge ${trend}">${trend}</span>`;

  // Volume spike
  const vs = s.volume_spike ?? 0;
  const vsClass = vs >= 2 ? 'high' : vs >= 1.5 ? 'med' : 'low';
  const vsHtml = `<span class="vol-val ${vsClass}">${vs.toFixed(1)}x</span>`;

  // Breakout
  const bo = s.breakout_status || 'INSIDE';
  const boLabel = bo.replace('_', ' ');
  const boHtml = `<span class="bo-badge ${bo}">${boLabel}</span>`;

  // Close %
  const cs = s.closing_strength ?? 50;
  const csColor = cs >= 70 ? 'var(--green)' : cs <= 30 ? 'var(--red)' : 'var(--text-muted)';
  const csHtml = buildClosePctBar(cs, csColor);

  // Scores
  const lScore = s.long_score ?? 0;
  const sScore = s.short_score ?? 0;
  const lHtml = buildScoreBar(lScore, 'long');
  const sHtml = buildScoreBar(sScore, 'short');

  // Signal badge
  const cat = s.category || 'NO_TRADE';
  const catLabel = cat.replace('HIGH_PROB_', '').replace('_', ' ');
  const signalHtml = `<span class="signal-badge ${cat}">${catLabel}</span>`;

  // Trade levels
  const tlHtml = buildTradeLevels(s);

  const rowClass = `data-row ${idx % 2 === 1 ? 'alt' : ''}`;

  return `
    <tr class="${rowClass}" data-category="${cat}" id="${id}" onclick="toggleDetail('${id}', '${s.symbol}')">
      <td>${s.rank ?? idx + 1}</td>
      <td><div class="sym-wrap">
        <span class="sym-name">${shortSym(s.symbol)}</span>
        <span class="sym-full" title="${s.name}">${s.name || ''}</span>
      </div></td>
      <td>${s.sector || '–'}</td>
      <td>${cmpHtml}</td>
      <td>${trendHtml}</td>
      <td>${vsHtml}</td>
      <td>${boHtml}</td>
      <td>${csHtml}</td>
      <td>${lHtml}</td>
      <td>${sHtml}</td>
      <td>${signalHtml}</td>
      <td>${tlHtml}</td>
    </tr>
    <tr class="detail-row" id="${id}-detail">
      <td colspan="12">${buildDetailContent(s)}</td>
    </tr>`;
}

function buildScoreBar(score, direction) {
  const pct = Math.min(100, Math.max(0, score));
  let fillClass, numClass;
  if (direction === 'long') {
    fillClass = score >= 70 ? 'long-high' : score >= 50 ? 'long-mid' : 'long-low';
    numClass  = score >= 70 ? 'high-long' : score >= 50 ? 'mid' : 'low';
  } else {
    fillClass = score >= 70 ? 'short-high' : score >= 50 ? 'short-mid' : 'short-low';
    numClass  = score >= 70 ? 'high-short' : score >= 50 ? 'mid' : 'low';
  }
  return `<div class="score-bar-wrap">
    <div class="score-bar-bg"><div class="score-bar-fill ${fillClass}" style="width:${pct}%"></div></div>
    <span class="score-num ${numClass}">${score}</span>
  </div>`;
}

function buildClosePctBar(cs, color) {
  return `<div class="close-pct-bar">
    <div class="cpb-track"><div class="cpb-fill" style="width:${cs}%;background:${color}"></div></div>
    <span style="color:${color};font-family:var(--mono);font-size:11px">${cs.toFixed(0)}%</span>
  </div>`;
}

function getSetupType(s) {
  const bo = s.breakout_status || 'INSIDE';
  const trend = s.trend_bias || 'NEUTRAL';
  const vs = s.volume_spike ?? 1;
  const dir = s.direction || 'LONG';
  if (bo === 'BREAKOUT')      return vs >= 2 ? 'Volume Breakout' : 'Range Breakout';
  if (bo === 'BREAKDOWN')     return vs >= 2 ? 'Volume Breakdown' : 'Range Breakdown';
  if (bo === 'NEAR_BREAKOUT') return 'Near Breakout';
  if (bo === 'NEAR_BREAKDOWN') return 'Near Breakdown';
  if ((trend === 'BULLISH' && dir === 'LONG') || (trend === 'BEARISH' && dir === 'SHORT'))
    return vs >= 2 ? 'Trend + Volume' : 'Trend Continuation';
  if (vs >= 2) return 'Volume Surge';
  return 'Mixed Setup';
}

function buildTradeLevels(s) {
  const trigger = s.entry_trigger || s.entry;
  if (!trigger) return '<span style="color:var(--text-dim)">–</span>';
  const setup = getSetupType(s);
  const dir = (s.direction || 'LONG').toUpperCase();
  const setupClass = dir === 'LONG' ? 'setup-long' : 'setup-short';
  const triggerLabel = dir === 'LONG' ? 'Buy above' : 'Sell below';
  return `<div class="trade-levels">
    <span class="tl-setup ${setupClass}">${setup}</span>
    <span class="tl-entry">${triggerLabel}: ₹${fmt(trigger)}</span>
    <span class="tl-sl">SL: ₹${fmt(s.stop_loss)} (${s.risk_pct?.toFixed(1)}%)</span>
    <span class="tl-t1">T1: ₹${fmt(s.target1)}${s.rr_t1 ? ` · ${s.rr_t1}:1` : ''}</span>
    <span class="tl-t2">T2: ₹${fmt(s.target2)}${s.rr_t2 ? ` · ${s.rr_t2}:1` : ''}</span>
  </div>`;
}

function buildDetailContent(s) {
  const explanation = (s.explanation || 'No explanation available.')
    .replace(/\n/g, '<br>')
    .replace(/\+/g, '<span class="plus">+</span>')
    .replace(/^  -/gm, '  <span class="minus">-</span>')
    .replace(/  ~/g, '  <span class="tilde">~</span>');

  const ind = s.indicators || {};

  const trigger = s.entry_trigger || s.entry;
  const triggerLabel = (s.direction || 'LONG').toUpperCase() === 'LONG' ? 'Enter above PDH' : 'Enter below PDL';
  const levelsHtml = trigger ? `
    <div class="detail-levels">
      ${s.setup_note ? `<div class="dl-note">${s.setup_note}</div>` : ''}
      <div class="dl-item"><div class="dl-label">${triggerLabel}</div><div class="dl-value entry">₹${fmt(trigger)}</div></div>
      <div class="dl-item"><div class="dl-label">Stop Loss (${s.risk_pct?.toFixed(1)}% risk)</div><div class="dl-value sl">₹${fmt(s.stop_loss)}</div></div>
      <div class="dl-item"><div class="dl-label">T1 · 1×ATR${s.rr_t1 ? ` · ${s.rr_t1}:1 RR` : ''}</div><div class="dl-value target">₹${fmt(s.target1)} <span class="dl-hint">Book 50%, move SL to breakeven</span></div></div>
      <div class="dl-item"><div class="dl-label">T2 · 2×ATR${s.rr_t2 ? ` · ${s.rr_t2}:1 RR` : ''}</div><div class="dl-value target">₹${fmt(s.target2)} <span class="dl-hint">Book 30%</span></div></div>
      <div class="dl-item"><div class="dl-label">T3 · 3×ATR${s.rr_t3 ? ` · ${s.rr_t3}:1 RR` : ''}</div><div class="dl-value target2">₹${fmt(s.target3)} <span class="dl-hint">Trail 20%</span></div></div>
      ${s.position_size_1L ? `<div class="dl-item"><div class="dl-label">Position Size (₹1L risk)</div><div class="dl-value" style="color:var(--text)">${s.position_size_1L} shares</div></div>` : ''}
    </div>` : '';

  const statsHtml = `
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px">
      ${statChip('MA20', ind.ma20 ? '₹' + fmt(ind.ma20) : '–')}
      ${statChip('MA50', ind.ma50 ? '₹' + fmt(ind.ma50) : '–')}
      ${statChip('MA200', ind.ma200 ? '₹' + fmt(ind.ma200) : '–')}
      ${statChip('ATR', ind.atr ? '₹' + fmt(ind.atr) : '–')}
      ${statChip('ATR Expansion', ind.atr_expansion ? ind.atr_expansion.toFixed(2) + 'x' : '–')}
      ${statChip('Market Structure', ind.market_structure || '–')}
    </div>`;

  const setup = getSetupType(s);
  const dir = (s.direction || 'LONG').toUpperCase();
  const setupClass = dir === 'LONG' ? 'setup-long' : 'setup-short';

  return `<div class="detail-grid">
    <div class="detail-section">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <h4 style="margin:0">Setup Analysis</h4>
        <span class="tl-setup ${setupClass}" style="font-size:11px;padding:3px 8px">${setup} · ${dir}</span>
      </div>
      <pre style="font-size:11.5px;line-height:1.65">${explanation}</pre>
    </div>
    <div class="detail-section">
      <h4>Trade Levels</h4>
      ${levelsHtml}
      <h4 style="margin-top:14px">Key Metrics</h4>
      ${statsHtml}
    </div>
  </div>`;
}

function statChip(label, value) {
  return `<div style="background:var(--card-bg);border:1px solid var(--border);border-radius:6px;padding:6px 10px">
    <div style="font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.4px">${label}</div>
    <div style="font-size:12px;font-weight:700;font-family:var(--mono);margin-top:2px">${value}</div>
  </div>`;
}

// ── Row Expansion ─────────────────────────────────────────────────────────────
const expandedRows = new Set();

function toggleDetail(rowId, symbol) {
  const detailRow = document.getElementById(`${rowId}-detail`);
  const mainRow = document.getElementById(rowId);
  if (!detailRow) return;

  const isVisible = detailRow.classList.contains('visible');
  if (isVisible) {
    detailRow.classList.remove('visible');
    mainRow.classList.remove('expanded');
    expandedRows.delete(rowId);
  } else {
    detailRow.classList.add('visible');
    mainRow.classList.add('expanded');
    expandedRows.add(rowId);
  }
}

// ── Modal ─────────────────────────────────────────────────────────────────────
function openModal(content) {
  document.getElementById('modalContent').innerHTML = content;
  document.getElementById('modalOverlay').classList.add('open');
}

function closeModal(e) {
  if (e && e.target !== document.getElementById('modalOverlay')) return;
  document.getElementById('modalOverlay').classList.remove('open');
}

// ── Loader ────────────────────────────────────────────────────────────────────
function showLoader(msg) {
  document.getElementById('loaderText').textContent = msg || 'Loading...';
  document.getElementById('loaderOverlay').style.display = 'flex';
}

function hideLoader() {
  document.getElementById('loaderOverlay').style.display = 'none';
}

// ── Toast Notification ────────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  const existing = document.getElementById('toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.id = 'toast';
  toast.style.cssText = `
    position:fixed;bottom:24px;right:24px;z-index:9999;
    background:${type === 'success' ? 'var(--green)' : type === 'error' ? 'var(--red)' : 'var(--blue)'};
    color:${type === 'success' ? '#000' : '#fff'};
    padding:12px 20px;border-radius:8px;font-weight:600;font-size:13px;
    box-shadow:0 4px 20px rgba(0,0,0,0.5);
    animation:fadeIn 0.3s ease;
  `;
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3500);
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmt(val) {
  if (val == null || val === '') return '–';
  const n = parseFloat(val);
  if (isNaN(n)) return '–';
  return n >= 1000 ? n.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : n.toFixed(2);
}

function shortSym(sym) {
  if (!sym) return '–';
  return sym.replace('.NS', '').replace('.BO', '');
}

// Fade-in animation
const style = document.createElement('style');
style.textContent = `
@keyframes fadeIn { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }
.data-row { animation: fadeIn 0.2s ease both; }
`;
document.head.appendChild(style);


/* ══════════════════════════════════════════════════════════════════════════
   NIFTY OPTIONS PAGE
   ══════════════════════════════════════════════════════════════════════════ */

// ── Page navigation ───────────────────────────────────────────────────────
let activePage = 'scanner';

function showPage(page) {
  activePage = page;
  document.querySelectorAll('.page-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.page === page);
  });

  const isScanner  = page === 'scanner';
  const isStrategy = page === 'strategy';
  document.getElementById('scannerPage').style.display  = isScanner  ? '' : 'none';
  document.getElementById('niftyPage').style.display    = page === 'nifty'    ? '' : 'none';
  document.getElementById('strategyPage').style.display = isStrategy          ? '' : 'none';
  document.getElementById('intraPage').style.display    = page === 'intra'    ? '' : 'none';
  document.getElementById('runBtn').style.display       = isScanner  ? '' : 'none';
  document.getElementById('lastRunTime').style.display  = isScanner  ? '' : 'none';
}

// ── NIFTY data load & render ──────────────────────────────────────────────
async function runNiftyAnalysis() {
  const btn = document.getElementById('niftyRunBtn');
  btn.disabled = true;
  btn.classList.add('loading');
  btn.textContent = '⏳ Analysing...';
  showLoader('Fetching NIFTY50 data...');

  const msgs = [
    'Computing technical indicators...',
    'Calculating historical volatility...',
    'Selecting options strategy...',
    'Running Black-Scholes model...',
    'Building trade plan...',
  ];
  let mi = 0;
  const msgTimer = setInterval(() => {
    document.getElementById('loaderText').textContent = msgs[mi++ % msgs.length];
  }, 5000);

  try {
    const res = await fetch(`${API}/api/nifty/analysis`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    renderNiftyPage(data);
    showToast('NIFTY analysis complete!', 'success');
  } catch (e) {
    showToast(`NIFTY analysis error: ${e.message}`, 'error');
    console.error(e);
  } finally {
    clearInterval(msgTimer);
    hideLoader();
    btn.disabled = false;
    btn.classList.remove('loading');
    btn.textContent = '⚡ Analyse NIFTY';
  }
}

// ── Master renderer ───────────────────────────────────────────────────────
function renderNiftyPage(data) {
  const ov   = data.nifty_overview   || {};
  const oa   = data.options_analysis || {};
  const gs   = data.global_sentiment || {};

  // Show content, hide empty state
  document.getElementById('niftyEmpty').style.display   = 'none';
  document.getElementById('niftyContent').style.display = '';

  // Update last-run timestamp
  const runLabel = (data.run_date && data.run_time)
    ? `Last: ${data.run_date} ${data.run_time}`
    : data.run_date || '–';
  document.getElementById('niftyLastRun').textContent = runLabel;

  renderNiftyOverview(ov, gs);
  renderNiftyLevels(ov);
  renderNiftyStrategy(oa);
  renderNiftyStrikes(oa);
  renderNiftyTradePlan(oa);
  renderNiftyGreeks(oa);
  renderNiftyExplanation(oa);
}

// ── Section 1: Overview ───────────────────────────────────────────────────
function renderNiftyOverview(ov, gs) {
  // Price
  const price  = ov.current_price ?? 0;
  const chgPct = ov.change_pct    ?? 0;
  const chgDir = chgPct > 0.05 ? 'up' : chgPct < -0.05 ? 'down' : 'flat';
  const chgPfx = chgPct > 0 ? '+' : '';

  document.getElementById('niftyPrice').textContent = '₹' + fmt(price);

  const chgEl = document.getElementById('niftyChange');
  chgEl.textContent  = `${chgPfx}${chgPct.toFixed(2)}%`;
  chgEl.className    = `nifty-change ${chgDir}`;

  // Expected move badge
  const em    = ov.expected_move || 'NEUTRAL';
  const emEl  = document.getElementById('niftyExpectedMove');
  emEl.textContent = em.replace('_', ' ');
  emEl.className   = `nifty-move-badge ${em}`;

  // Overview chips (right side)
  const chips = [
    { label: 'Trend',      value: (ov.trend_bias || '–').replace('_', ' '),
      cls: trendCls(ov.trend_bias) },
    { label: 'Global',     value: (gs.classification || '–').replace('_', ' '),
      cls: trendCls(gs.classification) },
    { label: 'PDH',        value: '₹' + fmt(ov.pdh), cls: 'resistance' },
    { label: 'PDL',        value: '₹' + fmt(ov.pdl), cls: 'support' },
    { label: 'ATR',        value: '₹' + fmt(ov.atr), cls: '' },
    { label: 'HV 30d',    value: (ov.hv_30 ?? '–') + ' %', cls: '' },
  ];

  document.getElementById('niftyOverviewChips').innerHTML = chips.map(c =>
    `<div class="nifty-chip">
       <span class="nifty-chip-label">${c.label}</span>
       <span class="nifty-chip-value ${c.cls}">${c.value}</span>
     </div>`
  ).join('');
}

function trendCls(bias) {
  if (!bias) return '';
  if (bias.includes('BULLISH') || bias === 'LONG') return 'bullish';
  if (bias.includes('BEARISH') || bias === 'SHORT') return 'bearish';
  return 'neutral';
}

// ── Section 2: Technical Levels ───────────────────────────────────────────
function renderNiftyLevels(ov) {
  const levels = [
    { label: 'Prev Close',   value: '₹' + fmt(ov.prev_close),  cls: '' },
    { label: 'Open',         value: '₹' + fmt(ov.current_open), cls: '' },
    { label: 'High',         value: '₹' + fmt(ov.current_high), cls: 'resistance' },
    { label: 'Low',          value: '₹' + fmt(ov.current_low),  cls: 'support' },
    { label: 'PDH',          value: '₹' + fmt(ov.pdh),          cls: 'resistance' },
    { label: 'PDL',          value: '₹' + fmt(ov.pdl),          cls: 'support' },
    { label: 'VWAP (5d)',    value: '₹' + fmt(ov.vwap_5d),      cls: 'key' },
    { label: 'MA 20',        value: '₹' + fmt(ov.ma20),         cls: 'ma' },
    { label: 'MA 50',        value: '₹' + fmt(ov.ma50),         cls: 'ma' },
    { label: 'MA 200',       value: '₹' + fmt(ov.ma200),        cls: 'ma' },
    { label: 'Support 1',    value: '₹' + fmt(ov.support1),     cls: 'support' },
    { label: 'Support 2',    value: '₹' + fmt(ov.support2),     cls: 'support' },
    { label: 'Resist 1',     value: '₹' + fmt(ov.resistance1),  cls: 'resistance' },
    { label: 'Resist 2',     value: '₹' + fmt(ov.resistance2),  cls: 'resistance' },
    { label: 'Exp High',     value: '₹' + fmt(ov.expected_high), cls: '' },
    { label: 'Exp Low',      value: '₹' + fmt(ov.expected_low),  cls: '' },
  ];

  document.getElementById('niftyLevelsGrid').innerHTML = levels.map(l =>
    `<div class="nifty-level-item">
       <div class="nifty-level-label">${l.label}</div>
       <div class="nifty-level-value ${l.cls}">${l.value}</div>
     </div>`
  ).join('');
}

// ── Section 3a: Strategy card ──────────────────────────────────────────────
function renderNiftyStrategy(oa) {
  const strat  = oa.strategy          || {};
  const ivEnv  = oa.iv_environment    || {};
  const dir    = strat.direction      || 'NEUTRAL';
  const ivLv   = ivEnv.iv_level       || 'MODERATE';
  const code   = strat.code           || 'NO_TRADE';

  // Direction badge
  const dirEl = document.getElementById('niftyDirection');
  dirEl.textContent = dir;
  dirEl.className   = `nifty-dir-badge ${dir}`;

  // Strategy name
  const nameEl = document.getElementById('niftyStrategyName');
  nameEl.textContent = strat.name || '–';
  nameEl.style.color = dir === 'LONG' ? 'var(--green)'
                     : dir === 'SHORT' ? 'var(--red)'
                     : 'var(--text-muted)';

  // IV badge
  const ivEl = document.getElementById('niftyIvLevel');
  ivEl.textContent = (ivLv + ' IV').replace('_', ' ');
  ivEl.className   = `nifty-iv-badge ${ivLv}`;

  // Rationale
  document.getElementById('niftyRationale').textContent = strat.rationale || '–';
}

// ── Section 3b: Strike & Expiry card ──────────────────────────────────────
function renderNiftyStrikes(oa) {
  const ss   = oa.strike_selection || {};
  const strat = oa.strategy        || {};
  const code  = strat.code         || 'NO_TRADE';
  const optT  = ss.option_type     || '–';
  const hedge = ss.hedge_strike;

  let rows = [
    { label: 'Spot Price',      value: '₹' + fmt(ss.spot),       cls: '' },
    { label: 'ATM Strike',      value: fmt0(ss.atm_strike),      cls: 'strike' },
    { label: 'Buy Strike',      value: `${fmt0(ss.buy_strike)} ${optT}`, cls: 'strike' },
  ];

  if (hedge && code !== 'NO_TRADE') {
    rows.push({ label: 'Sell Strike (hedge)', value: `${fmt0(hedge)} ${optT}`, cls: 'warn' });
  }

  rows = rows.concat([
    { label: 'Expiry',          value: ss.expiry || '–',          cls: '' },
    { label: 'DTE',             value: `${ss.dte ?? '–'} days`,   cls: ss.dte <= 2 ? 'warn' : '' },
    { label: 'Strike Type',     value: ss.strike_type || 'ATM',   cls: '' },
    { label: 'Lot Size',        value: `${ss.lot_size || 50} units`, cls: '' },
  ]);

  document.getElementById('niftyStrikeGrid').innerHTML = rows.map(r =>
    `<div class="nifty-mini-row">
       <span class="nifty-mini-label">${r.label}</span>
       <span class="nifty-mini-value ${r.cls}">${r.value}</span>
     </div>`
  ).join('');
}

// ── Section 3c: Trade Plan card ────────────────────────────────────────────
function renderNiftyTradePlan(oa) {
  const tp    = oa.trade_plan || {};
  const strat = oa.strategy   || {};
  const code  = strat.code    || 'NO_TRADE';

  if (code === 'NO_TRADE' || !tp.entry_premium) {
    document.getElementById('niftyTradePlan').innerHTML =
      `<div class="nifty-mini-row"><span class="nifty-mini-label" style="color:var(--text-muted);font-style:italic">
        No trade recommended — wait for directional confirmation.
      </span></div>`;
    return;
  }

  const rrLabel = tp.risk_reward ? ` · ${tp.risk_reward}:1 R:R` : '';
  const dir     = strat.direction || 'LONG';

  const premiumRows = [
    { label: 'Entry Premium',    value: '₹' + fmt(tp.entry_premium),    cls: 'entry' },
    { label: 'Stop Loss',        value: '₹' + fmt(tp.stop_loss_premium) + ' (−35%)', cls: 'sl' },
    { label: 'Target 1' + rrLabel, value: '₹' + fmt(tp.target1_premium), cls: 'target' },
    { label: 'Target 2',         value: '₹' + fmt(tp.target2_premium),  cls: 't2' },
    { label: 'Max Loss / Lot',   value: '₹' + fmt(tp.max_loss_per_lot), cls: 'sl' },
  ];

  const indexRows = [
    { label: dir === 'LONG' ? 'Buy above (Index)' : 'Sell below (Index)',
      value: '₹' + fmt(tp.index_entry_trigger), cls: 'entry' },
    { label: 'Index SL',  value: '₹' + fmt(tp.index_stop_loss),  cls: 'sl' },
    { label: 'Index T1',  value: '₹' + fmt(tp.index_target1),    cls: 'target' },
    { label: 'Index T2',  value: '₹' + fmt(tp.index_target2),    cls: 't2' },
  ];

  document.getElementById('niftyTradePlan').innerHTML =
    `<div class="nifty-trade-section-label">Option Premium Levels</div>` +
    premiumRows.map(r =>
      `<div class="nifty-mini-row">
         <span class="nifty-mini-label">${r.label}</span>
         <span class="nifty-mini-value ${r.cls}">${r.value}</span>
       </div>`
    ).join('') +
    `<div class="nifty-trade-section-label" style="margin-top:8px">Index Trigger Levels</div>` +
    indexRows.map(r =>
      `<div class="nifty-mini-row">
         <span class="nifty-mini-label">${r.label}</span>
         <span class="nifty-mini-value ${r.cls}">${r.value}</span>
       </div>`
    ).join('');
}

// ── Section 4: Greeks ─────────────────────────────────────────────────────
function renderNiftyGreeks(oa) {
  const gr    = oa.greeks   || {};
  const ivEnv = oa.iv_environment || {};
  const strat = oa.strategy || {};
  const code  = strat.code  || 'NO_TRADE';

  const netPremium = gr.net_premium ?? 0;
  const netDelta   = gr.net_delta   ?? 0;
  const netTheta   = gr.net_theta   ?? 0;
  const buyLeg     = gr.buy_leg     || {};
  const gamma      = buyLeg.gamma   ?? 0;
  const iv         = ivEnv.hv_30    ?? 0;

  if (code === 'NO_TRADE') {
    document.getElementById('niftyGreeksGrid').innerHTML =
      `<div style="grid-column:1/-1;color:var(--text-muted);font-style:italic;font-size:12px">
         No position selected — Greeks not applicable.
       </div>`;
    document.getElementById('niftyGreeksInterp').textContent = '';
    return;
  }

  const boxes = [
    { symbol: 'Δ', name: 'Delta',   value: fmtGreek(netDelta, 3),  hint: 'Directional sensitivity' },
    { symbol: 'Θ', name: 'Theta',   value: fmtGreek(netTheta, 2) + '/day', hint: 'Daily time decay' },
    { symbol: 'σ', name: 'IV (HV proxy)', value: iv.toFixed(1) + ' %', hint: '30-day annualised HV' },
    { symbol: 'γ', name: 'Gamma',   value: gamma.toFixed(5),        hint: 'Delta sensitivity' },
  ];

  document.getElementById('niftyGreeksGrid').innerHTML = boxes.map(b =>
    `<div class="nifty-greek-box">
       <span class="nifty-greek-symbol">${b.symbol}</span>
       <span class="nifty-greek-name">${b.name}</span>
       <span class="nifty-greek-value">${b.value}</span>
     </div>`
  ).join('');

  // Interpretation line
  const optType  = (strat.option_type || '').toUpperCase();
  const absDelta = Math.abs(netDelta);
  const absPremium = netPremium;
  const thetaDay   = Math.abs(netTheta).toFixed(1);

  let interp = '';
  if (absDelta > 0) {
    interp += `Δ ${fmtGreek(netDelta, 2)}: position gains/loses ~₹${(absDelta * 50).toFixed(0)} per 1-pt NIFTY move (50-unit lot). `;
  }
  if (netTheta !== 0) {
    interp += `Θ −₹${(Math.abs(netTheta) * 50).toFixed(0)}/day time decay per lot. `;
  }
  if (absPremium > 0) {
    interp += `Estimated net premium: ₹${absPremium.toFixed(0)} (₹${(absPremium * 50).toFixed(0)} per lot).`;
  }

  document.getElementById('niftyGreeksInterp').textContent = interp || '–';
}

function fmtGreek(val, dp = 3) {
  if (val == null || isNaN(val)) return '–';
  const prefix = val >= 0 ? '+' : '';
  return prefix + val.toFixed(dp);
}

function fmt0(val) {
  if (val == null) return '–';
  return Number(val).toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

// ── Section 5: Explanation ────────────────────────────────────────────────
function renderNiftyExplanation(oa) {
  const reasons = (oa.explanation || []);
  const ul = document.getElementById('niftyExplanation');

  if (!reasons.length) {
    ul.innerHTML = '<li>No explanation available.</li>';
    return;
  }

  ul.innerHTML = reasons.map(r => `<li>${r}</li>`).join('');

  // Disclaimer
  const disc = oa.disclaimer;
  if (disc) document.getElementById('niftyDisclaimer').textContent = '⚠ ' + disc;
}


/* ══════════════════════════════════════════════════════════════════════════
   TREND PULLBACK STRATEGY PAGE
   ══════════════════════════════════════════════════════════════════════════ */

let stratStocks    = [];
let stratFilter    = 'ALL';
let stratSortKey   = 'pattern_count';
let stratSortAsc   = false;
let stratExpandedRows = new Set();

// ── Data fetch ────────────────────────────────────────────────────────────
async function runStrategyAnalysis() {
  const btn = document.getElementById('stratRunBtn');
  btn.disabled = true;
  btn.classList.add('loading');
  btn.textContent = '⏳ Scanning…';
  showLoader('Fetching Nifty & VIX data…');

  const msgs = [
    'Computing sector relative strength…',
    'Applying quality gate filters…',
    'Scanning for EMA pullbacks…',
    'Detecting base breakouts…',
    'Checking gap-up reversals…',
    'Calculating position sizes…',
    'Ranking setups…',
  ];
  let mi = 0;
  const msgTimer = setInterval(() => {
    document.getElementById('loaderText').textContent = msgs[mi++ % msgs.length];
  }, 9000);

  try {
    const res = await fetch(`${API}/api/strategy/trend-pullback`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    renderStrategyPage(data);
    showToast('Sniper scan complete!', 'success');
  } catch (e) {
    showToast(`Strategy error: ${e.message}`, 'error');
    console.error(e);
  } finally {
    clearInterval(msgTimer);
    hideLoader();
    btn.disabled = false;
    btn.classList.remove('loading');
    btn.textContent = '🎯 Run Sniper';
  }
}

// ── Master renderer ───────────────────────────────────────────────────────
function renderStrategyPage(data) {
  document.getElementById('stratEmpty').style.display   = 'none';
  document.getElementById('stratContent').style.display = '';

  const ts = data.run_date && data.run_time
    ? `Last: ${data.run_date} ${data.run_time}` : (data.run_date || '–');
  document.getElementById('stratLastRun').textContent = ts;

  renderStratCtx(data.market_context || {});
  renderStratSectors(data.sector_rotation || {});
  stratStocks = data.stocks || [];
  renderStratSummaryChips(data.summary || {});
  applyStratFilters();
}

// ── Phase 1 — Market Context ──────────────────────────────────────────────
function renderStratCtx(ctx) {
  const biasColor = ctx.bias_color === 'green' ? 'var(--green)'
                  : ctx.bias_color === 'red'   ? 'var(--red)'
                  : 'var(--yellow)';

  const niftyChange = ctx.nifty_change_pct != null
    ? `<span style="color:${ctx.nifty_change_pct >= 0 ? 'var(--green)' : 'var(--red)'};font-size:13px">
        ${ctx.nifty_change_pct >= 0 ? '+' : ''}${ctx.nifty_change_pct.toFixed(2)}%
       </span>` : '';

  const aboveHtml = ctx.above_50ema == null ? '–'
    : ctx.above_50ema
      ? '<span style="color:var(--green)">▲ Above 50 EMA</span>'
      : '<span style="color:var(--red)">▼ Below 50 EMA</span>';

  const vixColor = ctx.vix_status === 'LOW'      ? 'var(--green)'
                 : ctx.vix_status === 'ELEVATED' ? 'var(--yellow)'
                 : ctx.vix_status === 'HIGH'      ? 'var(--red)'
                 : 'var(--text-muted)';

  document.getElementById('stratCtxGrid').innerHTML = `
    <div class="strat-ctx-card">
      <div class="strat-ctx-label">Nifty 50</div>
      <div class="strat-ctx-val" style="color:var(--text)">
        ${ctx.nifty_price != null ? '₹' + ctx.nifty_price.toLocaleString('en-IN') : '–'}
        ${niftyChange}
      </div>
      <div class="strat-ctx-sub">${aboveHtml}</div>
      <div class="strat-ctx-sub" style="color:var(--text-muted)">
        50 EMA: ${ctx.nifty_50ema != null ? '₹' + ctx.nifty_50ema.toLocaleString('en-IN') : '–'}
        &nbsp;|&nbsp;
        200 EMA: ${ctx.nifty_200ema != null ? '₹' + ctx.nifty_200ema.toLocaleString('en-IN') : '–'}
      </div>
    </div>
    <div class="strat-ctx-card">
      <div class="strat-ctx-label">India VIX</div>
      <div class="strat-ctx-val" style="color:${vixColor}">
        ${ctx.vix_value != null ? ctx.vix_value.toFixed(1) : '–'}
      </div>
      <div class="strat-ctx-sub" style="color:${vixColor}">${ctx.vix_status || '–'}</div>
      <div class="strat-ctx-sub" style="color:var(--text-muted)">${ctx.vix_label || '–'}</div>
    </div>
    <div class="strat-ctx-card strat-ctx-bias">
      <div class="strat-ctx-label">Market Bias</div>
      <div class="strat-ctx-val" style="color:${biasColor};font-size:26px">
        ${ctx.market_bias || '–'}
      </div>
      <div class="strat-ctx-sub" style="color:${biasColor}">
        ${ctx.allocation_pct}% capital allocation
      </div>
      <div class="strat-ctx-sub" style="color:var(--text-dim);font-size:10px;margin-top:4px">
        Long bias requires: Nifty > 50 EMA &amp; VIX &lt; 18
      </div>
    </div>
  `;
}

// ── Phase 2 — Sector Rotation ─────────────────────────────────────────────
function renderStratSectors(sr) {
  const qbadge = document.getElementById('stratQuarterBadge');
  if (sr.current_quarter) {
    qbadge.textContent = sr.current_quarter + ' seasonality: ' +
      (sr.calendar_sectors || []).join(', ');
  }

  const tbody = document.getElementById('stratSectorBody');
  if (!sr.sectors || !sr.sectors.length) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">No sector data</td></tr>';
    return;
  }

  const topSet = new Set((sr.top_sectors || []).slice(0, 3));
  const niftyRef = sr.nifty_4w_return != null
    ? ` <span style="color:var(--text-muted);font-size:10px">(Nifty 4W: ${sr.nifty_4w_return > 0 ? '+' : ''}${sr.nifty_4w_return}%)</span>` : '';

  tbody.innerHTML = sr.sectors.map(s => {
    const isTop = topSet.has(s.sector);
    const rs    = s.rs_score;
    const rsCol = rs == null ? 'var(--text-muted)'
                : rs > 2   ? 'var(--green)'
                : rs < -2  ? 'var(--red)'
                : 'var(--yellow)';
    const r4col = s.return_4w == null ? 'var(--text-muted)'
                : s.return_4w > 0 ? 'var(--green)' : 'var(--red)';
    const r1col = s.return_1w == null ? 'var(--text-muted)'
                : s.return_1w > 0 ? 'var(--green)' : 'var(--red)';
    const momHtml = s.momentum === 'ACCELERATING'
      ? '<span style="color:var(--green)">▲ Accel</span>'
      : '<span style="color:var(--red)">▼ Decel</span>';

    return `<tr class="${isTop ? 'strat-top-sector' : ''}">
      <td style="text-align:center;font-family:var(--mono);font-weight:700">
        ${s.rank || '–'}${isTop ? ' 🔥' : ''}
      </td>
      <td><strong>${s.sector}</strong></td>
      <td style="color:${r4col};font-family:var(--mono)">
        ${s.return_4w != null ? (s.return_4w > 0 ? '+' : '') + s.return_4w + '%' : '–'}
      </td>
      <td style="color:${r1col};font-family:var(--mono)">
        ${s.return_1w != null ? (s.return_1w > 0 ? '+' : '') + s.return_1w + '%' : '–'}
      </td>
      <td style="color:${rsCol};font-family:var(--mono);font-weight:600">
        ${rs != null ? (rs > 0 ? '+' : '') + rs + '%' : '–'}
      </td>
      <td>${s.momentum !== '—' ? momHtml : '–'}</td>
      <td>${isTop ? '<span class="strat-top-badge">TOP SECTOR</span>' : ''}</td>
    </tr>`;
  }).join('');
}

// ── Phase 3+4 — Summary chips ─────────────────────────────────────────────
function renderStratSummaryChips(summary) {
  const topSectorStocks = stratStocks.filter(s => s.top_sector).length;
  document.getElementById('stratSummaryChips').innerHTML = `
    <div class="strat-chip strat-chip-blue">
      <span class="strat-chip-num">${summary.total_qualified ?? 0}</span>
      <span class="strat-chip-lbl">NIFTY 100 Qualified</span>
    </div>
    <div class="strat-chip strat-chip-purple">
      <span class="strat-chip-num">${topSectorStocks}</span>
      <span class="strat-chip-lbl">🔥 Top-Sector Stocks</span>
    </div>
    <div class="strat-chip strat-chip-green">
      <span class="strat-chip-num">${summary.with_patterns ?? 0}</span>
      <span class="strat-chip-lbl">Active Setups</span>
    </div>
    <div class="strat-chip strat-chip-yellow">
      <span class="strat-chip-num">${summary.ema_pullback_count ?? 0}</span>
      <span class="strat-chip-lbl">📉 EMA Pullbacks</span>
    </div>
    <div class="strat-chip strat-chip-green">
      <span class="strat-chip-num">${summary.base_breakout_count ?? 0}</span>
      <span class="strat-chip-lbl">🚀 Base Breakouts</span>
    </div>
    <div class="strat-chip strat-chip-blue">
      <span class="strat-chip-num">${summary.gap_reversal_count ?? 0}</span>
      <span class="strat-chip-lbl">⚡ Gap Reversals</span>
    </div>
  `;
}

// ── Filter + sort ─────────────────────────────────────────────────────────
function setStratFilter(el, pf) {
  document.querySelectorAll('.strat-tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  stratFilter = pf;
  applyStratFilters();
}

function sortStrat(key) {
  if (stratSortKey === key) stratSortAsc = !stratSortAsc;
  else { stratSortKey = key; stratSortAsc = key === 'symbol'; }
  applyStratFilters();
}

function applyStratFilters() {
  let filtered = [...stratStocks];

  if (stratFilter === 'TOP_SECTOR') {
    filtered = filtered.filter(s => s.top_sector);
  } else if (stratFilter === 'WITH_PATTERN') {
    filtered = filtered.filter(s => s.has_setup);
  } else if (['EMA_PULLBACK', 'BASE_BREAKOUT', 'GAP_REVERSAL'].includes(stratFilter)) {
    filtered = filtered.filter(s =>
      s.patterns && s.patterns.some(p => p.pattern === stratFilter)
    );
  }

  filtered.sort((a, b) => {
    let va = a[stratSortKey], vb = b[stratSortKey];
    if (typeof va === 'string') va = va.toLowerCase();
    if (typeof vb === 'string') vb = vb.toLowerCase();
    if (va == null) return 1;
    if (vb == null) return -1;
    return stratSortAsc ? (va < vb ? -1 : va > vb ? 1 : 0)
                        : (va > vb ? -1 : va < vb ? 1 : 0);
  });

  renderStratTable(filtered);
}

// ── Table render ──────────────────────────────────────────────────────────
function renderStratTable(stocks) {
  const tbody = document.getElementById('stratStockBody');

  if (!stocks.length) {
    tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;padding:32px;color:var(--text-muted)">
      No stocks match this filter.
    </td></tr>`;
    return;
  }

  tbody.innerHTML = stocks.map(s => buildStratRow(s)).join('');

  // Re-expand
  stratExpandedRows.forEach(sym => {
    const dr = document.getElementById(`strat-detail-${sym}`);
    const mr = document.getElementById(`strat-row-${sym}`);
    if (dr) dr.style.display = '';
    if (mr) mr.classList.add('expanded');
  });
}

function buildStratRow(s) {
  const id    = s.symbol.replace(/[^a-zA-Z0-9]/g, '_');
  const rowId = `strat-row-${id}`;
  const detId = `strat-detail-${id}`;

  // Change %
  const chg = s.chg_pct;
  const chgHtml = chg != null
    ? `<span style="color:${chg >= 0 ? 'var(--green)' : 'var(--red)'}">${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%</span>`
    : '–';

  // Trend badge
  const trendColor = s.trend === 'STRONG_UP' ? 'var(--green)'
                   : s.trend === 'UPTREND'    ? '#7cf'
                   : 'var(--text-muted)';
  const trendLabel = s.trend === 'STRONG_UP' ? '↑↑ Strong Up'
                   : s.trend === 'UPTREND'    ? '↑ Uptrend'
                   : '↓ Downtrend';

  // EMA proximity
  const ema21pct = s.ema21 ? ((s.cmp - s.ema21) / s.ema21 * 100).toFixed(1) : null;
  const ema50pct = s.ema50 ? ((s.cmp - s.ema50) / s.ema50 * 100).toFixed(1) : null;
  const emaHtml = `
    <span style="color:${parseFloat(ema21pct) > 0 ? 'var(--green)' : 'var(--red)'}">21: ${ema21pct != null ? (ema21pct > 0 ? '+' : '') + ema21pct + '%' : '–'}</span>
    <span style="color:var(--text-dim)"> / </span>
    <span style="color:${parseFloat(ema50pct) > 0 ? 'var(--green)' : 'var(--red)'}">50: ${ema50pct != null ? (ema50pct > 0 ? '+' : '') + ema50pct + '%' : '–'}</span>
  `;

  // 52W distance
  const d52 = s.dist_52wh;
  const d52Color = d52 >= -5 ? 'var(--green)' : d52 >= -15 ? 'var(--yellow)' : 'var(--text-muted)';

  // Pattern badges
  const patHtml = !s.patterns || !s.patterns.length
    ? '<span style="color:var(--text-dim)">–</span>'
    : s.patterns.map(p =>
        `<span class="strat-pat-badge strat-pat-${p.pattern}">${p.pattern_icon} ${p.pattern_label}</span>`
      ).join(' ');

  const expandIcon = stratExpandedRows.has(id) ? '▼' : '▶';

  return `
    <tr id="${rowId}" class="strat-stock-row ${s.has_setup ? 'strat-has-setup' : ''}"
        onclick="toggleStratRow('${id}')">
      <td class="strat-expand-btn">${expandIcon}</td>
      <td><strong>${s.symbol}</strong><br><span style="color:var(--text-dim);font-size:10px">${s.name}</span></td>
      <td>
        <span style="color:var(--text-muted)">${s.sector}</span>
        ${s.top_sector
          ? `<br><span class="strat-sector-rank top">🔥 #${s.sector_rank}</span>`
          : `<br><span class="strat-sector-rank">#${s.sector_rank ?? '–'} ${s.sector_rs != null ? (s.sector_rs > 0 ? '+' : '') + s.sector_rs + '%' : ''}</span>`
        }
      </td>
      <td style="font-family:var(--mono)">₹${fmt(s.cmp)}</td>
      <td>${chgHtml}</td>
      <td style="color:${trendColor};font-size:11px">${trendLabel}</td>
      <td style="font-size:11px;font-family:var(--mono)">${emaHtml}</td>
      <td style="color:${d52Color};font-family:var(--mono)">${d52 != null ? d52 + '%' : '–'}</td>
      <td style="font-family:var(--mono);color:var(--text-muted)">${s.avg_daily_val_cr ?? '–'} Cr</td>
      <td class="strat-pat-cell">${patHtml}</td>
    </tr>
    <tr id="${detId}" class="strat-detail-row" style="display:none">
      <td colspan="10" class="strat-detail-cell">
        ${buildStratDetail(s)}
      </td>
    </tr>
  `;
}

function buildStratDetail(s) {
  if (!s.patterns || !s.patterns.length) {
    return `<div class="strat-detail-wrap">
      <div style="color:var(--text-dim);padding:12px">No active patterns. Stock passes quality gate (above 200 EMA, volume ok).</div>
      <div class="strat-ema-ladder">
        <div class="strat-ema-item"><span>10 EMA</span><span style="font-family:var(--mono)">₹${fmt(s.ema10)}</span></div>
        <div class="strat-ema-item"><span>21 EMA</span><span style="font-family:var(--mono)">₹${fmt(s.ema21)}</span></div>
        <div class="strat-ema-item"><span>50 EMA</span><span style="font-family:var(--mono)">₹${fmt(s.ema50)}</span></div>
        <div class="strat-ema-item"><span>200 EMA</span><span style="font-family:var(--mono)">₹${fmt(s.ema200)}</span></div>
      </div>
    </div>`;
  }

  const patsHtml = s.patterns.map(p => {
    const risk = p.entry && p.stop_loss ? (p.entry - p.stop_loss) : null;
    const riskPct = risk && p.entry ? ((risk / p.entry) * 100).toFixed(1) : null;

    // Phase 5: position size for 1L capital
    const posSize1L = risk ? Math.floor(100000 * 0.015 / risk) : null;

    return `
      <div class="strat-pattern-card strat-pat-card-${p.pattern}">
        <div class="strat-pattern-header">
          <span class="strat-pattern-name">${p.pattern_icon} ${p.pattern_label}</span>
          <span class="strat-pattern-note">${p.note || ''}</span>
        </div>
        <div class="strat-levels-grid">
          <div class="strat-level-item strat-entry">
            <span class="strat-level-label">Entry</span>
            <span class="strat-level-val">₹${fmt(p.entry)}</span>
          </div>
          <div class="strat-level-item strat-stop">
            <span class="strat-level-label">Stop Loss</span>
            <span class="strat-level-val">₹${fmt(p.stop_loss)}</span>
            ${riskPct ? `<span class="strat-level-sub">−${riskPct}%</span>` : ''}
          </div>
          <div class="strat-level-item strat-t1">
            <span class="strat-level-label">Target 1 (1:2)</span>
            <span class="strat-level-val">₹${fmt(p.target1)}</span>
          </div>
          <div class="strat-level-item strat-t2">
            <span class="strat-level-label">Target 2 (1:3)</span>
            <span class="strat-level-val">₹${fmt(p.target2)}</span>
          </div>
          <div class="strat-level-item strat-t3">
            <span class="strat-level-label">Target 3 (1:4)</span>
            <span class="strat-level-val">₹${fmt(p.target3)}</span>
          </div>
          <div class="strat-level-item strat-scale">
            <span class="strat-level-label">Exit 50% at</span>
            <span class="strat-level-val">₹${fmt(p.scale_out_50pct)}</span>
            <span class="strat-level-sub">then trail 10 EMA</span>
          </div>
        </div>
        <div class="strat-pattern-footer">
          <span>Vol ratio: <strong>${p.vol_ratio != null ? p.vol_ratio + 'x' : '–'}</strong></span>
          ${posSize1L ? `<span>Shares for ₹1L @ 1.5% risk: <strong>${posSize1L}</strong></span>` : ''}
          ${p.trail_stop ? `<span>10 EMA trail: <strong>₹${fmt(p.trail_stop)}</strong></span>` : ''}
        </div>
      </div>
    `;
  }).join('');

  return `<div class="strat-detail-wrap">
    <div class="strat-ema-ladder">
      <div class="strat-ema-item"><span>CMP</span><span style="font-family:var(--mono);color:var(--text)">₹${fmt(s.cmp)}</span></div>
      <div class="strat-ema-item"><span>10 EMA</span><span style="font-family:var(--mono)">₹${fmt(s.ema10)}</span></div>
      <div class="strat-ema-item"><span>21 EMA</span><span style="font-family:var(--mono)">₹${fmt(s.ema21)}</span></div>
      <div class="strat-ema-item"><span>50 EMA</span><span style="font-family:var(--mono)">₹${fmt(s.ema50)}</span></div>
      <div class="strat-ema-item"><span>200 EMA</span><span style="font-family:var(--mono)">₹${fmt(s.ema200)}</span></div>
      <div class="strat-ema-item"><span>52W High</span><span style="font-family:var(--mono);color:var(--green)">₹${fmt(s.w52_high)}</span></div>
      <div class="strat-ema-item"><span>Avg Vol 20d</span><span style="font-family:var(--mono)">${s.avg_daily_val_cr ?? '–'} Cr/day</span></div>
    </div>
    <div class="strat-patterns-list">${patsHtml}</div>
  </div>`;
}

function toggleStratRow(id) {
  const detRow = document.getElementById(`strat-detail-${id}`);
  const mainRow = document.getElementById(`strat-row-${id}`);
  if (!detRow) return;

  const isOpen = detRow.style.display !== 'none';
  detRow.style.display = isOpen ? 'none' : '';
  mainRow.classList.toggle('expanded', !isOpen);
  if (isOpen) stratExpandedRows.delete(id);
  else stratExpandedRows.add(id);

  // Update expand icon
  const btn = mainRow.querySelector('.strat-expand-btn');
  if (btn) btn.textContent = isOpen ? '▶' : '▼';
}

// ── Phase 5 — Position size calculator ───────────────────────────────────
function calcPosition() {
  const capital  = parseFloat(document.getElementById('calcCapital').value)  || 0;
  const entry    = parseFloat(document.getElementById('calcEntry').value)    || 0;
  const stop     = parseFloat(document.getElementById('calcStop').value)     || 0;
  const riskPct  = parseFloat(document.getElementById('calcRiskPct').value)  || 1.5;
  const el       = document.getElementById('calcResults');

  if (!entry || !stop || entry <= stop) {
    el.innerHTML = '<p style="color:var(--text-dim);font-size:12px">Enter valid Entry and Stop Loss (Entry must be above Stop).</p>';
    return;
  }

  const riskPerTrade = capital * (riskPct / 100);
  const riskPerShare = entry - stop;
  const shares       = Math.floor(riskPerTrade / riskPerShare);
  const posValue     = shares * entry;
  const posValuePct  = (posValue / capital * 100).toFixed(1);
  const t1           = entry + riskPerShare * 2;
  const t2           = entry + riskPerShare * 3;
  const t3           = entry + riskPerShare * 4;
  const exit50pct    = t1;

  el.innerHTML = `
    <div class="calc-row">
      <span>Capital at Risk</span>
      <strong style="color:var(--red)">₹${riskPerTrade.toLocaleString('en-IN', {maximumFractionDigits: 0})}</strong>
    </div>
    <div class="calc-row">
      <span>Risk Per Share</span>
      <strong>₹${riskPerShare.toFixed(2)}</strong>
    </div>
    <div class="calc-row">
      <span>Position Size</span>
      <strong style="color:var(--blue)">${shares.toLocaleString('en-IN')} shares</strong>
    </div>
    <div class="calc-row">
      <span>Position Value</span>
      <strong>₹${posValue.toLocaleString('en-IN', {maximumFractionDigits: 0})} (${posValuePct}%)</strong>
    </div>
    <hr style="border-color:var(--border);margin:8px 0">
    <div class="calc-row">
      <span>Target 1 (1:2 R:R)</span>
      <strong style="color:var(--green)">₹${t1.toFixed(2)}</strong>
    </div>
    <div class="calc-row">
      <span>Target 2 (1:3 R:R)</span>
      <strong style="color:var(--green)">₹${t2.toFixed(2)}</strong>
    </div>
    <div class="calc-row">
      <span>Target 3 (1:4 R:R)</span>
      <strong style="color:var(--green)">₹${t3.toFixed(2)}</strong>
    </div>
    <hr style="border-color:var(--border);margin:8px 0">
    <div class="calc-row">
      <span>Exit 50% at T1</span>
      <strong>₹${exit50pct.toFixed(2)} → move stop to ₹${entry.toFixed(2)}</strong>
    </div>
    <div class="calc-row" style="margin-top:6px;font-size:10px;color:var(--text-dim)">
      <span>Max portfolio heat (6 positions)</span>
      <strong>${(riskPct * 6).toFixed(1)}%</strong>
    </div>
  `;
}


/* ══════════════════════════════════════════════════════════════════════════
   INTRACONTRA — 3M MOMENTUM SWING SYSTEM
   ══════════════════════════════════════════════════════════════════════════ */

let icStocks   = [];
let icFilter   = 'ALL';
let icSortKey  = 'setup_count';
let icSortAsc  = false;
let icExpanded = new Set();

// ── Fetch ─────────────────────────────────────────────────────────────────
async function runIntraContra() {
  const btn = document.getElementById('icRunBtn');
  btn.disabled = true;
  btn.classList.add('loading');
  btn.textContent = '⏳ Scanning…';
  showLoader('Fetching Nifty trend + VIX…');

  const msgs = [
    'Computing sector ranks…',
    'Screening EMA alignment…',
    'RSI + ADX quality gate…',
    'Detecting Flag & Pole setups…',
    'Scanning 52-week breakouts…',
    'Finding EMA pullback entries…',
    'Identifying sector rotation plays…',
    'Building trade plans…',
  ];
  let mi = 0;
  const t = setInterval(() => {
    document.getElementById('loaderText').textContent = msgs[mi++ % msgs.length];
  }, 9000);

  try {
    const res = await fetch(`${API}/api/strategy/intra-contra`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    renderIntraContra(data);
    showToast('IntraContra scan complete!', 'success');
  } catch (e) {
    showToast(`IntraContra error: ${e.message}`, 'error');
    console.error(e);
  } finally {
    clearInterval(t);
    hideLoader();
    btn.disabled = false;
    btn.classList.remove('loading');
    btn.textContent = '⚡ Run Scanner';
  }
}

// ── Master renderer ───────────────────────────────────────────────────────
function renderIntraContra(data) {
  document.getElementById('icEmpty').style.display   = 'none';
  document.getElementById('icContent').style.display = '';

  const ts = data.run_date && data.run_time
    ? `Last: ${data.run_date} ${data.run_time}` : (data.run_date || '–');
  document.getElementById('icLastRun').textContent = ts;

  renderIcCtx(data.market_context || {});
  icStocks = data.stocks || [];
  renderIcChips(data.summary || {});
  applyIcFilters();
}

// ── Market Pulse ──────────────────────────────────────────────────────────
function renderIcCtx(ctx) {
  const biasCol = ctx.trade_bias_color === 'green' ? 'var(--green)'
                : ctx.trade_bias_color === 'red'   ? 'var(--red)'
                : '#f59e0b';

  const wkCol = ctx.nifty_weekly === 'BULL'     ? 'var(--green)'
              : ctx.nifty_weekly === 'BEAR'     ? 'var(--red)'
              : '#f59e0b';
  const dyCol = ctx.nifty_daily === 'STRONG_BULL' || ctx.nifty_daily === 'BULL'
              ? 'var(--green)' : ctx.nifty_daily === 'BEAR' ? 'var(--red)' : '#f59e0b';

  const vixCol = ctx.vix_status === 'LOW'     ? 'var(--green)'
               : ctx.vix_status === 'ELEVATED'? '#f59e0b'
               : ctx.vix_status === 'HIGH'    ? 'var(--red)'
               : 'var(--text-muted)';

  const chgHtml = ctx.nifty_chg_pct != null
    ? `<span style="color:${ctx.nifty_chg_pct >= 0 ? 'var(--green)' : 'var(--red)'};font-size:13px">
        ${ctx.nifty_chg_pct >= 0 ? '+' : ''}${ctx.nifty_chg_pct.toFixed(2)}%</span>` : '';

  document.getElementById('icCtxGrid').innerHTML = `
    <div class="ic-ctx-card">
      <div class="ic-ctx-label">Nifty 50</div>
      <div class="ic-ctx-val">
        ${ctx.nifty_price != null ? '₹' + ctx.nifty_price.toLocaleString('en-IN') : '–'}
        ${chgHtml}
      </div>
      <div class="ic-ctx-sub" style="color:var(--text-muted)">
        EMA20: ${ctx.nifty_ema20 != null ? '₹' + ctx.nifty_ema20.toLocaleString('en-IN') : '–'}
        &nbsp;/&nbsp; EMA50: ${ctx.nifty_ema50 != null ? '₹' + ctx.nifty_ema50.toLocaleString('en-IN') : '–'}
      </div>
      <div class="ic-ctx-sub">RSI: <strong style="color:${ctx.nifty_rsi >= 55 && ctx.nifty_rsi <= 75 ? 'var(--green)' : 'var(--text-muted)'}">${ctx.nifty_rsi != null ? ctx.nifty_rsi.toFixed(1) : '–'}</strong>
        &nbsp;ADX: <strong>${ctx.nifty_adx != null ? ctx.nifty_adx.toFixed(1) : '–'}</strong></div>
    </div>
    <div class="ic-ctx-card">
      <div class="ic-ctx-label">Weekly Trend</div>
      <div class="ic-ctx-val" style="color:${wkCol}">${ctx.nifty_weekly || '–'}</div>
      <div class="ic-ctx-sub" style="color:var(--text-muted)">From weekly EMA(10)/EMA(20)</div>
    </div>
    <div class="ic-ctx-card">
      <div class="ic-ctx-label">Daily Trend</div>
      <div class="ic-ctx-val" style="color:${dyCol}">${(ctx.nifty_daily || '–').replace('_', ' ')}</div>
      <div class="ic-ctx-sub" style="color:var(--text-muted)">EMA 20 / 50 alignment</div>
    </div>
    <div class="ic-ctx-card">
      <div class="ic-ctx-label">India VIX</div>
      <div class="ic-ctx-val" style="color:${vixCol}">${ctx.vix_value != null ? ctx.vix_value.toFixed(1) : '–'}</div>
      <div class="ic-ctx-sub" style="color:${vixCol}">${ctx.vix_status || '–'}</div>
    </div>
    <div class="ic-ctx-card ic-ctx-bias">
      <div class="ic-ctx-label">Trade Bias</div>
      <div class="ic-ctx-val" style="color:${biasCol};font-size:22px">${ctx.trade_bias || '–'}</div>
      <div class="ic-ctx-sub" style="color:var(--text-dim);font-size:10px">
        Both Weekly &amp; Daily must be BULL for LONG bias
      </div>
    </div>
  `;
}

// ── Summary chips ─────────────────────────────────────────────────────────
function renderIcChips(s) {
  document.getElementById('icChips').innerHTML = `
    <div class="ic-chip ic-chip-blue"><span class="ic-chip-num">${s.total ?? 0}</span><span class="ic-chip-lbl">NIFTY 100</span></div>
    <div class="ic-chip ic-chip-green"><span class="ic-chip-num">${s.ema_aligned ?? 0}</span><span class="ic-chip-lbl">EMA Aligned</span></div>
    <div class="ic-chip ic-chip-orange"><span class="ic-chip-num">${s.with_setups ?? 0}</span><span class="ic-chip-lbl">Active Setups</span></div>
    <div class="ic-chip ic-chip-orange"><span class="ic-chip-num">${s.flag_pole ?? 0}</span><span class="ic-chip-lbl">Flag &amp; Pole</span></div>
    <div class="ic-chip ic-chip-green"><span class="ic-chip-num">${s.ema_pullback ?? 0}</span><span class="ic-chip-lbl">EMA Pullback</span></div>
    <div class="ic-chip ic-chip-blue"><span class="ic-chip-num">${s.high_breakout ?? 0}</span><span class="ic-chip-lbl">52W Breakout</span></div>
    <div class="ic-chip ic-chip-purple"><span class="ic-chip-num">${s.sector_rotation ?? 0}</span><span class="ic-chip-lbl">Sector Rotation</span></div>
  `;
}

// ── Filters + Sort ────────────────────────────────────────────────────────
function setIcFilter(el, f) {
  document.querySelectorAll('.ic-tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  icFilter = f;
  applyIcFilters();
}

function sortIc(key) {
  if (icSortKey === key) icSortAsc = !icSortAsc;
  else { icSortKey = key; icSortAsc = key === 'symbol'; }
  applyIcFilters();
}

function applyIcFilters() {
  let f = [...icStocks];
  if (icFilter === 'HAS_SETUP') {
    f = f.filter(s => s.has_setup);
  } else if (icFilter === 'EMA_ALIGNED') {
    f = f.filter(s => s.ema_aligned);
  } else if (['FLAG_POLE','EMA_PULLBACK','HIGH_BREAKOUT','SECTOR_ROTATION'].includes(icFilter)) {
    f = f.filter(s => s.setups && s.setups.some(st => st.setup === icFilter));
  }
  f.sort((a, b) => {
    let va = a[icSortKey], vb = b[icSortKey];
    if (typeof va === 'string') va = va.toLowerCase();
    if (typeof vb === 'string') vb = vb.toLowerCase();
    if (va == null) return 1;
    if (vb == null) return -1;
    return icSortAsc ? (va < vb ? -1 : va > vb ? 1 : 0)
                     : (va > vb ? -1 : va < vb ? 1 : 0);
  });
  renderIcTable(f);
}

// ── Table ─────────────────────────────────────────────────────────────────
function renderIcTable(stocks) {
  const tbody = document.getElementById('icTableBody');
  if (!stocks.length) {
    tbody.innerHTML = `<tr><td colspan="11" style="text-align:center;padding:32px;color:var(--text-muted)">No stocks match this filter.</td></tr>`;
    return;
  }
  tbody.innerHTML = stocks.map(s => buildIcRow(s)).join('');
  icExpanded.forEach(id => {
    const dr = document.getElementById(`ic-det-${id}`);
    const mr = document.getElementById(`ic-row-${id}`);
    if (dr) dr.style.display = '';
    if (mr) mr.classList.add('expanded');
  });
}

function buildIcRow(s) {
  const id    = s.symbol.replace(/[^a-zA-Z0-9]/g, '_');
  const rowId = `ic-row-${id}`;
  const detId = `ic-det-${id}`;

  const chg = s.chg_pct;
  const chgHtml = chg != null
    ? `<span style="color:${chg >= 0 ? 'var(--green)' : 'var(--red)'}">${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%</span>`
    : '–';

  // Weekly / Daily trend badges
  const wkCol = s.weekly_trend === 'BULL' ? 'var(--green)' : s.weekly_trend === 'BEAR' ? 'var(--red)' : '#f59e0b';
  const dyCol = s.daily_trend  === 'STRONG_BULL' || s.daily_trend === 'BULL' ? 'var(--green)'
              : s.daily_trend  === 'BEAR' ? 'var(--red)' : '#f59e0b';
  const trendHtml = `<span style="color:${wkCol};font-size:10px">W:${s.weekly_trend?.charAt(0) ?? '?'}</span>
    <span style="color:var(--text-dim)"> / </span>
    <span style="color:${dyCol};font-size:10px">D:${(s.daily_trend || '?').replace('STRONG_','S+').replace('BULL','B').replace('BEAR','Br').replace('NEUTRAL','N')}</span>`;

  // RSI colour
  const rsiCol = s.rsi_14 != null && s.rsi_14 >= 55 && s.rsi_14 <= 75 ? 'var(--green)'
               : s.rsi_14 != null && s.rsi_14 < 40 ? 'var(--red)' : 'var(--text-muted)';

  // ADX
  const adxCol = s.adx_14 != null && s.adx_14 >= 25 ? 'var(--green)' : 'var(--text-muted)';

  // Volume
  const volCol = s.vol_ratio >= 1.5 ? 'var(--green)' : s.vol_ratio >= 1.0 ? 'var(--text-muted)' : 'var(--red)';

  // 52W
  const d52Col = s.dist_52wh >= -5 ? 'var(--green)' : s.dist_52wh >= -15 ? '#f59e0b' : 'var(--text-muted)';

  // Sector
  const secHtml = `<span style="color:var(--text-muted)">${s.sector}</span>
    <br><span style="font-size:10px;color:${s.sector_rank <= 3 ? '#f59e0b' : 'var(--text-dim)'}">
      ${s.sector_rank <= 3 ? '🔥' : ''} #${s.sector_rank ?? '–'}
    </span>`;

  // Setup badges
  const setupCols = { FLAG_POLE: '#f59e0b', EMA_PULLBACK: 'var(--green)', HIGH_BREAKOUT: 'var(--blue)', SECTOR_ROTATION: '#a855f7' };
  const setupIcons = { FLAG_POLE: '🚩', EMA_PULLBACK: '📉', HIGH_BREAKOUT: '🚀', SECTOR_ROTATION: '🔄' };
  const setupsHtml = !s.setups?.length
    ? `<span style="color:var(--text-dim);font-size:10px">${s.ema_aligned ? 'Aligned' : '–'}</span>`
    : s.setups.map(st =>
        `<span class="ic-setup-badge" style="background:${setupCols[st.setup]}22;color:${setupCols[st.setup]};border:1px solid ${setupCols[st.setup]}44">
          ${setupIcons[st.setup]} ${st.setup_label}
        </span>`
      ).join('');

  return `
    <tr id="${rowId}" class="ic-stock-row ${s.has_setup ? 'ic-has-setup' : ''}" onclick="toggleIcRow('${id}')">
      <td class="ic-expand">${icExpanded.has(id) ? '▼' : '▶'}</td>
      <td><strong>${s.symbol}</strong><br><span style="color:var(--text-dim);font-size:10px">${s.name}</span></td>
      <td>${secHtml}</td>
      <td style="font-family:var(--mono)">₹${fmt(s.cmp)}</td>
      <td>${chgHtml}</td>
      <td style="white-space:nowrap">${trendHtml}</td>
      <td style="color:${rsiCol};font-family:var(--mono)">${s.rsi_14 != null ? s.rsi_14.toFixed(1) : '–'}</td>
      <td style="color:${adxCol};font-family:var(--mono)">${s.adx_14 != null ? s.adx_14.toFixed(1) : '–'}</td>
      <td style="color:${volCol};font-family:var(--mono)">${s.vol_ratio != null ? s.vol_ratio.toFixed(1) + 'x' : '–'}</td>
      <td style="color:${d52Col};font-family:var(--mono)">${s.dist_52wh != null ? s.dist_52wh + '%' : '–'}</td>
      <td class="ic-setups-cell">${setupsHtml}</td>
    </tr>
    <tr id="${detId}" class="ic-detail-row" style="display:none">
      <td colspan="11" class="ic-detail-cell">${buildIcDetail(s)}</td>
    </tr>
  `;
}

function buildIcDetail(s) {
  const emaLadder = `
    <div class="ic-ema-ladder">
      <div class="ic-ema-row"><span>CMP</span><span style="font-family:var(--mono);color:var(--text)">₹${fmt(s.cmp)}</span></div>
      <div class="ic-ema-row"><span>EMA 20</span><span style="font-family:var(--mono)">₹${fmt(s.ema20)}</span></div>
      <div class="ic-ema-row"><span>EMA 50</span><span style="font-family:var(--mono)">₹${fmt(s.ema50)}</span></div>
      <div class="ic-ema-row"><span>EMA 200</span><span style="font-family:var(--mono)">₹${fmt(s.ema200)}</span></div>
      <div class="ic-ema-row"><span>52W High</span><span style="font-family:var(--mono);color:var(--green)">₹${fmt(s.w52_high)}</span></div>
      <div class="ic-ema-row"><span>RSI(14)</span><span style="font-family:var(--mono)">${s.rsi_14 != null ? s.rsi_14.toFixed(1) : '–'}</span></div>
      <div class="ic-ema-row"><span>ADX(14)</span><span style="font-family:var(--mono)">${s.adx_14 != null ? s.adx_14.toFixed(1) : '–'}</span></div>
      <div class="ic-ema-row"><span>Vol Ratio</span><span style="font-family:var(--mono)">${s.vol_ratio != null ? s.vol_ratio.toFixed(2) + 'x' : '–'}</span></div>
      <div class="ic-ema-row"><span>Daily Val</span><span style="font-family:var(--mono)">${s.avg_val_cr ?? '–'} Cr</span></div>
    </div>`;

  if (!s.setups?.length) {
    return `<div class="ic-detail-wrap">${emaLadder}<div style="padding:14px;color:var(--text-dim)">No active setups. Stock screened but no pattern trigger yet.</div></div>`;
  }

  const setupCols = { FLAG_POLE: '#f59e0b', EMA_PULLBACK: 'var(--green)', HIGH_BREAKOUT: 'var(--blue)', SECTOR_ROTATION: '#a855f7' };
  const cardsHtml = s.setups.map(st => {
    const risk = st.entry && st.stop_loss ? st.entry - st.stop_loss : null;
    const riskPct = risk && st.entry ? ((risk / st.entry) * 100).toFixed(1) : null;
    const pos1L = risk ? Math.floor(1000000 * 0.02 / risk) : null; // 2% of 10L
    const col   = setupCols[st.setup] || 'var(--text)';

    return `
      <div class="ic-setup-card" style="border-top-color:${col}">
        <div class="ic-setup-hdr">
          <span class="ic-setup-name" style="color:${col}">${st.setup_icon} ${st.setup_label}</span>
          <span class="ic-setup-wr" style="color:${col}">${st.win_rate}</span>
        </div>
        <div class="ic-setup-note">${st.note || ''}</div>
        <div class="ic-levels-grid">
          <div class="ic-lvl ic-entry"><span class="ic-lvl-lbl">Entry</span><span class="ic-lvl-val">₹${fmt(st.entry)}</span></div>
          <div class="ic-lvl ic-stop"><span class="ic-lvl-lbl">Stop Loss</span><span class="ic-lvl-val">₹${fmt(st.stop_loss)}</span>${riskPct ? `<span class="ic-lvl-sub">−${riskPct}%</span>` : ''}</div>
          <div class="ic-lvl ic-t1"><span class="ic-lvl-lbl">T1 (1.5R) — 40%</span><span class="ic-lvl-val">₹${fmt(st.target1)}</span></div>
          <div class="ic-lvl ic-t2"><span class="ic-lvl-lbl">T2 (2.5R) — 40%</span><span class="ic-lvl-val">₹${fmt(st.target2)}</span></div>
          <div class="ic-lvl ic-t3"><span class="ic-lvl-lbl">T3 (trail) — 20%</span><span class="ic-lvl-val">₹${fmt(st.target3)}</span></div>
          <div class="ic-lvl ic-trail"><span class="ic-lvl-lbl">Trail Stop</span><span class="ic-lvl-val">₹${fmt(st.trail_ref)} <span style="font-size:9px">(${st.trail_label})</span></span></div>
        </div>
        <div class="ic-setup-ftr">
          ${pos1L ? `<span>Qty for ₹10L @ 2% risk: <strong>${pos1L.toLocaleString('en-IN')}</strong></span>` : ''}
          <span>Vol: <strong>${st.vol_ratio != null ? st.vol_ratio + 'x' : '–'}</strong></span>
        </div>
      </div>`;
  }).join('');

  return `<div class="ic-detail-wrap">${emaLadder}<div class="ic-setups-list">${cardsHtml}</div></div>`;
}

function toggleIcRow(id) {
  const det = document.getElementById(`ic-det-${id}`);
  const row = document.getElementById(`ic-row-${id}`);
  if (!det) return;
  const open = det.style.display !== 'none';
  det.style.display = open ? 'none' : '';
  row.classList.toggle('expanded', !open);
  if (open) icExpanded.delete(id); else icExpanded.add(id);
  const btn = row.querySelector('.ic-expand');
  if (btn) btn.textContent = open ? '▶' : '▼';
}

// ── Position size calculator ──────────────────────────────────────────────
function calcIcPosition() {
  const capital = parseFloat(document.getElementById('icCapital').value) || 0;
  const entry   = parseFloat(document.getElementById('icEntry').value)   || 0;
  const stop    = parseFloat(document.getElementById('icStop').value)    || 0;
  const riskPct = parseFloat(document.getElementById('icRiskPct').value) || 2;
  const el      = document.getElementById('icCalcOut');

  if (!entry || !stop || entry <= stop) {
    el.innerHTML = '<p style="color:var(--text-dim);font-size:12px">Enter valid Entry &gt; Stop Loss.</p>';
    return;
  }

  const maxLoss  = capital * (riskPct / 100);
  const riskPer  = entry - stop;
  const shares   = Math.floor(maxLoss / riskPer);
  const posVal   = shares * entry;
  const posValPct= (posVal / capital * 100).toFixed(1);
  const t1       = entry + riskPer * 1.5;
  const t2       = entry + riskPer * 2.5;
  const t3       = entry + riskPer * 4.0;
  const be       = entry;                  // breakeven after moving SL at +2R
  const addAt    = entry + riskPer * 1.5;  // pyramid add trigger

  el.innerHTML = `
    <div class="ic-calc-row"><span>Capital at Risk</span><strong style="color:var(--red)">₹${maxLoss.toLocaleString('en-IN',{maximumFractionDigits:0})}</strong></div>
    <div class="ic-calc-row"><span>Risk Per Share</span><strong>₹${riskPer.toFixed(2)}</strong></div>
    <div class="ic-calc-row"><span>Position Size</span><strong style="color:#f59e0b">${shares.toLocaleString('en-IN')} shares</strong></div>
    <div class="ic-calc-row"><span>Position Value</span><strong>₹${posVal.toLocaleString('en-IN',{maximumFractionDigits:0})} (${posValPct}%)</strong></div>
    <hr style="border-color:var(--border);margin:8px 0">
    <div class="ic-calc-row"><span>T1 @ 1.5R — exit 40%</span><strong style="color:var(--green)">₹${t1.toFixed(2)}</strong></div>
    <div class="ic-calc-row"><span>T2 @ 2.5R — exit 40%</span><strong style="color:var(--green)">₹${t2.toFixed(2)}</strong></div>
    <div class="ic-calc-row"><span>T3 trail 20%</span><strong style="color:var(--green)">₹${t3.toFixed(2)}</strong></div>
    <hr style="border-color:var(--border);margin:8px 0">
    <div class="ic-calc-row"><span>At +2R → SL to breakeven</span><strong>₹${be.toFixed(2)}</strong></div>
    <div class="ic-calc-row"><span>Pyramid add trigger (+1.5R)</span><strong style="color:#f59e0b">₹${addAt.toFixed(2)}</strong></div>
    <div class="ic-calc-row" style="font-size:10px;color:var(--text-dim);margin-top:4px">
      <span>Max 6 positions → heat</span><strong>${(riskPct * 6).toFixed(1)}%</strong>
    </div>
  `;
}
