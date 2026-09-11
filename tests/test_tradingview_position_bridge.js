'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const pine = fs.readFileSync('Symbiose_Signal_System_v1.pine', 'utf8');

function getFunction(name) {
  const asyncMarker = `async function ${name}(`;
  const syncMarker = `function ${name}(`;
  const asyncStart = html.indexOf(asyncMarker);
  const start = asyncStart >= 0 ? asyncStart : html.indexOf(syncMarker);
  if (start < 0) throw new Error(`${name} not found`);
  let depth = 0;
  let bodyStarted = false;
  for (let i = start; i < html.length; i += 1) {
    if (html[i] === '{') { depth += 1; bodyStarted = true; }
    if (html[i] === '}') {
      depth -= 1;
      if (bodyStarted && depth === 0) return html.slice(start, i + 1);
    }
  }
  throw new Error(`${name} is incomplete`);
}

const calls = { clipboard: [], fetch: [], opened: [] };
const context = {
  console,
  Number,
  Math,
  String,
  Array,
  Object,
  Promise,
  setTimeout: (fn) => fn(),
  navigator: { clipboard: { writeText: async (text) => calls.clipboard.push(text) } },
  window: { open: (url) => { calls.opened.push(url); return { opener: 'initial' }; } },
  App: {
    symbol: 'BTCUSDT', chartTF: '1h', tradingView: {}, leverage: 10,
    equity: 1000, riskPct: 5, data: { live: {} }
  },
  preloadTradingViewPine: async () => pine,
  Autobot: { trades: [], equity: 1000, riskPerTradePct: 5 },
  tradingViewPineText: pine,
  tradingViewPineLoad: null,
  relayBase: () => 'http://127.0.0.1:8787',
  buildTradingViewUrl: (symbol, tf) => `https://www.tradingview.com/chart/?symbol=BITGET:${symbol}.P&interval=${tf}`,
  buildTradingViewDesktopUrl: (symbol, tf) => `tradingview://chart/?symbol=BITGET:${symbol}.P&interval=${tf}`,
  fallbackCopy: () => { throw new Error('fallback copy should not be needed'); },
  fetch: async (url) => {
    calls.fetch.push(url);
    return { ok: true, json: async () => ({ ok: true }) };
  }
};

vm.createContext(context);
for (const name of ['buildCustomTradingViewPine', 'findActiveTradeForPine', 'getTradingViewPineText', 'openInTradingView']) {
  vm.runInContext(`${getFunction(name)}; this.${name} = ${name};`, context);
}

const candidate = {
  coin: 'SOLUSDT', dir: -1, entry: 102.5, sl: 105.0,
  tp1: 100.0, tp2: 97.5, tp3: 92.5, leverage: 8
};

(async () => {
  const result = await context.openInTradingView('SOLUSDT', '1h', null, candidate);
  assert.equal(result.desktopOpened, true, 'relay must open TradingView Desktop');
  assert.equal(result.pineCopied, true, 'custom Pine must reach the clipboard');
  assert.equal(calls.clipboard.length, 1, 'exactly one Pine script must be copied');
  const customized = calls.clipboard[0];
  assert(customized.includes('fcMode     = input.string("Custom"'));
  assert(customized.includes('fcDir      = input.string("Short"'));
  assert(customized.includes('fcEntry    = input.float(102.5000'));
  assert(customized.includes('fcSl       = input.float(105.0000'));
  assert(customized.includes('fcTp2      = input.float(97.5000'));
  assert(customized.includes('max_boxes_count=500'));
  assert(customized.includes('fcBoxProfit := box.new'));
  assert(customized.includes('fcBoxLoss   := box.new'));
  calls.clipboard.length = 0;
  context.tradingViewPineText = '';
  const preloadResult = await context.openInTradingView('SOLUSDT', '1h', null, candidate);
  assert.equal(preloadResult.pineCopied, true, 'a click must still copy Pine when the preload cache is initially empty');
  assert.equal(calls.clipboard.length, 1, 'the freshly preloaded Pine script must be copied');
  console.log('PASS TradingView bridge copies a custom position overlay before desktop launch');
})().catch((error) => {
  console.error(error.stack || error);
  process.exit(1);
});
