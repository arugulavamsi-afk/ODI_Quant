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

  const isScanner = page === 'scanner';
  document.getElementById('scannerPage').style.display = isScanner ? '' : 'none';
  document.getElementById('niftyPage').style.display   = isScanner ? 'none' : '';
  document.getElementById('runBtn').style.display      = isScanner ? '' : 'none';
  document.getElementById('lastRunTime').style.display = isScanner ? '' : 'none';
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
