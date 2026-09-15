
'use strict';

const assert = require('assert');
const fs = require('fs');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  let start = html.indexOf(`async function ${name}(`);
  if (start < 0) start = html.indexOf(`function ${name}(`);
  assert(start >= 0, `${name} source missing`);
  const brace = html.indexOf('{', start);
  let depth = 0;
  for (let i = brace; i < html.length; i++) {
    if (html[i] === '{') depth++;
    else if (html[i] === '}' && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error(`${name} source incomplete`);
}

const loadSource = extractFunction('loadChartData');
const resetSource = extractFunction('resetMarketState');

assert(/chartLoad/.test(html), 'PF-32 chart load state is required');
assert(/Erneut laden/.test(html), 'PF-32 retry button text is required');
assert(/unref\(\)/.test(html), 'PF-32 retry timer must unref when supported');
assert(!/App\.data\.chart = null;\n  App\.data\.candles = null;/.test(resetSource), 'reset must preserve the stale chart until a focused load succeeds');

const App = {
  gen: 4,
  symbol: 'ETHUSDT',
  chartTF: '1h',
  data: { chart: { n: 120, last: { c: 100 } }, candles: [{ t: 1 }], wf: null, bt: [], probMap: null },
  fees: {},
  timeStopBars: 15,
  status: { bin: '' },
  chartLoad: { status: 'loading', attempt: 0, target: { symbol: 'ETHUSDT', tf: '1h' } },
};
let calls = 0;
let scheduled;
const timer = { unrefCalled: false, unref() { this.unrefCalled = true; } };
const context = {
  App,
  fetchKlines: async () => {
    calls++;
    if (calls === 1) throw new Error('temporary focused chart failure');
    return { candles: [{ t: 2 }], source: 'BITGET' };
  },
  analyze: candles => ({ n: 120, last: { c: candles[0].t } }),
  runWalkForwardBacktest: () => ({ oosTrades: [], probMap: {} }),
  tfToMinutes: () => 60,
  bitgetContracts: async () => ({ takerFee: 0, makerFee: 0 }),
  resolveSlippage: value => value || 0.0005,
  fetchTicker: async () => ({ price: 101 }),
  setTimeout: fn => { scheduled = fn; return timer; },
  clearTimeout: () => {},
  $: () => null,
};

const helperSources = ['isCurrentChartLoad', 'scheduleFocusedChartRetry', 'renderChartLoadState'].map(extractFunction).join('\n');
const contextKeys = Object.keys(context);
const loadChartDataFactory = new Function(...contextKeys, `${helperSources}\n${loadSource}\nreturn loadChartData;`);
const loadChartData = loadChartDataFactory(...Object.values(context));
(async () => {
  await assert.rejects(loadChartData(0), /temporary focused chart failure/);
  assert(App.data.chart && App.data.chart.n === 120, 'old valid chart must remain visible after first focused load failure');
  assert.strictEqual(App.chartLoad.status, 'error', 'first focused failure must expose chart error state');
  assert.strictEqual(App.chartLoad.message, 'Chart konnte nicht geladen werden. Erneut laden.');
  assert(scheduled, 'bounded retry must be scheduled');
  assert(timer.unrefCalled, 'retry timer must be unrefed when available');
  await loadChartData(1);
  assert.strictEqual(App.chartLoad.status, 'ready', 'same generation/symbol/TF retry success must clear chart error');
  assert.strictEqual(App.data.candles[0].t, 2, 'retry success must replace the stale chart data');
  assert(/retryFocusedChartLoad/.test(html), 'manual retry must call the same focused chart load path');
  console.log('PASS PF-32 focus-chart stale-while-revalidate retry contract');
})().catch(error => {
  console.error(`FAIL PF-32: ${error.message}`);
  process.exitCode = 1;
});
