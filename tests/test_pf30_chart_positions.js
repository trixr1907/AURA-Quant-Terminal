'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  const start = html.indexOf(`function ${name}(`);
  assert(start >= 0, `${name} source missing`);
  const brace = html.indexOf('{', start);
  let depth = 0;
  for (let i = brace; i < html.length; i++) {
    if (html[i] === '{') depth++;
    else if (html[i] === '}' && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error(`${name} source incomplete`);
}

const sources = [
  extractFunction('collectChartPositionTrades'),
  extractFunction('chartPositionLevels'),
  extractFunction('drawChartPositionLevels'),
  extractFunction('buildTradingViewChartUrl'),
  extractFunction('openTradingViewChart'),
].join('\n');

const calls = [];
const sandbox = {
  Number,
  String,
  Set,
  Map,
  encodeURIComponent,
  fmtPx: value => Number(value).toFixed(2),
  fmtP: value => Number(value).toFixed(2),
  window: {
    open: (...args) => {
      calls.push(args);
      return { opener: 'unsafe' };
    },
  },
};
vm.createContext(sandbox);
vm.runInContext(`${sources}
this.collectChartPositionTrades = collectChartPositionTrades;
this.drawChartPositionLevels = drawChartPositionLevels;
this.buildTradingViewChartUrl = buildTradingViewChartUrl;
this.openTradingViewChart = openTradingViewChart;`, sandbox);

const manualTrades = [
  { id: 'manual-1', coin: 'ALCHUSDT', dir: 1, leverage: 6, entry: 10, currentSl: 9, tp: 12, tp2: 13, tp3: 14 },
  { id: 'elsewhere', coin: 'BTCUSDT', dir: -1, leverage: 3, entry: 100, currentSl: 105, tp: 90 },
  { id: 'invalid', coin: 'ALCHUSDT', dir: 1, entry: 'bad', currentSl: 9, tp: 12 },
];
const autobotTrades = [
  { id: 'manual-1', coin: 'ALCHUSDT', dir: 1, leverage: 6, entry: 10, currentSl: 9, tp: 12 },
  { id: 'bot-2', coin: 'ALCHUSDT', dir: -1, leverage: 4, entry: 20, currentSl: 22, tp1: 18, tp2: 16, tp3: 14 },
];

const collected = sandbox.collectChartPositionTrades('ALCHUSDT', manualTrades, autobotTrades);
assert.strictEqual(collected.focused.length, 2, 'collects focused manual/autobot positions and de-duplicates IDs');
assert.strictEqual(collected.otherCount, 1, 'reports active positions on other symbols');
assert.strictEqual(collected.focused[0].id, 'manual-1');

const drawCalls = [];
const ctx = {
  save: () => drawCalls.push(['save']),
  restore: () => drawCalls.push(['restore']),
  beginPath: () => drawCalls.push(['beginPath']),
  moveTo: (...args) => drawCalls.push(['moveTo', ...args]),
  lineTo: (...args) => drawCalls.push(['lineTo', ...args]),
  stroke: () => drawCalls.push(['stroke']),
  fillText: (...args) => drawCalls.push(['fillText', ...args]),
  setLineDash: (...args) => drawCalls.push(['setLineDash', ...args]),
  set strokeStyle(value) { drawCalls.push(['strokeStyle', value]); },
  set fillStyle(value) { drawCalls.push(['fillStyle', value]); },
  set lineWidth(value) { drawCalls.push(['lineWidth', value]); },
  set font(value) { drawCalls.push(['font', value]); },
};
sandbox.drawChartPositionLevels(ctx, collected.focused, { left: 10, right: 210, top: 5, bottom: 105, yAt: price => 105 - price * 5 });
assert(drawCalls.some(call => call[0] === 'moveTo' && call[1] === 10), 'levels span current plot width');
assert(drawCalls.some(call => call[0] === 'lineTo' && call[1] === 210), 'levels span current plot width');
assert(drawCalls.some(call => call[0] === 'fillText' && String(call[1]).includes('10.00')), 'levels receive formatted price labels');
assert(drawCalls.some(call => call[0] === 'strokeStyle' && call[1] === '#ef4444'), 'SL is red');
assert(drawCalls.some(call => call[0] === 'strokeStyle' && call[1] === '#22c55e'), 'TP is green');

for (const symbol of ['BTCUSDT', 'ALCHUSDT', 'ethusdt']) {
  const url = sandbox.buildTradingViewChartUrl(symbol);
  const parsed = new URL(url);
  assert.strictEqual(parsed.origin + parsed.pathname, 'https://www.tradingview.com/chart/');
  assert.strictEqual(parsed.searchParams.get('symbol'), `BITGET:${symbol.toUpperCase()}.P`);
}
const opened = sandbox.openTradingViewChart('ALCHUSDT');
assert.strictEqual(opened.opener, null, 'new tab opener is cleared defensively');
assert.deepStrictEqual(calls[0], ['https://www.tradingview.com/chart/?symbol=BITGET%3AALCHUSDT.P', '_blank', 'noopener,noreferrer']);

assert(!/\/api\/open-tradingview|launchTradingViewDesktop/.test(html), 'active dashboard source must not retain desktop relay path');
console.log('PASS PF-30 chart position helpers and direct TradingView web link');
