'use strict';
/**
 * Look-ahead metamorphic tests for the AURA engine (Task 10C).
 *
 * Metamorphic property under test: appending FUTURE bars must never change
 *   (a) historical indicator values / signals,
 *   (b) completed trade outcomes within a shared window,
 *   (c) a fold's train-fold parameter selection.
 * A causal engine is invariant under future-bar extension; a look-ahead bug is not.
 *
 * Run:  node tests/test_lookahead_metamorphic.js
 */
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const begin = html.indexOf('//  ==ENGINE_BEGIN==');
const end = html.indexOf('// ==ENGINE_END==');
assert(begin >= 0 && end > begin, 'engine markers missing');

const ctx = { console, Float64Array, Int8Array, Uint8Array, Math, Date, isFinite, isNaN, Infinity };
vm.createContext(ctx);
vm.runInContext(
  html.slice(begin, end) + `
  this.__E = { analyze, simulateRange, runWalkForwardBacktest, evaluateTrades, SYM };`,
  ctx
);
const { analyze, simulateRange, runWalkForwardBacktest, SYM } = ctx.__E;

// Deterministic synthetic candles: identical prefix for any n.
function synthCandles(n) {
  const out = [];
  let price = 50000;
  for (let i = 0; i < n; i++) {
    const trend = 0.0006 * i;
    const wave = 0.02 * Math.sin(i / 12) + 0.012 * Math.sin(i / 5 + 1.7);
    const o = price * (1 + 0.01 * Math.sin(i / 8));
    const c = price * (1 + trend + wave);
    const h = Math.max(o, c) * (1 + 0.004 + 0.003 * Math.abs(Math.sin(i / 3)));
    const l = Math.min(o, c) * (1 - 0.004 - 0.003 * Math.abs(Math.cos(i / 7)));
    const v = 1000 * (1 + 0.5 * Math.sin(i / 9 + 0.3));
    out.push({ t: i * 3600000, o, h, l, c, v });
    price = c;
  }
  return out;
}

const N = 800, M = 200;
const base = synthCandles(N);
const full = synthCandles(N + M);
const A1 = analyze(base);
const A2 = analyze(full);

// Shared prefix candles must be bit-identical by construction.
for (let i = 0; i < N; i++) assert.strictEqual(base[i].c, full[i].c, `prefix candle ${i}`);

const warmup = Math.min(SYM.warmup || 235, Math.max(14, N - 60));

let passed = 0;
function test(name, fn) {
  fn();
  passed++;
  console.log(`  ok  ${name}`);
}

// (a) Indicator causality: no historical value may repaint on future bars.
test('analyze: historical score/ATR/SuperTrend unchanged by future bars', () => {
  let changed = 0;
  for (let i = warmup; i < N; i++) {
    if (A1.score[i] !== A2.score[i]) changed++;
    if (A1.atr[i] !== A2.atr[i]) changed++;
    if (A1.stDir[i] !== A2.stDir[i]) changed++;
    if (A1.stLine[i] !== A2.stLine[i]) changed++;
    if (A1.e50[i] !== A2.e50[i]) changed++;
    if (A1.e200[i] !== A2.e200[i]) changed++;
  }
  assert.strictEqual(changed, 0, `${changed} historical indicator values repainted`);
});

// (b) Completed trades within a shared window are identical.
test('simulateRange: completed trades identical under future extension', () => {
  const params = { longTh: SYM.longTh, shortTh: SYM.shortTh, regimeGate: true, makerFee: 0.0002, takerFee: 0.0006, slippage: 0, timeStopBars: SYM.timeStopBars, atrSl: SYM.atrSl, cooldown: SYM.cooldown, maxHold: 40 };
  // endIdx leaves maxHold margin so every trade closes inside the shared window.
  const endIdx = N - 2 - 40;
  const t1 = simulateRange(base, A1, warmup, endIdx, params);
  const t2 = simulateRange(full, A2, warmup, endIdx, params);
  assert.strictEqual(t1.length, t2.length, 'trade count differs');
  for (let k = 0; k < t1.length; k++) assert.deepStrictEqual(t1[k], t2[k], `trade ${k} differs`);
});

// (c) A fold's train-fold selection must not react to its own test-fold bars.
test('runWalkForwardBacktest: train-fold params invariant to test-fold mutation', () => {
  const mkOpts = () => ({ makerFee: 0.0002, takerFee: 0.0006, slippage: 0 });
  const wf0 = runWalkForwardBacktest(base, A1, mkOpts());
  assert(wf0.folds.length >= 1, 'no folds');

  // Mutate fold 1's test range only (bars after fold 1's trainEnd).
  const [testStart, testEnd] = wf0.folds[0].testRange;
  const mutated = base.slice();
  for (let i = testStart; i <= testEnd; i++) {
    mutated[i] = { t: base[i].t, o: 1e9, h: 1e9 + 1, l: 1e9 - 1, c: 1e9, v: 1e9 };
  }
  const wf1 = runWalkForwardBacktest(mutated, analyze(mutated), mkOpts());

  // Fold 1 params (chosen on train [warmup..trainEnd]) must be unchanged.
  assert.deepStrictEqual(wf1.folds[0].params, wf0.folds[0].params,
    'fold 1 train selection changed by its own test-fold bars (look-ahead)');
});

console.log(`\nLOOK-AHEAD METAMORPHIC: ${passed} PASSED`);
