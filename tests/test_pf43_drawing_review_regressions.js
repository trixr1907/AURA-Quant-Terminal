'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

const ctx = {
  console, JSON, Math, Date, Promise, Set, Map, Number, String, Array, Object,
  localStorage: { getItem() { throw new Error('SecurityError'); }, setItem() { throw new Error('SecurityError'); } },
  document: { getElementById: () => null, querySelectorAll: () => ({ forEach() {} }), addEventListener() {}, createElement: () => ({}), body: {} },
  window: { addEventListener() {}, requestAnimationFrame: cb => cb() },
  setTimeout: () => 1, setInterval: () => 1, clearTimeout() {}, requestAnimationFrame: cb => cb(),
  fetch: async () => ({ ok: true, json: async () => ({}) }), location: { search: '' }
};
vm.createContext(ctx);
vm.runInContext(`${script}; this.App=App; this.loadChartDrawings=loadChartDrawings; this.saveChartDrawings=saveChartDrawings; this.findDrawingHit=findDrawingHit;`, ctx);

ctx.App.drawings = [{ id: 'safe', type: 'horizontal', points: [{ time: 1000, price: 10 }] }];
assert.doesNotThrow(() => ctx.saveChartDrawings(), 'PF-43: blocked localStorage must not crash drawing save');
assert.deepStrictEqual(JSON.parse(JSON.stringify(ctx.loadChartDrawings())), [], 'PF-43: blocked localStorage must fail closed');

const plot = { xAtTime: t => t, yAt: p => p };
const trend = { id: 'trend', type: 'trend', points: [{ time: 10, price: 10 }, { time: 110, price: 110 }] };
const segmentHit = ctx.findDrawingHit(60, 60, plot, [trend]);
assert(segmentHit && segmentHit.id === 'trend', 'PF-43: trend must be selectable from its visible segment');

assert(html.includes('Array.from(A.ms)'), 'PF-43: drawing time projection must use analyzed candle timestamps (A.ms)');
assert(html.includes("cv.addEventListener('pointerdown'"), 'PF-43: canvas drawing must support Pointer Events');
assert(!html.includes("cv.addEventListener('mousedown'"), 'PF-43: canvas must not use mouse-only drawing events');
assert(html.includes("const x = clientX - r.left, y = clientY - r.top"), 'PF-43: pointer coordinates must stay in CSS-pixel plot space');
assert(/#chart\{[^}]*touch-action:none/.test(html), 'PF-43: canvas must suppress native touch gestures while drawing');
assert((html.match(/e\.preventDefault\(\)/g) || []).length >= 4, 'PF-43: pointer drawing/selection must prevent native touch handling');
console.log('PASS PF-43 review regressions: timestamp projection, segment hit, pointer input, safe storage');
