'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const crypto = require('crypto');

const htmlPath = process.argv[2];
if (!htmlPath) throw new Error('usage: node aura_pwf_snapshot.js <dashboard.html>');
const ROOT = '/home/ivo/projects/AURA_Quant_Terminal';
const html = fs.readFileSync(htmlPath, 'utf8');
const begin = html.indexOf('//  ==ENGINE_BEGIN==');
const end = html.indexOf('// ==ENGINE_END==');
if (begin < 0 || end <= begin) throw new Error('engine markers missing');

const ctx = { console, Float64Array, Int8Array, Uint8Array, Math, Date, Array, Object, JSON, isFinite, isNaN, Infinity };
vm.createContext(ctx);
vm.runInContext(html.slice(begin, end) + '\nthis.__E={analyze,runWalkForwardBacktest,SYM};', ctx);
const E = ctx.__E;

function splitCsvLine(line) {
  const out = [];
  let cur = '';
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (quoted && line[i + 1] === '"') { cur += '"'; i++; }
      else quoted = !quoted;
    } else if (ch === ',' && !quoted) {
      out.push(cur);
      cur = '';
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out;
}

function loadCandles(file, lastN = 1500) {
  const lines = fs.readFileSync(file, 'utf8').trim().split(/\r?\n/);
  const header = splitCsvLine(lines[0]).map(x => x.trim().toLowerCase());
  const idx = {
    t: header.indexOf('time'), o: header.indexOf('open'), h: header.indexOf('high'),
    l: header.indexOf('low'), c: header.indexOf('close'), v: header.indexOf('volume')
  };
  for (const [key, value] of Object.entries(idx)) {
    if (value < 0) throw new Error(`missing CSV column ${key} in ${file}`);
  }
  return lines.slice(1).slice(-lastN).map(line => {
    const x = splitCsvLine(line);
    let t = Number(x[idx.t]);
    if (t < 1e10) t *= 1000;
    return { t, o: +x[idx.o], h: +x[idx.h], l: +x[idx.l], c: +x[idx.c], v: +x[idx.v] };
  });
}

function num(value, digits = 6) {
  return Number.isFinite(value) ? +value.toFixed(digits) : (value ?? null);
}

function rangeHours(range, tfMinutes) {
  if (!Array.isArray(range) || range.length < 2) return null;
  return num((range[1] - range[0] + 1) * tfMinutes / 60, 2);
}

function summarizeFixture(file, tfMinutes) {
  const candles = loadCandles(path.join(ROOT, 'tests/fixtures/golden', file));
  const A = E.analyze(candles);
  const wf = E.runWalkForwardBacktest(candles, A, {
    makerFee: 0.0002,
    takerFee: 0.0006,
    slippage: 0.0005,
    timeStopBars: E.SYM.timeStopBars,
    tfMinutes
  });
  const stats = wf.stats || {};
  const oosTrades = Array.isArray(wf.oosTrades) ? wf.oosTrades : [];
  return {
    file,
    tfMinutes,
    bars: candles.length,
    evidenceStatus: wf.evidenceStatus || null,
    totalTrials: wf.totalTrials ?? null,
    oosClosedTrades: stats.total ?? oosTrades.filter(t => t.outcome !== 'open' && t.exitBar != null).length,
    expectancyR: num(stats.exp),
    winRate: num(stats.wr),
    profitFactor: num(stats.pf),
    maxDrawdownR: num(stats.maxDd),
    dsr: num(wf.dsr && wf.dsr.dsr),
    folds: (wf.folds || []).map(f => ({
      fold: f.fold,
      trainRange: f.trainRange || null,
      testRange: f.testRange || null,
      trainBars: f.trainBars ?? (f.trainRange ? f.trainRange[1] - f.trainRange[0] + 1 : null),
      trainHours: num(f.trainHours ?? rangeHours(f.trainRange, tfMinutes), 2),
      testHours: num(f.testHours ?? rangeHours(f.testRange, tfMinutes), 2),
      trainClosed: Array.isArray(f.trainTrades) ? f.trainTrades.length : null,
      purgedByT1: f.purgedByT1 ?? null,
      censoredTest: f.censoredTest ?? null,
      selectionObjective: num(f.selectionObjective),
      testClosed: f.stats ? f.stats.total : null,
      testExpectancyR: num(f.stats && f.stats.exp),
      selected: f.params ? {
        longTh: f.params.longTh,
        shortTh: f.params.shortTh,
        regimeGate: f.params.regimeGate,
        timeStopBars: f.params.timeStopBars
      } : null
    }))
  };
}

const fixtures = [
  ['BTCUSDT_1h.csv', 60],
  ['ETHUSDT_1h.csv', 60],
  ['SOLUSDT_1h.csv', 60],
  ['XRPUSDT_4h.csv', 240],
  ['DOGEUSDT_4h.csv', 240]
];

console.log(JSON.stringify({
  dashboard: path.basename(htmlPath),
  sha256: crypto.createHash('sha256').update(html).digest('hex'),
  fixtures: fixtures.map(([file, tfMinutes]) => summarizeFixture(file, tfMinutes))
}, null, 2));
