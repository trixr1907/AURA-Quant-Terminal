'use strict';
/**
 * AURA Quant Terminal — Edge Diagnostic Tool (Phase A)
 *
 * Runs non-invasive diagnostic sweeps D1..D6 on the 5 Golden Master fixtures
 * without modifying any strategy or engine code.
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

// 1. Load canonical engine from dashboard
const html = fs.readFileSync(path.join(__dirname, '..', 'Symbiose_Dashboard.html'), 'utf8');
const b = html.indexOf('//  ==ENGINE_BEGIN==');
const e = html.indexOf('// ==ENGINE_END==', b);
const code = html.slice(b, e);
const sandbox = { console, Float64Array, Date, Math, Array, Object, JSON, Number };
vm.createContext(sandbox);
vm.runInContext(code + '\n__E = { analyze, runWalkForwardBacktest, evaluateTrades, regimeOf, calcDSR, dynamicTp1At, SYM };', sandbox);
const { analyze, runWalkForwardBacktest, evaluateTrades, regimeOf, calcDSR, SYM } = sandbox.__E;
const { parseCsv, normalizeTimestamp } = require('../tests/model_evidence_real.js');

const GOLDEN_DIR = path.join(__dirname, '..', 'tests', 'fixtures', 'golden');
const GOLDEN_FILES = [
  { file: 'BTCUSDT_1h.csv', symbol: 'BTC 1h', tf: '1h' },
  { file: 'ETHUSDT_1h.csv', symbol: 'ETH 1h', tf: '1h' },
  { file: 'SOLUSDT_1h.csv', symbol: 'SOL 1h', tf: '1h' },
  { file: 'XRPUSDT_4h.csv', symbol: 'XRP 4h', tf: '4h' },
  { file: 'DOGEUSDT_4h.csv', symbol: 'DOGE 4h', tf: '4h' },
];

const standardOptions = {
  makerFee: 0.0002,
  takerFee: 0.0006,
  slippage: 0.0005,
  timeStopBars: 15,
};

const zeroOptions = {
  makerFee: 0,
  takerFee: 0,
  slippage: 0,
  timeStopBars: 15,
};

const makerOnlyOptions = {
  makerFee: 0.0002,
  takerFee: 0,
  slippage: 0,
  timeStopBars: 15,
};

const takerOnlyOptions = {
  makerFee: 0,
  takerFee: 0.0006,
  slippage: 0,
  timeStopBars: 15,
};

const slipOnlyOptions = {
  makerFee: 0,
  takerFee: 0,
  slippage: 0.0005,
  timeStopBars: 15,
};

const data = [];

for (const item of GOLDEN_FILES) {
  const filePath = path.join(GOLDEN_DIR, item.file);
  const content = fs.readFileSync(filePath, 'utf8');
  const allCandles = parseCsv(content);
  const candles = allCandles.slice(allCandles.length - 1500);
  const A = analyze(candles);

  const wfNet = runWalkForwardBacktest(candles, A, standardOptions);
  const wfGross = runWalkForwardBacktest(candles, A, zeroOptions);
  const wfMaker = runWalkForwardBacktest(candles, A, makerOnlyOptions);
  const wfTaker = runWalkForwardBacktest(candles, A, takerOnlyOptions);
  const wfSlip = runWalkForwardBacktest(candles, A, slipOnlyOptions);

  data.push({
    item,
    candles,
    A,
    wfNet,
    wfGross,
    wfMaker,
    wfTaker,
    wfSlip,
  });
}

console.log('========================================================================================');
console.log('                 AURA EDGE FORSCHUNG PHASE A — DIAGNOSEBERICHT                          ');
console.log('========================================================================================\n');

// -------------------------------------------------------------
// D1: KOSTEN-DEKOMPOSITION
// -------------------------------------------------------------
console.log('### D1: KOSTEN-DEKOMPOSITION (R PRO TRADE)');
console.log('| Fixture | Trades | Gross Exp | Net Exp | Total Cost | Entry Fee (Maker) | Exit Fee (Taker) | Slippage (Maker+Taker) | Kosten-Anteil am Brutto |');
console.log('|---|---|---|---|---|---|---|---|---|');

for (const d of data) {
  const n = d.wfNet.stats.total;
  const grossExp = d.wfGross.stats.exp;
  const netExp = d.wfNet.stats.exp;
  const totalCost = grossExp - netExp;

  const entryFeeCost = grossExp - d.wfMaker.stats.exp;
  const exitFeeCost = grossExp - d.wfTaker.stats.exp;
  const slipCost = grossExp - d.wfSlip.stats.exp;
  const costPctOfGross = (totalCost / grossExp) * 100;

  console.log(`| ${d.item.symbol} | ${n} | +${grossExp.toFixed(3)} R | ${netExp >= 0 ? '+' : ''}${netExp.toFixed(3)} R | ${totalCost.toFixed(3)} R | ${entryFeeCost.toFixed(3)} R | ${exitFeeCost.toFixed(3)} R | ${slipCost.toFixed(3)} R | ${costPctOfGross.toFixed(1)}% |`);
}
console.log('\n');

// -------------------------------------------------------------
// D2: PAYOFF- & WIN-RATE-STRUKTUR
// -------------------------------------------------------------
console.log('### D2: PAYOFF- & WIN-RATE-STRUKTUR');
console.log('| Fixture | Closed Trades | Win Rate | avgWinR | avgLossR | Payoff Ratio | TP1-Hit Rate | Win Bars | Loss Bars | Runner Dur (Bars) |');
console.log('|---|---|---|---|---|---|---|---|---|---|');

for (const d of data) {
  const trades = d.wfNet.oosTrades.filter(t => t.outcome !== 'open');
  const wins = trades.filter(t => t.outcome === 'win');
  const losses = trades.filter(t => t.outcome === 'loss');
  const tp1Hits = trades.filter(t => t.tp1Hit);

  const avgWinR = d.wfNet.stats.avgWinR;
  const avgLossR = d.wfNet.stats.avgLossR;
  const payoff = avgLossR > 0 ? avgWinR / avgLossR : 0;
  const tp1HitRate = (tp1Hits.length / trades.length) * 100;
  const winBars = wins.length ? wins.reduce((s, t) => s + t.bars, 0) / wins.length : 0;
  const lossBars = losses.length ? losses.reduce((s, t) => s + t.bars, 0) / losses.length : 0;
  const runnerTrades = trades.filter(t => t.tp1Hit || t.exitReason === 'supertrend');
  const runnerBars = runnerTrades.length ? runnerTrades.reduce((s, t) => s + t.bars, 0) / runnerTrades.length : 0;

  console.log(`| ${d.item.symbol} | ${trades.length} | ${(d.wfNet.stats.wr * 100).toFixed(1)}% | ${avgWinR.toFixed(2)} R | ${avgLossR.toFixed(2)} R | ${payoff.toFixed(2)}:1 | ${tp1HitRate.toFixed(1)}% | ${winBars.toFixed(1)} | ${lossBars.toFixed(1)} | ${runnerBars.toFixed(1)} |`);
}
console.log('\n');

// -------------------------------------------------------------
// D3: EXIT-GRUND-ZERLEGUNG
// -------------------------------------------------------------
console.log('### D3: EXIT-GRUND-ZERLEGUNG (GESCHLOSSENE TRADES)');
for (const d of data) {
  const trades = d.wfNet.oosTrades.filter(t => t.outcome !== 'open');
  console.log(`#### ${d.item.symbol} (${trades.length} Trades)`);
  console.log('| Exit Reason | Count | % of Trades | Mean Net R | Sum Net R | Win Rate | Mean Duration (Bars) |');
  console.log('|---|---|---|---|---|---|---|');

  const reasons = ['stop', 'breakeven', 'time_stop', 'supertrend'];
  for (const reason of reasons) {
    const subset = trades.filter(t => t.exitReason === reason);
    if (!subset.length) continue;
    const cnt = subset.length;
    const pct = (cnt / trades.length) * 100;
    const sumNet = subset.reduce((s, t) => s + t.rNet, 0);
    const meanNet = sumNet / cnt;
    const subWins = subset.filter(t => t.rNet > 0).length;
    const wr = (subWins / cnt) * 100;
    const meanBars = subset.reduce((s, t) => s + t.bars, 0) / cnt;
    console.log(`| ${reason} | ${cnt} | ${pct.toFixed(1)}% | ${meanNet >= 0 ? '+' : ''}${meanNet.toFixed(3)} R | ${sumNet >= 0 ? '+' : ''}${sumNet.toFixed(2)} R | ${wr.toFixed(1)}% | ${meanBars.toFixed(1)} |`);
  }
  console.log('');
}
console.log('\n');

// -------------------------------------------------------------
// D4: REGIME-BEDINGUNG
// -------------------------------------------------------------
console.log('### D4: REGIME-BEDINGUNG (ENTRY-REGIME)');
console.log('| Fixture | ADX < 20 (Chop) [N, Net R] | ADX 20-30 (Trend) [N, Net R] | ADX > 30 (Strong Trend) [N, Net R] | Squeeze vs Non-Sqz |');
console.log('|---|---|---|---|---|');

for (const d of data) {
  const trades = d.wfNet.oosTrades.filter(t => t.outcome !== 'open');
  const adxLow = [], adxMid = [], adxHigh = [];
  let sqzCount = 0, nonSqzCount = 0;

  for (const t of trades) {
    const entryIdx = t.i;
    const adxVal = d.A.adx ? d.A.adx[entryIdx] : 0;
    const reg = regimeOf(d.A, entryIdx);
    if (reg.isSqz) sqzCount++; else nonSqzCount++;

    if (adxVal < 20) adxLow.push(t.rNet);
    else if (adxVal <= 30) adxMid.push(t.rNet);
    else adxHigh.push(t.rNet);
  }

  const statLow = adxLow.length ? `N=${adxLow.length}, Net=${(adxLow.reduce((a, b) => a + b, 0) / adxLow.length).toFixed(3)} R` : 'N=0';
  const statMid = adxMid.length ? `N=${adxMid.length}, Net=+${(adxMid.reduce((a, b) => a + b, 0) / adxMid.length).toFixed(3)} R` : 'N=0';
  const statHigh = adxHigh.length ? `N=${adxHigh.length}, Net=${(adxHigh.reduce((a, b) => a + b, 0) / adxHigh.length).toFixed(3)} R` : 'N=0';

  console.log(`| ${d.item.symbol} | ${statLow} | ${statMid} | ${statHigh} | Sqz=${sqzCount}, NonSqz=${nonSqzCount} |`);
}
console.log('\n');

// -------------------------------------------------------------
// D5: SAMPLE-SIZE-REALITÄT & DSR-INVERSION
// -------------------------------------------------------------
console.log('### D5: SAMPLE-SIZE-REALITÄT & DSR-INVERSION');

function findSharpeForDSR(targetDSR, n, trials, skew = 0.5, kurt = 4.0) {
  let low = 0.0, high = 3.0;
  for (let iter = 0; iter < 100; iter++) {
    const mid = (low + high) / 2;
    const gamma = 0.5772156649;
    const p1 = Math.max(1e-6, Math.min(1 - 1e-6, 1.0 - 1.0 / trials));
    const p2 = Math.max(1e-6, Math.min(1 - 1e-6, 1.0 - 1.0 / (trials * Math.E)));
    const z1 = normInv(p1), z2 = normInv(p2);
    const srStar = ((1.0 - gamma) * z1 + gamma * z2) / Math.sqrt(n - 1);
    const varSr = (1.0 - skew * mid + ((kurt - 1.0) / 4.0) * (mid ** 2)) / (n - 1);
    const stdSr = Math.sqrt(Math.max(1e-9, varSr));
    const z = (mid - srStar) / stdSr;
    const dsr = normCdf(z);

    if (dsr < targetDSR) {
      low = mid;
    } else {
      high = mid;
    }
  }
  return (low + high) / 2;
}

function normInv(p) {
  const a = [-39.69683028665376, 220.9460984245205, -275.9285104469687, 138.3577518672690, -30.66479806614716, 2.506628277459239];
  const b = [-54.47609879822406, 161.5858368580409, -155.6989798598866, 66.80131188771972, -13.28068155288572];
  const c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783];
  const d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416];
  const q = p < 0.5 ? p : 1 - p;
  let r, x;
  if (q > 0.02425) {
    r = q - 0.5;
    const s = r * r;
    x = r * (((((a[0] * s + a[1]) * s + a[2]) * s + a[3]) * s + a[4]) * s + a[5]) /
      (((((b[0] * s + b[1]) * s + b[2]) * s + b[3]) * s + b[4]) * s + 1);
  } else {
    r = Math.sqrt(-2 * Math.log(q));
    x = (((((c[0] * r + c[1]) * r + c[2]) * r + c[3]) * r + c[4]) * r + c[5]) /
      ((((d[0] * r + d[1]) * r + d[2]) * r + d[3]) * r + 1);
    if (p < 0.5) x = -x;
  }
  return p < 0.5 ? x : -x;
}

function normCdf(x) {
  const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741, a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
  const sign = x < 0 ? -1 : 1;
  const absX = Math.abs(x) / Math.SQRT2;
  const t = 1.0 / (1.0 + p * absX);
  const y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-absX * absX);
  return 0.5 * (1.0 + sign * y);
}

console.log('| n (Trades) | Setup Trials T=18 (DSR ≥ 0.50) | Setup Trials T=18 (DSR ≥ 0.90) | Universe Trials T=8640 (DSR ≥ 0.50) | Universe Trials T=8640 (DSR ≥ 0.90) |');
console.log('|---|---|---|---|---|');
for (const n of [15, 33, 35, 50, 100, 200, 500, 1000]) {
  const sr18_50 = findSharpeForDSR(0.50, n, 18);
  const sr18_90 = findSharpeForDSR(0.90, n, 18);
  const sr8640_50 = findSharpeForDSR(0.50, n, 8640);
  const sr8640_90 = findSharpeForDSR(0.90, n, 8640);
  console.log(`| n = ${n} | SR ≥ ${sr18_50.toFixed(3)} | SR ≥ ${sr18_90.toFixed(3)} | SR ≥ ${sr8640_50.toFixed(3)} | SR ≥ ${sr8640_90.toFixed(3)} |`);
}
console.log('\n');

// -------------------------------------------------------------
// D6: QUERSCHNITTS-KONSISTENZ
// -------------------------------------------------------------
console.log('### D6: QUERSCHNITTS-KONSISTENZ (ZUSAMMENFASSUNG)');
console.log('| Fixture | TF | Trades | Gross Exp | Net Exp | Cost/Trade | PF (Net) | DSR (Setup) | Alpha Status | Dominanter Exit |');
console.log('|---|---|---|---|---|---|---|---|---|---|');
for (const d of data) {
  const n = d.wfNet.stats.total;
  const grossExp = d.wfGross.stats.exp;
  const netExp = d.wfNet.stats.exp;
  const costExp = grossExp - netExp;
  const pf = d.wfNet.stats.pf;
  const dsr = d.wfNet.setupDsr ? d.wfNet.setupDsr.dsr : 0;
  const alphaStatus = grossExp > 0 ? (netExp > 0 ? 'Netto-Positiv (Alpha > Kosten)' : 'Brutto-Positiv (Kosten fressen Alpha)') : 'Kein Alpha';
  const dominantExit = `${d.wfNet.oosTrades.filter(t => t.exitReason === 'stop' && t.outcome !== 'open').length} Stop (${((d.wfNet.oosTrades.filter(t => t.exitReason === 'stop' && t.outcome !== 'open').length / n) * 100).toFixed(0)}%)`;

  console.log(`| ${d.item.symbol} | ${d.item.tf} | ${n} | +${grossExp.toFixed(3)} R | ${netExp >= 0 ? '+' : ''}${netExp.toFixed(3)} R | ${costExp.toFixed(3)} R | ${pf.toFixed(2)} | ${dsr.toFixed(3)} | ${alphaStatus} | ${dominantExit} |`);
}
