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
  const prevPage = activePage;
  activePage = page;
  document.querySelectorAll('.page-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.page === page);
  });

  const isScanner  = page === 'scanner';
  const isStrategy = page === 'strategy';
  document.getElementById('scannerPage').style.display  = isScanner          ? '' : 'none';
  document.getElementById('niftyPage').style.display    = page === 'nifty'   ? '' : 'none';
  document.getElementById('strategyPage').style.display = isStrategy         ? '' : 'none';
  document.getElementById('intraPage').style.display    = page === 'intra'   ? '' : 'none';
  document.getElementById('bigbagPage').style.display   = page === 'bigbag'  ? '' : 'none';
  document.getElementById('runbookPage').style.display  = page === 'runbook' ? '' : 'none';
  document.getElementById('runBtn').style.display       = isScanner  ? '' : 'none';
  document.getElementById('lastRunTime').style.display  = isScanner  ? '' : 'none';

  // Auto-refresh live mode when on IntraContra page during market hours
  if (page === 'intra') startIcLiveMode();
  else if (prevPage === 'intra') stopIcLiveMode();
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

let icStocks        = [];
let icFilter        = 'ALL';
let icSortKey       = 'setup_count';
let icSortAsc       = false;
let icExpanded      = new Set();
let icGlobalCapital = 1000000;   // default ₹10L — user-editable from the sub-header

function onIcCapitalChange() {
  const v = parseFloat(document.getElementById('icGlobalCapital').value) || 0;
  icGlobalCapital = v;
  // Keep the Risk Engine calculator in sync
  const calcEl = document.getElementById('icCapital');
  if (calcEl && parseFloat(calcEl.value) !== v) calcEl.value = v || '';
  calcIcPosition();
  // Re-render the table so every expanded setup card shows updated position sizes
  applyIcFilters();
}

// Live mode state
let icLiveTimer     = null;   // setTimeout handle for next auto-refresh
let icCountdownTimer = null;  // setInterval handle for 1-s countdown display
let icNextRefreshAt  = null;  // epoch ms of next scheduled refresh
const IC_REFRESH_MS  = 3 * 60 * 1000;   // auto-refresh every 3 min during market hours

// ── IST / NSE market-hours helpers ────────────────────────────────────────────
function getISTNow() {
  // Returns a Date representing current wall-clock time in IST (UTC+5:30)
  const now = new Date();
  return new Date(now.getTime() + (now.getTimezoneOffset() + 330) * 60 * 1000);
}

function isNSEOpen() {
  const ist = getISTNow();
  const day  = ist.getDay();          // 0=Sun, 6=Sat
  if (day === 0 || day === 6) return false;
  const mins = ist.getHours() * 60 + ist.getMinutes();
  return mins >= 9 * 60 + 15 && mins <= 15 * 60 + 30;
}

// ── Live-mode control ─────────────────────────────────────────────────────────
function updateIcLiveBadge(isLive) {
  const el = document.getElementById('icLiveBadge');
  if (!el) return;
  if (isLive) {
    el.innerHTML = '<span class="ic-live-dot"></span>LIVE';
    el.style.display = '';
  } else {
    el.style.display = 'none';
  }
}

function updateIcCountdown() {
  const el = document.getElementById('icCountdown');
  if (!el || !icNextRefreshAt) { if (el) el.textContent = ''; return; }
  const secs = Math.max(0, Math.floor((icNextRefreshAt - Date.now()) / 1000));
  const m = Math.floor(secs / 60), s = secs % 60;
  el.textContent = `↻ ${m}:${s.toString().padStart(2, '0')}`;
}

function startIcLiveMode() {
  stopIcLiveMode();
  if (!isNSEOpen()) { updateIcLiveBadge(false); return; }
  updateIcLiveBadge(true);

  function scheduleNext() {
    icNextRefreshAt = Date.now() + IC_REFRESH_MS;
    icLiveTimer = setTimeout(() => {
      runIntraContra(true);  // silent auto-refresh
      scheduleNext();
    }, IC_REFRESH_MS);
  }
  scheduleNext();
  icCountdownTimer = setInterval(updateIcCountdown, 1000);
  updateIcCountdown();
}

function stopIcLiveMode() {
  if (icLiveTimer)     { clearTimeout(icLiveTimer);    icLiveTimer = null; }
  if (icCountdownTimer){ clearInterval(icCountdownTimer); icCountdownTimer = null; }
  icNextRefreshAt = null;
  updateIcLiveBadge(false);
  const el = document.getElementById('icCountdown');
  if (el) el.textContent = '';
}

// ── Time Windows Definition ────────────────────────────────────────────────
const IC_TIME_WINDOWS = [
  { label: 'Pre-Market',   time: '9:00–9:15',   color: '#666',    tip: 'Gap analysis, PDH/PDL prep, news scan' },
  { label: 'Opening',      time: '9:15–9:30',   color: '#f59e0b', tip: 'Opening auction — observe only, no trades' },
  { label: 'ORB Window',   time: '9:30–10:15',  color: '#22c55e', tip: '?? PRIME: Opening Range Breakout setup' },
  { label: 'Trend Follow', time: '10:15–11:30', color: '#4a9eff', tip: 'Momentum continuation + VWAP reversion' },
  { label: 'Dead Zone',    time: '11:30–12:30', color: '#444',    tip: '❌ NO TRADES — lunch chop, low volume' },
  { label: 'Afternoon',    time: '12:30–2:00',  color: '#a855f7', tip: 'Institutional activity + VWAP plays' },
  { label: 'Close',        time: '2:00–3:30',   color: '#f59e0b', tip: '⚠️ Exit all positions before 3:15 PM' },
];

// ── Fetch ─────────────────────────────────────────────────────────────────
// silent=true: called by live-mode timer — no full-screen loader overlay
async function runIntraContra(silent = false) {
  const btn = document.getElementById('icRunBtn');
  btn.disabled = true;
  btn.classList.add('loading');
  btn.textContent = silent ? '↻ Refreshing…' : '⏳ Scanning…';

  let t = null;
  if (!silent) {
    showLoader('Fetching Nifty VWAP levels…');
    const msgs = [
      'Fetching PDH / PDL levels…',
      'Computing 20-day VWAP proxy…',
      'Detecting ORB breakout setups…',
      'Scanning live 5-min intraday bars…',
      'Computing Opening Range levels…',
      'Scanning VWAP reversion plays…',
      'Identifying gap setups…',
      'Ranking by setup priority…',
    ];
    let mi = 0;
    t = setInterval(() => {
      document.getElementById('loaderText').textContent = msgs[mi++ % msgs.length];
    }, 6000);
  }

  try {
    const res = await fetch(`${API}/api/strategy/intra-contra`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    renderIntraContra(data);
    if (!silent) showToast('IntraContra scan complete!', 'success');
    // On manual scan restart the countdown from now
    if (!silent && isNSEOpen()) startIcLiveMode();
  } catch (e) {
    showToast(`IntraContra error: ${e.message}`, 'error');
    console.error(e);
  } finally {
    if (t) clearInterval(t);
    if (!silent) hideLoader();
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
    ? `${data.run_date} ${data.run_time}` : (data.run_date || '–');
  document.getElementById('icLastRun').textContent = ts;

  // Live badge (header) — mirrors is_live from response
  updateIcLiveBadge(data.is_live === true);

  // Session info bar
  const sessEl = document.getElementById('icSessionInfo');
  const ms = data.market_session || data.market_context || {};
  if (sessEl) {
    if (ms.is_market_open || ms.is_open) {
      const elapsed = ms.session_elapsed_min;
      const orbDone = ms.orb_complete;
      const liveCount = (data.summary || {}).live_count ?? 0;
      sessEl.style.display = '';
      sessEl.innerHTML = `
        <span class="ic-live-dot" style="width:6px;height:6px;margin-right:5px"></span>
        <strong style="color:var(--green)">NSE OPEN</strong>
        &nbsp;&middot;&nbsp; ${ms.ist_time || ''}
        ${elapsed != null ? `&nbsp;&middot;&nbsp; ${elapsed} min elapsed` : ''}
        &nbsp;&middot;&nbsp; ORB: <strong style="color:${orbDone ? 'var(--green)' : '#f59e0b'}">${orbDone ? 'Complete' : 'In progress (9:15–9:30)'}</strong>
        &nbsp;&middot;&nbsp; ${liveCount} stocks with live 5-min data
        &nbsp;&middot;&nbsp; <span style="color:var(--text-dim)">Data: ~15-min delay (yfinance free tier)</span>
      `;
    } else {
      sessEl.style.display = '';
      sessEl.innerHTML = `
        <span style="color:var(--text-dim)">&#9679; Market CLOSED &nbsp;&middot;&nbsp; ${ms.ist_time || ''} &nbsp;&middot;&nbsp; Showing pre-market analysis (EOD data) — ORB setups appear when market opens</span>
      `;
    }
  }

  // Watchlist source banner
  const bannerEl = document.getElementById('icSourceBanner');
  if (bannerEl) {
    if (data.watchlist_source === 'screener' && data.screener_date) {
      const s = data.summary || {};
      bannerEl.style.display = '';
      bannerEl.innerHTML = `
        <span style="color:var(--green)">&#9679;</span>
        Watchlist sourced from Screener run
        <strong>${data.screener_date}</strong>
        &mdash; ${s.from_screener ?? '?'} HIGH PROB/WATCHLIST stocks
        + ${s.from_baseline ?? '?'} baseline F&amp;O names
      `;
    } else {
      bannerEl.style.display = '';
      bannerEl.innerHTML = `
        <span style="color:#f59e0b">&#9651;</span>
        Using default watchlist &mdash; run the Stock Screener first to get
        a dynamic, signal-driven watchlist here.
      `;
    }
  }

  renderIcCtx(data.market_context || {});
  renderIcTimeBar();
  icStocks = data.stocks || [];
  renderIcChips(data.summary || {});
  applyIcFilters();
}

// ── Market Pulse ──────────────────────────────────────────────────────────
function renderIcCtx(ctx) {
  const biasCol = ctx.trade_bias_color === 'green' ? 'var(--green)'
                : ctx.trade_bias_color === 'red'   ? 'var(--red)'
                : '#f59e0b';

  const vixCol = ctx.vix_status === 'LOW'      ? 'var(--green)'
               : ctx.vix_status === 'MODERATE' ? 'var(--green)'
               : ctx.vix_status === 'ELEVATED' ? '#f59e0b'
               : ctx.vix_status === 'HIGH'     ? 'var(--red)'
               : 'var(--text-muted)';

  const chgHtml = ctx.nifty_chg_pct != null
    ? `<span style="color:${ctx.nifty_chg_pct >= 0 ? 'var(--green)' : 'var(--red)'};font-size:13px">
        ${ctx.nifty_chg_pct >= 0 ? '+' : ''}${ctx.nifty_chg_pct.toFixed(2)}%</span>` : '';

  const vwapDev = ctx.nifty_price && ctx.nifty_vwap
    ? ((ctx.nifty_price - ctx.nifty_vwap) / ctx.nifty_vwap * 100).toFixed(1) : null;

  const vixNote = !ctx.vix_value ? '' :
    ctx.vix_value < 13  ? 'Low vol — trending moves' :
    ctx.vix_value <= 18 ? 'Moderate — normal intraday' :
    ctx.vix_value <= 22 ? 'Elevated — reduce size' : 'High — avoid ORB';

  document.getElementById('icCtxGrid').innerHTML = `
    <div class="ic-ctx-card">
      <div class="ic-ctx-label">Nifty 50</div>
      <div class="ic-ctx-val">
        ${ctx.nifty_price != null ? '₹' + ctx.nifty_price.toLocaleString('en-IN') : '–'}
        ${chgHtml}
      </div>
      <div class="ic-ctx-sub" style="color:var(--text-muted)">
        PDH: ${ctx.nifty_pdh != null ? '₹' + ctx.nifty_pdh.toLocaleString('en-IN') : '–'}
        &nbsp;/&nbsp; PDL: ${ctx.nifty_pdl != null ? '₹' + ctx.nifty_pdl.toLocaleString('en-IN') : '–'}
      </div>
      <div class="ic-ctx-sub">RSI: <strong style="color:${ctx.nifty_rsi >= 55 && ctx.nifty_rsi <= 75 ? 'var(--green)' : ctx.nifty_rsi < 40 ? 'var(--red)' : 'var(--text-muted)'}">${ctx.nifty_rsi != null ? ctx.nifty_rsi.toFixed(1) : '–'}</strong></div>
    </div>
    <div class="ic-ctx-card">
      <div class="ic-ctx-label">VWAP (20-day proxy)</div>
      <div class="ic-ctx-val">${ctx.nifty_vwap != null ? '₹' + ctx.nifty_vwap.toLocaleString('en-IN') : '–'}</div>
      <div class="ic-ctx-sub" style="color:${vwapDev != null && parseFloat(vwapDev) >= 0 ? 'var(--green)' : 'var(--red)'}">
        ${vwapDev != null ? (parseFloat(vwapDev) >= 0 ? '+' : '') + vwapDev + '% from VWAP' : '–'}
      </div>
      <div class="ic-ctx-sub" style="color:var(--text-dim)">Nifty ${ctx.trade_bias === 'LONG' ? 'above' : 'below'} VWAP</div>
    </div>
    <div class="ic-ctx-card">
      <div class="ic-ctx-label">India VIX</div>
      <div class="ic-ctx-val" style="color:${vixCol}">${ctx.vix_value != null ? ctx.vix_value.toFixed(1) : '–'}</div>
      <div class="ic-ctx-sub" style="color:${vixCol}">${ctx.vix_status || '–'}</div>
      <div class="ic-ctx-sub" style="color:var(--text-dim)">${vixNote}</div>
    </div>
    <div class="ic-ctx-card ic-ctx-bias">
      <div class="ic-ctx-label">Trade Bias</div>
      <div class="ic-ctx-val" style="color:${biasCol};font-size:22px">${ctx.trade_bias || '–'}</div>
      <div class="ic-ctx-sub" style="color:var(--text-dim);font-size:10px">
        ${ctx.trade_bias === 'LONG' ? 'Nifty above VWAP → favour longs' : 'Nifty below VWAP → favour shorts / caution'}
      </div>
    </div>
  `;
}

// ── Time Windows Bar ──────────────────────────────────────────────────────
function renderIcTimeBar() {
  const el = document.getElementById('icTimeBar');
  if (!el) return;
  el.innerHTML = IC_TIME_WINDOWS.map(w => `
    <div class="ic-tw-block" style="border-top:3px solid ${w.color}">
      <div class="ic-tw-label" style="color:${w.color}">${w.label}</div>
      <div class="ic-tw-time">${w.time}</div>
      <div class="ic-tw-tip">${w.tip}</div>
    </div>
  `).join('');
}

// ── Summary chips ─────────────────────────────────────────────────────────
function renderIcChips(s) {
  const orbHtml = (s.orb_plays ?? 0) > 0
    ? `<div class="ic-chip ic-chip-green" title="Live Opening Range Breakout signals"><span class="ic-chip-num">${s.orb_plays}</span><span class="ic-chip-lbl">ORB Live</span></div>`
    : '';
  const liveHtml = (s.live_count ?? 0) > 0
    ? `<div class="ic-chip ic-chip-green" title="Stocks with live 5-min data"><span class="ic-chip-num">${s.live_count}</span><span class="ic-chip-lbl">Live Data</span></div>`
    : '';
  document.getElementById('icChips').innerHTML = `
    ${orbHtml}${liveHtml}
    <div class="ic-chip ic-chip-blue"><span class="ic-chip-num">${s.total ?? 0}</span><span class="ic-chip-lbl">Watchlist</span></div>
    <div class="ic-chip ic-chip-green"><span class="ic-chip-num">${s.from_screener ?? 0}</span><span class="ic-chip-lbl">From Screener</span></div>
    <div class="ic-chip ic-chip-green"><span class="ic-chip-num">${s.qualified ?? 0}</span><span class="ic-chip-lbl">Qualified</span></div>
    <div class="ic-chip ic-chip-orange"><span class="ic-chip-num">${s.with_setups ?? 0}</span><span class="ic-chip-lbl">Has Setup</span></div>
    <div class="ic-chip ic-chip-green"><span class="ic-chip-num">${s.pdh_breakout ?? 0}</span><span class="ic-chip-lbl">PDH Break</span></div>
    <div class="ic-chip ic-chip-red"><span class="ic-chip-num">${s.pdl_breakdown ?? 0}</span><span class="ic-chip-lbl">PDL Break</span></div>
    <div class="ic-chip ic-chip-orange"><span class="ic-chip-num">${s.session_rev ?? 0}</span><span class="ic-chip-lbl">Sess Rev</span></div>
    <div class="ic-chip ic-chip-purple"><span class="ic-chip-num">${s.gap_plays ?? 0}</span><span class="ic-chip-lbl">Gap Plays</span></div>
    <div class="ic-chip ic-chip-blue"><span class="ic-chip-num">${s.above_session_tp ?? 0}</span><span class="ic-chip-lbl">Above STP</span></div>
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
  } else if (icFilter === 'ABOVE_VWAP') {
    f = f.filter(s => s.above_session_tp || s.above_20d_vwap);
  } else if (icFilter === 'QUALIFIED') {
    f = f.filter(s => s.qualified);
  } else if (icFilter === 'SCREENER') {
    f = f.filter(s => s.watchlist_source === 'screener');
  } else if (icFilter === 'ORB_LONG') {
    f = f.filter(s => s.setups && s.setups.some(st => st.setup === 'PDH_BREAKOUT'));
  } else if (icFilter === 'ORB_SHORT') {
    f = f.filter(s => s.setups && s.setups.some(st => st.setup === 'PDL_BREAKDOWN'));
  } else if (icFilter === 'VWAP_REVERSION') {
    f = f.filter(s => s.setups && s.setups.some(st => st.setup.startsWith('SESSION_REVERSION')));
  } else if (icFilter === 'GAP_PLAY') {
    f = f.filter(s => s.setups && s.setups.some(st => st.setup === 'GAP_UP' || st.setup === 'GAP_DOWN'));
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

  // Session TP deviation (replaces old vwap_dev_pct)
  const vd = s.session_tp_dev;
  const vdCol = vd != null
    ? (vd >= 1.5 ? 'var(--red)' : vd <= -1.5 ? 'var(--green)' : 'var(--text-muted)')
    : 'var(--text-dim)';
  const vdHtml = vd != null
    ? `<span style="color:${vdCol};font-family:var(--mono)">${vd >= 0 ? '+' : ''}${vd.toFixed(1)}%</span>`
    : '–';

  // ATR%
  const atrCol = s.atr_pct != null && s.atr_pct >= 1.5 ? 'var(--green)' : 'var(--text-dim)';

  // Volume in lakhs
  const volCol = s.avg_vol_l >= 100 ? 'var(--green)' : s.avg_vol_l >= 50 ? 'var(--text-muted)' : 'var(--red)';

  // RSI
  const rsiCol = s.rsi_14 != null && s.rsi_14 >= 55 && s.rsi_14 <= 75 ? 'var(--green)'
               : s.rsi_14 != null && s.rsi_14 < 35 ? 'var(--red)'
               : s.rsi_14 != null && s.rsi_14 > 75 ? '#f59e0b' : 'var(--text-muted)';

  // PDH/PDL compact
  const pdhpdl = (s.pdh && s.pdl)
    ? `<span style="color:var(--green);font-size:10px">H:${fmt(s.pdh)}</span><br><span style="color:var(--red);font-size:10px">L:${fmt(s.pdl)}</span>`
    : '–';

  // Setup badges — ORB setups are live-only (highest priority colour)
  const setupCols = {
    ORB_LONG:  'var(--green)', ORB_SHORT: 'var(--red)',
    PDH_BREAKOUT: 'var(--green)', PDL_BREAKDOWN: 'var(--red)',
    SESSION_REVERSION_LONG: '#f59e0b', SESSION_REVERSION_SHORT: '#f59e0b',
    GAP_UP: '#4a9eff', GAP_DOWN: '#a855f7',
  };
  const aboveSTPDot = s.above_session_tp ? `<span style="color:var(--green);font-size:10px" title="Above Session TP"> ↑S</span>` : '';
  const screenerBadge = s.watchlist_source === 'screener'
    ? `<span style="background:#4a9eff22;color:#4a9eff;border:1px solid #4a9eff44;border-radius:3px;padding:1px 4px;font-size:9px;margin-left:3px"
            title="Sourced from Screener · ${s.screener_category || ''}">${s.screener_category ? s.screener_category.replace('HIGH_PROB_','').replace('_',' ') : 'SCR'}</span>`
    : '';
  const setupsHtml = !s.setups?.length
    ? `<span style="color:var(--text-dim);font-size:10px">${s.above_session_tp ? '↑ STP' : s.qualified ? 'Qualified' : '–'}</span>`
    : s.setups.map(st => {
        const c = setupCols[st.setup] || '#f59e0b';
        return `<span class="ic-setup-badge" style="background:${c}22;color:${c};border:1px solid ${c}44">${st.icon} ${st.setup_label}</span>`;
      }).join('');

  return `
    <tr id="${rowId}" class="ic-stock-row ${s.has_setup ? 'ic-has-setup' : ''}" onclick="toggleIcRow('${id}')">
      <td class="ic-expand">${icExpanded.has(id) ? '▼' : '▶'}</td>
      <td><strong>${s.symbol}</strong>${aboveSTPDot}${screenerBadge}<br><span style="color:var(--text-dim);font-size:10px">${s.name}</span></td>
      <td><span style="color:var(--text-muted)">${s.sector}</span></td>
      <td style="font-family:var(--mono)">${s.is_live
        ? `<span class="ic-live-price" title="Live 5-min price">₹${fmt(s.live_price ?? s.cmp)}</span>`
        : `₹${fmt(s.cmp)}`}</td>
      <td>${chgHtml}</td>
      <td>${vdHtml}</td>
      <td style="color:${atrCol};font-family:var(--mono)">${s.atr_pct != null ? s.atr_pct.toFixed(1) + '%' : '–'}</td>
      <td style="color:${volCol};font-family:var(--mono)">${s.avg_vol_l != null ? s.avg_vol_l.toFixed(0) + 'L' : '–'}</td>
      <td style="color:${rsiCol};font-family:var(--mono)">${s.rsi_14 != null ? s.rsi_14.toFixed(1) : '–'}</td>
      <td style="font-size:10px">${pdhpdl}</td>
      <td class="ic-setups-cell">${setupsHtml}</td>
    </tr>
    <tr id="${detId}" class="ic-detail-row" style="display:none">
      <td colspan="11" class="ic-detail-cell">${buildIcDetail(s)}</td>
    </tr>
  `;
}

function buildIcDetail(s) {
  const liveRows = s.is_live ? `
    <div class="ic-ema-row" style="background:#22c55e0d;border-left:2px solid var(--green)">
      <span style="color:var(--green);font-weight:600">Live Price</span>
      <span style="font-family:var(--mono);color:var(--green)">₹${fmt(s.live_price ?? s.cmp)} <span class="ic-live-dot" style="width:5px;height:5px"></span></span>
    </div>
    ${s.intraday_vwap ? `<div class="ic-ema-row"><span style="color:#f59e0b">Intraday VWAP</span><span style="font-family:var(--mono);color:#f59e0b">₹${fmt(s.intraday_vwap)}</span></div>` : ''}
    ${s.orb_high ? `<div class="ic-ema-row"><span style="color:var(--green)">ORB High</span><span style="font-family:var(--mono);color:var(--green)">₹${fmt(s.orb_high)}</span></div>` : ''}
    ${s.orb_low  ? `<div class="ic-ema-row"><span style="color:var(--red)">ORB Low</span><span style="font-family:var(--mono);color:var(--red)">₹${fmt(s.orb_low)}</span></div>` : ''}
  ` : '';

  const levelsHtml = `
    <div class="ic-ema-ladder">
      ${liveRows}
      <div class="ic-ema-row"><span>${s.is_live ? 'EOD Close' : 'CMP'}</span><span style="font-family:var(--mono);color:var(--text)">₹${fmt(s.cmp)}</span></div>
      <div class="ic-ema-row"><span>Session TP</span><span style="font-family:var(--mono);color:#f59e0b">₹${fmt(s.session_tp)}${s.session_tp_dev != null ? ` <span style="font-size:10px">(${s.session_tp_dev >= 0 ? '+' : ''}${s.session_tp_dev.toFixed(1)}%)</span>` : ''}</span></div>
      <div class="ic-ema-row"><span>VWAP (20d swing)</span><span style="font-family:var(--mono);color:var(--text-muted)">₹${fmt(s.vwap_20d)}</span></div>
      <div class="ic-ema-row"><span>PDH</span><span style="font-family:var(--mono);color:var(--green)">₹${fmt(s.pdh)}</span></div>
      <div class="ic-ema-row"><span>PDL</span><span style="font-family:var(--mono);color:var(--red)">₹${fmt(s.pdl)}</span></div>
      <div class="ic-ema-row"><span>Wk Pivot</span><span style="font-family:var(--mono)">₹${fmt(s.wk_pivot)}</span></div>
      <div class="ic-ema-row"><span>Wk R1</span><span style="font-family:var(--mono);color:var(--green)">₹${fmt(s.wk_r1)}</span></div>
      <div class="ic-ema-row"><span>Wk S1</span><span style="font-family:var(--mono);color:var(--red)">₹${fmt(s.wk_s1)}</span></div>
      <div class="ic-ema-row"><span>EMA 9</span><span style="font-family:var(--mono)">₹${fmt(s.ema9)}</span></div>
      <div class="ic-ema-row"><span>EMA 21</span><span style="font-family:var(--mono)">₹${fmt(s.ema21)}</span></div>
      <div class="ic-ema-row"><span>ATR(14)</span><span style="font-family:var(--mono)">${s.atr_14 != null ? '₹' + fmt(s.atr_14) : '–'} (${s.atr_pct != null ? s.atr_pct.toFixed(1) + '%' : '–'})</span></div>
      <div class="ic-ema-row"><span>RSI(14)</span><span style="font-family:var(--mono)">${s.rsi_14 != null ? s.rsi_14.toFixed(1) : '–'}</span></div>
      <div class="ic-ema-row"><span>Vol (20d avg)</span><span style="font-family:var(--mono)">${s.avg_vol_l != null ? s.avg_vol_l.toFixed(0) + 'L' : '–'}</span></div>
    </div>`;

  if (!s.setups?.length) {
    return `<div class="ic-detail-wrap">${levelsHtml}<div style="padding:14px;color:var(--text-dim)">${
      s.qualified ? 'Stock qualified — waiting for price trigger near PDH/PDL.' : 'Below ATR or volume threshold.'
    }</div></div>`;
  }

  const setupCols = {
    ORB_LONG: 'var(--green)', ORB_SHORT: 'var(--red)',
    VWAP_REVERSION_LONG: '#f59e0b', VWAP_REVERSION_SHORT: '#f59e0b',
    GAP_UP: '#4a9eff', GAP_DOWN: '#a855f7',
  };

  const cardsHtml = s.setups.map(st => {
    const col      = setupCols[st.setup] || '#f59e0b';
    const isShort  = st.setup.includes('SHORT') || st.setup === 'GAP_DOWN';
    const risk     = st.entry && st.stop_loss
      ? (isShort ? st.stop_loss - st.entry : st.entry - st.stop_loss) : null;
    const riskPct  = risk && st.entry ? (Math.abs(risk) / st.entry * 100).toFixed(1) : null;
    const cap          = icGlobalCapital || 1000000;
    const LEVERAGE     = 5;                                   // NSE MIS intraday leverage
    const buyingPower  = cap * LEVERAGE;
    const maxByLev     = st.entry ? Math.floor(buyingPower / st.entry) : Infinity;
    const riskAmt      = risk && Math.abs(risk) > 0 ? Math.abs(risk) : null;
    const sizingHtml   = riskAmt ? (() => {
      const tiers = [
        { label: 'Normal 1%',    pct: 0.01,  col: '#4a9eff' },
        { label: 'High Conv 2%', pct: 0.02,  col: 'var(--orange)' },
        { label: 'Reduced 0.5%', pct: 0.005, col: 'var(--text-dim)' },
      ];
      return tiers.map(t => {
        const qtyByRisk    = Math.floor(cap * t.pct / riskAmt);
        const qty          = Math.min(qtyByRisk, maxByLev);
        const atRisk       = Math.round(cap * t.pct);        // risk on actual capital
        const posVal       = Math.round(qty * (st.entry || 0));
        const marginBlocked = Math.round(posVal / LEVERAGE); // what leaves your account
        const levLimited   = qty < qtyByRisk;                // leverage was the binding cap
        return `<div class="ic-sizing-row">
          <span style="color:${t.col};min-width:100px">${t.label}</span>
          <span class="ic-sizing-qty">${qty.toLocaleString('en-IN')} sh${levLimited ? ' <span style="color:#f59e0b;font-size:9px" title="Leverage cap hit">⚡lev cap</span>' : ''}</span>
          <span class="ic-sizing-risk">₹${atRisk.toLocaleString('en-IN')} risk</span>
          <span class="ic-sizing-margin" title="Margin blocked from your account">₹${marginBlocked.toLocaleString('en-IN')} margin</span>
          <span class="ic-sizing-pos" style="color:var(--text-dim)">₹${posVal.toLocaleString('en-IN')} pos</span>
        </div>`;
      }).join('');
    })() : null;

    const isLiveSetup = st.setup === 'ORB_LONG' || st.setup === 'ORB_SHORT';
    return `
      <div class="ic-setup-card" style="border-top-color:${col}${isLiveSetup ? ';box-shadow:0 0 0 1px ' + col + '33' : ''}">
        <div class="ic-setup-hdr">
          <span class="ic-setup-name" style="color:${col}">${st.icon} ${st.setup_label}</span>
          ${isLiveSetup ? '<span class="ic-live-badge" style="font-size:9px;padding:1px 5px"><span class="ic-live-dot" style="width:5px;height:5px"></span>LIVE</span>' : ''}
          <span class="ic-setup-wr" style="color:var(--text-muted);font-size:10px">⏰ ${st.window}</span>
        </div>
        ${st.data_note ? `<div style="font-size:10px;color:${isLiveSetup ? 'var(--green)' : 'var(--text-dim)'};margin-bottom:4px">📡 ${st.data_note}</div>` : ''}
        <div class="ic-setup-note">${st.note || ''}</div>
        <div class="ic-levels-grid">
          <div class="ic-lvl ic-entry"><span class="ic-lvl-lbl">Entry</span><span class="ic-lvl-val">₹${fmt(st.entry)}</span></div>
          <div class="ic-lvl ic-stop"><span class="ic-lvl-lbl">Stop Loss</span><span class="ic-lvl-val">₹${fmt(st.stop_loss)}</span>${riskPct ? `<span class="ic-lvl-sub">${isShort ? '+' : '−'}${riskPct}%</span>` : ''}</div>
          <div class="ic-lvl ic-t1"><span class="ic-lvl-lbl">T1 (1:2 R:R)</span><span class="ic-lvl-val">₹${fmt(st.target1)}</span></div>
          <div class="ic-lvl ic-t2"><span class="ic-lvl-lbl">T2 (1:3 R:R)</span><span class="ic-lvl-val">₹${fmt(st.target2)}</span></div>
        </div>
        <div class="ic-setup-ftr">
          <span>R:R — ${st.rr}</span>
        </div>
        ${sizingHtml ? `
        <div class="ic-sizing-block">
          <div class="ic-sizing-hdr">Position Sizing &nbsp;·&nbsp; ₹${(cap/100000).toFixed(cap%100000===0?0:1)}L capital &nbsp;·&nbsp; <span style="color:var(--orange)">5× MIS → ₹${(buyingPower/100000).toFixed(buyingPower%100000===0?0:1)}L buying power</span></div>
          ${sizingHtml}
        </div>` : ''}
      </div>`;
  }).join('');

  return `<div class="ic-detail-wrap">${levelsHtml}<div class="ic-setups-list">${cardsHtml}</div></div>`;
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

// ── Position size calculator (2-tier risk) ───────────────────────────────
function calcIcPosition() {
  const capEl   = document.getElementById('icCapital');
  const capital = parseFloat(capEl?.value) || icGlobalCapital;
  // Sync back to global and sub-header input if the user typed here
  if (capEl && parseFloat(capEl.value) > 0) {
    icGlobalCapital = parseFloat(capEl.value);
    const hdr = document.getElementById('icGlobalCapital');
    if (hdr && parseFloat(hdr.value) !== icGlobalCapital) hdr.value = icGlobalCapital;
  }
  const entry    = parseFloat(document.getElementById('icEntry').value)   || 0;
  const stop     = parseFloat(document.getElementById('icStop').value)    || 0;
  const riskTier = parseFloat(document.getElementById('icRiskTier').value) || 1;
  const el       = document.getElementById('icCalcOut');

  if (!entry || !stop || entry <= stop) {
    el.innerHTML = '<p style="color:var(--text-dim);font-size:12px">Enter valid Entry &gt; Stop Loss.</p>';
    return;
  }

  const LEVERAGE     = 5;
  const buyingPower  = capital * LEVERAGE;
  const maxLoss      = capital * (riskTier / 100);
  const riskPer      = entry - stop;
  const qtyByRisk    = Math.floor(maxLoss / riskPer);
  const qtyByLev     = Math.floor(buyingPower / entry);
  const shares       = Math.min(qtyByRisk, qtyByLev);
  const levLimited   = shares < qtyByRisk;
  const posVal       = shares * entry;
  const marginBlocked = posVal / LEVERAGE;
  const t1           = entry + riskPer * 2;
  const t2           = entry + riskPer * 3;

  el.innerHTML = `
    <div class="ic-calc-row"><span>Buying Power (5× MIS)</span><strong style="color:var(--orange)">₹${buyingPower.toLocaleString('en-IN',{maximumFractionDigits:0})}</strong></div>
    <div class="ic-calc-row"><span>Capital at Risk</span><strong style="color:var(--red)">₹${maxLoss.toLocaleString('en-IN',{maximumFractionDigits:0})}</strong></div>
    <div class="ic-calc-row"><span>Risk Per Share</span><strong>₹${riskPer.toFixed(2)}</strong></div>
    <div class="ic-calc-row"><span>Position Size</span><strong style="color:#f59e0b">${shares.toLocaleString('en-IN')} shares${levLimited ? ' <span style="color:#f59e0b;font-size:10px">(leverage cap)</span>' : ''}</strong></div>
    <div class="ic-calc-row"><span>Position Value</span><strong>₹${posVal.toLocaleString('en-IN',{maximumFractionDigits:0})}</strong></div>
    <div class="ic-calc-row"><span>Margin Blocked</span><strong style="color:var(--text-muted)">₹${marginBlocked.toLocaleString('en-IN',{maximumFractionDigits:0})} (from your capital)</strong></div>
    <hr style="border-color:var(--border);margin:8px 0">
    <div class="ic-calc-row"><span>T1 @ 1:2 R:R</span><strong style="color:var(--green)">₹${t1.toFixed(2)}</strong></div>
    <div class="ic-calc-row"><span>T2 @ 1:3 R:R</span><strong style="color:var(--green)">₹${t2.toFixed(2)}</strong></div>
    <hr style="border-color:var(--border);margin:8px 0">
    <div class="ic-calc-row"><span>Breakeven (at +1R)</span><strong>₹${entry.toFixed(2)}</strong></div>
    <div class="ic-calc-row" style="font-size:10px;color:var(--text-dim);margin-top:4px">
      <span>Max 3 positions → heat</span><strong>${(riskTier * 3).toFixed(1)}%</strong>
    </div>
  `;
}


// ══════════════════════════════════════════════════════════════════════════════
// BIGBAG — Asymmetric Compounding Quality Screen
// ══════════════════════════════════════════════════════════════════════════════

let bbStocks   = [];
let bbFilter   = 'ALL';
let bbSortKey  = 'empire_score';
let bbSortAsc  = false;
let bbExpanded = new Set();

// ── Fetch ─────────────────────────────────────────────────────────────────
async function runBigBag() {
  const btn = document.getElementById('bbRunBtn');
  btn.disabled = true;
  btn.classList.add('loading');
  btn.textContent = '\u23f3 Screening\u2026';
  showLoader('Fetching fundamental data\u2026');

  const msgs = [
    'Fetching ROE & earnings growth\u2026',
    'Computing D/E ratios\u2026',
    'Scoring operating margins\u2026',
    'Calculating PEG ratios\u2026',
    'Running EMPIRE scoring\u2026',
    'Ranking quality compounders\u2026',
    'Assigning conviction tiers\u2026',
  ];
  let mi = 0;
  const t = setInterval(() => {
    document.getElementById('loaderText').textContent = msgs[mi++ % msgs.length];
  }, 7000);

  try {
    const res = await fetch(`${API}/api/strategy/bigbag`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    renderBigBag(data);
    showToast('BigBag screen complete!', 'success');
  } catch (e) {
    showToast(`BigBag error: ${e.message}`, 'error');
    console.error(e);
  } finally {
    clearInterval(t);
    hideLoader();
    btn.disabled = false;
    btn.classList.remove('loading');
    btn.textContent = '\u2728 Screen Compounders';
  }
}

// ── Master renderer ───────────────────────────────────────────────────────
function renderBigBag(data) {
  document.getElementById('bbEmpty').style.display   = 'none';
  document.getElementById('bbResults').style.display = '';

  const ts = data.run_date && data.run_time
    ? `Last: ${data.run_date} ${data.run_time}` : (data.run_date || '\u2013');
  document.getElementById('bbLastRun').textContent = ts;

  bbStocks = data.stocks || [];
  renderBbChips(data.summary || {});
  applyBbFilters();
}

// ── Summary chips ─────────────────────────────────────────────────────────
function renderBbChips(s) {
  document.getElementById('bbChips').innerHTML = `
    <div class="bb-chip bb-chip-gold"><span class="bb-chip-num">${s.total ?? 0}</span><span class="bb-chip-lbl">Screened</span></div>
    <div class="bb-chip bb-chip-gold"><span class="bb-chip-num">${s.tier1 ?? 0}</span><span class="bb-chip-lbl">Tier 1</span></div>
    <div class="bb-chip bb-chip-blue"><span class="bb-chip-num">${s.tier2 ?? 0}</span><span class="bb-chip-lbl">Tier 2</span></div>
    <div class="bb-chip bb-chip-green"><span class="bb-chip-num">${s.high_roe ?? 0}</span><span class="bb-chip-lbl">ROE &ge;20%</span></div>
    <div class="bb-chip bb-chip-green"><span class="bb-chip-num">${s.low_de ?? 0}</span><span class="bb-chip-lbl">Low Debt</span></div>
    <div class="bb-chip bb-chip-blue"><span class="bb-chip-num">${s.good_peg ?? 0}</span><span class="bb-chip-lbl">PEG &lt;1.5</span></div>
    <div class="bb-chip bb-chip-gold"><span class="bb-chip-num">${s.near_52wh ?? 0}</span><span class="bb-chip-lbl">Near 52W High</span></div>
  `;
}

// ── Filters + Sort ────────────────────────────────────────────────────────
function setBbFilter(el, f) {
  document.querySelectorAll('.bb-tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  bbFilter = f;
  applyBbFilters();
}

function sortBb(key) {
  if (bbSortKey === key) bbSortAsc = !bbSortAsc;
  else { bbSortKey = key; bbSortAsc = key === 'symbol'; }
  applyBbFilters();
}

function applyBbFilters() {
  let f = [...bbStocks];
  if (bbFilter === 'TIER_1') {
    f = f.filter(s => s.conviction === 'TIER_1');
  } else if (bbFilter === 'TIER_2') {
    f = f.filter(s => s.conviction === 'TIER_2');
  } else if (bbFilter === 'HIGH_ROE') {
    f = f.filter(s => s.roe != null && s.roe >= 20);
  } else if (bbFilter === 'LOW_DEBT') {
    f = f.filter(s => !s.is_financial && s.de_ratio != null && s.de_ratio < 0.3);
  } else if (bbFilter === 'GOOD_PEG') {
    f = f.filter(s => s.peg != null && s.peg < 1.5);
  } else if (bbFilter === 'NEAR_52WH') {
    f = f.filter(s => s.dist_52wh != null && s.dist_52wh >= -10);
  }
  f.sort((a, b) => {
    let va = a[bbSortKey], vb = b[bbSortKey];
    if (typeof va === 'string') va = va.toLowerCase();
    if (typeof vb === 'string') vb = vb.toLowerCase();
    if (va == null) return 1;
    if (vb == null) return -1;
    return bbSortAsc ? (va < vb ? -1 : va > vb ? 1 : 0)
                     : (va > vb ? -1 : va < vb ? 1 : 0);
  });
  renderBbTable(f);
}

// ── Table ─────────────────────────────────────────────────────────────────
function renderBbTable(stocks) {
  const tbody = document.getElementById('bbTableBody');
  if (!stocks.length) {
    tbody.innerHTML = `<tr><td colspan="13" style="text-align:center;padding:32px;color:var(--text-muted)">No stocks match this filter.</td></tr>`;
    return;
  }
  tbody.innerHTML = stocks.map(s => buildBbRow(s)).join('');
  bbExpanded.forEach(id => {
    const dr = document.getElementById(`bb-det-${id}`);
    const mr = document.getElementById(`bb-row-${id}`);
    if (dr) dr.style.display = '';
    if (mr) mr.classList.add('expanded');
  });
}

function buildBbRow(s) {
  const id    = s.symbol.replace(/[^a-zA-Z0-9]/g, '_');
  const rowId = `bb-row-${id}`;
  const detId = `bb-det-${id}`;

  // Market cap
  const mcHtml = s.market_cap_cr
    ? (s.market_cap_cr >= 100000
        ? `<span style="color:var(--text-muted)">${(s.market_cap_cr/100000).toFixed(1)}L Cr</span>`
        : s.market_cap_cr >= 1000
          ? `<span style="color:var(--text-muted)">${(s.market_cap_cr/1000).toFixed(1)}K Cr</span>`
          : `<span style="color:var(--text-muted)">${s.market_cap_cr} Cr</span>`)
    : '\u2013';

  // 52W High
  const d52Col = s.dist_52wh != null
    ? (s.dist_52wh >= -5 ? 'var(--green)' : s.dist_52wh >= -15 ? '#eab308' : 'var(--text-muted)')
    : 'var(--text-dim)';
  const d52Html = s.dist_52wh != null
    ? `<span style="color:${d52Col};font-family:var(--mono)">${s.dist_52wh.toFixed(1)}%</span>`
    : '\u2013';

  // ROE
  const roeCol = s.roe != null
    ? (s.roe >= 25 ? 'var(--green)' : s.roe >= 20 ? '#eab308' : 'var(--text-muted)')
    : 'var(--text-dim)';

  // D/E
  const deCol = s.is_financial ? 'var(--text-dim)'
    : s.de_ratio != null
      ? (s.de_ratio < 0.1 ? 'var(--green)' : s.de_ratio < 0.3 ? '#eab308' : 'var(--red)')
      : 'var(--text-dim)';
  const deHtml = s.is_financial
    ? `<span style="color:var(--text-dim);font-size:10px">n/a (fin)</span>`
    : s.de_ratio != null
      ? `<span style="color:${deCol};font-family:var(--mono)">${s.de_ratio.toFixed(2)}</span>`
      : '\u2013';

  // EPS growth
  const egCol = s.eps_growth != null
    ? (s.eps_growth >= 20 ? 'var(--green)' : s.eps_growth >= 10 ? '#eab308' : s.eps_growth < 0 ? 'var(--red)' : 'var(--text-muted)')
    : 'var(--text-dim)';

  // P/E
  const peCol = s.pe != null
    ? (s.pe < 25 ? 'var(--green)' : s.pe < 40 ? '#eab308' : 'var(--text-muted)')
    : 'var(--text-dim)';

  // PEG
  const pegCol = s.peg != null
    ? (s.peg < 1.0 ? 'var(--green)' : s.peg < 1.5 ? '#eab308' : s.peg < 2 ? 'var(--text-muted)' : 'var(--red)')
    : 'var(--text-dim)';

  // EMPIRE score bar
  const scoreCol = s.empire_score >= 70 ? '#eab308' : s.empire_score >= 50 ? '#4a9eff' : 'var(--text-muted)';
  const scoreHtml = `
    <div style="display:flex;align-items:center;gap:6px">
      <div style="flex:1;background:var(--border);border-radius:3px;height:6px;min-width:40px">
        <div style="width:${Math.min(s.empire_score,100)}%;height:100%;background:${scoreCol};border-radius:3px"></div>
      </div>
      <span style="font-family:var(--mono);color:${scoreCol};font-size:11px;white-space:nowrap">${s.empire_score.toFixed(0)}</span>
    </div>`;

  // Conviction
  const convHtml = `<span style="background:${s.conviction_color}22;color:${s.conviction_color};border:1px solid ${s.conviction_color}44;border-radius:4px;padding:2px 7px;font-size:10px;font-weight:700;white-space:nowrap">${s.conviction_label}</span>`;

  return `
    <tr id="${rowId}" class="bb-stock-row ${s.conviction === 'TIER_1' ? 'bb-tier1-row' : ''}" onclick="toggleBbRow('${id}')">
      <td class="bb-expand">${bbExpanded.has(id) ? '\u25bc' : '\u25b6'}</td>
      <td><strong>${s.symbol}</strong><br><span style="color:var(--text-dim);font-size:10px">${s.name}</span></td>
      <td>
        <span style="color:var(--text-muted)">${s.sector}</span><br>
        <span style="font-size:10px;color:var(--text-dim)">${s.theme}</span>
      </td>
      <td>${mcHtml}</td>
      <td style="font-family:var(--mono)">${s.cmp ? '\u20b9' + fmt(s.cmp) : '\u2013'}</td>
      <td>${d52Html}</td>
      <td style="color:${roeCol};font-family:var(--mono)">${s.roe != null ? s.roe.toFixed(1) + '%' : '\u2013'}</td>
      <td>${deHtml}</td>
      <td style="color:${egCol};font-family:var(--mono)">${s.eps_growth != null ? (s.eps_growth >= 0 ? '+' : '') + s.eps_growth.toFixed(1) + '%' : '\u2013'}</td>
      <td style="color:${peCol};font-family:var(--mono)">${s.pe != null ? s.pe.toFixed(1) : '\u2013'}</td>
      <td style="color:${pegCol};font-family:var(--mono)">${s.peg != null ? s.peg.toFixed(2) : '\u2013'}</td>
      <td style="min-width:120px">${scoreHtml}</td>
      <td>${convHtml}</td>
    </tr>
    <tr id="${detId}" class="bb-detail-row" style="display:none">
      <td colspan="13" class="bb-detail-cell">${buildBbDetail(s)}</td>
    </tr>
  `;
}

function buildBbDetail(s) {
  // Key metrics panel
  const metricsHtml = `
    <div class="bb-det-metrics">
      <div class="bb-det-row"><span>CMP</span><strong style="font-family:var(--mono)">\u20b9${fmt(s.cmp)}</strong></div>
      <div class="bb-det-row"><span>Market Cap</span><strong style="font-family:var(--mono)">${s.market_cap_cr ? (s.market_cap_cr >= 1000 ? (s.market_cap_cr/1000).toFixed(1) + 'K Cr' : s.market_cap_cr + ' Cr') : '\u2013'}</strong></div>
      <div class="bb-det-row"><span>52W High</span><strong style="font-family:var(--mono)">\u20b9${fmt(s.w52h)}</strong></div>
      <div class="bb-det-row"><span>52W Low</span><strong style="font-family:var(--mono)">\u20b9${fmt(s.w52l)}</strong></div>
      <div class="bb-det-row"><span>ROE</span><strong style="font-family:var(--mono)">${s.roe != null ? s.roe.toFixed(1) + '%' : '\u2013'}</strong></div>
      <div class="bb-det-row"><span>D/E Ratio</span><strong style="font-family:var(--mono)">${s.is_financial ? 'N/A (fin)' : s.de_ratio != null ? s.de_ratio.toFixed(2) : '\u2013'}</strong></div>
      <div class="bb-det-row"><span>P/E</span><strong style="font-family:var(--mono)">${s.pe != null ? s.pe.toFixed(1) : '\u2013'}</strong></div>
      <div class="bb-det-row"><span>P/B</span><strong style="font-family:var(--mono)">${s.pb != null ? s.pb.toFixed(1) : '\u2013'}</strong></div>
      <div class="bb-det-row"><span>PEG</span><strong style="font-family:var(--mono)">${s.peg != null ? s.peg.toFixed(2) : '\u2013'}</strong></div>
      <div class="bb-det-row"><span>EPS Growth</span><strong style="font-family:var(--mono)">${s.eps_growth != null ? (s.eps_growth >= 0 ? '+' : '') + s.eps_growth.toFixed(1) + '%' : '\u2013'}</strong></div>
      <div class="bb-det-row"><span>Rev Growth</span><strong style="font-family:var(--mono)">${s.rev_growth != null ? (s.rev_growth >= 0 ? '+' : '') + s.rev_growth.toFixed(1) + '%' : '\u2013'}</strong></div>
      <div class="bb-det-row"><span>Op. Margin</span><strong style="font-family:var(--mono)">${s.op_margin != null ? s.op_margin.toFixed(1) + '%' : '\u2013'}</strong></div>
      <div class="bb-det-row"><span>Net Margin</span><strong style="font-family:var(--mono)">${s.net_margin != null ? s.net_margin.toFixed(1) + '%' : '\u2013'}</strong></div>
    </div>`;

  // EMPIRE breakdown
  const bd = s.empire_breakdown || {};
  const letters = { roe: 'E', eps_growth: 'E', op_margin: 'M', rev_growth: 'P', de_ratio: 'R', peg: 'E' };
  const bdHtml = Object.entries(bd).map(([k, v]) => {
    const pct = v.max > 0 ? (v.score / v.max * 100) : 0;
    const col = pct >= 75 ? 'var(--green)' : pct >= 40 ? '#eab308' : 'var(--red)';
    return `
      <div class="bb-empire-score-row">
        <span class="bb-empire-score-letter" style="color:${col}">${letters[k] || 'E'}</span>
        <span class="bb-empire-score-label">${v.label}</span>
        <span class="bb-empire-score-val" style="font-family:var(--mono)">${v.value != null ? v.value.toFixed(1) + (k.includes('margin') || k.includes('growth') || k === 'roe' ? '%' : '') : '\u2013'}</span>
        <div class="bb-empire-score-bar">
          <div style="width:${pct}%;background:${col};height:100%;border-radius:3px"></div>
        </div>
        <span style="font-family:var(--mono);font-size:10px;color:${col};min-width:28px;text-align:right">${v.score}/${v.max}</span>
      </div>`;
  }).join('');

  return `
    <div class="bb-detail-wrap">
      ${metricsHtml}
      <div class="bb-empire-scorecard">
        <div class="bb-empire-sc-title">
          EMPIRE Score: <strong style="color:${s.empire_score >= 70 ? '#eab308' : s.empire_score >= 50 ? '#4a9eff' : 'var(--text-muted)'}">${s.empire_score.toFixed(0)} / 100</strong>
          &nbsp;<span style="color:${s.conviction_color};font-size:11px">${s.conviction_label}</span>
        </div>
        ${bdHtml || '<p style="color:var(--text-dim);font-size:11px;padding:8px">Limited fundamental data available for this stock.</p>'}
      </div>
    </div>`;
}

function toggleBbRow(id) {
  const det = document.getElementById(`bb-det-${id}`);
  const row = document.getElementById(`bb-row-${id}`);
  if (!det) return;
  const open = det.style.display !== 'none';
  det.style.display = open ? 'none' : '';
  row.classList.toggle('expanded', !open);
  if (open) bbExpanded.delete(id); else bbExpanded.add(id);
  const btn = row.querySelector('.bb-expand');
  if (btn) btn.textContent = open ? '\u25b6' : '\u25bc';
}

// ── Position Size Calculator (BigBag) ────────────────────────────────────
function calcBbPosition() {
  const capital = parseFloat(document.getElementById('bbCapital').value) || 0;
  const entry   = parseFloat(document.getElementById('bbEntry').value)   || 0;
  const tierPct = parseFloat(document.getElementById('bbTier').value)    || 10;
  const slPct   = parseFloat(document.getElementById('bbSlPct').value)   || 20;
  const el      = document.getElementById('bbCalcOut');

  if (!capital || !entry) {
    el.innerHTML = '<p style="color:var(--text-dim);font-size:12px">Enter Portfolio Value and Entry Price.</p>';
    return;
  }

  const positionVal = capital * (tierPct / 100);
  const shares      = Math.floor(positionVal / entry);
  const posVal      = shares * entry;
  const sl          = entry * (1 - slPct / 100);
  const riskPerShare= entry - sl;
  const maxRisk     = shares * riskPerShare;
  const maxRiskPct  = (maxRisk / capital * 100).toFixed(1);
  // Tranche sizes (3 tranches)
  const t1shares    = Math.floor(shares * 0.4);
  const t2shares    = Math.floor(shares * 0.3);
  const t3shares    = shares - t1shares - t2shares;

  el.innerHTML = `
    <div class="bb-calc-row"><span>Position Allocation</span><strong style="color:#eab308">${tierPct}% = \u20b9${posVal.toLocaleString('en-IN',{maximumFractionDigits:0})}</strong></div>
    <div class="bb-calc-row"><span>Total Shares</span><strong>${shares.toLocaleString('en-IN')}</strong></div>
    <div class="bb-calc-row"><span>Stop Loss (${slPct}% below)</span><strong style="color:var(--red)">\u20b9${sl.toFixed(2)}</strong></div>
    <div class="bb-calc-row"><span>Max Risk if SL hit</span><strong style="color:var(--red)">\u20b9${maxRisk.toLocaleString('en-IN',{maximumFractionDigits:0})} (${maxRiskPct}%)</strong></div>
    <hr style="border-color:var(--border);margin:8px 0">
    <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px">3-Tranche Buying Plan:</div>
    <div class="bb-calc-row"><span>Tranche 1 (40%) &mdash; at CMP</span><strong>${t1shares} shares @ \u20b9${entry.toFixed(2)}</strong></div>
    <div class="bb-calc-row"><span>Tranche 2 (30%) &mdash; on &minus;10% dip</span><strong>${t2shares} shares @ \u20b9${(entry * 0.90).toFixed(2)}</strong></div>
    <div class="bb-calc-row"><span>Tranche 3 (30%) &mdash; on &minus;20% dip</span><strong>${t3shares} shares @ \u20b9${(entry * 0.80).toFixed(2)}</strong></div>
    <div class="bb-calc-row" style="font-size:10px;color:var(--text-dim);margin-top:4px">
      <span>Avg cost after all tranches</span><strong>\u20b9${((t1shares*entry + t2shares*entry*0.90 + t3shares*entry*0.80)/shares).toFixed(2)}</strong>
    </div>
  `;
}
