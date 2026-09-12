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
  document: { createElement: () => ({ style: {}, click: () => {} }), body: { appendChild: () => {}, removeChild: () => {} } },
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
  fallbackCopy: (text) => { calls.clipboard.push(text); },
  fetch: async (url) => {
    calls.fetch.push(url);
    return { ok: true, json: async () => ({ ok: true }) };
  }
};

vm.createContext(context);
for (const name of [
  'generateTradingViewPositionScript',
  'launchTradingViewDesktop',
  'copyTvPositionToolForTrade',
  'findActiveTradeForPine',
  'getTradingViewPineText',
  'openInTradingView'
]) {
  vm.runInContext(`${getFunction(name)}; this.${name} = ${name};`, context);
}

const longTrade = {
  coin: 'ETHUSDT', dir: 1, entry: 3200.0, sl: 3120.0,
  tp: 3360.0, tp2: 3440.0, tp3: 3600.0, leverage: 10, remainingMargin: 150
};

const shortTrade = {
  coin: 'SOLUSDT', dir: -1, entry: 102.5, currentSl: 105.0,
  tp: 97.5, tp2: 95.0, tp3: 90.0, leverage: 8, remainingMargin: 100
};

(async () => {
  // 1. Verify 1:1 Standalone Position Tool for Active Trades
  const longScript = context.generateTradingViewPositionScript(longTrade);
  assert(longScript.includes('//@version=6'));
  assert(longScript.includes('AURA LONG Position — ETHUSDT'));
  assert(longScript.includes('posDir    = input.string("LONG"'));
  assert(longScript.includes('box.new(x1, profitTop, x2, profitBot'));
  assert(longScript.includes('#089981')); // Green profit zone
  assert(longScript.includes('#f23645')); // Red loss zone
  assert(longScript.includes('43000517002')); // Long position reference

  const shortScript = context.generateTradingViewPositionScript(shortTrade);
  assert(shortScript.includes('//@version=6'));
  assert(shortScript.includes('AURA SHORT Position — SOLUSDT'));
  assert(shortScript.includes('posDir    = input.string("SHORT"'));
  assert(shortScript.includes('43000516992')); // Short position reference

  // 2. Verify click action on active trade card
  await context.copyTvPositionToolForTrade(shortTrade, null);
  assert.equal(calls.clipboard.length, 1);
  assert(calls.clipboard[0].includes('AURA SHORT Position — SOLUSDT'));
  calls.clipboard.length = 0;

  // 3. Verify top button copies pure indicator Pine script
  const result = await context.openInTradingView('BTCUSDT', '1h', null, null);
  assert.equal(result.desktopOpened, true);
  assert.equal(result.pineCopied, true);
  assert(calls.clipboard[0].includes('indicator("AURA — Confluence Signal-System"'));

  console.log('PASS TradingView 1:1 Position Tool and Indicator bridge verified');
})().catch((error) => {
  console.error(error.stack || error);
  process.exit(1);
});
