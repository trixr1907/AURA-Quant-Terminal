'use strict';
/**
 * AURA Quant Terminal — Edge Diagnostic Tool (Phase B)
 *
 * Runs non-invasive experiments B1 (Gated Grid on 1500 bars) and
 * B2 (Full Depth Fixture History on Gated vs Ungated).
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
vm.runInContext(code + '\n__E = { analyze, runWalkForwardBacktest, evaluateTrades, regimeOf, calcDSR, simulateRange, calibrateProbabilities, SYM };', sandbox);
const { analyze, runWalkForwardBacktest, evaluateTrades, regimeOf, calcDSR, simulateRange, calibrateProbabilities, SYM } = sandbox.__E;
const { parseCsv } = require('../tests/model_evidence_real.js');

const GOLDEN_DIR = path.join(__dirname, '..', 'tests', 'fixtures', 'golden');
const GOLDEN_FILES = [
  { file: 'BTCUSDT_1h.csv', symbol: 'BTCUSDT', label: 'BTC 1h', tf: '1h', tfMin: 60 },
  { file: 'ETHUSDT_1h.csv', symbol: 'ETHUSDT', label: 'ETH 1h', tf: '1h', tfMin: 60 },
  { file: 'SOLUSDT_1h.csv', symbol: 'SOLUSDT', label: 'SOL 1h', tf: '1h', tfMin: 60 },
  { file: 'XRPUSDT_4h.csv', symbol: 'XRPUSDT', label: 'XRP 4h', tf: '4h', tfMin: 240 },
  { file: 'DOGEUSDT_4h.csv', symbol: 'DOGEUSDT', label: 'DOGE 4h', tf: '4h', tfMin: 240 },
];

const standardOptions = {
  makerFee: 0.0002,
  takerFee: 0.0006,
  slippage: 0.0005,
  timeStopBars: 15,
};

/**
 * Custom Walk-Forward Runner with custom paramGrid constraint
 * (e.g. force regimeGate: true or standard).
 */
function runCustomWalkForward(candles, A, options = {}, forcedRegimeGate = null, K = 4) {
  const n = candles.length;
  const effWarmup = Math.min(SYM.warmup || 235, Math.max(14, n - 60));
  const warmup = effWarmup;
  const minTrainBars = 300;
  const minTrainTrades = 5;
  const minTestPerFold = 60;
  const tfMinutes = options.tfMinutes || 60;
  const trialMultiplier = options.trialMultiplier || 1;
  const firstTestStart = warmup + minTrainBars + 1;
  const lastSignalIdx = n - 2;
  const testableBars = Math.max(0, lastSignalIdx - firstTestStart + 1);

  if (testableBars < minTestPerFold * K) {
    const oosTrades = [];
    const stats = evaluateTrades(oosTrades);
    return { oosTrades, stats, dsr: calcDSR(stats.returns, 1), folds: [], totalTrials: 0 };
  }

  const paramGrid = [];
  const rGates = forcedRegimeGate !== null ? [forcedRegimeGate] : [true, false];
  for (const lt of [72, 75, 78]) {
    for (const st of [22, 25, 28]) {
      for (const rg of rGates) {
        paramGrid.push({
          longTh: lt, shortTh: st, regimeGate: rg, atrSl: SYM.atrSl || 1.5,
          cooldown: SYM.cooldown || 10, maxHold: SYM.maxHold || 200,
          timeStopBars: options.timeStopBars || SYM.timeStopBars,
          makerFee: options.makerFee, takerFee: options.takerFee, slippage: options.slippage
        });
      }
    }
  }

  const testFoldSize = Math.floor(testableBars / K);
  const trainStart = warmup;
  const allOosTrades = [];
  const foldReports = [];

  for (let k = 0; k < K; k++) {
    const testStart = firstTestStart + k * testFoldSize;
    const testEnd = k === K - 1 ? n - 2 : testStart + testFoldSize - 1;
    const trainEnd = testStart - 2;
    const trainExitBoundary = testStart - 1;
    let bestParams = paramGrid[0];
    let bestScore = -Infinity;
    let selectedTrainTrades = [];
    let selectedPurgedByT1 = 0;

    for (const params of paramGrid) {
      const simulated = simulateRange(candles, A, trainStart, trainEnd, params, null, trainExitBoundary);
      const trainTrades = simulated.filter(t => t.exitBar != null && t.exitBar < testStart);
      const purgedByT1 = simulated.length - trainTrades.length;
      const stats = evaluateTrades(trainTrades);
      const obj = stats.total >= minTrainTrades ? stats.exp * Math.sqrt(stats.total) : -Infinity;
      if (obj > bestScore) {
        bestScore = obj;
        bestParams = params;
        selectedTrainTrades = trainTrades;
        selectedPurgedByT1 = purgedByT1;
      }
    }

    if (bestScore === -Infinity) {
      const simulated = simulateRange(candles, A, trainStart, trainEnd, bestParams, null, trainExitBoundary);
      selectedTrainTrades = simulated.filter(t => t.exitBar != null && t.exitBar < testStart);
      selectedPurgedByT1 = simulated.length - selectedTrainTrades.length;
    }

    const oosTrades = simulateRange(candles, A, testStart, testEnd - 1, bestParams, k + 1, testEnd);
    const foldStats = evaluateTrades(oosTrades);
    const trainBars = trainEnd - trainStart + 1;
    const testBars = testEnd - testStart + 1;
    foldReports.push({
      fold: k + 1,
      trainRange: [trainStart, trainEnd],
      testRange: [testStart, testEnd],
      trainBars,
      trainTrades: selectedTrainTrades.length,
      purgedByT1: selectedPurgedByT1,
      selectionObjective: Number.isFinite(bestScore) ? bestScore : null,
      params: bestParams,
      stats: foldStats,
      trades: oosTrades,
    });
    allOosTrades.push(...oosTrades);
  }

  const aggStats = evaluateTrades(allOosTrades);
  const setupTrials = paramGrid.length;
  const totalTrials = paramGrid.length * trialMultiplier;
  const setupDsr = calcDSR(aggStats.returns, setupTrials);
  const universeDsr = calcDSR(aggStats.returns, totalTrials);

  return {
    oosTrades: allOosTrades,
    stats: aggStats,
    dsr: universeDsr,
    setupDsr,
    universeDsr,
    setupTrials,
    paramGridLength: paramGrid.length,
    folds: foldReports,
    probMap: calibrateProbabilities(allOosTrades),
  };
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
    if (dsr < targetDSR) low = mid; else high = mid;
  }
  return (low + high) / 2;
}

console.log('========================================================================================');
console.log('                 AURA EDGE FORSCHUNG PHASE B — EXPERIMENTBERICHT                        ');
console.log('========================================================================================\n');

// -------------------------------------------------------------
// EXPERIMENT B1: GATED VARIANT (1500 BARS)
// -------------------------------------------------------------
console.log('### EXPERIMENT B1: GATED-VARIANTE (REGIMEGATE: TRUE ERZWUNGEN, 1500 BARS)\n');

const b1Results = [];

for (const item of GOLDEN_FILES) {
  const filePath = path.join(GOLDEN_DIR, item.file);
  const content = fs.readFileSync(filePath, 'utf8');
  const allCandles = parseCsv(content);
  const candles = allCandles.slice(allCandles.length - 1500);
  const A = analyze(candles);

  const wfBaseline = runCustomWalkForward(candles, A, { ...standardOptions, tfMinutes: item.tfMin }, null);
  const wfGated = runCustomWalkForward(candles, A, { ...standardOptions, tfMinutes: item.tfMin }, true);

  b1Results.push({
    item,
    wfBaseline,
    wfGated,
  });
}

console.log('#### B1.1: Aggregierte Gegenüberstellung (1500 Bars: Baseline ungated vs. Gated)');
console.log('| Fixture | TF | Baseline Trades | Gated Trades | Baseline Net Exp | Gated Net Exp | Δ Net Exp | Baseline WR | Gated WR | Baseline DSR | Gated DSR | Status |');
console.log('|---|---|---|---|---|---|---|---|---|---|---|---|');

let improvedCount = 0;
let baseSumExp = 0, gatedSumExp = 0;
let baseSumDsr = 0, gatedSumDsr = 0;

for (const r of b1Results) {
  const base = r.wfBaseline.stats;
  const gated = r.wfGated.stats;
  const baseExp = base.exp;
  const gatedExp = gated.exp;
  const deltaExp = gatedExp - baseExp;
  const baseDsr = r.wfBaseline.setupDsr.dsr;
  const gatedDsr = r.wfGated.setupDsr.dsr;

  baseSumExp += baseExp;
  gatedSumExp += gatedExp;
  baseSumDsr += baseDsr;
  gatedSumDsr += gatedDsr;

  const isImproved = deltaExp > 0;
  if (isImproved) improvedCount++;

  console.log(`| ${r.item.label} | ${r.item.tf} | ${base.total} | ${gated.total} | ${baseExp >= 0 ? '+' : ''}${baseExp.toFixed(3)} R | ${gatedExp >= 0 ? '+' : ''}${gatedExp.toFixed(3)} R | ${deltaExp >= 0 ? '+' : ''}${deltaExp.toFixed(3)} R | ${(base.wr * 100).toFixed(1)}% | ${(gated.wr * 100).toFixed(1)}% | ${baseDsr.toFixed(3)} | ${gatedDsr.toFixed(3)} | ${isImproved ? 'VERBESSERT' : 'SCHLECHTER'} |`);
}

const baseMeanExp = baseSumExp / b1Results.length;
const gatedMeanExp = gatedSumExp / b1Results.length;
const baseMeanDsr = baseSumDsr / b1Results.length;
const gatedMeanDsr = gatedSumDsr / b1Results.length;

console.log(`| **GESAMT Ø** | — | — | — | **${baseMeanExp >= 0 ? '+' : ''}${baseMeanExp.toFixed(3)} R** | **${gatedMeanExp >= 0 ? '+' : ''}${gatedMeanExp.toFixed(3)} R** | **${(gatedMeanExp - baseMeanExp) >= 0 ? '+' : ''}${(gatedMeanExp - baseMeanExp).toFixed(3)} R** | — | — | **${baseMeanDsr.toFixed(3)}** | **${gatedMeanDsr.toFixed(3)}** | **${improvedCount}/5 Assets** |\n`);

console.log('#### B1.2: Fold-für-Fold Detailaufschlüsselung (1500 Bars)');
for (const r of b1Results) {
  console.log(`\n**${r.item.label} (${r.item.tf}) — Fold Breakdown:**`);
  console.log('| Fold | Test Range | Baseline Params (rg) | Baseline Trades [Win/Loss] | Baseline Exp | Gated Params (rg) | Gated Trades [Win/Loss] | Gated Exp | Δ Exp |');
  console.log('|---|---|---|---|---|---|---|---|---|');

  for (let k = 0; k < 4; k++) {
    const bf = r.wfBaseline.folds[k];
    const gf = r.wfGated.folds[k];
    const bParams = `${bf.params.longTh}/${bf.params.shortTh} (rg=${bf.params.regimeGate})`;
    const gParams = `${gf.params.longTh}/${gf.params.shortTh} (rg=${gf.params.regimeGate})`;
    const bExp = bf.stats.exp;
    const gExp = gf.stats.exp;
    const dExp = gExp - bExp;

    console.log(`| Fold ${k + 1} | [${bf.testRange[0]}, ${bf.testRange[1]}] | ${bParams} | ${bf.stats.total} [${bf.stats.wins}/${bf.stats.losses}] | ${bExp >= 0 ? '+' : ''}${bExp.toFixed(3)} R | ${gParams} | ${gf.stats.total} [${gf.stats.wins}/${gf.stats.losses}] | ${gExp >= 0 ? '+' : ''}${gExp.toFixed(3)} R | ${dExp >= 0 ? '+' : ''}${dExp.toFixed(3)} R |`);
  }
}

// -------------------------------------------------------------
// EXPERIMENT B2: VOLLE TIEFE DER FIXTURES
// -------------------------------------------------------------
console.log('\n\n========================================================================================');
console.log('### EXPERIMENT B2: STICHPROBE AUF VOLLE FIXTURE-TIEFE (BIS ZU 14.773 BARS)\n');

const b2Results = [];

for (const item of GOLDEN_FILES) {
  const filePath = path.join(GOLDEN_DIR, item.file);
  const content = fs.readFileSync(filePath, 'utf8');
  const allCandles = parseCsv(content);
  const candles = allCandles; // Full depth!
  const A = analyze(candles);

  const wfBaselineFull = runCustomWalkForward(candles, A, { ...standardOptions, tfMinutes: item.tfMin }, null);
  const wfGatedFull = runCustomWalkForward(candles, A, { ...standardOptions, tfMinutes: item.tfMin }, true);

  b2Results.push({
    item,
    totalBars: candles.length,
    wfBaselineFull,
    wfGatedFull,
  });
}

console.log('#### B2.1: Volle Fixture-Tiefe (Baseline vs. Gated)');
console.log('| Fixture | Total Bars | Base Trades | Gated Trades | Base Net Exp | Gated Net Exp | Δ Net Exp | Base DSR | Gated DSR | SR für DSR ≥ 0.50 (n_gated) | SR für DSR ≥ 0.90 (n_gated) |');
console.log('|---|---|---|---|---|---|---|---|---|---|---|');

let b2ImprovedCount = 0;
let b2BaseSumExp = 0, b2GatedSumExp = 0;
let b2BaseSumDsr = 0, b2GatedSumDsr = 0;

for (const r of b2Results) {
  const base = r.wfBaselineFull.stats;
  const gated = r.wfGatedFull.stats;
  const baseExp = base.exp;
  const gatedExp = gated.exp;
  const deltaExp = gatedExp - baseExp;
  const baseDsr = r.wfBaselineFull.setupDsr.dsr;
  const gatedDsr = r.wfGatedFull.setupDsr.dsr;
  const nGated = gated.total;

  const srReq50 = findSharpeForDSR(0.50, Math.max(3, nGated), r.wfGatedFull.paramGridLength);
  const srReq90 = findSharpeForDSR(0.90, Math.max(3, nGated), r.wfGatedFull.paramGridLength);

  b2BaseSumExp += baseExp;
  b2GatedSumExp += gatedExp;
  b2BaseSumDsr += baseDsr;
  b2GatedSumDsr += gatedDsr;

  const isImproved = deltaExp > 0;
  if (isImproved) b2ImprovedCount++;

  console.log(`| ${r.item.label} | ${r.totalBars} | ${base.total} | ${gated.total} | ${baseExp >= 0 ? '+' : ''}${baseExp.toFixed(3)} R | ${gatedExp >= 0 ? '+' : ''}${gatedExp.toFixed(3)} R | ${deltaExp >= 0 ? '+' : ''}${deltaExp.toFixed(3)} R | ${baseDsr.toFixed(3)} | ${gatedDsr.toFixed(3)} | SR ≥ ${srReq50.toFixed(3)} | SR ≥ ${srReq90.toFixed(3)} |`);
}

const b2BaseMeanExp = b2BaseSumExp / b2Results.length;
const b2GatedMeanExp = b2GatedSumExp / b2Results.length;
const b2BaseMeanDsr = b2BaseSumDsr / b2Results.length;
const b2GatedMeanDsr = b2GatedSumDsr / b2Results.length;

console.log(`| **GESAMT Ø** | — | — | — | **${b2BaseMeanExp >= 0 ? '+' : ''}${b2BaseMeanExp.toFixed(3)} R** | **${b2GatedMeanExp >= 0 ? '+' : ''}${b2GatedMeanExp.toFixed(3)} R** | **${(b2GatedMeanExp - b2BaseMeanExp) >= 0 ? '+' : ''}${(b2GatedMeanExp - b2BaseMeanExp).toFixed(3)} R** | **${b2BaseMeanDsr.toFixed(3)}** | **${b2GatedMeanDsr.toFixed(3)}** | — | — |\n`);

console.log('#### B2.2: Volle Tiefe Fold-Breakdown');
for (const r of b2Results) {
  console.log(`\n**${r.item.label} (${r.totalBars} Bars) — Fold Breakdown:**`);
  console.log('| Fold | Test Range | Base Params (rg) | Base Trades [Win/Loss] | Base Exp | Gated Params (rg) | Gated Trades [Win/Loss] | Gated Exp | Δ Exp |');
  console.log('|---|---|---|---|---|---|---|---|---|');

  for (let k = 0; k < 4; k++) {
    const bf = r.wfBaselineFull.folds[k];
    const gf = r.wfGatedFull.folds[k];
    const bParams = `${bf.params.longTh}/${bf.params.shortTh} (rg=${bf.params.regimeGate})`;
    const gParams = `${gf.params.longTh}/${gf.params.shortTh} (rg=${gf.params.regimeGate})`;
    const bExp = bf.stats.exp;
    const gExp = gf.stats.exp;
    const dExp = gExp - bExp;

    console.log(`| Fold ${k + 1} | [${bf.testRange[0]}, ${bf.testRange[1]}] | ${bParams} | ${bf.stats.total} [${bf.stats.wins}/${bf.stats.losses}] | ${bExp >= 0 ? '+' : ''}${bExp.toFixed(3)} R | ${gParams} | ${gf.stats.total} [${gf.stats.wins}/${gf.stats.losses}] | ${gExp >= 0 ? '+' : ''}${gExp.toFixed(3)} R | ${dExp >= 0 ? '+' : ''}${dExp.toFixed(3)} R |`);
  }
}
