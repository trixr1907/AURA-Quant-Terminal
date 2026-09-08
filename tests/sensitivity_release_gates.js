'use strict';
/**
 * Task 10D — Sensitivity sweep and computed release gates.
 *
 * Runs the purged walk-forward engine over a fixed small parameter neighborhood
 * (time-stop × slippage) on one deterministic synthetic series and reports the
 * dispersion of trade count, expectancy and drawdown plus a confidence interval
 * on out-of-sample expectancy. The release state is COMPUTED from those metrics,
 * never asserted by hand — poor results stay visible and block release.
 *
 * Usage: node tests/sensitivity_release_gates.js
 * Output: one JSON line on stdout. Always exits 0 (it is a report, not a gate).
 */

const fs = require('fs'), vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const b = html.indexOf('//  ==ENGINE_BEGIN==');
const e = html.indexOf('// ==ENGINE_END==', b);
const code = html.slice(b, e);
const sandbox = { console, Float64Array, Date, Math, Array, Object, JSON };
vm.createContext(sandbox);
vm.runInContext(code + '\n__E = { analyze, runWalkForwardBacktest, evaluateTrades };', sandbox);
const { analyze, runWalkForwardBacktest, evaluateTrades } = sandbox.__E;

// Deterministic synthetic series with trend + multi-frequency cycles + volume,
// enough volatility to produce real entries (same generator family as the
// look-ahead metamorphic test).
function synth(n) {
  const candles = [];
  let price = 40000;
  for (let i = 0; i < n; i++) {
    const trend = 0.0008 * Math.sin(i / 60) + 0.00035 * Math.sin(i / 23 + 1.3);
    const wave = 0.015 * Math.sin(i / 9) + 0.008 * Math.sin(i / 4 + 0.7);
    const o = price;
    const c = price * (1 + trend + wave);
    const h = Math.max(o, c) * (1 + 0.005 + 0.004 * Math.abs(Math.sin(i / 5)));
    const l = Math.min(o, c) * (1 - 0.005 - 0.004 * Math.abs(Math.cos(i / 7)));
    const v = 1200 * (1 + 0.6 * Math.sin(i / 11 + 0.2));
    candles.push({ t: i * 3600000, o, h, l, c, v });
    price = c;
  }
  return candles;
}

const N = 1500;
const candles = synth(N);
const A = analyze(candles);

// Small fixed neighborhood — we do NOT re-pick the best after seeing OOS.
const grid = [];
for (const timeStopBars of [12, 15, 18]) {
  for (const slippage of [0, 0.0002, 0.0005]) {
    grid.push({ timeStopBars, slippage, makerFee: 0.0002, takerFee: 0.0006 });
  }
}

const runs = grid.map((opt) => {
  const wf = runWalkForwardBacktest(candles, A, opt);
  const foldExps = wf.folds.map((f) => f.stats.exp);
  return {
    opt,
    total: wf.stats.total,
    exp: wf.stats.exp,
    maxDd: wf.stats.maxDd,
    pf: wf.stats.pf,
    dsr: wf.dsr.dsr,
    foldExps,
  };
});

const mean = (a) => a.reduce((x, y) => x + y, 0) / (a.length || 1);
const std = (a) => {
  if (a.length < 2) return 0;
  const m = mean(a);
  return Math.sqrt(a.reduce((x, y) => x + (y - m) ** 2, 0) / (a.length - 1));
};

// Confidence interval on OOS expectancy from the CENTER run's realized returns.
const center = grid.find((g) => g.timeStopBars === 15 && g.slippage === 0.0002);
const centerWF = runWalkForwardBacktest(candles, A, center);
const rets = centerWF.stats.returns;
const n = rets.length;
const m = centerWF.stats.exp;
const se = n > 1 ? std(rets) / Math.sqrt(n) : Infinity;
const ci = [m - 1.96 * se, m + 1.96 * se];

const totals = runs.map((r) => r.total);
const exps = runs.map((r) => r.exp);
const ddws = runs.map((r) => r.maxDd);
const foldDispersion = std(centerWF.folds.map((f) => f.stats.exp));

// Computed release state (conservative; never auto-promoted to live).
let release = 'PAPER_CANDIDATE';
const reasons = [];
if (n < 30) { release = 'NO_EVIDENCE'; reasons.push(`only ${n} OOS trades (<30)`); }
if (m <= 0) { release = 'NO_EVIDENCE'; reasons.push(`expectancy ${m.toFixed(3)}R <= 0`); }
if (ci[0] < -0.05) { release = 'NO_EVIDENCE'; reasons.push(`CI lower bound ${ci[0].toFixed(3)}R crosses -0.05R`); }
const expSigns = exps.map((x) => Math.sign(x));
const signStable = expSigns.every((s) => s === expSigns[0]);
if (release === 'PAPER_CANDIDATE' && (!signStable || foldDispersion > Math.abs(m))) {
  release = 'RESEARCH_ONLY';
  reasons.push(`unstable across neighborhood (foldDisp ${foldDispersion.toFixed(3)}, exp ${m.toFixed(3)})`);
}

console.log(JSON.stringify({
  series: { n: N, warmup: 235 },
  neighborhood: grid,
  metrics: {
    tradeCount: { min: Math.min(...totals), max: Math.max(...totals), median: totals[4] },
    expectancy: { median: exps[4], spread: [Math.min(...exps), Math.max(...exps)] },
    maxDrawdown: { worst: Math.max(...ddws), spread: [Math.min(...ddws), Math.max(...ddws)] },
    foldDispersion,
    confidenceInterval95: ci,
    oosTrades: n,
  },
  release,
  reasons,
}, null, 2));
