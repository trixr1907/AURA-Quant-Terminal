'use strict';
/**
 * AURA Quant Terminal — Edge Diagnostic Tool (Phase D)
 *
 * Evaluates EXP-025: Fair Fold-1 Geometry Fix on Full Fixture Depth
 * 1h: minTrainBars = 2000 bars (~83 days)
 * 4h: minTrainBars = 500 bars (~83 days)
 *
 * Evaluates both Baseline (18-grid with EXP-024 reform objective)
 * and Gated-Only (9-grid with forced regimeGate: true).
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const html = fs.readFileSync(path.join(__dirname, '../Symbiose_Dashboard.html'), 'utf8');
const b = html.indexOf('//  ==ENGINE_BEGIN==');
const e = html.indexOf('// ==ENGINE_END==', b);
const code = html.slice(b, e);

const sandbox = { console, Float64Array, Date, Math, Array, Object, JSON, Number };
vm.createContext(sandbox);
vm.runInContext(code + '\n__E = { analyze, runWalkForwardBacktest, evaluateTrades, regimeOf, calcDSR, simulateRange, calibrateProbabilities, SYM };', sandbox);
const { analyze, runWalkForwardBacktest, evaluateTrades, regimeOf, calcDSR, simulateRange, calibrateProbabilities, SYM } = sandbox.__E;
const { parseCsv } = require('../tests/model_evidence_real.js');
const { fairFoldBoundaries } = require('./fold_geometry.js');

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

function reformObj(stats, minTrades = 2) {
  if (stats.total < minTrades) return -Infinity;
  return stats.exp * Math.sqrt(stats.total) * (1 - 1 / (1 + stats.total));
}

function runFairWalkForward(candles, A, options = {}, forcedRegimeGate = null, K = 4) {
  const n = candles.length;
  const effWarmup = Math.min(SYM.warmup || 235, Math.max(14, n - 60));
  const warmup = effWarmup;
  const tfMinutes = options.tfMinutes || 60;
  // EXP-025 Fair initial training window: 2000 bars for 1h, 500 bars for 4h
  const geometry = fairFoldBoundaries(n, tfMinutes, K, warmup);
  const minTrainBars = geometry.minTrainBars;
  const minTrainTrades = 2;
  const minTestPerFold = 60;
  const trialMultiplier = options.trialMultiplier || 1;
  const firstTestStart = warmup + minTrainBars + 1;
  const lastSignalIdx = n - 2;
  const testableBars = Math.max(0, lastSignalIdx - firstTestStart + 1);

  if (testableBars < minTestPerFold * K) {
    const oosTrades = [];
    const stats = evaluateTrades(oosTrades);
    return { oosTrades, stats, dsr: calcDSR(stats.returns, 1), setupDsr: calcDSR(stats.returns, 18), folds: [], totalTrials: 0 };
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

    // Also check max available gated train trades to test Kriterium 2
    let maxGatedTrainTrades = 0;

    for (const params of paramGrid) {
      const simulated = simulateRange(candles, A, trainStart, trainEnd, params, null, trainExitBoundary);
      const trainTrades = simulated.filter(t => t.exitBar != null && t.exitBar < testStart);
      const purgedByT1 = simulated.length - trainTrades.length;
      const stats = evaluateTrades(trainTrades);
      const obj = reformObj(stats, minTrainTrades);

      if (params.regimeGate === true && trainTrades.length > maxGatedTrainTrades) {
        maxGatedTrainTrades = trainTrades.length;
      }

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
      trainHours: trainBars * tfMinutes / 60,
      testBars,
      testHours: testBars * tfMinutes / 60,
      trainTrades: selectedTrainTrades.length,
      maxGatedTrainTrades,
      purgedByT1: selectedPurgedByT1,
      censoredTest: oosTrades.filter(t => t.exitBar == null).length,
      selectionObjective: Number.isFinite(bestScore) ? bestScore : null,
      params: bestParams,
      stats: foldStats,
      trades: oosTrades
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
    totalTrials,
    folds: foldReports,
    probMap: calibrateProbabilities(allOosTrades),
    evidenceStatus: 'OOS',
    method: 'anchored_t1'
  };
}

console.log('=== RUNNING EXP-025 EVALUATION (FAIR FOLD-1 GEOMETRY) ===\n');

const results = [];

for (const fix of GOLDEN_FILES) {
  const p = path.join(GOLDEN_DIR, fix.file);
  const content = fs.readFileSync(p, 'utf8');
  const allCandles = parseCsv(content);
  const A = analyze(allCandles);
  const opts = { ...standardOptions, tfMinutes: fix.tfMin };

  const wfBase = runFairWalkForward(allCandles, A, opts, null);
  const wfGated = runFairWalkForward(allCandles, A, opts, true);

  results.push({
    fix,
    totalBars: allCandles.length,
    base: wfBase,
    gated: wfGated
  });
}

console.log('--- SUMMARY TABLE (EXP-025 FAIR GEOMETRY: BASELINE VS GATED) ---');
console.log('Fixture | Bars | Base N | Gated N | Base NetExp | Gated NetExp | Δ NetExp | Base WR | Gated WR | Base DSR | Gated DSR | Base RG Folds');
console.log('---|---|---|---|---|---|---|---|---|---|---|---');

let sumBaseExp = 0, sumGatedExp = 0, sumBaseDsr = 0, sumGatedDsr = 0;
let totalRgFolds = 0, totalFolds = 0;

for (const r of results) {
  const baseStats = r.base.stats;
  const gatedStats = r.gated.stats;
  const deltaExp = gatedStats.exp - baseStats.exp;
  const rgFoldsCount = r.base.folds.filter(f => f.params.regimeGate === true).length;
  totalRgFolds += rgFoldsCount;
  totalFolds += r.base.folds.length;
  sumBaseExp += baseStats.exp;
  sumGatedExp += gatedStats.exp;
  const baseDsrVal = r.base.setupDsr.dsr;
  const gatedDsrVal = r.gated.setupDsr.dsr;
  sumBaseDsr += baseDsrVal;
  sumGatedDsr += gatedDsrVal;

  console.log(`${r.fix.label} | ${r.totalBars} | ${baseStats.total} | ${gatedStats.total} | ${baseStats.exp.toFixed(3)} R | ${gatedStats.exp.toFixed(3)} R | ${deltaExp >= 0 ? '+' : ''}${deltaExp.toFixed(3)} R | ${(baseStats.wr*100).toFixed(1)}% | ${(gatedStats.wr*100).toFixed(1)}% | ${baseDsrVal.toFixed(3)} | ${gatedDsrVal.toFixed(3)} | ${rgFoldsCount}/4`);
}

const avgBaseExp = sumBaseExp / results.length;
const avgGatedExp = sumGatedExp / results.length;
const avgDeltaExp = avgGatedExp - avgBaseExp;
const avgBaseDsr = sumBaseDsr / results.length;
const avgGatedDsr = sumGatedDsr / results.length;

  const allGatedReturns = results.flatMap(r => r.gated.stats.returns);
  const aggregatedGatedDsr = calcDSR(allGatedReturns, 18).dsr;

  console.log(`AVERAGE | - | - | - | ${avgBaseExp.toFixed(3)} R | ${avgGatedExp.toFixed(3)} R | ${avgDeltaExp >= 0 ? '+' : ''}${avgDeltaExp.toFixed(3)} R | - | - | ${avgBaseDsr.toFixed(3)} | ${avgGatedDsr.toFixed(3)} | ${totalRgFolds}/${totalFolds} (${((totalRgFolds/totalFolds)*100).toFixed(1)}%)`);
  console.log(`POOLED GATED DSR (all ${allGatedReturns.length} OOS returns, T=18): ${aggregatedGatedDsr.toFixed(3)}`);

console.log('\n--- FOLD 1 SHARE & GEOMETRY VERIFICATION (KRITERIEN 1 & 2) ---');
for (const r of results) {
  const f1 = r.base.folds[0];
  const totalTrades = r.base.stats.total;
  const f1TradePct = totalTrades > 0 ? (f1.stats.total / totalTrades * 100) : 0;
  const allFoldsTrainOk = r.base.folds.every(f => f.maxGatedTrainTrades >= 5);
  console.log(`${r.fix.label}: Fold 1 TestBars=${f1.testBars}/${r.totalBars} (${((f1.testBars/r.totalBars)*100).toFixed(1)}%) | Fold 1 Trades=${f1.stats.total}/${totalTrades} (${f1TradePct.toFixed(1)}%) | Fold 1 Gated Train Capacity >= 5: ${f1.maxGatedTrainTrades >= 5 ? 'YES (' + f1.maxGatedTrainTrades + ')' : 'NO (' + f1.maxGatedTrainTrades + ')'}`);
}

console.log('\n--- FOLD-BY-FOLD DETAILS (BASELINE WITH FAIR GEOMETRY) ---');
for (const r of results) {
  console.log(`\n### ${r.fix.label} (${r.fix.tf})`);
  for (let k = 0; k < 4; k++) {
    const fb = r.base.folds[k];
    const fg = r.gated.folds[k];
    console.log(`Fold ${k+1}:`);
    console.log(`  Train Bars: ${fb.trainBars} | Test Bars: ${fb.testBars}`);
    console.log(`  Base : Params={lt:${fb.params.longTh}, st:${fb.params.shortTh}, rg:${fb.params.regimeGate}} | TrainTrades=${fb.trainTrades} (MaxGatedTrain=${fb.maxGatedTrainTrades}) | TestTrades=${fb.stats.total} | NetExp=${fb.stats.exp.toFixed(3)} R | PF=${fb.stats.pf.toFixed(2)}`);
    console.log(`  Gated: Params={lt:${fg.params.longTh}, st:${fg.params.shortTh}, rg:${fg.params.regimeGate}} | TrainTrades=${fg.trainTrades} | TestTrades=${fg.stats.total} | NetExp=${fg.stats.exp.toFixed(3)} R | PF=${fg.stats.pf.toFixed(2)}`);
  }
}
