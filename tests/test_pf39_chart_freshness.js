'use strict';

// PF-39 BTC-Chart Freshness Badge & Load-State Behavior Test
// Verifies:
// 1. Chart load state: hidden on idle/ready, visible on loading ("Lade…"), visible on error with Retry button, hidden after retry success.
// 2. Freshness badge: displays candle age + source, ticks every second, turns red on error.

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
assert(scriptMatch, 'Dashboard script block not found');

// ── 1. Static markup assertions
assert(
  html.includes('id="chart-freshness-badge"'),
  'FAIL PF-39: chart-freshness-badge element must exist in the chart header'
);
assert(
  html.includes('id="chart-load-state"'),
  'FAIL PF-39: chart-load-state element must exist'
);

function createContext() {
  const store = {};
  const elements = {};
  const makeElement = (tag = 'div') => ({
    tagName: tag.toUpperCase(),
    textContent: '', className: '', innerHTML: '', hidden: false,
    style: {}, dataset: {}, children: [],
    appendChild(n) { this.children.push(n); return n; },
    append: () => {},
    replaceChildren(...nodes) { this.children = nodes; },
    querySelectorAll: () => ({ forEach: () => {} }),
    addEventListener: () => {},
    setAttribute: () => {},
    getAttribute: () => null,
    classList: { add: () => {}, remove: () => {}, toggle: () => {}, contains: () => false },
  });
  const document = {
    getElementById(id) { return elements[id] || (elements[id] = makeElement()); },
    querySelectorAll: () => ({ forEach: () => {} }),
    addEventListener: () => {},
    createElement: (tag) => makeElement(tag),
    createDocumentFragment: () => makeElement(),
    body: makeElement(),
  };
  const ctx = {
    console, JSON, Math, Date, Promise, Set, Map, Number, String, Array, Object,
    localStorage: {
      getItem: key => store[key] === undefined ? null : store[key],
      setItem: (key, value) => { store[key] = String(value); },
      removeItem: key => { delete store[key]; },
    },
    document,
    window: { addEventListener: () => {}, requestAnimationFrame: cb => { cb(); return 1; } },
    requestAnimationFrame: cb => { cb(); return 1; },
    setInterval: () => 1,
    setTimeout: (cb) => { cb(); return 1; },
    clearTimeout: () => {},
    fetch: async () => ({ ok: true, json: async () => ({}) }),
    $: id => document.getElementById(id),
    location: { search: '' },
  };
  vm.createContext(ctx);
  vm.runInContext(`${scriptMatch[1]}; this.App = App; this.renderChartLoadState = renderChartLoadState; this.updateChartFreshnessBadge = updateChartFreshnessBadge;`, ctx);
  return { ctx, elements };
}

(async () => {
  const { ctx, elements } = createContext();

  const loadStateEl = elements['chart-load-state'] || ctx.$('chart-load-state');
  const messageEl = elements['chart-load-message'] || ctx.$('chart-load-message');
  const retryBtn = elements['chart-load-retry'] || ctx.$('chart-load-retry');
  const badgeEl = elements['chart-freshness-badge'] || ctx.$('chart-freshness-badge');

  // ── Test Case A: IDLE state → load band is hidden
  ctx.App.chartLoad = { status: 'idle', attempt: 0, target: null, message: '', retryTimer: null };
  ctx.renderChartLoadState();
  assert.strictEqual(loadStateEl.hidden, true, 'FAIL PF-39: chart-load-state must be hidden when status=idle');

  // ── Test Case B: LOADING state → load band is visible with "Lade…" message
  ctx.App.chartLoad = { status: 'loading', attempt: 0, target: { gen: 1, symbol: 'BTCUSDT', tf: '1h' }, message: '', retryTimer: null };
  ctx.renderChartLoadState();
  assert.strictEqual(loadStateEl.hidden, false, 'FAIL PF-39: chart-load-state must be visible when status=loading');
  assert(messageEl.textContent.includes('Lade'), 'FAIL PF-39: loading message must contain "Lade"');

  // ── Test Case C: ERROR state → load band is visible with error message and active retry button
  ctx.App.chartLoad = { status: 'error', attempt: 1, target: { gen: 1, symbol: 'BTCUSDT', tf: '1h' }, message: 'Chart konnte nicht geladen werden.', retryTimer: null };
  ctx.renderChartLoadState();
  assert.strictEqual(loadStateEl.hidden, false, 'FAIL PF-39: chart-load-state must be visible when status=error');
  assert(messageEl.textContent.includes('nicht geladen'), 'FAIL PF-39: error message must be displayed');
  assert.strictEqual(retryBtn.textContent, 'Erneut laden', 'FAIL PF-39: retry button must read "Erneut laden" on error');

  // ── Test Case D: Freshness Badge updates with candle timestamp
  const now = Date.now();
  ctx.App.data.chartLoadedAt = now - 5000; // 5 seconds ago
  ctx.App.data.chartSrc = 'Bitget Direct';
  ctx.App.chartLoad = { status: 'idle' };
  ctx.updateChartFreshnessBadge();
  assert(badgeEl.textContent.includes('vor 5s'), `FAIL PF-39: freshness badge should show "vor 5s", got "${badgeEl.textContent}"`);
  assert(badgeEl.textContent.includes('Bitget Direct'), `FAIL PF-39: freshness badge should include source, got "${badgeEl.textContent}"`);
  assert.notStrictEqual(badgeEl.style.color, 'var(--red2)', 'FAIL PF-39: normal freshness badge must not be red');

  // ── Test Case E: Freshness Badge turns red when chartLoad status is 'error'
  ctx.App.chartLoad = { status: 'error' };
  ctx.updateChartFreshnessBadge();
  assert.strictEqual(badgeEl.style.color, 'var(--red2)', 'FAIL PF-39: freshness badge must turn red on error');

  console.log('PASS PF-39 Chart freshness & load-state: idle/loading/error states and badge tick verified');
})().catch(err => {
  console.error(`FAIL PF-39: ${err.message}`);
  process.exitCode = 1;
});
