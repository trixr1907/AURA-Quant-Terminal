'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function functionSource(name, nextAnchor) {
  const start = html.indexOf(`function ${name}(`);
  if (start === -1) throw new Error(`function ${name} not found`);
  const end = nextAnchor ? html.indexOf(nextAnchor, start) : html.indexOf('\n}\n', start) + 3;
  if (end === -1) throw new Error(`end anchor for ${name} not found`);
  return html.slice(start, end);
}

const context = {
  console,
  setTimeout,
  clearTimeout,
  window: {},
  navigator: {},
  document: {},
  App: { symbol: 'BTCUSDT', chartTF: '1h', data: {} }
};
vm.createContext(context);

// Extract helper functions
try {
  vm.runInContext(functionSource('mapTradingViewInterval', 'function formatTradingViewSymbol'), context);
  vm.runInContext(functionSource('formatTradingViewSymbol', 'function buildTradingViewUrl'), context);
  vm.runInContext(functionSource('buildTradingViewUrl', 'async function openInTradingView'), context);
} catch (e) {
  console.log('Extraction failed (expected in RED phase):', e.message);
}

// 1. Timeframe mapping
assert.strictEqual(context.mapTradingViewInterval('15m'), '15', '15m must map to 15');
assert.strictEqual(context.mapTradingViewInterval('1h'), '60', '1h must map to 60');
assert.strictEqual(context.mapTradingViewInterval('4h'), '240', '4h must map to 240');
assert.strictEqual(context.mapTradingViewInterval('1d'), 'D', '1d must map to D');
assert.strictEqual(context.mapTradingViewInterval('unknown'), '60', 'unknown TF must fallback to 60');

// 2. Symbol formatting
assert.strictEqual(context.formatTradingViewSymbol('BTCUSDT'), 'BITGET:BTCUSDT.P', 'BTCUSDT must default to the AURA Bitget perpetual feed');
assert.strictEqual(context.formatTradingViewSymbol('SOLUSDT'), 'BITGET:SOLUSDT.P', 'SOLUSDT must default to the AURA Bitget perpetual feed');

// 3. URL building
assert.strictEqual(
  context.buildTradingViewUrl('SOLUSDT', '4h'),
  'https://www.tradingview.com/chart/?symbol=BITGET%3ASOLUSDT.P&interval=240',
  'TradingView URL must be properly formatted and encoded'
);
assert.strictEqual(
  context.buildTradingViewUrl('BITGET:SOLUSDT.P', '4h'),
  'https://www.tradingview.com/chart/?symbol=BITGET%3ASOLUSDT.P&interval=240',
  'Already-qualified TradingView symbols must remain intact'
);
assert.strictEqual(
  context.buildTradingViewUrl('BINANCE:BTCUSDT.P', '1h'),
  'https://www.tradingview.com/chart/?symbol=BITGET%3ABTCUSDT.P&interval=60',
  'Symbols must normalize strictly to Bitget perpetual'
);

console.log('PASS TradingView link generation and timeframe mapping');
