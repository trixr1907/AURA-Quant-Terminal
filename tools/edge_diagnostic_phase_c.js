'use strict';
/**
 * AURA Quant Terminal — Edge Diagnostic Tool (Phase C)
 *
 * Evaluates EXP-024: Selection Objective Reform
 * Baseline: stats.total >= 5 ? stats.exp * Math.sqrt(stats.total) : -Infinity
 * Reform: stats.total >= 2 ? stats.exp * Math.sqrt(stats.total) * (1 - 1 / (1 + stats.total)) : -Infinity
 *
 * Full depth fixture history across BTC 1h, ETH 1h, SOL 1h, XRP 4h, DOGE 4h.
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

function runCustomWalkForward(candles, A, options = {}, objFn, minTrades = 5, K = 4) {
  const n = candles.length;
  const effWarmup = Math.min(SYM.warmup || 235, Math.max(14, n - 60));
  const warmup = effWarmup;
  const minTrainBars = 300;
  const minTrainTrades = minTrades;
  const minTestPerFold = 60;
  const tfMinutes = options.tfMinutes || 60;
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
  for (const lt of [72, 75, 78]) {
    for (const st of [22, 25, 28]) {
      for (const rg of [true, false]) {
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
      const obj = objFn(stats, minTrainTrades);
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

const baselineObj = (stats, minTrades) => {
  return stats.total >= minTrades ? stats.exp * Math.sqrt(stats.total) : -Infinity;
};

const reformObj = (stats, minTrades) => {
  if (stats.total < minTrades) return -Infinity;
  return stats.exp * Math.sqrt(stats.total) * (1 - 1 / (1 + stats.total));
};

console.log('=== RUNNING EXP-024 EVALUATION (FULL FIXTURE DEPTH) ===\n');

const results = [];

for (const fix of GOLDEN_FILES) {
  const p = path.join(GOLDEN_DIR, fix.file);
  const content = fs.readFileSync(p, 'utf8');
  const allCandles = parseCsv(content);
  const A = analyze(allCandles);
  const opts = { ...standardOptions, tfMinutes: fix.tfMin };

  const wfBase = runCustomWalkForward(allCandles, A, opts, baselineObj, 5);
  const wfReform = runCustomWalkForward(allCandles, A, opts, reformObj, 2);

  results.push({
    fix,
    totalBars: allCandles.length,
    base: wfBase,
    reform: wfReform
  });
}

console.log('--- SUMMARY TABLE (EXP-024) ---');
console.log('Fixture | Bars | Base N | Ref N | Base NetExp | Ref NetExp | Delta NetExp | Base WR | Ref WR | Base DSR | Ref DSR | Ref RG Folds');
console.log('---|---|---|---|---|---|---|---|---|---|---|---');

let sumBaseExp = 0, sumRefExp = 0, sumBaseDsr = 0, sumRefDsr = 0;
let totalRgFolds = 0, totalFolds = 0;

for (const r of results) {
  const baseStats = r.base.stats;
  const refStats = r.reform.stats;
  const deltaExp = refStats.exp - baseStats.exp;
  const rgFoldsCount = r.reform.folds.filter(f => f.params.regimeGate === true).length;
  totalRgFolds += rgFoldsCount;
  totalFolds += r.reform.folds.length;
  sumBaseExp += baseStats.exp;
  sumRefExp += refStats.exp;
  const baseDsrVal = r.base.setupDsr.dsr;
  const refDsrVal = r.reform.setupDsr.dsr;
  sumBaseDsr += baseDsrVal;
  sumRefDsr += refDsrVal;

  console.log(`${r.fix.label} | ${r.totalBars} | ${baseStats.total} | ${refStats.total} | ${baseStats.exp.toFixed(3)} R | ${refStats.exp.toFixed(3)} R | ${deltaExp >= 0 ? '+' : ''}${deltaExp.toFixed(3)} R | ${(baseStats.wr*100).toFixed(1)}% | ${(refStats.wr*100).toFixed(1)}% | ${baseDsrVal.toFixed(3)} | ${refDsrVal.toFixed(3)} | ${rgFoldsCount}/4`);
}

const avgBaseExp = sumBaseExp / results.length;
const avgRefExp = sumRefExp / results.length;
const avgDeltaExp = avgRefExp - avgBaseExp;
const avgBaseDsr = sumBaseDsr / results.length;
const avgRefDsr = sumRefDsr / results.length;

console.log(`AVERAGE | - | - | - | ${avgBaseExp.toFixed(3)} R | ${avgRefExp.toFixed(3)} R | ${avgDeltaExp >= 0 ? '+' : ''}${avgDeltaExp.toFixed(3)} R | - | - | ${avgBaseDsr.toFixed(3)} | ${avgRefDsr.toFixed(3)} | ${totalRgFolds}/${totalFolds} (${((totalRgFolds/totalFolds)*100).toFixed(1)}%)`);

console.log('\n--- FOLD-BY-FOLD BREAKDOWN ---');
for (const r of results) {
  console.log(`\n### ${r.fix.label} (${r.fix.tf})`);
  for (let k = 0; k < 4; k++) {
    const fb = r.base.folds[k];
    const fr = r.reform.folds[k];
    console.log(`Fold ${k+1}:`);
    console.log(`  Train Bars: ${fr.trainBars} | Test Bars: ${fr.testBars}`);
    console.log(`  Base: Params={lt:${fb.params.longTh}, st:${fb.params.shortTh}, rg:${fb.params.regimeGate}} | TrainTrades=${fb.trainTrades} | TestTrades=${fb.stats.total} | NetExp=${fb.stats.exp.toFixed(3)} R | PF=${fb.stats.pf.toFixed(2)}`);
    console.log(`  Ref : Params={lt:${fr.params.longTh}, st:${fr.params.shortTh}, rg:${fr.params.regimeGate}} | TrainTrades=${fr.trainTrades} | TestTrades=${fr.stats.total} | NetExp=${fr.stats.exp.toFixed(3)} R | PF=${fr.stats.pf.toFixed(2)}`);
  }
}

console.log('\n--- FOLD 1 GEOMETRY BIAS ANALYSIS (C2) ---');
for (const r of results) {
  const f1 = r.reform.folds[0];
  const totalTrades = r.reform.stats.total;
  const f1TradePct = totalTrades > 0 ? (f1.stats.total / totalTrades * 100) : 0;
  console.log(`${r.fix.label}: Fold 1 TestBars=${f1.testBars}/${r.totalBars} (${((f1.testBars/r.totalBars)*100).toFixed(1)}%) | Fold 1 Trades=${f1.stats.total}/${totalTrades} (${f1TradePct.toFixed(1)}%) | Fold 1 NetExp=${f1.stats.exp.toFixed(3)} R | Overall NetExp=${r.reform.stats.exp.toFixed(3)} R`);
}
