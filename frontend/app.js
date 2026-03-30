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
  if (!s.entry) return '<span style="color:var(--text-dim)">–</span>';
  const setup = getSetupType(s);
  const dir = (s.direction || 'LONG').toUpperCase();
  const setupClass = dir === 'LONG' ? 'setup-long' : 'setup-short';
  return `<div class="trade-levels">
    <span class="tl-setup ${setupClass}">${setup}</span>
    <span class="tl-entry">E: ₹${fmt(s.entry)}</span>
    <span class="tl-sl">SL: ₹${fmt(s.stop_loss)}</span>
    <span class="tl-t1">T1: ₹${fmt(s.target1)}</span>
    <span class="tl-t2">T2: ₹${fmt(s.target2)}</span>
  </div>`;
}

function buildDetailContent(s) {
  const explanation = (s.explanation || 'No explanation available.')
    .replace(/\n/g, '<br>')
    .replace(/\+/g, '<span class="plus">+</span>')
    .replace(/^  -/gm, '  <span class="minus">-</span>')
    .replace(/  ~/g, '  <span class="tilde">~</span>');

  const ind = s.indicators || {};

  const levelsHtml = s.entry ? `
    <div class="detail-levels">
      <div class="dl-item"><div class="dl-label">Entry</div><div class="dl-value entry">₹${fmt(s.entry)}</div></div>
      <div class="dl-item"><div class="dl-label">Stop Loss</div><div class="dl-value sl">₹${fmt(s.stop_loss)} (${s.risk_pct?.toFixed(1)}%)</div></div>
      <div class="dl-item"><div class="dl-label">Target 1 (2:1)</div><div class="dl-value target">₹${fmt(s.target1)}</div></div>
      <div class="dl-item"><div class="dl-label">Target 2 (3:1)</div><div class="dl-value target">₹${fmt(s.target2)}</div></div>
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
