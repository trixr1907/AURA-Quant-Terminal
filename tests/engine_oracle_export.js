'use strict';
/**
 * Engine oracle export — dumps deterministic engine outputs for the fixtures so
 * the independent Python reference (tests/reference_backtest.py) can cross-check.
 * Not a test itself; it is invoked BY the Python reference.
 */
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const begin = html.indexOf('//  ==ENGINE_BEGIN==');
const end = html.indexOf('// ==ENGINE_END==');
if (begin < 0 || end <= begin) { console.error('engine markers missing'); process.exit(2); }

const ctx = { console, Float64Array, Int8Array, Uint8Array, Math, Date, isFinite, isNaN, Infinity };
vm.createContext(ctx);
vm.runInContext(
  html.slice(begin, end) + `
  this.__E = { evaluateTrades, reconcileBacktestAccounting, calcDSR, calibrateProbabilities, runWalkForwardBacktest };`,
  ctx
);
const E = ctx.__E;

const trades = JSON.parse(fs.readFileSync('tests/fixtures/backtest/trades.json', 'utf8'));
const returns = JSON.parse(fs.readFileSync('tests/fixtures/backtest/returns.json', 'utf8'));

const out = {};

// 10A — accounting oracle
out.evaluateTrades = E.evaluateTrades(trades);
out.reconcile = E.reconcileBacktestAccounting({ startingEquity: 1000, trades, riskPerR: 100 });

// 10B — DSR oracle
out.dsr = {};
for (const [name, arr] of Object.entries(returns)) {
  out.dsr[name] = E.calcDSR(arr, 18);
}

// 10B — calibration oracle (sample the returned PAVA function at key scores)
const pm = E.calibrateProbabilities(trades);
out.calibration = {};
for (const s of [0, 5, 15, 25, 35, 45, 50, 55, 65, 75, 85, 95, 100]) {
  out.calibration[String(s)] = pm(s);
}

// 10A — fold-boundary oracle (score all zero => no trades, but folds still computed)
const n = 1000;
const candles = [];
for (let i = 0; i < n; i++) candles.push({ t: i * 3600000, o: 100, h: 101, l: 99, c: 100, v: 1 });
const A = { score: new Float64Array(n).fill(50) }; // neutral score => dir 0 everywhere => no entries
const wf = E.runWalkForwardBacktest(candles, A, { makerFee: 0.0002, takerFee: 0.0006, slippage: 0 });
out.folds = wf.folds.map(f => ({ fold: f.fold, trainRange: f.trainRange, testRange: f.testRange }));
out.totalTrials = wf.totalTrials;

console.log(JSON.stringify(out));
