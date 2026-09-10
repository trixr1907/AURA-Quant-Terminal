'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const start = html.indexOf('function switchToAsset(');
const end = html.indexOf('\nfunction copySetupToClipboard(', start);
assert(start >= 0 && end > start, 'switchToAsset source not found');
const switchSource = html.slice(start, end);

const rowBindingStart = html.indexOf("list.querySelectorAll('.radar-row')");
const rowBindingEnd = html.indexOf("list.querySelectorAll('.rr-pill')", rowBindingStart);
assert(rowBindingStart >= 0 && rowBindingEnd > rowBindingStart, 'radar row click binding not found');
const rowBindingSource = html.slice(rowBindingStart, rowBindingEnd);

assert(
  rowBindingSource.includes('switchToAsset(sym, tf)'),
  'radar row clicks must use the canonical asset-switch transaction'
);
assert(
  !rowBindingSource.includes('App.symbol = sym'),
  'radar row clicks must not partially mutate focus state before switching'
);

const pillBindingStart = rowBindingEnd;
const pillBindingEnd = html.indexOf('\n}', pillBindingStart);
assert(pillBindingEnd > pillBindingStart, 'radar timeframe-pill click binding not found');
const pillBindingSource = html.slice(pillBindingStart, pillBindingEnd);
assert(
  pillBindingSource.includes('switchToAsset(sym, tf)'),
  'radar timeframe clicks must use the canonical asset-switch transaction'
);
assert(
  !pillBindingSource.includes('App.symbol = sym'),
  'radar timeframe clicks must not partially mutate focus state before switching'
);

const nodes = {
  symsel: { value: '' },
  symcustom: { value: '' },
};
const tfButtons = [
  { dataset: { tf: '15m' }, classList: { toggle(_name, on) { this.on = on; } } },
  { dataset: { tf: '4h' }, classList: { toggle(_name, on) { this.on = on; } } },
];
let restarted = 0;
let scrolled = 0;
let cacheInvalidations = 0;
const context = {
  App: { symbol: 'BTCUSDT', chartTF: '1h' },
  RenderCache: { invalidate() { cacheInvalidations += 1; } },
  $: id => nodes[id] || null,
  document: { querySelectorAll: () => tfButtons },
  window: { scrollTo() { scrolled += 1; } },
  restart() { restarted += 1; },
};
vm.createContext(context);
vm.runInContext(`${switchSource}\nthis.switchToAsset = switchToAsset;`, context);
context.switchToAsset('SOLUSDT', '4h');

assert.strictEqual(context.App.symbol, 'SOLUSDT');
assert.strictEqual(context.App.chartTF, '4h');
assert.strictEqual(nodes.symsel.value, 'SOLUSDT');
assert.strictEqual(nodes.symcustom.value, 'SOLUSDT');
assert.strictEqual(tfButtons[0].classList.on, false);
assert.strictEqual(tfButtons[1].classList.on, true);
assert.strictEqual(cacheInvalidations, 1, 'asset switches must invalidate all panel render caches');
assert.strictEqual(restarted, 1, 'one click must start exactly one fresh load generation');
assert.strictEqual(scrolled, 1, 'radar selection must return the user to the focus setup');

console.log('PASS Action Radar selection atomically updates the focused asset and timeframe');
