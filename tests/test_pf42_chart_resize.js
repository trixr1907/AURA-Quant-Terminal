'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

assert(html.includes('id="chart-resize-handle"'), 'PF-42: resize handle missing');
assert(html.includes('min-height:44px'), 'PF-42: touch hitbox must be at least 44px');
assert(html.includes('aura_chart_height_v1'), 'PF-42: height persistence missing');
assert(html.includes("handle.addEventListener('pointerdown'"), 'PF-42: unified mouse/touch pointer binding missing');
assert(html.includes("clamp(Math.round(value), 320, 900)"), 'PF-42: resize boundaries missing');
assert(html.includes('id="barslider"'), 'PF-42: integrated bars slider missing');

const store = {};
const ctx = {
  console, JSON, Math, Date, Promise, Set, Map, Number, String, Array, Object,
  localStorage: { getItem: k => store[k] ?? null, setItem: (k,v) => { store[k]=String(v); }, removeItem: k => delete store[k] },
  document: { getElementById: () => null, querySelectorAll: () => ({forEach(){}}), addEventListener(){}, createElement: () => ({}), body: {} },
  window: { addEventListener(){}, requestAnimationFrame: cb => cb() },
  setTimeout: () => 1, setInterval: () => 1, clearTimeout(){}, requestAnimationFrame: cb => cb(),
  fetch: async () => ({ok:true,json:async()=>({})}), location:{search:''}
};
vm.createContext(ctx);
vm.runInContext(`${script}; this.clamp=clamp;`, ctx);
assert.strictEqual(ctx.clamp(100, 320, 900), 320);
assert.strictEqual(ctx.clamp(1000, 320, 900), 900);
console.log('PASS PF-42 chart resize, persistence, bounds, touch and timeline controls');
