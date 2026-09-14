'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  const start = html.indexOf(`function ${name}(`);
  assert(start >= 0, `missing function ${name}`);
  const bodyStart = html.indexOf('{', start);
  let depth = 0;
  for (let i = bodyStart; i < html.length; i++) {
    if (html[i] === '{') depth++;
    else if (html[i] === '}') {
      depth--;
      if (depth === 0) return html.slice(start, i + 1);
    }
  }
  throw new Error(`unterminated function ${name}`);
}

const ctx = {
  console,
  Number,
  Math,
  Date,
  fmtPx: p => Number(p).toFixed(2),
  fmtDsr: v => Number(v).toFixed(2),
  fmtTrials: v => String(v),
  formatTimeStopDisplay: (bars, tf) => `${bars} Bars (${tf})`,
};
vm.createContext(ctx);
vm.runInContext(`${extractFunction('formatAutobotEntryLog')}; this.formatAutobotEntryLog = formatAutobotEntryLog;`, ctx);

const line = ctx.formatAutobotEntryLog({
  symbol: 'SOLUSDT', dir: 1, leverage: 5, tf: '2h', score: 88,
  setupDsr: 0.8, universeDsr: 0.7, effectiveTrials: 20,
  edge: 0.2, sampleSize: 42, margin: 50, timeStopBars: 12,
  entry: 145.42, signalPrice: 145.50, sl: 140, tp2: 160,
});
assert(line.includes('Entry: 145.42 (Signal 145.50, -0.05%)'), line);

const source = html.slice(
  html.indexOf('async scanAndExecuteOpportunities()'),
  html.indexOf('// Update live trade prices', html.indexOf('async scanAndExecuteOpportunities()')),
);
assert(source.includes('const signalPrice = lastCandle.c;'));
assert(source.includes('const tk = await fetchTicker(c.symbol);'));
assert(
  source.indexOf('const edgeGate = evaluateAutobotEdge') < source.indexOf('const tk = await fetchTicker(c.symbol);'),
  'live ticker must be fetched after the OOS edge gate',
);
assert(
  source.indexOf('const kelly = calcKelly') < source.indexOf('const tk = await fetchTicker(c.symbol);'),
  'live ticker must be fetched after Kelly authorization',
);
assert(
  source.indexOf('const tk = await fetchTicker(c.symbol);') < source.indexOf('const slDist = Math.max(execPrice'),
  'risk levels must be calculated from the just-fetched ticker',
);
assert(source.includes('entry: execPrice'));
assert(source.includes('markPrice: execPrice'));
assert(source.includes('initialSl: sl'));
assert(source.includes('const priceRiskPct = slDist / execPrice;'));
assert(source.includes("addAutobotReject(funnel, 'STALE_CANDLE');"));
assert(source.includes('1.5 * tfMs'));
assert(source.includes('Fallback auf Kerzenschluss'));
assert(source.includes("emitTradeEvent(newTrade, 'open', { price: execPrice, signalPrice })"));

console.log('v1.8.2 browser execution split: ticker entry/risk, fallback warning, stale guard and signal transparency OK');
