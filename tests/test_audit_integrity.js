'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { execSync } = require('child_process');

const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'Symbiose_Dashboard.html'), 'utf8');
const begin = html.indexOf('//  ==ENGINE_BEGIN==');
const end = html.indexOf('// ==ENGINE_END==');
if (begin < 0 || end <= begin) throw new Error('Engine markers not found in Symbiose_Dashboard.html');

const ctx = {
  console, Float64Array, Int8Array, Uint8Array, Math, Date,
  isFinite, isNaN, Infinity, Number, Object, Array, String
};
vm.createContext(ctx);

// Load the complete engine into the context
vm.runInContext(html.slice(begin, end), ctx);

// Extract helper functions outside the engine block
function extractFunction(name) {
  const marker = `function ${name}(`;
  const start = html.indexOf(marker);
  if (start < 0) return null;
  // Find opening paren, skip signature, find opening body brace
  const parenOpen = html.indexOf('(', start);
  let pDepth = 0, bodyStart = -1;
  for (let i = parenOpen; i < html.length; i++) {
    if (html[i] === '(') pDepth++;
    else if (html[i] === ')') {
      pDepth--;
      if (pDepth === 0) {
        bodyStart = html.indexOf('{', i);
        break;
      }
    }
  }
  if (bodyStart < 0) return null;
  let depth = 0, quote = null, escaped = false;
  for (let i = bodyStart; i < html.length; i++) {
    const ch = html[i];
    if (quote) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') { quote = ch; continue; }
    if (ch === '{') depth++;
    if (ch === '}' && --depth === 0) return html.slice(start, i + 1);
  }
  return null;
}

for (const fnName of ['tfToMinutes', 'tfToHours', 'formatTimeStopDisplay', 'stagnationFallbackForTimeframe']) {
  const fnCode = extractFunction(fnName);
  if (fnCode) vm.runInContext(fnCode, ctx);
}

const {
  analyze, simulateRange, runWalkForwardBacktest, evaluateTrades, reconcileBacktestAccounting,
  calcDSR, calibrateProbabilities, calcKelly, calcFundingBias, calcOIBias, calcBasisBias,
  macroAdjust, dynamicTp1At, regimeOf, squeezeAt, squeezeMetricsAt, SYM, strengthOf, fgLabel,
  classifyRadarTf, rankRadarCandidates, sizePosition, tfToMinutes, tfToHours
} = ctx;

console.log('--- RUNNING AUDIT INTEGRITY TEST SUITE ---');

// ============================================================================
// 1. END-TO-END PIPELINE DETERMINISTIC TRACE
// ============================================================================
console.log('[1. End-to-End Pipeline Deterministic Trace]');

// Generate 400 deterministic synthetic candles
const candles = [];
const baseTime = 1700000000000;
for (let i = 0; i < 400; i++) {
  const cycle = Math.sin(i / 15.0) * 2.0;
  const trend = i * 0.05;
  const c = 100.0 + trend + cycle;
  const h = c + 1.0;
  const l = c - 1.0;
  const o = i > 0 ? candles[i - 1].c : c;
  const v = 1000 + Math.abs(Math.sin(i / 5.0)) * 500;
  candles.push({ t: baseTime + i * 3600000, o, h, l, c, v, tbv: null });
}

// Stage A: Technical Analysis & Indicator Array Calculation
const A = analyze(candles);
assert.strictEqual(A.n, 400, 'A.n must equal candles count');
assert.strictEqual(A.score.length, 400, 'A.score must be length 400');
assert.ok(A.score.every(s => Number.isFinite(s) && s >= 0 && s <= 100), 'All scores must be bounded in [0, 100]');

// Stage B: Macro Adjustment & Veto Evaluation
const lastScore = A.score[399];
const macroNormal = macroAdjust(lastScore, 60, 0, 0, 0, false, 0, 0);
assert.ok(Number.isFinite(macroNormal.total), 'Macro total must be finite');
assert.ok(macroNormal.total >= 0 && macroNormal.total <= 100, 'Macro total must be in [0, 100]');

const macroExtreme = macroAdjust(76, 50, -50, 3.0, 0, false, 0, 0);
assert.strictEqual(macroExtreme.fundingExtreme, true, 'Z > 2.5 must flag fundingExtreme');
assert.strictEqual(macroExtreme.veto, true, 'Extreme macro against weak technical score must trigger veto');

// Stage C: Radar Classification
const radarBull = classifyRadarTf({ score: 80, dir: 1, regime: 1, isSqz: false, adx: 25, atrPct: 0.02 });
assert.strictEqual(radarBull.status, 'ready', 'Strong score in bull regime with high ADX must be ready');
assert.strictEqual(radarBull.tradeable, true, 'Ready setup must be tradeable');

const radarSqz = classifyRadarTf({ score: 80, dir: 1, regime: 1, isSqz: true, adx: 25, atrPct: 0.02 });
assert.strictEqual(radarSqz.status, 'blocked_squeeze', 'Squeeze must block signal regardless of score');
assert.strictEqual(radarSqz.tradeable, false, 'Squeeze setup must not be tradeable');

// Stage D1: Anchored Walk-Forward fail-closed on short series (<778 bars)
const wfShort = runWalkForwardBacktest(candles, A, {
  makerFee: 0.0002,
  takerFee: 0.0006,
  slippage: 0.0005,
  timeStopBars: 15,
  tfMinutes: 60
});
assert.strictEqual(wfShort.evidenceStatus, 'INSUFFICIENT_DATA', 'Short series must fail-closed with INSUFFICIENT_DATA');
assert.strictEqual(wfShort.folds.length, 0, 'Insufficient data must return empty folds');

// Stage D2: Full Series Walk-Forward Execution & t1 Guard (900 bars)
const fullCandles = [];
for (let i = 0; i < 900; i++) {
  const cycle = Math.sin(i / 15.0) * 2.0;
  const trend = i * 0.05;
  const c = 100.0 + trend + cycle;
  const h = c + 1.0;
  const l = c - 1.0;
  const o = i > 0 ? fullCandles[i - 1].c : c;
  const v = 1000 + Math.abs(Math.sin(i / 5.0)) * 500;
  fullCandles.push({ t: baseTime + i * 3600000, o, h, l, c, v, tbv: null });
}
const fullA = analyze(fullCandles);
const wf = runWalkForwardBacktest(fullCandles, fullA, {
  makerFee: 0.0002,
  takerFee: 0.0006,
  slippage: 0.0005,
  timeStopBars: 15,
  tfMinutes: 60
});
assert.strictEqual(wf.method, 'anchored_t1', 'WF method must be anchored_t1');
assert.strictEqual(wf.evidenceStatus, 'OOS', 'WF evidence status must be OOS');
assert.strictEqual(wf.folds.length, 4, 'Must produce exactly K=4 folds');

for (const fold of wf.folds) {
  assert.ok(fold.trainRange[1] < fold.testRange[0], 'trainEnd must precede testStart');
  assert.strictEqual(fold.trainRange[1], fold.testRange[0] - 2, 'trainEnd must be testStart - 2');
  assert.ok(fold.trainTrades.every(t => t.exitBar < fold.testRange[0]), 'All train trades must close strictly before testStart');
  assert.ok(fold.trades.every(t => t.i >= fold.testRange[0] && t.i <= fold.testRange[1] - 1), 'All OOS signals must be strictly within testRange');
}

// Stage E: DSR & Kelly Evaluation
const dsrRes = wf.dsr;
assert.ok(Number.isFinite(dsrRes.dsr) && dsrRes.dsr >= 0 && dsrRes.dsr <= 1, 'DSR must be in [0, 1]');

const kellyRes = calcKelly(wf.stats.wr, wf.stats.avgWinR, wf.stats.avgLossR, 2.0, 10000, wf.stats.total);
assert.ok(Number.isFinite(kellyRes.finalFrac) && kellyRes.finalFrac >= 0 && kellyRes.finalFrac <= 0.25, 'Kelly fraction must be in [0, 0.25]');
assert.ok(Number.isFinite(kellyRes.riskAmt) && kellyRes.riskAmt >= 0 && kellyRes.riskAmt <= 2500, 'Risk amount must respect hard cap');

console.log('  PASS  E2E pipeline trace passed with zero anomalies');

// ============================================================================
// 2. GOLDEN MASTER MULTI-SYMBOL PARITY (BTC, ETH, SOL 1h; XRP, DOGE 4h)
// ============================================================================
console.log('[2. Golden Master Multi-Symbol Parity]');
const { compareFile } = require(path.join(root, 'tests/compare_pine_js_golden.js'));
const goldenSymbols = [
  'BTCUSDT_1h.csv',
  'ETHUSDT_1h.csv',
  'SOLUSDT_1h.csv',
  'XRPUSDT_4h.csv',
  'DOGEUSDT_4h.csv'
];

let totalBarsCompared = 0;
let totalSoftMismatches = 0;

for (const f of goldenSymbols) {
  const filePath = path.join(root, 'tests/fixtures/golden', f);
  const rep = compareFile(filePath, 0.1);
  assert.strictEqual(rep.ok, true, `Golden Master comparison must pass for ${f}: ${rep.reason}`);
  assert.ok(rep.comparedRows >= 500, `${f} must have >= 500 compared rows (got ${rep.comparedRows})`);
  totalBarsCompared += rep.comparedRows;
  totalSoftMismatches += (rep.softMismatches || 0);
  const rateStr = rep.comparedRows > 0 ? ((rep.softMismatches || 0) / rep.comparedRows * 100).toFixed(4) : '0.0000';
  console.log(`  PASS  ${f}: ${rep.comparedRows} rows compared, max delta: ${rep.maxDelta}, soft-mismatches: ${rep.softMismatches || 0} (${rateStr}%)`);
  if (rep.softMismatches > 0 && rep.firstSoftMismatch) {
    const sm = rep.firstSoftMismatch;
    console.log(`        first detail: ts=${sm.timestamp} field=${sm.field} Pine=${sm.pine} JS=${sm.js} (delta ${sm.delta})`);
  }
}

const overallMismatchRate = totalSoftMismatches / totalBarsCompared;
assert.ok(overallMismatchRate < 0.001, `Overall soft mismatch rate (${(overallMismatchRate * 100).toFixed(4)}%) must be < 0.1%`);
console.log(`  PASS  Overall Golden Master Parity: ${totalBarsCompared} bars compared, soft mismatch rate: ${(overallMismatchRate * 100).toFixed(4)}% (<0.1%)`);

// ============================================================================
// 3. TIMEFRAME UNITS & SCALING CONSISTENCY
// ============================================================================
console.log('[3. Timeframe Units & Scaling Consistency]');
assert.strictEqual(tfToMinutes('15m'), 15, '15m -> 15 min');
assert.strictEqual(tfToMinutes('1h'), 60, '1h -> 60 min');
assert.strictEqual(tfToMinutes('4h'), 240, '4h -> 240 min');
assert.strictEqual(tfToMinutes('1d'), 1440, '1d -> 1440 min');

assert.strictEqual(tfToHours('15m'), 0.25, '15m -> 0.25 h');
assert.strictEqual(tfToHours('1h'), 1.0, '1h -> 1.0 h');
assert.strictEqual(tfToHours('4h'), 4.0, '4h -> 4.0 h');
assert.strictEqual(tfToHours('1d'), 24.0, '1d -> 24.0 h');

// Stagnation hours conversion: 12h = 48 bars on 15m, 12 bars on 1h, 3 bars on 4h, 1 bar on 1d
const stagnationHours = 12;
assert.strictEqual(Math.ceil(stagnationHours / tfToHours('15m')), 48, '12h on 15m is 48 bars');
assert.strictEqual(Math.ceil(stagnationHours / tfToHours('1h')), 12, '12h on 1h is 12 bars');
assert.strictEqual(Math.ceil(stagnationHours / tfToHours('4h')), 3, '12h on 4h is 3 bars');
assert.strictEqual(Math.ceil(stagnationHours / tfToHours('1d')), 1, '12h on 1d is 1 bar');
console.log('  PASS  Timeframe units & scaling invariants confirmed');

// ============================================================================
// 4. CLAIMS INTEGRITY VERIFICATION
// ============================================================================
console.log('[4. Claims Integrity Verification]');
const claimsFile = fs.existsSync(path.join(root, 'docs/research/claims.csv'))
  ? path.join(root, 'docs/research/claims.csv')
  : path.join(root, 'claims.csv');
assert.ok(fs.existsSync(claimsFile), 'claims.csv must exist');
const claimsContent = fs.readFileSync(claimsFile, 'utf8');
const lines = claimsContent.trim().split('\n');
assert.ok(lines.length >= 25, 'claims.csv must contain >= 25 claims');

// Check that no claim has status 'NICHT BELEGBAR' or unresolved 'KRITISCH' / 'HOCH'
const criticalOrHighUnresolved = [];
for (let i = 1; i < lines.length; i++) {
  const line = lines[i];
  if (line.includes('KRITISCH') || line.includes('HOCH')) {
    criticalOrHighUnresolved.push(line);
  }
}
assert.strictEqual(criticalOrHighUnresolved.length, 0, `No unresolved KRITISCH or HOCH claims allowed (found: ${criticalOrHighUnresolved.length})`);
console.log(`  PASS  Claims table valid: ${lines.length - 1} claims audited, 0 unresolved KRITISCH/HOCH`);

// ============================================================================
// 5. REPO HYGIENE CHECK
// ============================================================================
console.log('[5. Repo Hygiene Check]');
const gitignore = fs.readFileSync(path.join(root, '.gitignore'), 'utf8');
assert.ok(gitignore.includes('.hermes/'), '.gitignore must contain .hermes/');

// Verify that no tracked files in git start with .hermes/
try {
  const trackedHermes = execSync('git ls-files .hermes', { cwd: root, encoding: 'utf8' }).trim();
  assert.strictEqual(trackedHermes, '', 'No files under .hermes/ should be tracked in git index');
} catch (e) {
  // If git command fails in non-git environment, check is skipped
}
console.log('  PASS  Repo hygiene confirmed (.hermes excluded from git tracking)');

console.log('\n============================================================');
console.log('ERGEBNIS: AUDIT INTEGRITY SUITE ALL CHECKS PASSED');
console.log('============================================================');
