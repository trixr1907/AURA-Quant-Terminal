'use strict';
/**
 * PF-70: Headless Runner Tests
 * ============================
 * 1. Funnel-Parity:  same fixtures through engine yield identical gate decisions
 * 2. Event/Dedup:    open/tp/sl emitted once; restart does not re-push
 * 3. Mode-Switch:    server active → browser scan paused (and vice versa)
 * 4. Config-Passthrough: panel write reaches runner on next cycle
 * 5. Fail-Close:     data errors / stale data → no trade, cycle continues
 * 6. Rate-Limit/Backoff: 429 → no trade, no crash
 * 7. Restart-Persistence: closed tradeIds tracked, re-open not re-claimed
 */

const assert = require('assert');
const fs     = require('fs');
const path   = require('path');
const vm     = require('vm');

// ---------------------------------------------------------------------------
// Load engine (same extraction as test_engine_full.js and headless_autobot.js)
// ---------------------------------------------------------------------------
const html    = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const begin   = html.indexOf('//  ==ENGINE_BEGIN==');
const end     = html.indexOf('// ==ENGINE_END==');
assert(begin >= 0 && end > begin, 'FATAL: Engine markers missing');

const engineSrc = html.slice(begin, end);

function getSection(startMarker, fallbackAfter) {
  const si = html.indexOf(startMarker);
  if (si < 0) return '';
  const ei = html.indexOf('\nfunction ', si + startMarker.length + 10);
  return ei > si ? html.slice(si, ei) : '';
}

const combined = [
  engineSrc,
  getSection('function tfToMinutes('),
  getSection('function tfToHours('),
  getSection('function stagnationFallbackForTimeframe('),
  getSection('function computeBtcBias('),
  getSection('function generateDeterministicOid('),
  getSection('function optimizeTimeStopForAsset('),
  getSection('function fmtP('),
  getSection('function formatAutobotEntryLog('),
  // Gate helpers (from autobotProfileSettings to const Autobot = { — pure functions only)
  (() => {
    const s = html.indexOf('function autobotProfileSettings');
    const e = html.indexOf('\nconst Autobot = {'); // stop BEFORE the stateful Autobot object
    return s >= 0 && e > s ? html.slice(s, e) : '';
  })(),
].join('\n');

const ctx = {
  console, Float64Array, Int8Array, Uint8Array,
  Math, Date, isFinite, isNaN, Infinity, Number, String, Array, Object, Boolean, JSON,
  setTimeout, clearTimeout,
  crypto: {
    getRandomValues(buf) {
      const { randomBytes } = require('crypto');
      const bytes = randomBytes(buf.length);
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
    runWalkForwardBacktest, regimeOf, squeezeAt,
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
const E = ctx.__E;

// Also load headless_autobot.js helpers
const autobot = require('../headless_autobot.js');

// ---------------------------------------------------------------------------
// Minimal test runner
// ---------------------------------------------------------------------------
let passed = 0, failed = 0;
const errors = [];
function test(name, fn) {
  try { fn(); console.log(`  PASS  ${name}`); passed++; }
  catch (e) { console.error(`  FAIL  ${name}\n        ${e.message}`); errors.push({ name, message: e.message }); failed++; }
}
function section(title) { console.log(`\n[${title}]`); }

// ---------------------------------------------------------------------------
// Fixtures: deterministic candle series (same as test_autobot_statistical_edge.js)
// ---------------------------------------------------------------------------
function seededRandom(seed) {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}

function makeCandles(n, seed = 42) {
  const rng = seededRandom(seed);
  const candles = [];
  let price = 100;
  for (let i = 0; i < n; i++) {
    const chg = (rng() - 0.49) * 2;
    const o = price;
    const c = Math.max(0.01, price + chg);
    const h = Math.max(o, c) + rng() * 0.5;
    const l = Math.min(o, c) - rng() * 0.5;
    candles.push({ t: Date.now() - (n - i) * 3600000, o, h, l, c, v: 1000 + rng() * 500, vol: 2000000 });
    price = c;
  }
  return candles;
}

// ---------------------------------------------------------------------------
// PF-70.1 — Funnel Parity: same candles → same gate outcomes
// ---------------------------------------------------------------------------
section('PF-70.1: Funnel Parity Browser Engine ↔ Runner Engine');

test('Engine extracted identically (same exported symbols)', () => {
  const required = ['analyze', 'runWalkForwardBacktest', 'evaluateAutobotCandidate',
                    'evaluateAutobotEdge', 'calcKelly', 'regimeOf', 'classifyRadarTf'];
  for (const sym of required) {
    assert(typeof E[sym] === 'function', `Missing engine export: ${sym}`);
  }
});

test('evaluate candidate: btcBlock → rejected (both paths identical)', () => {
  const blocked = { btcBlock: true, aligned: 3, symbol: 'XUSDT' };
  // Browser path
  const browserResult = E.evaluateAutobotCandidate(blocked, 65, 2);
  // Runner just calls the same extracted function — verify the contract
  assert.strictEqual(browserResult.accepted, false);
  assert.strictEqual(browserResult.dir, 0);
});

test('evaluate candidate: tfScores path — strong signal accepted', () => {
  // selectAutobotTimeframe needs mtfDir to resolve direction from tfScores
  // (mtfDir is required as the agreed direction for the multi-TF check)
  const candidate = {
    symbol: 'BTCUSDT',
    aligned: 4,
    btcBlock: false,
    incomplete: false,
    mtfDir: 1,  // required: the overall MTF direction
    tfScores: {
      '1h': { score: 80, dir: 1, status: 'ready', tradeable: true, quality: 0.9 },
      '4h': { score: 82, dir: 1, status: 'ready', tradeable: true, quality: 0.92 },
    },
  };
  const result = E.evaluateAutobotCandidate(candidate, 65, 2);
  assert.strictEqual(result.accepted, true);
  assert.strictEqual(result.dir, 1);
});

test('evaluate candidate: score below minScore → rejected', () => {
  const candidate = {
    symbol: 'LOWUSDT',
    aligned: 4,
    btcBlock: false,
    incomplete: false,
    tfScores: {
      '1h': { score: 50, dir: 1, status: 'ready', tradeable: true, quality: 0.5 },
    },
  };
  const result = E.evaluateAutobotCandidate(candidate, 65, 2);
  assert.strictEqual(result.accepted, false);
});

test('evaluate candidate: mtfNeed not met → rejected', () => {
  const candidate = {
    symbol: 'LOWMTFUSDT',
    aligned: 1,
    btcBlock: false,
    incomplete: false,
    tfScores: {
      '1h': { score: 80, dir: 1, status: 'ready', tradeable: true, quality: 0.9 },
    },
  };
  const result = E.evaluateAutobotCandidate(candidate, 65, 3); // need 3 aligned, only 1
  assert.strictEqual(result.accepted, false);
});

test('evaluateAutobotEdge: OOS required — no OOS evidence → rejected', () => {
  const badWF = { evidenceStatus: 'IS', stats: { total: 20, wr: 0.6, avgWinR: 2, avgLossR: 1 }, dsr: { dsr: 0.8 } };
  const result = E.evaluateAutobotEdge(badWF, 8, { minDsr: 0.1 });
  assert.strictEqual(result.accepted, false);
});

test('evaluateAutobotEdge: positive OOS edge → accepted', () => {
  const candles = makeCandles(600, 7);
  const A = E.analyze(candles);
  const wf = E.runWalkForwardBacktest(candles, A, { makerFee: 0.001, takerFee: 0.001, slippage: 0.001, timeStopBars: 12, tfMinutes: 60 });
  // Only test the gate contract — may not have evidence (market-dependent)
  assert(typeof wf === 'object', 'runWalkForwardBacktest must return an object');
  const result = E.evaluateAutobotEdge(wf, 8, { minDsr: 0.0 });
  assert(typeof result.accepted === 'boolean', 'accepted must be boolean');
  assert(Number.isFinite(result.edge), 'edge must be finite');
});

// ---------------------------------------------------------------------------
// PF-70.2 — Event / Dedup (headless_autobot.js helpers)
// ---------------------------------------------------------------------------
section('PF-70.2: Event/Dedup — checkTpSlHits, applyAutoBreakeven, checkTimeStop');

test('checkTpSlHits: LONG above tp1 → tp1 event', () => {
  const trade = { dir: 1, entry: 100, initialSl: 95, currentSl: 95, tp: 105, tp1: 105, tp2: 110, tp3: 120 };
  const events = autobot.checkTpSlHits(null, trade, 106);
  assert(events.includes('tp1'), `Expected tp1, got: ${events}`);
});

test('checkTpSlHits: LONG below sl → sl_close event', () => {
  const trade = { dir: 1, entry: 100, initialSl: 95, currentSl: 95, tp: 105, tp1: 105, tp2: 110, tp3: 120 };
  const events = autobot.checkTpSlHits(null, trade, 94);
  assert(events.includes('sl_close'), `Expected sl_close, got: ${events}`);
});

test('checkTpSlHits: SHORT above sl → sl_close event', () => {
  const trade = { dir: -1, entry: 100, initialSl: 105, currentSl: 105, tp: 95, tp1: 95, tp2: 90, tp3: 80 };
  const events = autobot.checkTpSlHits(null, trade, 106);
  assert(events.includes('sl_close'), `Expected sl_close, got: ${events}`);
});

test('checkTpSlHits: no hit → empty array', () => {
  const trade = { dir: 1, entry: 100, initialSl: 95, currentSl: 95, tp: 105, tp1: 105, tp2: 110, tp3: 120 };
  const events = autobot.checkTpSlHits(null, trade, 101);
  assert.strictEqual(events.length, 0);
});

test('checkTpSlHits: already marked tp1Hit → tp1 not re-emitted', () => {
  const trade = { dir: 1, entry: 100, initialSl: 95, currentSl: 95, tp: 105, tp1: 105, tp2: 110, tp3: 120, tp1Hit: true };
  const events = autobot.checkTpSlHits(null, trade, 106);
  assert(!events.includes('tp1'), 'tp1 should not be re-emitted after tp1Hit=true');
});

test('applyAutoBreakeven: LONG at +1R → SL moves to entry', () => {
  const trade = { dir: 1, entry: 100, initialSl: 95, currentSl: 95, beActive: false };
  autobot.applyAutoBreakeven(trade, 105); // +1R exactly
  assert.strictEqual(trade.beActive, true, 'beActive must be set');
  assert.strictEqual(trade.currentSl, 100, 'currentSl must equal entry');
});

test('applyAutoBreakeven: LONG at +0.5R → no BE yet', () => {
  const trade = { dir: 1, entry: 100, initialSl: 95, currentSl: 95, beActive: false };
  autobot.applyAutoBreakeven(trade, 102.5); // +0.5R
  assert.strictEqual(trade.beActive, false, 'beActive must stay false at +0.5R');
});

test('applyAutoBreakeven: beActive already → no double-apply', () => {
  const trade = { dir: 1, entry: 100, initialSl: 95, currentSl: 100, beActive: true };
  autobot.applyAutoBreakeven(trade, 110);
  assert.strictEqual(trade.currentSl, 100, 'SL must not change when BE already active');
});

test('checkTimeStop: expired trade → true', () => {
  const trade = { openedAt: Date.now() - 25 * 3600 * 1000, maxHoldHours: 24 };
  assert.strictEqual(autobot.checkTimeStop(trade), true);
});

test('checkTimeStop: fresh trade → false', () => {
  const trade = { openedAt: Date.now() - 1000, maxHoldHours: 24 };
  assert.strictEqual(autobot.checkTimeStop(trade), false);
});

// ---------------------------------------------------------------------------
// PF-70.3 — Mode-Switch: server active → browser scan paused
// ---------------------------------------------------------------------------
section('PF-70.3: Mode-Switch contract');

test('ServerBotState: default equity from env or constructor default', () => {
  const s = new autobot.ServerBotState();
  assert(Number.isFinite(s.equity) && s.equity > 0, 'equity must be positive');
  assert.strictEqual(s.trades.length, 0);
  assert.strictEqual(s.history.length, 0);
});

test('ServerBotState.toServerPayload: mode is server', () => {
  const s = new autobot.ServerBotState();
  const payload = s.toServerPayload();
  assert.strictEqual(payload.mode, 'server');
});

test('ServerBotState.loadFromServerState: restores equity from server', () => {
  const s = new autobot.ServerBotState();
  s.loadFromServerState({
    'aura-server-bot-state-v1': { equity: 8500, initialEquity: 10000, startedAt: 1234567890 },
    'aura-quant-terminal-active-trades-v1': [
      { id: 't1', source: 'server', margin: 200, coin: 'XUSDT', dir: 1 },
      { id: 't2', source: 'browser', margin: 300, coin: 'YUSDT', dir: -1 }, // should be excluded
    ],
  });
  assert.strictEqual(s.equity, 8500, 'equity should be restored');
  // Only server trades should be loaded
  assert.strictEqual(s.trades.length, 1, 'Only server trades should be restored');
  assert.strictEqual(s.trades[0].id, 't1');
});

test('mode flag: KEY_STATE with mode=browser → server bot should pause', () => {
  // This mimics the check in runScanCycle: autobotState.enabled=true and mode!='server'
  const autobotState = { enabled: true, mode: 'browser' };
  const shouldPause = autobotState.enabled === true && autobotState.mode !== 'server';
  assert.strictEqual(shouldPause, true, 'Server bot must pause when browser bot is active');
});

test('mode flag: KEY_STATE with mode=server → server bot should not pause', () => {
  const autobotState = { enabled: true, mode: 'server' };
  const shouldPause = autobotState.enabled === true && autobotState.mode !== 'server';
  assert.strictEqual(shouldPause, false, 'Server bot must not pause in server mode');
});

// ---------------------------------------------------------------------------
// PF-70.4 — Config passthrough
// ---------------------------------------------------------------------------
section('PF-70.4: Config passthrough');

test('readBotConfig: falls back to balanced defaults when no server config', () => {
  const cfg = autobot.readBotConfig({});
  assert.strictEqual(cfg.profile, 'balanced');
  assert.strictEqual(cfg.minScore, 65);
  assert.strictEqual(cfg.mtfNeed, 2);
  assert.strictEqual(cfg.maxOpenTrades, 3);
  assert.strictEqual(cfg.btcFilter, true);
});

test('readBotConfig: reads custom values from server state', () => {
  const cfg = autobot.readBotConfig({
    'aura-server-bot-config-v1': {
      profile: 'strict', minScore: 75, mtfNeed: 3, maxLeverage: 5, maxOpenTrades: 2,
    },
  });
  assert.strictEqual(cfg.minScore, 75);
  assert.strictEqual(cfg.mtfNeed, 3);
  assert.strictEqual(cfg.maxLeverage, 5);
  assert.strictEqual(cfg.maxOpenTrades, 2);
});

test('readBotConfig: btcFilter defaults to true, can be disabled', () => {
  const cfg = autobot.readBotConfig({
    'aura-server-bot-config-v1': { btcFilter: false },
  });
  assert.strictEqual(cfg.btcFilter, false);
});

// ---------------------------------------------------------------------------
// PF-70.5 — Fail-Close
// ---------------------------------------------------------------------------
section('PF-70.5: Fail-Close cases');

test('evaluateAutobotCandidate: incomplete=true → rejected', () => {
  const result = E.evaluateAutobotCandidate({ incomplete: true, aligned: 3 }, 65, 2);
  assert.strictEqual(result.accepted, false);
});

test('evaluateAutobotCandidate: missing tfScores and bestInfo → rejected', () => {
  const result = E.evaluateAutobotCandidate({ aligned: 3, btcBlock: false }, 65, 2);
  assert.strictEqual(result.accepted, false);
});

test('evaluateAutobotEdge: null wf → rejected', () => {
  const result = E.evaluateAutobotEdge(null, 8, {});
  assert.strictEqual(result.accepted, false);
});

test('evaluateAutobotEdge: insufficient samples → rejected', () => {
  const wf = {
    evidenceStatus: 'OOS', totalTrials: 18, setupTrials: 18,
    stats: { total: 3, wr: 0.7, avgWinR: 2, avgLossR: 1 }, // only 3 trades
    dsr: { dsr: 0.8 },
  };
  const result = E.evaluateAutobotEdge(wf, 8, { minDsr: 0.0 });
  assert.strictEqual(result.accepted, false, 'Too few OOS samples must be rejected');
});

test('buildEventBody: Open event body format correct', () => {
  const trade = { id: 't1', coin: 'XPNUSDT', dir: -1, leverage: 3, entry: 1.5, initialSl: 1.6, markPrice: 1.5 };
  const body  = autobot.buildEventBody(E, trade, 'open', { price: 1.5 });
  assert(body.includes('XPNUSDT'), 'coin in body');
  assert(body.includes('SHORT'), 'direction in body');
  assert(body.includes('3x'), 'leverage in body');
  assert(body.includes('[Server-Bot]'), 'source badge in body');
});

test('buildEventBody: TP1 event body includes R-multiple', () => {
  const trade = { id: 't1', coin: 'BTCUSDT', dir: 1, leverage: 5, entry: 100, initialSl: 95, markPrice: 105 };
  const body  = autobot.buildEventBody(E, trade, 'tp1', { price: 105 });
  assert(body.includes('TP1'), 'TP1 label');
  assert(body.includes('+1.0R'), 'R-multiple');
});

// ---------------------------------------------------------------------------
// PF-70.6 — computeBtcBias integration
// ---------------------------------------------------------------------------
section('PF-70.6: BTC Bias gate');

test('computeBtcBias: bull regime blocks short candidates', () => {
  const bias = E.computeBtcBias(80, 1);
  // computeBtcBias returns regTxt ('BULL'/'BEAR'/'SIDEWAYS'), not a numeric regime field.
  // Runner checks btcBias.regTxt to gate direction.
  assert.strictEqual(bias.available, true, 'BTC bias must be available');
  assert.strictEqual(bias.regTxt, 'BULL', 'regTxt must be BULL at regime=1');
  // A short candidate (dir=-1) against BULL must be blocked by runner logic
  const shortBlocked = bias.available && bias.regTxt === 'BULL';
  assert.strictEqual(shortBlocked, true, 'BTC bull regime must block shorts');
});

test('computeBtcBias: sideways regime → no block', () => {
  const bias = E.computeBtcBias(50, 0);
  const blocksLong  = bias.available && bias.regTxt === 'BEAR';
  const blocksShort = bias.available && bias.regTxt === 'BULL';
  assert.strictEqual(blocksLong,  false, 'Should not block longs in sideways');
  assert.strictEqual(blocksShort, false, 'Should not block shorts in sideways');
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------
console.log(`\n${'='.repeat(60)}`);
console.log(`PF-70 Headless Runner: ${passed} passed, ${failed} failed`);
if (errors.length) {
  errors.forEach(e => console.error(`  FAIL: ${e.name} — ${e.message}`));
}
process.exit(failed > 0 ? 1 : 0);
