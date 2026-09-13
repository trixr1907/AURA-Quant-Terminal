'use strict';

// PF-37 Regression test: Autobot trade cards must pass real calculateTradeMetrics
// to renderTradeCard — null metrics path must not exist.

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
assert(scriptMatch, 'Dashboard script block not found');

// ── 1. Static source-code assertion: null must not appear in autobot render path
const autobotRenderSrc = (() => {
  const renderStart = html.indexOf('render() {');
  // find inside the Autobot object (after the render function declaration)
  const renderEnd = html.indexOf('renderLogs() {', renderStart);
  return html.slice(renderStart, renderEnd);
})();

assert(
  !autobotRenderSrc.includes('renderTradeCard(t, null'),
  'FAIL PF-37: renderTradeCard(t, null, …) still exists in Autobot render() — regression'
);

// ── 2. Runtime: simulate ticker ticks and verify both containers update
function createContext() {
  const store = {};
  const elements = {};
  const makeElement = (tag = 'div') => {
    const el = {
      tagName: String(tag).toUpperCase(),
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
      cloneNode() { return makeElement(tag); },
    };
    if (tag.toLowerCase() === 'template') {
      el.content = { cloneNode: () => makeElement('div') };
    }
    return el;
  };
  const document = {
    getElementById(id) { return elements[id] || (elements[id] = makeElement()); },
    querySelectorAll: () => ({ forEach: () => {} }),
    addEventListener: () => {},
    createElement: tag => makeElement(tag),
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
  vm.runInContext(`${scriptMatch[1]}; this.Autobot = Autobot; this.calculateTradeMetrics = calculateTradeMetrics; this.tradePrices = tradePrices; this.scheduleLiveTradesRender = scheduleLiveTradesRender; this.renderLiveTrades = renderLiveTrades;`, ctx);
  return { ctx, store };
}

(async () => {
  const { ctx } = createContext();

  // Craft a realistic autobot trade
  const trade = {
    id: 'ab-test-trade-1',
    coin: 'ETHUSDT',
    dir: 1,
    entry: 3000,
    initialSl: 2940,
    currentSl: 2940,
    tp: 3090,
    tp1: 3060,
    tp2: 3120,
    margin: 100,
    initialMargin: 100,
    notional: 1000,
    leverage: 10,
    openedAt: Date.now() - 60000,
    score: 75,
    setupDsr: 0.62,
    timeStopBars: 12,
    signalTf: '1h',
    beActive: false,
  };

  // Simulate ticker prices arriving (two ticks, different prices)
  const capturedMetricsCallArgs = [];
  const origCalc = ctx.calculateTradeMetrics;
  ctx.calculateTradeMetrics = function(t, px) {
    const result = origCalc.call(this, t, px);
    capturedMetricsCallArgs.push({ trade: t, px, pnlGross: result.pnlGross });
    return result;
  };

  // Simulate a tradePrices tick at price 3030 (should show +1R progress)
  ctx.tradePrices['ETHUSDT'] = 3030;

  // Set up Autobot with the trade and call render
  ctx.Autobot.trades = [trade];
  ctx.Autobot.render();

  // After render, calculateTradeMetrics must have been called with the trade
  assert(
    capturedMetricsCallArgs.length >= 1,
    'FAIL PF-37: calculateTradeMetrics was never called during Autobot.render()'
  );
  const call = capturedMetricsCallArgs[0];
  assert.strictEqual(call.trade.coin, 'ETHUSDT', 'FAIL PF-37: wrong trade passed to calculateTradeMetrics');
  assert.strictEqual(call.px, 3030, 'FAIL PF-37: tradePrices price not forwarded to calculateTradeMetrics');
  // PnL at 3030 for LONG: (3030-3000)/3000 * 1 * 1000 = +10 USDT
  const expectedPnl = ((3030 - 3000) / 3000) * 1 * 1000;
  assert(
    Math.abs(call.pnlGross - expectedPnl) < 0.01,
    `FAIL PF-37: pnlGross ${call.pnlGross.toFixed(4)} ≠ expected ${expectedPnl.toFixed(4)}`
  );

  // ── 3. Verify scheduleLiveTradesRender triggers Autobot.render() too
  let autobotRenderCalled = false;
  ctx.Autobot.render = () => { autobotRenderCalled = true; };
  ctx.tradePrices['BTCUSDT'] = 50000;
  // Inject a minimal live trade so renderLiveTrades finds something
  ctx.localStorage.setItem('trades', JSON.stringify([{
    id: 'lt-1', coin: 'BTCUSDT', dir: 1, entry: 49000, initialSl: 48000, currentSl: 48000,
    tp: 51000, margin: 50, initialMargin: 50, notional: 500, leverage: 10,
    openedAt: Date.now() - 120000, markUpdatedAt: Date.now() - 5000,
  }]));
  ctx.scheduleLiveTradesRender();
  // scheduleLiveTradesRender uses rAF which our stub calls immediately
  assert(
    autobotRenderCalled,
    'FAIL PF-37: Autobot.render() was not called from scheduleLiveTradesRender chain'
  );

  console.log('PASS PF-37 Autobot live metrics: calculateTradeMetrics used, null path eliminated, Autobot synced to ticker tact');
})().catch(err => {
  console.error(`FAIL PF-37: ${err.message}`);
  process.exitCode = 1;
});
