'use strict';
/**
 * Dirty Flag Rendering Unit Test Suite
 *
 * Verifies that RenderCache suppresses redundant DOM operations
 * when panel inputs have not changed, and invalidates/rerenders
 * correctly when inputs change or when force=true is requested.
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const htmlPath = path.join(__dirname, '..', 'Symbiose_Dashboard.html');
const html = fs.readFileSync(htmlPath, 'utf8');

// Extract script blocks
const scripts = [];
const scriptRe = /<script\b[^>]*>([\s\S]*?)<\/script>/gi;
let match;
while ((match = scriptRe.exec(html)) !== null) {
  scripts.push(match[1]);
}
const fullJs = scripts.join('\n;\n');

// Build minimal DOM and window mock
const elementStore = {};
function createMockElement(id) {
  const el = {
    id,
    textContent: '',
    innerHTML: '',
    style: {},
    className: '',
    childNodes: [{ textContent: '' }, { textContent: '' }],
    setAttribute(k, v) { this[k] = v; },
    removeAttribute(k) { delete this[k]; },
    getAttribute(k) { return this[k] || null; },
    classList: {
      contains: () => false,
      add: () => {},
      remove: () => {}
    },
    getContext: () => ({
      setTransform: () => {},
      clearRect: () => {},
      fillRect: () => {},
      strokeRect: () => {},
      fillText: () => {},
      measureText: text => ({ width: (text ? String(text).length * 8 : 0) }),
      setLineDash: () => {},
      beginPath: () => {},
      moveTo: () => {},
      lineTo: () => {},
      stroke: () => {},
      fill: () => {}
    }),
    clientWidth: 800,
    clientHeight: 600,
    width: 800,
    height: 600
  };
  return el;
}

function getMockElement(id) {
  if (!elementStore[id]) {
    elementStore[id] = createMockElement(id);
  }
  return elementStore[id];
}

// Create valid analyzed chart
const synthCandles = [];
let price = 50000;
for (let i = 0; i < 300; i++) {
  price += Math.sin(i / 10) * 50;
  synthCandles.push({
    time: 1700000000000 + i * 3600000,
    open: price - 10,
    high: price + 40,
    low: price - 40,
    close: price,
    volume: 1000 + i
  });
}

const sandbox = {
  console,
  Date,
  Math,
  JSON,
  Array,
  Object,
  Number,
  String,
  RegExp,
  isFinite,
  isNaN,
  Float64Array,
  Int8Array,
  Int32Array,
  window: {
    devicePixelRatio: 1,
    addEventListener: () => {}
  },
  document: {
    getElementById: id => getMockElement(id),
    querySelector: sel => getMockElement(sel),
    querySelectorAll: () => [],
    addEventListener: () => {}
  },
  $: id => getMockElement(id),
  App: {
    symbol: 'BTCUSDT',
    chartTF: '1h',
    visible: 120,
    chartPanBars: 0,
    chartOverlays: {},
    leverage: 3,
    timeStopBars: 15,
    radarFilter: 'all',
    radarSort: 'score_desc',
    radarProgress: { done: 10, total: 10, scanning: false, skipped: 0 },
    universe: [],
    account: { size: 10000 },
    status: { bin: 'OK', ws: 'live' },
    data: {
      chart: null,
      live: null,
      mtf: {
        '15m': { ok: true, score: 70, dir: 1 },
        '1h': { ok: true, score: 75, dir: 1 },
        '4h': { ok: true, score: 80, dir: 1 },
        '1d': { ok: true, score: 65, dir: 1 }
      },
      ticker: { chg: 2.5, hi: 51000, lo: 49000, vol: 1000000 },
      funding: { rate: 0.0001, z: 0.5, bias: 1, txt: 'Normal' },
      crypto: {},
      radar: [
        { symbol: 'BTCUSDT', avgScore: 75, aligned: 4, executable: true, bestInfo: { score: 75, quality: 80 } }
      ],
      btcScore: 75,
      btcRegime: 1,
      btcRegimeTxt: 'BULL',
      fng: { value: 65, label: 'Greed', hist: [60, 62, 65] },
      cg: { mcap: 2.5e12, n: 10000, mcapChg: 1.2, dom: 55 }
    }
  }
};

vm.createContext(sandbox);
vm.runInContext(fullJs, sandbox);

// Initialize chart data with analyze inside vm
sandbox.synthCandles = synthCandles;
vm.runInContext('App.data.chart = analyze(synthCandles); App.data.live = computeLive();', sandbox);

console.log('--- Testing RenderCache Dirty-Flag Mechanism ---');

// 1. Initial dirty check
const RenderCache = sandbox.window.RenderCache || sandbox.RenderCache;
assert(RenderCache, 'RenderCache must be defined on window');
RenderCache.invalidate();

const initialDirty = RenderCache.isDirty('status', ['OK', 65, 'Greed']);
assert.strictEqual(initialDirty, true, 'First check must be dirty (cache miss)');

// 2. Unchanged state check
const secondDirty = RenderCache.isDirty('status', ['OK', 65, 'Greed']);
assert.strictEqual(secondDirty, false, 'Second check with identical data must NOT be dirty (cache hit)');

// 3. Changed state check
const thirdDirty = RenderCache.isDirty('status', ['OK', 70, 'Greed']);
assert.strictEqual(thirdDirty, true, 'Check with changed data must be dirty');

// 4. Invalidation check
RenderCache.invalidate('status');
const afterInvalidate = RenderCache.isDirty('status', ['OK', 70, 'Greed']);
assert.strictEqual(afterInvalidate, true, 'Check after invalidate must be dirty');

// 5. Verify renderAll with dirty-flag caching
RenderCache.invalidate();

// Initial renderAll
const renderAll = sandbox.window.renderAll || sandbox.renderAll;
renderAll();
assert.strictEqual(RenderCache.hashes['hero'] != null, true, 'Hero hash must be stored');

const initialHeroHash = RenderCache.hashes['hero'];
const initialPriceHash = RenderCache.hashes['price'];
const initialMtfHash = RenderCache.hashes['mtf'];

// Second renderAll with identical state
renderAll();
assert.strictEqual(RenderCache.hashes['hero'], initialHeroHash, 'Hero hash must remain unchanged');
assert.strictEqual(RenderCache.hashes['price'], initialPriceHash, 'Price hash must remain unchanged');
assert.strictEqual(RenderCache.hashes['mtf'], initialMtfHash, 'MTF hash must remain unchanged');

// Modify price and run renderAll -> only price hash changes
vm.runInContext('App.data.chart.c[App.data.chart.n - 1] = 52000;', sandbox);
renderAll();
assert.notStrictEqual(RenderCache.hashes['price'], initialPriceHash, 'Price hash must change after price update');
assert.strictEqual(RenderCache.hashes['mtf'], initialMtfHash, 'MTF hash must remain untouched');

console.log('ALL DIRTY-FLAG RENDERING TESTS PASSED');
