#!/usr/bin/env node
'use strict';

const fs = require('fs');
const assert = require('assert');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

// Gen-2 token catalogue
for (const token of [
  '--color-base', '--color-surface', '--color-accent', '--color-success',
  '--color-warning', '--color-danger', '--font-sans', '--font-mono',
  '--space-1', '--space-6', '--radius-sm', '--radius-lg', '--shadow-sm',
  '--z-drawer', '--breakpoint-mobile', '--touch-target',
]) {
  assert(html.includes(token), `missing design token ${token}`);
}

assert(/:root\s*\{/.test(html), 'missing :root token scope');
assert(/@media\(max-width:420px\)/.test(html), 'missing 420px mobile breakpoint');
assert(/@media\(prefers-reduced-motion:reduce\)/.test(html), 'missing reduced-motion rule');
assert(/:focus-visible/.test(html), 'missing focus-visible rule');

// Self-contained contract: no external styles, scripts, fonts, or CSS image URLs.
assert(!/<(?:script|img|link)[^>]+(?:src|href)=["']https?:\/\//i.test(html), 'external HTML resource found');
assert(!/url\(\s*["']?https?:\/\//i.test(html), 'external CSS resource found');

// Core panel structure must remain available.
for (const id of ['hero', 'autobot-section', 'trade-portfolio-kpis', 'radarcard']) {
  assert(new RegExp(`id=["']${id}["']`).test(html), `missing core panel #${id}`);
}

// Behavioral test for migrateTradeStorageV2 in browser context
const vm = require('vm');
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
assert(scriptMatch, 'missing dashboard script tag');

const store = {
  'aura-quant-terminal-active-trades-v1': JSON.stringify([{ id: 'trade-v1-test', coin: 'BTCUSDT' }]),
  'aura-quant-terminal-history-trades-v1': JSON.stringify([{ id: 'hist-v1-test', parentId: 'trade-v1-test' }]),
};

const mockLocalStorage = {
  getItem: (key) => (key in store ? store[key] : null),
  setItem: (key, val) => { store[key] = String(val); },
  removeItem: (key) => { delete store[key]; },
};

const ctx = {
  localStorage: mockLocalStorage,
  window: {},
  document: { getElementById: () => null, querySelectorAll: () => [], addEventListener: () => {} },
  console,
  setTimeout: () => 1,
  setInterval: () => 1,
  requestAnimationFrame: (cb) => { cb(); return 1; },
};
vm.createContext(ctx);
vm.runInContext(scriptMatch[1], ctx);

// After script execution, migrateTradeStorageV2 should have run
assert.strictEqual(
  store['aura-quant-terminal-active-trades-v2'],
  store['aura-quant-terminal-active-trades-v1'],
  'v2 active trades must match v1 bytes exactly',
);
assert.strictEqual(
  store['aura-quant-terminal-active-trades-v1-imported'],
  store['aura-quant-terminal-active-trades-v1'],
  'imported active trades retention must match v1 bytes',
);
assert.strictEqual(
  store['aura-quant-terminal-history-trades-v2'],
  store['aura-quant-terminal-history-trades-v1'],
  'v2 history trades must match v1 bytes exactly',
);
assert.strictEqual(
  store['aura-quant-terminal-history-trades-v1-imported'],
  store['aura-quant-terminal-history-trades-v1'],
  'imported history trades retention must match v1 bytes',
);

console.log('Design system Gen-2 static checks passed');
