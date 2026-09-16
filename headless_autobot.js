'use strict';
/**
 * AURA v2.5.0 — Headless Paper Autobot (Server-Only Live)
 * ====================================================
 * PF-66: Runs the full Autobot cycle server-side inside the Docker container.
 *        Loads the Engine block directly from Symbiose_Dashboard.html
 *        (same extraction pattern as existing Node tests — zero divergence risk).
 *
 * PF-67: Reads config and writes trades/history via /api/state (relay server state).
 *        Browser state is control-plane input only and never pauses this runner.
 *
 * PF-68: Emits trade events through relay's _ntfy_notify path via /api/signals
 *        (relay-side endpoint) with server-side claim/dedup via _signal_claims.
 *
 * PF-69: Restart-persistent state, 429 backoff, fail-close on data errors.
 *
 * Usage:  node headless_autobot.js
 * ENV:    AURA_BOT_MODE=server            (required to activate; default off)
 *         AURA_BOT_SCAN_SEC=60            (scan interval, default 60)
 *         AURA_BOT_EQUITY=10000           (starting paper equity USDT)
 *         AURA_RELAY_URL=http://127.0.0.1:8787  (relay base URL)
 *         AURA_RELAY_TOKEN                (privileged token if configured)
 */

const fs      = require('fs');
const vm      = require('vm');
const http    = require('http');
const https   = require('https');
const path    = require('path');
const crypto  = require('crypto');
const { ShadowCollector } = require('./shadow_collector.js');

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const BOT_MODE     = (process.env.AURA_BOT_MODE || '').toLowerCase();
const SCAN_SEC     = Math.max(15, parseInt(process.env.AURA_BOT_SCAN_SEC || '60', 10));
const RELAY_URL    = (process.env.AURA_RELAY_URL || 'http://127.0.0.1:8787').replace(/\/$/, '');
const RELAY_TOKEN  = process.env.AURA_RELAY_TOKEN || '';
const DASHBOARD    = path.resolve(process.env.AURA_DASHBOARD || 'Symbiose_Dashboard.html');
// Version hash is checked on startup so Dashboard and Runner never drift apart.
const EXPECTED_ENGINE_HASH = process.env.AURA_ENGINE_HASH || ''; // optional; skip when empty

// Persistent state keys (same key namespace as browser/relay)
const KEY_TRADES   = 'aura-quant-terminal-active-trades-v2';
const KEY_HISTORY  = 'aura-quant-terminal-history-trades-v2';
const KEY_STATE    = 'aura-autobot-state-v2';
const KEY_SRV_CFG  = 'aura-server-bot-config-v1';   // written by Dashboard panel
const KEY_SRV_BOT  = 'aura-server-bot-state-v1';    // Runner writes here (mode flag, equity, flags)

// ---------------------------------------------------------------------------
// Engine extraction (mirrors test_engine_full.js pattern exactly)
// ---------------------------------------------------------------------------
function loadEngine() {
  const html  = fs.readFileSync(DASHBOARD, 'utf8');
  const begin = html.indexOf('//  ==ENGINE_BEGIN==');
  const end   = html.indexOf('// ==ENGINE_END==');
  if (begin < 0 || end <= begin) {
    throw new Error('FATAL: Engine markers not found in Symbiose_Dashboard.html');
  }
  const engineSrc = html.slice(begin, end);

  // Optionally verify hash to detect Dashboard/Runner drift
  if (EXPECTED_ENGINE_HASH) {
    const actual = crypto.createHash('sha256').update(engineSrc, 'utf8').digest('hex');
    if (actual !== EXPECTED_ENGINE_HASH) {
      throw new Error(`Engine hash mismatch! Expected ${EXPECTED_ENGINE_HASH}, got ${actual}`);
    }
  }

  // Helper to extract a complete top-level function by brace-matching
  function extractFunction(name) {
    const start = html.indexOf('function ' + name + '(');
    if (start < 0) return '';
    const paramEnd = html.indexOf(')', start);
    if (paramEnd < 0) return '';
    const bodyStart = html.indexOf('{', paramEnd);
    if (bodyStart < 0) return '';
    let depth = 0;
    for (let i = bodyStart; i < html.length; i++) {
      if (html[i] === '{') depth++;
      else if (html[i] === '}') {
        depth--;
        if (depth === 0) {
          return html.slice(start, i + 1);
        }
      }
    }
    return '';
  }

  // Also extract Autobot gate helpers (pure functions before const Autobot = {)
  // These functions are pure: collectAutobotCandidates, sortAutobotCandidates,
  // selectAutobotTimeframe, evaluateAutobotCandidate, evaluateAutobotEdge,
  // addAutobotReject, sanitizeAutobotError, autobotProfileSettings
  const gateBegin = html.indexOf('function autobotProfileSettings');
  const gateEnd   = html.indexOf('\nconst Autobot = {'); // stop BEFORE the stateful Autobot object
  if (gateBegin < 0 || gateEnd <= gateBegin) {
    throw new Error('FATAL: Autobot gate function block not found in dashboard');
  }
  const gateSrc = html.slice(gateBegin, gateEnd);

  const combined = [
    engineSrc,
    extractFunction('tfToMinutes'),
    extractFunction('tfToHours'),
    extractFunction('stagnationFallbackForTimeframe'),
    extractFunction('computeBtcBias'),
    extractFunction('generateDeterministicOid'),
    extractFunction('optimizeTimeStopForAsset'),
    extractFunction('fmtP'),
    extractFunction('formatAutobotEntryLog'),
    gateSrc,
  ].join('\n;\n');

  // Node-compatible crypto shim for generateDeterministicOid
  const ctx = {
    console,
    Float64Array, Int8Array, Uint8Array,
    Math, Date, isFinite, isNaN, Infinity, Number, String, Array, Object, Boolean, JSON,
    setTimeout, clearTimeout,
    crypto: {
      getRandomValues(buf) {
        const bytes = crypto.randomBytes(buf.length);
        for (let i = 0; i < buf.length; i++) buf[i] = bytes[i];
        return buf;
      },
    },
  };
  vm.createContext(ctx);
  vm.runInContext(
    combined + `\nthis.__E = {
      clamp, SYM, strengthOf, fgLabel,
      macroAdjust, calcDSR, calcKelly, dynamicTp1At,
      simulateRange, evaluateTrades, reconcileBacktestAccounting,
      runWalkForwardBacktest, calcFundingBias, calcOIBias, calcBasisBias,
      regimeOf, squeezeAt,
      classifyRadarTf, rankRadarCandidates, recommendLeverage, explainDecision,
      sizePosition, analyze,
      tfToMinutes, tfToHours, stagnationFallbackForTimeframe,
      computeBtcBias, generateDeterministicOid, optimizeTimeStopForAsset,
      fmtP, formatAutobotEntryLog,
      autobotProfileSettings, collectAutobotCandidates, sortAutobotCandidates,
      selectAutobotTimeframe, evaluateAutobotCandidate, evaluateAutobotEdge,
      addAutobotReject, sanitizeAutobotError,
    };`,
    ctx,
  );
  return ctx.__E;
}

// ---------------------------------------------------------------------------
// HTTP helpers (relay calls)
// ---------------------------------------------------------------------------
function relayRequest(method, urlPath, body = null, requestImpl = null) {
  return new Promise((resolve, reject) => {
    const full = RELAY_URL + urlPath;
    const parsed = new URL(full);
    const lib = parsed.protocol === 'https:' ? https : http;
    const bodyData = body ? JSON.stringify(body) : null;
    const headers = { 'Content-Type': 'application/json' };
    if (RELAY_TOKEN) headers['X-AURA-Token'] = RELAY_TOKEN;
    if (bodyData) headers['Content-Length'] = Buffer.byteLength(bodyData);

    let settled = false;
    let req;
    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      callback(value);
    };
    const onError = error => finish(reject, error);
    const request = requestImpl || lib.request.bind(lib);
    req = request({
      hostname: parsed.hostname,
      port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
      path: parsed.pathname + (parsed.search || ''),
      method,
      headers,
    }, (res) => {
      let raw = '';
      res.on('data', chunk => { raw += chunk; });
      res.on('end', () => {
        try { finish(resolve, { status: res.statusCode, body: JSON.parse(raw) }); }
        catch { finish(resolve, { status: res.statusCode, body: raw }); }
      });
      res.on('error', onError);
    });
    req.once('error', onError);
    req.setTimeout(10000, () => {
      const error = new Error('Relay request timed out after 10000ms');
      req.destroy(error);
      finish(reject, error);
    });
    if (bodyData) req.write(bodyData);
    req.end();
  });
}

async function getState() {
  const r = await relayRequest('GET', '/api/state');
  if (r.status !== 200 || !r.body?.data) throw new Error('State read failed: ' + r.status);
  return r.body.data;
}

async function writeStateKey(key, value, expectedRev) {
  const payload = { key, value };
  if (expectedRev !== undefined) payload.expected_rev = expectedRev;
  const r = await relayRequest('POST', '/api/state', payload);
  return r;
}

async function writeStateMutations(mutations, expectedRev) {
  const payload = { mutations, expected_rev: expectedRev };
  const r = await relayRequest('POST', '/api/state', payload);
  if (r.status === 409) throw new Error('State revision conflict');
  if (r.status !== 200 || r.body?.ok !== true) throw new Error('State mutation failed: ' + r.status);
  return r.body;
}

async function claimSignalEvent(key) {
  const r = await relayRequest('POST', '/api/state', { signal_claim: { key } });
  return r.body?.claimed === true;
}

// ---------------------------------------------------------------------------
// Bitget market data via relay /api/public
// ---------------------------------------------------------------------------
async function fetchKlinesViaRelay(symbol, tf, limit = 1000) {
  const tfMap = { '1m': '1m', '5m': '5m', '15m': '15m', '30m': '30m',
                  '1h': '1H', '4h': '4H', '1d': '1D' };
  const granularity = tfMap[tf] || '1H';
  const r = await relayRequest('POST', '/api/public', {
    path: `/api/v2/mix/market/candles?symbol=${symbol}&granularity=${granularity}&limit=${limit}&productType=usdt-futures`,
    method: 'GET',
  });
  if (!r.body?.data || !Array.isArray(r.body.data)) return null;
  // Bitget format: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
  // confirmed-only candles: confirm === '1'
  const raw = r.body.data;
  const candles = raw
    .filter(c => c[8] === '1')
    .map(c => ({
      t: +c[0], o: +c[1], h: +c[2], l: +c[3], c: +c[4],
      v: +c[5], vol: +c[7],
    }))
    .sort((a, b) => a.t - b.t);
  return candles.length >= 40 ? { candles } : null;
}

async function fetchTickerViaRelay(symbol) {
  const r = await relayRequest('POST', '/api/public', {
    path: `/api/v2/mix/market/ticker?symbol=${symbol}&productType=usdt-futures`,
    method: 'GET',
  });
  const item = Array.isArray(r.body?.data) ? r.body.data[0] : r.body?.data;
  const price = Number(item?.lastPr ?? item?.last ?? item?.markPrice);
  if (!Number.isFinite(price) || price <= 0) throw new Error('Ticker response has no valid price');
  return { price };
}

function candleDurationMs(tf) {
  const minutes = { '1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60, '2h': 120, '4h': 240, '1d': 1440 }[tf] || 60;
  return minutes * 60_000;
}

// ---------------------------------------------------------------------------
// Universe fetch via relay (cached by relay)
// ---------------------------------------------------------------------------
async function fetchUniverseViaRelay() {
  const r = await relayRequest('GET', '/api/universe');
  if (r.status === 200 && r.body) {
    if (Array.isArray(r.body)) return r.body;
    if (Array.isArray(r.body.contracts)) return r.body.contracts;
    if (Array.isArray(r.body.symbols)) return r.body.symbols;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Signal emission via relay /api/signals (PF-68 relay-side endpoint)
// Rationale: relay owns ntfy credentials; runner never needs AURA_NTFY_URL.
// Central dedup via _signal_claims (same mechanism as browser NtfySignals.claim).
// ---------------------------------------------------------------------------
async function emitTradeEvent(engine, trade, event, detail = {}) {
  const key = `${trade.id}:${event}`;
  const claimed = await claimSignalEvent(key);
  if (!claimed) return false; // already emitted (dedup)

  // Signal is claimed — ask relay to push
  const body = buildEventBody(engine, trade, event, detail);
  const priority = event === 'sl_close' ? 4 : 3;
  const title = event === 'sl_close' ? 'AURA · Risiko-Alarm' : 'AURA · Trade-Signal';

  const r = await relayRequest('POST', '/api/signals', { title, body, priority });
  return r.status === 200;
}

function buildEventBody(engine, trade, event, detail = {}) {
  const fmtP = engine.fmtP || (p => String(p));
  const coin = String(trade?.coin || trade?.symbol || '?').toUpperCase();
  const side = Number(trade?.dir) === -1 ? 'SHORT' : 'LONG';
  const leverage = Number.isFinite(+trade?.leverage) ? `${+trade.leverage}x` : '';
  const labels = {
    open: 'Trade eröffnet', tp1: 'TP1 getroffen', tp2: 'TP2 getroffen', tp3: 'TP3 getroffen',
    sl_close: 'Stop-Loss getroffen', other_close: detail.reason === 'Time-Stop' ? 'Time-Stop' : 'Trade geschlossen',
  };
  const initialRisk = Math.abs((+trade?.entry || 0) - (+trade?.initialSl || +trade?.currentSl || 0));
  const price = Number.isFinite(+detail.price) ? +detail.price : (+trade?.markPrice || +trade?.entry || 0);
  const direction = Number(trade?.dir) === -1 ? -1 : 1;
  const r = initialRisk > 0 ? ((price - (+trade?.entry || 0)) * direction) / initialRisk : null;
  const pct = +trade?.entry > 0 ? ((price - +trade.entry) / +trade.entry) * direction * 100 : null;
  const parts = [`${coin} ${side}${leverage ? ` ${leverage}` : ''} — ${labels[event] || event} [Server-Bot]`];
  if (r !== null) parts[0] += ` (${r >= 0 ? '+' : ''}${r.toFixed(1)}R)`;
  if (price > 0) parts.push(`Preis ${fmtP(price)}${pct !== null ? ` (${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%)` : ''}`);
  if (detail.reason && event === 'other_close') parts.push(`Grund: ${detail.reason}`);
  return parts.join(' · ');
}

// ---------------------------------------------------------------------------
// In-trade tick monitoring (TP/SL checks per cycle)
// ---------------------------------------------------------------------------
function checkTpSlHits(engine, trade, markPrice) {
  if (!Number.isFinite(markPrice) || markPrice <= 0) return [];
  const dir = Number(trade.dir);
  const events = [];
  const hit = price => price > 0 && (dir === 1 ? markPrice >= price : markPrice <= price);

  if (!trade.tp1Hit && hit(trade.tp1 || trade.tp)) events.push('tp1');
  if (!trade.tp2Hit && hit(trade.tp2))             events.push('tp2');
  if (!trade.tp3Hit && hit(trade.tp3))             events.push('tp3');
  if (!trade.slHit  && !hit(trade.tp1 || trade.tp)) {
    if (dir === 1 && markPrice <= trade.currentSl) events.push('sl_close');
    if (dir === -1 && markPrice >= trade.currentSl) events.push('sl_close');
  }
  return events;
}

function applyAutoBreakeven(trade, markPrice) {
  if (trade.beActive) return; // already at BE
  const dir = Number(trade.dir);
  const initialRisk = Math.abs(trade.entry - trade.initialSl);
  if (initialRisk <= 0) return;
  const r = ((markPrice - trade.entry) * dir) / initialRisk;
  if (r >= 1.0) {
    trade.beActive = true;
    trade.currentSl = trade.entry;
    console.log(`[AutoBE] ${trade.coin} SL -> entry ${trade.entry} at +1R`);
  }
}

function checkTimeStop(trade) {
  if (!trade.maxHoldHours || !trade.openedAt) return false;
  const heldMs = Date.now() - trade.openedAt;
  const maxMs  = trade.maxHoldHours * 60 * 60 * 1000;
  return heldMs >= maxMs;
}

// ---------------------------------------------------------------------------
// Server Bot State (PF-67: equity, flags, mode flag, restart-persistent)
// ---------------------------------------------------------------------------
function computeFunnel24h(funnelCycles, now = Date.now()) {
  const cutoff = now - 86400000;
  const recent = Array.isArray(funnelCycles)
    ? funnelCycles.filter(c => c && Number.isFinite(c.ts) && c.ts >= cutoff)
    : [];
  let scanned = 0;
  let radar_passed = 0;
  let wf_evaluated = 0;
  let selected = 0;
  const reject_reasons = {};

  for (const c of recent) {
    scanned += Number(c.scanned) || 0;
    radar_passed += Number(c.radar_passed || c.radarFiltered) || 0;
    wf_evaluated += Number(c.wf_evaluated || c.wfEvaluated) || 0;
    selected += Number(c.selected) || 0;
    const rej = c.reject_reasons || c.rejects || {};
    for (const [code, cnt] of Object.entries(rej)) {
      reject_reasons[code] = (reject_reasons[code] || 0) + (Number(cnt) || 0);
    }
  }

  return {
    scanned,
    radar_passed,
    wf_evaluated,
    selected,
    reject_reasons,
  };
}

class ServerBotState {
  constructor() {
    this.trades        = [];
    this.history       = [];
    this.equity        = parseFloat(process.env.AURA_BOT_EQUITY || '10000');
    this.initialEquity = this.equity;
    this.startedAt     = Date.now();
    this.lastCycleAt   = null;
    this.lastHeartbeatAt = Date.now();
    this.paused        = false;
    this.pausedBy      = null;
    this.cycleCount    = 0;
    this.funnelCycles  = [];
    this.rev           = undefined; // track server state rev
  }

  // Merge state loaded from relay (restart recovery)
  loadFromServerState(serverState) {
    const srv = serverState[KEY_SRV_BOT];
    if (srv && typeof srv === 'object') {
      if (Number.isFinite(srv.equity)) this.equity = srv.equity;
      if (Number.isFinite(srv.initialEquity)) this.initialEquity = srv.initialEquity;
      if (Number.isFinite(srv.startedAt)) this.startedAt = srv.startedAt;
      if (Number.isFinite(srv.lastCycleAt) && srv.lastCycleAt >= 0) this.lastCycleAt = srv.lastCycleAt;
      if (Number.isFinite(srv.lastHeartbeatAt) && srv.lastHeartbeatAt >= 0) this.lastHeartbeatAt = srv.lastHeartbeatAt;
      // Server-Only Live: never restore legacy pause state from server — runner is always live.
      // if (typeof srv.paused === 'boolean') this.paused = srv.paused;
      // if (typeof srv.pausedBy === 'string' || srv.pausedBy === null) this.pausedBy = srv.pausedBy;
      if (Number.isInteger(srv.cycleCount) && srv.cycleCount >= 0) this.cycleCount = srv.cycleCount;
      if (Array.isArray(srv.funnelCycles)) this.funnelCycles = srv.funnelCycles;
    }
    // Restore server-owned trades (identified by source: 'server')
    const remoteTrades = serverState[KEY_TRADES];
    if (Array.isArray(remoteTrades)) {
      this.trades = remoteTrades.filter(t => t && t.source === 'server');
    }
    const remoteHistory = serverState[KEY_HISTORY];
    if (Array.isArray(remoteHistory)) {
      this.history = remoteHistory.filter(h => h && h.source === 'server');
    }
    this.rev = serverState._rev;
  }

  toServerPayload() {
    return {
      mode: 'server',
      equity: this.equity,
      initialEquity: this.initialEquity,
      startedAt: this.startedAt,
      lastCycleAt: this.lastCycleAt,
      lastHeartbeatAt: this.lastHeartbeatAt,
      paused: false,
      pausedBy: null,
      cycleCount: this.cycleCount,
      tradeCount: this.trades.length,
      funnel24h: computeFunnel24h(this.funnelCycles),
      funnelCycles: Array.isArray(this.funnelCycles) ? this.funnelCycles.slice(-1440) : [],
    };
  }
}

// ---------------------------------------------------------------------------
// Config: read from server state KEY_SRV_CFG (written by Dashboard panel)
// ---------------------------------------------------------------------------
function readBotConfig(serverState) {
  const cfg = serverState[KEY_SRV_CFG];
  if (cfg && typeof cfg === 'object') {
    return {
      profile:           cfg.profile        || 'balanced',
      minScore:          Number.isFinite(+cfg.minScore)        ? +cfg.minScore        : 65,
      mtfNeed:           Number.isFinite(+cfg.mtfNeed)         ? +cfg.mtfNeed         : 2,
      minOosSamples:     Number.isFinite(+cfg.minOosSamples)   ? +cfg.minOosSamples   : 8,
      minSetupDsr:       Number.isFinite(+cfg.minSetupDsr)     ? +cfg.minSetupDsr     : 0.10,
      minDsr:            Number.isFinite(+cfg.minDsr)          ? +cfg.minDsr          : 0.10,
      strictUniverseGate: cfg.strictUniverseGate === true,
      min24hVol:         Number.isFinite(+cfg.min24hVol)       ? +cfg.min24hVol       : 500000,
      maxOpenTrades:     Number.isFinite(+cfg.maxOpenTrades)   ? +cfg.maxOpenTrades   : 3,
      riskPerTradePct:   Number.isFinite(+cfg.riskPerTradePct) ? +cfg.riskPerTradePct : 1.0,
      maxLeverage:       Number.isFinite(+cfg.maxLeverage)     ? +cfg.maxLeverage     : 10,
      stagnationHours:   Number.isFinite(+cfg.stagnationHours) ? +cfg.stagnationHours : 24,
      btcFilter:         cfg.btcFilter !== false,
      initialEquity:     Number.isFinite(+cfg.initialEquity) ? +cfg.initialEquity : 10000,
      makerFee:          0.001, takerFee: 0.001, slippage: 0.001,
      timeStopBars:      Number.isFinite(+cfg.timeStopBars) ? +cfg.timeStopBars : 12,
    };
  }
  // Defaults (balanced profile)
  return {
    profile: 'balanced', minScore: 65, mtfNeed: 2, minOosSamples: 8,
    minSetupDsr: 0.10, minDsr: 0.10, strictUniverseGate: false,
    min24hVol: 500000, maxOpenTrades: 3, riskPerTradePct: 1.0,
    maxLeverage: 10, stagnationHours: 24, btcFilter: true, initialEquity: 10000,
    makerFee: 0.001, takerFee: 0.001, slippage: 0.001, timeStopBars: 12,
  };
}

// ---------------------------------------------------------------------------
// Main scan cycle (PF-66 Autobot logic, server-side)
// ---------------------------------------------------------------------------
let _scanInProgress = false;
let _defaultShadowCollector = null;

function getDefaultShadowCollector() {
  if (!_defaultShadowCollector) {
    _defaultShadowCollector = new ShadowCollector();
  }
  return _defaultShadowCollector;
}

async function runScanCycle(engine, state, config, collector = null) {
  if (_scanInProgress) {
    console.log('[Runner] Scan already in progress — skipping cycle');
    return null;
  }
  _scanInProgress = true;
  const cycleStart = Date.now();
  const shadowCollector = collector || getDefaultShadowCollector();

  const funnel = {
    scanned: 0, radarFiltered: 0, wfEvaluated: 1, selected: 0,
    rejects: {}, lastError: null,
  };

  try {
    // --- 1. Read server state (get current rev, mode flag, config, trades) ---
    let serverState;
    try {
      const getStateFn = config.getState || getState;
      serverState = await getStateFn();
    } catch (e) {
      console.error('[Runner] Cannot read relay state:', e.message);
      return null;
    }

    state.rev = serverState._rev;

    // --- 2. Server-Only Live: browser state can configure but never pause the runner ---
    const autobotState = serverState[KEY_STATE];
    state.paused = false;
    state.pausedBy = null;
    state.lastHeartbeatAt = Date.now();

    // --- 3. Sync local trade/history from server (post-restart recovery) ---
    const remoteTrades  = (Array.isArray(serverState[KEY_TRADES])  ? serverState[KEY_TRADES]  : []).filter(t => t?.source === 'server');
    const remoteHistory = (Array.isArray(serverState[KEY_HISTORY]) ? serverState[KEY_HISTORY] : []).filter(h => h?.source === 'server');
    // Reconcile: trust server as source of truth for server-owned records
    state.trades  = remoteTrades;
    state.history = remoteHistory;

    // Recompute equity from open positions (restart recovery)
    const usedMargin = state.trades.reduce((s, t) => s + (Number.isFinite(+t.margin) ? +t.margin : 0), 0);
    const savedEquity = autobotState?.serverEquity;
    if (Number.isFinite(savedEquity) && state.cycleCount === 0) {
      state.equity = savedEquity - usedMargin;
    }

    // --- 4. Re-read config (Dashboard panel may have changed it) ---
    const cfg = readBotConfig(serverState);
    funnel.configMinScore = cfg.minScore;
    if (state.cycleCount === 0 && !state.trades.length && Number.isFinite(cfg.initialEquity) && cfg.initialEquity > 0) {
      state.initialEquity = cfg.initialEquity;
      state.equity = cfg.initialEquity;
    }

    // --- 5. Fetch Universe ---
    const universe = config.universe || await fetchUniverseViaRelay();
    if (!universe || !universe.length) {
      console.log('[Runner] Universe unavailable — skipping scan');
      funnel.lastError = 'Universe fetch failed';
      return funnel;
    }

    // --- 6. BTC regime from server state ---
    const btcData = serverState['aura-btc-regime-v1'] || {};
    const btcBias = config.btcBias || engine.computeBtcBias(
      Number.isFinite(+btcData.score) ? +btcData.score : 50,
      Number.isFinite(+btcData.regime) ? +btcData.regime : 0,
    );

    // --- 7. Build radar snapshot from universe (server has no live radar; build minimal candidates) ---
    // Server bot uses universe rows directly as candidates if they carry tfScores.
    // If not available, we do a lightweight per-symbol analysis on the top-N by vol.
    const liquidUniverse = universe
      .map(row => {
        if (!row) return null;
        const vol = Number.isFinite(+row.usdtVolume) ? +row.usdtVolume : (Number.isFinite(+row.vol) ? +row.vol : 0);
        const liquidityVerified = row.liquidityVerified === true || row.symbolStatus === 'normal' || vol > 0;
        return { ...row, vol, usdtVolume: vol, liquidityVerified };
      })
      .filter(row => row && row.liquidityVerified && row.vol >= cfg.min24hVol)
      .sort((a, b) => (+b.vol || 0) - (+a.vol || 0));

    funnel.scanned = liquidUniverse.length * 4; // 4 TFs hypothetically

    // Candidates that already have tfScores (full radar rows) can be accepted directly
    const radarCandidates = config.radarData || engine.sortAutobotCandidates(
      engine.collectAutobotCandidates(liquidUniverse)
    );
    funnel.radarFiltered = radarCandidates.filter(
      c => engine.evaluateAutobotCandidate(c, cfg.minScore, cfg.mtfNeed).accepted
    ).length;
    funnel.wfEvaluated = Math.max(funnel.radarFiltered, 1);

    // --- 8. In-trade monitoring: TP/SL/TimeStop checks ---
    const closedTradeIds = new Set();
    const updatedTrades  = [];
    const newHistory     = [];

    for (const trade of state.trades) {
      // Fetch fresh mark price for this position
      let markPrice = null;
      try {
        const kdata = await fetchKlinesViaRelay(trade.coin, '1m', 5);
        if (kdata?.candles?.length) {
          markPrice = kdata.candles[kdata.candles.length - 1].c;
        }
      } catch (_) { /* fail-soft */ }

      if (!markPrice) { updatedTrades.push(trade); continue; }

      // Update running extrema
      const updated = { ...trade, markPrice };
      if (!Number.isFinite(updated.highestPrice) || markPrice > updated.highestPrice) updated.highestPrice = markPrice;
      if (!Number.isFinite(updated.lowestPrice)  || markPrice < updated.lowestPrice)  updated.lowestPrice  = markPrice;

      // Auto break-even
      applyAutoBreakeven(updated, markPrice);

      // TP/SL event check
      const hits = checkTpSlHits(engine, updated, markPrice);
      let closed = false;
      for (const event of hits) {
        if (event === 'sl_close') {
          closed = true;
          await emitTradeEvent(engine, updated, 'sl_close', { price: markPrice });
        } else if (['tp1', 'tp2', 'tp3'].includes(event)) {
          updated[`${event}Hit`] = true;
          await emitTradeEvent(engine, updated, event, { price: markPrice });
        }
      }

      // Time-stop
      if (!closed && checkTimeStop(updated)) {
        closed = true;
        await emitTradeEvent(engine, updated, 'other_close', { price: markPrice, reason: 'Time-Stop' });
      }

      if (closed) {
        closedTradeIds.add(trade.id);
        const histEntry = closeTradeRecord(updated, markPrice, closed ? 'sl_close' : 'timestop');
        newHistory.push(histEntry);
        state.equity += updated.margin;
      } else {
        updatedTrades.push(updated);
      }
    }

    state.trades  = updatedTrades;
    state.history = [...state.history, ...newHistory];

    // --- 9. New trade scan ---
    const openCoins = new Set(state.trades.map(t => t.coin));

    for (const c of radarCandidates) {
      if (state.trades.length >= cfg.maxOpenTrades) break;

      const candidateTf = c.bestTF || '1h';
      const cScore = Number(c.tfScores?.[candidateTf]?.score ?? c.bestInfo?.score ?? 0);
      const cDir = Number(c.mtfDir ?? c.tfScores?.[candidateTf]?.dir ?? 0);
      const cReg = c.tfScores?.[candidateTf]?.regime ?? 0;
      const cAdx = Number(c.tfScores?.[candidateTf]?.adx ?? 0);
      const cAtrPct = Number(c.tfScores?.[candidateTf]?.atrPct ?? 0);
      const cPrice = Number(c.price ?? c.tfScores?.[candidateTf]?.price ?? 0);

      const candidateBase = {
        symbol: c.symbol,
        tf: candidateTf,
        dir: cDir,
        score: cScore,
        regime: cReg,
        adx: cAdx,
        atrPct: cAtrPct,
        signalPrice: cPrice,
      };

      if (!c?.symbol || openCoins.has(c.symbol)) {
        engine.addAutobotReject(funnel, 'DUPLICATE_OR_INVALID');
        try {
          shadowCollector.recordDecision({
            ...candidateBase,
            decision: 'REJECTED',
            reject_reason: 'DUPLICATE_OR_INVALID',
            config: cfg,
          });
        } catch (_) {}
        continue;
      }

      const universeRow = liquidUniverse.find(r => r.symbol === c.symbol);
      if (!universeRow || universeRow.liquidityVerified !== true ||
          !Number.isFinite(+universeRow.vol) || +universeRow.vol < cfg.min24hVol) {
        engine.addAutobotReject(funnel, 'LIQUIDITY');
        try {
          shadowCollector.recordDecision({
            ...candidateBase,
            decision: 'REJECTED',
            reject_reason: 'LIQUIDITY',
            config: cfg,
          });
        } catch (_) {}
        continue;
      }

      const candidateGate = engine.evaluateAutobotCandidate(c, cfg.minScore, cfg.mtfNeed);
      if (!candidateGate.accepted) {
        engine.addAutobotReject(funnel, 'NO_RADAR_READY');
        try {
          shadowCollector.recordDecision({
            ...candidateBase,
            tf: candidateGate.tf || candidateBase.tf,
            dir: candidateGate.dir || candidateBase.dir,
            decision: 'REJECTED',
            reject_reason: 'NO_RADAR_READY',
            config: cfg,
          });
        } catch (_) {}
        continue;
      }

      // BTC macro gate
      if (cfg.btcFilter && btcBias.available) {
        if ((candidateGate.dir === 1  && btcBias.regTxt === 'BEAR') ||
            (candidateGate.dir === -1 && btcBias.regTxt === 'BULL')) {
          engine.addAutobotReject(funnel, 'BTC_CONFLICT');
          try {
            shadowCollector.recordDecision({
              ...candidateBase,
              tf: candidateGate.tf,
              dir: candidateGate.dir,
              decision: 'REJECTED',
              reject_reason: 'BTC_CONFLICT',
              config: cfg,
            });
          } catch (_) {}
          continue;
        }
      }

      // Fresh revalidation
      let kdata;
      try {
        kdata = await fetchKlinesViaRelay(c.symbol, candidateGate.tf, 1000);
        if (!kdata || kdata.candles.length < 40) {
          engine.addAutobotReject(funnel, 'FRESH_DATA');
          try {
            shadowCollector.recordDecision({
              ...candidateBase,
              tf: candidateGate.tf,
              dir: candidateGate.dir,
              decision: 'REJECTED',
              reject_reason: 'FRESH_DATA',
              config: cfg,
            });
          } catch (_) {}
          continue;
        }
      } catch {
        engine.addAutobotReject(funnel, 'FRESH_DATA');
        try {
          shadowCollector.recordDecision({
            ...candidateBase,
            tf: candidateGate.tf,
            dir: candidateGate.dir,
            decision: 'REJECTED',
            reject_reason: 'FRESH_DATA',
            config: cfg,
          });
        } catch (_) {}
        continue;
      }

      const A = engine.analyze(kdata.candles);
      if (!A || !A.n || !A.last) {
        engine.addAutobotReject(funnel, 'FRESH_ANALYSIS');
        try {
          shadowCollector.recordDecision({
            ...candidateBase,
            tf: candidateGate.tf,
            dir: candidateGate.dir,
            decision: 'REJECTED',
            reject_reason: 'FRESH_ANALYSIS',
            config: cfg,
          });
        } catch (_) {}
        continue;
      }

      const freshRegime = engine.regimeOf(A);
      const lastCandle  = kdata.candles[kdata.candles.length - 1];
      const lastCandleTs = Number(lastCandle?.t || 0);
      if (lastCandleTs > 1_000_000_000_000 && Date.now() - lastCandleTs > 1.5 * candleDurationMs(candidateGate.tf)) {
        engine.addAutobotReject(funnel, 'STALE_CANDLE');
        try {
          shadowCollector.recordDecision({
            ...candidateBase,
            tf: candidateGate.tf,
            dir: candidateGate.dir,
            score: A.last.score,
            regime: freshRegime.reg,
            adx: A.last.adx,
            atrPct: lastCandle.c > 0 ? (A.last.atr / lastCandle.c * 100) : 0,
            signalPrice: lastCandle.c,
            decision: 'REJECTED',
            reject_reason: 'STALE_CANDLE',
            config: cfg,
          });
        } catch (_) {}
        continue;
      }
      const signalPrice = lastCandle.c;
      const freshGate   = engine.classifyRadarTf({
        score: A.last.score, dir: A.last.dir,
        regime: freshRegime.reg, isSqz: freshRegime.isSqz,
        adx: A.last.adx,
        atrPct: signalPrice > 0 ? (A.last.atr / signalPrice * 100) : 0,
        longTh: cfg.minScore,
        shortTh: 100 - cfg.minScore,
      });
      const freshCandidate = engine.evaluateAutobotCandidate({
        executable: freshGate.tradeable,
        bestInfo: { ...freshGate, score: A.last.score, dir: A.last.dir },
        aligned: c.aligned,
        bestTF: candidateGate.tf,
      }, cfg.minScore, cfg.mtfNeed);

      const candidateEvaluated = {
        symbol: c.symbol,
        tf: candidateGate.tf,
        dir: freshCandidate.dir || candidateGate.dir,
        score: A.last.score,
        regime: freshRegime.reg,
        adx: A.last.adx,
        atrPct: signalPrice > 0 ? (A.last.atr / signalPrice * 100) : 0,
        signalPrice: signalPrice,
      };

      if (!freshGate.tradeable || !freshCandidate.accepted ||
          freshCandidate.dir !== candidateGate.dir) {
        engine.addAutobotReject(funnel, 'FRESH_GATE');
        try {
          shadowCollector.recordDecision({
            ...candidateEvaluated,
            decision: 'REJECTED',
            reject_reason: 'FRESH_GATE',
            config: cfg,
          });
        } catch (_) {}
        continue;
      }

      // OOS Walk-Forward
      const freshWF = engine.runWalkForwardBacktest(kdata.candles, A, {
        makerFee: cfg.makerFee, takerFee: cfg.takerFee, slippage: cfg.slippage,
        timeStopBars: cfg.timeStopBars,
        trialMultiplier: funnel.wfEvaluated,
        tfMinutes: engine.tfToMinutes(freshCandidate.tf),
      });
      const edgeGate = engine.evaluateAutobotEdge(freshWF, cfg.minOosSamples, {
        strictUniverseGate: cfg.strictUniverseGate,
        minDsr: cfg.minSetupDsr,
      });
      if (!edgeGate.accepted) {
        engine.addAutobotReject(funnel, 'MODEL_NO_EVIDENCE');
        try {
          shadowCollector.recordDecision({
            ...candidateEvaluated,
            decision: 'REJECTED',
            reject_reason: 'MODEL_NO_EVIDENCE',
            config: cfg,
          });
        } catch (_) {}
        continue;
      }

      // Kelly sizing
      const wfStats  = freshWF?.stats ?? {};
      const kelly    = engine.calcKelly(
        wfStats.wr ?? 0.5, wfStats.avgWinR ?? 1.8, wfStats.avgLossR ?? 1.05,
        cfg.riskPerTradePct, state.equity, wfStats.total ?? 0,
      );
      if (!kelly.hasEdge || kelly.riskAmt <= 0) {
        engine.addAutobotReject(funnel, 'MODEL_NO_EVIDENCE');
        try {
          shadowCollector.recordDecision({
            ...candidateEvaluated,
            decision: 'REJECTED',
            reject_reason: 'MODEL_NO_EVIDENCE',
            config: cfg,
          });
        } catch (_) {}
        continue;
      }

      // Fetch the executable mark only after every signal/evidence gate has passed.
      let execPrice = signalPrice;
      try {
        const ticker = await fetchTickerViaRelay(c.symbol);
        execPrice = ticker.price;
      } catch (tickerError) {
        console.warn(`[Runner] Live ticker failed for ${c.symbol}; using closed-candle fallback ${signalPrice}: ${tickerError.message}`);
      }

      const dir     = freshCandidate.dir;
      const atr     = A.last.atr || (signalPrice * 0.015);
      const slDist  = Math.max(execPrice * 0.005, atr * 1.5);
      const sl      = dir === 1 ? (execPrice - slDist) : (execPrice + slDist);
      const tp1     = dir === 1 ? (execPrice + slDist * 1.5) : (execPrice - slDist * 1.5);
      const tp2     = dir === 1 ? (execPrice + slDist * 3.0) : (execPrice - slDist * 3.0);
      const tp3     = dir === 1 ? (execPrice + slDist * 5.0) : (execPrice - slDist * 5.0);

      const priceRiskPct   = slDist / execPrice;
      const targetNotional = Math.min(state.equity * 2.5, kelly.riskAmt / priceRiskPct);
      const leverage       = Math.min(cfg.maxLeverage, Math.max(2, Math.ceil(targetNotional / (state.equity * 0.25))));
      const margin         = Math.round(targetNotional / leverage);

      if (margin > state.equity * 0.35 || margin < 10) {
        engine.addAutobotReject(funnel, 'MARGIN');
        try {
          shadowCollector.recordDecision({
            ...candidateEvaluated,
            decision: 'REJECTED',
            reject_reason: 'MARGIN',
            config: cfg,
          });
        } catch (_) {}
        continue;
      }

      // Belt-and-suspenders duplicate check after all awaits
      if (state.trades.some(x => x.coin === c.symbol)) {
        engine.addAutobotReject(funnel, 'DUPLICATE_OR_INVALID');
        try {
          shadowCollector.recordDecision({
            ...candidateEvaluated,
            decision: 'REJECTED',
            reject_reason: 'DUPLICATE_OR_INVALID',
            config: cfg,
          });
        } catch (_) {}
        continue;
      }

      const tfHours   = engine.tfToHours(freshCandidate.tf);
      const optTS     = engine.optimizeTimeStopForAsset(kdata.candles, A, {
        timeframe: freshCandidate.tf, timeframeHours: tfHours,
        fallbackBars: engine.stagnationFallbackForTimeframe(cfg.stagnationHours, freshCandidate.tf).bars,
        fallbackHours: engine.stagnationFallbackForTimeframe(cfg.stagnationHours, freshCandidate.tf).hours,
        maxCapHours: Math.max(36 * tfHours, 24),
        minFloorHours: 2 * tfHours,
      });

      const newTrade = {
        record_schema: 2,
        schemaVersion: 2,
        id:           engine.generateDeterministicOid('sb'),
        source:       'server',
        coin:         c.symbol,
        dir,
        signalPrice,
        entry:        execPrice, markPrice: execPrice,
        initialSl:    sl, currentSl: sl,
        tp: tp1, tp1, tp2, tp3,
        margin, initialMargin: margin, leverage,
        notional:     margin * leverage,
        openedAt:     Date.now(),
        beActive:     false, scaledOut: false,
        score:        Math.round(freshCandidate.score),
        signalTf:     freshCandidate.tf,
        edge:         edgeGate.edge,
        edgeSamples:  edgeGate.sampleSize,
        dsr:          edgeGate.setupDsr, setupDsr: edgeGate.setupDsr,
        universeDsr:  edgeGate.universeDsr,
        effectiveTrials: edgeGate.effectiveTrials,
        setupTrials:  edgeGate.setupTrials || 18,
        timeStopBars: optTS.bars, maxHoldHours: optTS.hours,
        timeStopReason: optTS.reason,
      };

      state.equity -= margin;
      state.trades.push(newTrade);
      openCoins.add(c.symbol);
      funnel.selected++;

      try {
        shadowCollector.recordDecision({
          ...candidateEvaluated,
          decision: 'ACCEPTED',
          reject_reason: null,
          config: cfg,
        });
      } catch (_) {}

      const slippagePct = signalPrice > 0 ? ((execPrice - signalPrice) / signalPrice) * 100 : 0;
      console.log(`[Runner] OPEN ${c.symbol} ${dir === 1 ? 'LONG' : 'SHORT'} ${leverage}x entry=${execPrice} signal=${signalPrice} slippage=${slippagePct >= 0 ? '+' : ''}${slippagePct.toFixed(2)}% margin=${margin} tf=${freshCandidate.tf} score=${newTrade.score} dsr=${edgeGate.setupDsr.toFixed(2)} edge=${edgeGate.edge.toFixed(3)}`);

      // Emit open signal
      await emitTradeEvent(engine, newTrade, 'open', { price: execPrice, signalPrice });

      break; // 1 trade per scan cycle (consistent with browser bot)
    }

    // --- 10. Persist state back to relay ---
    state.cycleCount++;
    state.lastCycleAt = Date.now();

    // Record funnel in rolling 24h history
    if (!Array.isArray(state.funnelCycles)) state.funnelCycles = [];
    state.funnelCycles.push({
      ts: Date.now(),
      scanned: funnel.scanned,
      radar_passed: funnel.radarFiltered,
      wf_evaluated: funnel.wfEvaluated,
      selected: funnel.selected,
      rejects: { ...funnel.rejects },
    });
    const cutoff24h = Date.now() - 86400000;
    state.funnelCycles = state.funnelCycles.filter(c => c && c.ts >= cutoff24h);

    // Persist server-owned records atomically with optimistic concurrency. This
    // avoids overwriting concurrent browser mutations between separate writes.
    const currentServerState = await getState();
    const metaWrite = await writeStateKey(KEY_SRV_BOT, state.toServerPayload(), currentServerState._rev);
    if (metaWrite.status === 409) throw new Error('State revision conflict');
    if (metaWrite.status !== 200 || metaWrite.body?.ok !== true) throw new Error('State metadata write failed: ' + metaWrite.status);

    // Refresh revision after metadata write, then batch record-level mutations.
    const afterMeta = await getState();
    const tradeMutations = [];
    const existingServerTrades = (Array.isArray(afterMeta[KEY_TRADES]) ? afterMeta[KEY_TRADES] : [])
      .filter(t => t?.source === 'server');
    const existingServerHistory = (Array.isArray(afterMeta[KEY_HISTORY]) ? afterMeta[KEY_HISTORY] : [])
      .filter(h => h?.source === 'server');
    for (const trade of existingServerTrades) {
      if (!state.trades.some(item => item.id === trade.id)) tradeMutations.push({ key: KEY_TRADES, op: 'delete', id: trade.id });
    }
    for (const trade of state.trades) tradeMutations.push({ key: KEY_TRADES, op: 'upsert', id: trade.id, value: trade });
    for (const history of existingServerHistory) {
      if (!state.history.some(item => item.id === history.id)) tradeMutations.push({ key: KEY_HISTORY, op: 'delete', id: history.id });
    }
    for (const history of state.history) tradeMutations.push({ key: KEY_HISTORY, op: 'upsert', id: history.id, value: history });
    if (tradeMutations.length) await writeStateMutations(tradeMutations, afterMeta._rev);

    const cycleMs = Date.now() - cycleStart;
    console.log(`[Runner] Cycle #${state.cycleCount} done. Open=${state.trades.length} Equity=${state.equity.toFixed(0)} Funnel=${JSON.stringify(funnel.rejects)} (${cycleMs}ms)`);

    return funnel;
  } catch (e) {
    console.error('[Runner] Cycle error:', e.message);
    funnel.lastError = e.message;
    return funnel;
  } finally {
    _scanInProgress = false;
  }
}

// ---------------------------------------------------------------------------
// Close trade helper
// ---------------------------------------------------------------------------
function closeTradeRecord(trade, exitPrice, reason) {
  const dir = Number(trade.dir);
  const initialRisk = Math.abs(trade.entry - trade.initialSl);
  const pnl = (exitPrice - trade.entry) * dir * (trade.notional / trade.entry);
  const r   = initialRisk > 0 ? ((exitPrice - trade.entry) * dir) / initialRisk : 0;
  return {
    ...trade,
    record_schema: 2,
    schemaVersion: 2,
    id:         engine_generateHistoryId(trade.id),
    parentId:   trade.id,
    source:     'server',
    exit:       exitPrice,
    closedAt:   Date.now(),
    realizedPnl: pnl,
    realizedR:  r,
    closeReason: reason,
  };
}
function engine_generateHistoryId(parentId) {
  return `${parentId}_close_${Date.now().toString(36)}`;
}

// ---------------------------------------------------------------------------
// Health check output (for relay /ready runner field)
// ---------------------------------------------------------------------------
function exposeHealth(state) {
  // Write a small health file that bitget_relay.py can read
  const healthPath = path.join(
    process.env.AURA_STATE_DIR || path.resolve('data'),
    'runner_health.json',
  );
  try {
    const data = {
      running:         true,
      lastCycleAt:     state.lastCycleAt,
      lastHeartbeatAt: state.lastHeartbeatAt || state.lastCycleAt || Date.now(),
      paused:          false,
      pausedBy:        null,
      cycleCount:      state.cycleCount,
      tradeCount:      state.trades.length,
      equity:          state.equity,
      funnel24h:       computeFunnel24h(state.funnelCycles),
      updatedAt:       Date.now(),
    };
    fs.writeFileSync(healthPath, JSON.stringify(data), 'utf8');
  } catch (_) { /* non-critical */ }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------
async function main() {
  if (BOT_MODE !== 'server') {
    console.log('[Runner] AURA_BOT_MODE is not "server" — headless bot disabled. Set AURA_BOT_MODE=server to activate.');
    process.exit(0);
  }

  console.log(`[Runner] AURA Headless Paper Autobot starting (v2.5.0 Server-Only Live)`);
  console.log(`[Runner] Dashboard: ${DASHBOARD}`);
  console.log(`[Runner] Relay:     ${RELAY_URL}`);
  console.log(`[Runner] Interval:  ${SCAN_SEC}s`);

  // Load engine (fail-fast on marker/hash error)
  let engine;
  try {
    engine = loadEngine();
    console.log('[Runner] Engine loaded OK');
  } catch (e) {
    console.error('[Runner] FATAL:', e.message);
    process.exit(1);
  }

  // Init state
  const state = new ServerBotState();

  // Restore persistent state from relay
  try {
    const serverState = await getState();
    state.loadFromServerState(serverState);
    console.log(`[Runner] State restored: ${state.trades.length} open trades, equity=${state.equity}`);
  } catch (e) {
    console.warn('[Runner] Could not restore state:', e.message, '— starting fresh');
  }

  // Announce server-bot mode to relay so dashboard can detect it
  try {
    const currentState = await getState();
    const existing = currentState[KEY_STATE] || {};
    await writeStateKey(KEY_STATE, { ...existing, mode: 'server', serverBotActive: true, serverBotStartedAt: state.startedAt });
    console.log('[Runner] Mode flag written to relay state (KEY_STATE mode=server)');
  } catch (e) {
    console.warn('[Runner] Could not write mode flag:', e.message);
  }

  // Run first cycle immediately
  await runScanCycle(engine, state, {});
  exposeHealth(state);

  // Periodic scan
  const timer = setInterval(async () => {
    await runScanCycle(engine, state, {});
    exposeHealth(state);
  }, SCAN_SEC * 1000);

  // Keep the process alive for periodic scanning
  // (timer stays referenced in main process)

  // Graceful shutdown
  process.on('SIGTERM', () => {
    console.log('[Runner] SIGTERM received — shutting down');
    clearInterval(timer);
    exposeHealth(state);
    process.exit(0);
  });
  process.on('SIGINT', () => {
    console.log('[Runner] SIGINT received — shutting down');
    clearInterval(timer);
    exposeHealth(state);
    process.exit(0);
  });
}

// Only run main() when executed directly (not when require()'d by tests)
if (require.main === module) {
  main().catch(e => { console.error('[Runner] Fatal startup error:', e); process.exit(1); });
}

// Export for tests (CommonJS)
module.exports = {
  loadEngine,
  buildEventBody,
  checkTpSlHits,
  applyAutoBreakeven,
  checkTimeStop,
  readBotConfig,
  ServerBotState,
  computeFunnel24h,
  closeTradeRecord,
  schemaV2Keys: { trades: KEY_TRADES, history: KEY_HISTORY },
  relayRequest,
  fetchTickerViaRelay,
  candleDurationMs,
  runScanCycle,
  getDefaultShadowCollector,
  isScanInProgress: () => _scanInProgress,
};
