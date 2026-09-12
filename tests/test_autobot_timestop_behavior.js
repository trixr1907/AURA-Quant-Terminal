'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const html = fs.readFileSync(path.resolve(__dirname, '..', 'Symbiose_Dashboard.html'), 'utf8');
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
assert(scriptMatch, 'Symbiose_Dashboard.html script block missing');

function createTestHarness() {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) {
      elements.set(id, {
        id,
        value: '',
        textContent: '',
        innerHTML: '',
        className: '',
        style: {},
        dataset: {},
        classList: { add() {}, remove() {}, toggle() {} },
        addEventListener() {},
        querySelectorAll() { return []; },
        setAttribute() {},
        reset() {},
      });
    }
    return elements.get(id);
  }

  const storage = new Map();
  let currentTimestamp = 1700000000000;

  const ctx = {
    console,
    document: {
      getElementById: element,
      addEventListener() {},
      querySelectorAll() { return []; },
    },
    window: {
      addEventListener() {},
      AudioContext: function () {},
      webkitAudioContext: function () {},
    },
    localStorage: {
      getItem(key) { return storage.has(key) ? storage.get(key) : null; },
      setItem(key, value) { storage.set(key, String(value)); },
    },
    navigator: {},
    location: { protocol: 'http:', host: '127.0.0.1:8787' },
    requestAnimationFrame(fn) { return 1; },
    cancelAnimationFrame() {},
    setTimeout() { return 1; },
    clearTimeout() {},
    setInterval() { return 1; },
    clearInterval() {},
    fetch: async () => ({ ok: true, json: async () => null }),
    WebSocket: function () {},
    ResizeObserver: function () { this.observe = () => {}; },
    Float64Array,
    Int8Array,
    Uint8Array,
    Math,
    Date: class extends Date {
      constructor(...args) {
        if (args.length) super(...args);
        else super(currentTimestamp);
      }
      static now() {
        return currentTimestamp;
      }
    },
    JSON,
    Number,
    String,
    Object,
    Array,
    Promise,
    isFinite,
    isNaN,
    Infinity,
  };
  ctx.window.document = ctx.document;
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(scriptMatch[1] + '\nthis.__Autobot = Autobot;\nthis.__tradePrices = tradePrices;', ctx);

  const Autobot = ctx.__Autobot;
  const tradePrices = ctx.__tradePrices;

  // Mock UI/persistence side-effects
  Autobot.enabled = true;
  Autobot.trades = [];
  Autobot.history = [];
  Autobot.save = () => {};
  Autobot.render = () => {};
  Autobot.log = () => {};

  return {
    Autobot,
    tradePrices,
    setTime: (ts) => { currentTimestamp = ts; },
    getTime: () => currentTimestamp,
  };
}

// ============================================================================
//  BEHAVIOR-BASED MATRIX TESTS FOR AUTOBOT.MONITORTRADES / UPDATEACTIVETRADES
// ============================================================================

const TIMEFRAME_MINUTES = {
  '15m': 15,
  '1h': 60,
  '4h': 240,
  '1d': 1440,
};

// 1. Timeframe Duration Scaling Matrix Test
//    Verifies that maxHoldMs is computed as timeStopBars * tfMinutes * 60,000 ms
for (const [tf, tfMins] of Object.entries(TIMEFRAME_MINUTES)) {
  const bars = 8;
  const expectedMaxHoldMs = bars * tfMins * 60 * 1000;
  const baseTime = 1700000000000;

  // A. Before deadline (50% elapsed) -> Trade remains open
  {
    const harness = createTestHarness();
    harness.setTime(baseTime);
    harness.Autobot.trades = [{
      id: `trade-scaling-${tf}-before`,
      coin: 'BTCUSDT',
      dir: 1,
      entry: 100,
      initialSl: 90,
      currentSl: 90,
      margin: 100,
      initialMargin: 100,
      leverage: 10,
      notional: 1000,
      openedAt: baseTime,
      beActive: false,
      scaledOut: false,
      signalTf: tf,
      timeStopBars: bars,
    }];
    harness.tradePrices['BTCUSDT'] = 99.0; // ROI = -10% (< -3.0% loss)
    
    harness.setTime(baseTime + Math.floor(expectedMaxHoldMs * 0.5));
    harness.Autobot.updateActiveTrades();
    assert.strictEqual(harness.Autobot.trades.length, 1, `Trade on ${tf} at 50% hold time must remain open`);
    assert.strictEqual(harness.Autobot.history.length, 0);
  }

  // B. Exactly on deadline (100% elapsed) -> Trade remains open (strict inequality elapsedMs > maxHoldMs)
  {
    const harness = createTestHarness();
    harness.setTime(baseTime);
    harness.Autobot.trades = [{
      id: `trade-scaling-${tf}-exact`,
      coin: 'BTCUSDT',
      dir: 1,
      entry: 100,
      initialSl: 90,
      currentSl: 90,
      margin: 100,
      initialMargin: 100,
      leverage: 10,
      notional: 1000,
      openedAt: baseTime,
      beActive: false,
      scaledOut: false,
      signalTf: tf,
      timeStopBars: bars,
    }];
    harness.tradePrices['BTCUSDT'] = 99.0; // ROI = -10% (< -3.0% loss)
    
    harness.setTime(baseTime + expectedMaxHoldMs);
    harness.Autobot.updateActiveTrades();
    assert.strictEqual(harness.Autobot.trades.length, 1, `Trade on ${tf} exactly at deadline must remain open`);
    assert.strictEqual(harness.Autobot.history.length, 0);
  }

  // C. Past deadline (100% + 1s elapsed) -> Trade closes via TIME_STOP_DYNAMIC
  {
    const harness = createTestHarness();
    harness.setTime(baseTime);
    harness.Autobot.trades = [{
      id: `trade-scaling-${tf}-after`,
      coin: 'BTCUSDT',
      dir: 1,
      entry: 100,
      initialSl: 90,
      currentSl: 90,
      margin: 100,
      initialMargin: 100,
      leverage: 10,
      notional: 1000,
      openedAt: baseTime,
      beActive: false,
      scaledOut: false,
      signalTf: tf,
      timeStopBars: bars,
    }];
    harness.tradePrices['BTCUSDT'] = 99.0; // ROI = -10% (< -3.0% loss)
    
    harness.setTime(baseTime + expectedMaxHoldMs + 1000);
    harness.Autobot.updateActiveTrades();
    assert.strictEqual(harness.Autobot.trades.length, 0, `Trade on ${tf} past deadline must be closed`);
    assert.strictEqual(harness.Autobot.history.length, 1, `Trade on ${tf} must be recorded in history`);
    assert.strictEqual(harness.Autobot.history[0].reason, 'TIME_STOP_DYNAMIC', `Exit reason must be TIME_STOP_DYNAMIC on ${tf}`);
  }
}

// 2. Asymmetric PnL Condition Matrix Test
//    Verifies that time stop ONLY triggers on stagnant losing positions (curRoi < -3.0)
//    and NEVER on winning, break-even, or mildly losing positions.
{
  const baseTime = 1700000000000;
  const holdMs = 10 * 60 * 60 * 1000; // 10h hold time

  const pnlScenarios = [
    { name: 'Profitable Long (+5% ROI)', dir: 1, entry: 100, px: 100.5, leverage: 10, beActive: false, shouldClose: false },
    { name: 'Profitable Short (+5% ROI)', dir: -1, entry: 100, px: 99.5, leverage: 10, beActive: false, shouldClose: false },
    { name: 'Break-Even Active Flag', dir: 1, entry: 100, px: 99.0, leverage: 10, beActive: true, shouldClose: false },
    { name: 'Mild Loss Long (-2.0% ROI, > -3.0% threshold)', dir: 1, entry: 100, px: 99.8, leverage: 10, beActive: false, shouldClose: false },
    { name: 'Mild Loss Short (-2.0% ROI, > -3.0% threshold)', dir: -1, entry: 100, px: 100.2, leverage: 10, beActive: false, shouldClose: false },
    { name: 'Stagnant Loss Long (-5.0% ROI, < -3.0% threshold)', dir: 1, entry: 100, px: 99.5, leverage: 10, beActive: false, shouldClose: true },
    { name: 'Stagnant Loss Short (-5.0% ROI, < -3.0% threshold)', dir: -1, entry: 100, px: 100.5, leverage: 10, beActive: false, shouldClose: true },
  ];

  for (const s of pnlScenarios) {
    const harness = createTestHarness();
    harness.setTime(baseTime);
    harness.Autobot.trades = [{
      id: `pnl-scenario-${s.name}`,
      coin: 'TESTCOIN',
      dir: s.dir,
      entry: s.entry,
      initialSl: s.dir === 1 ? s.entry * 0.9 : s.entry * 1.1,
      currentSl: s.dir === 1 ? s.entry * 0.9 : s.entry * 1.1,
      margin: 100,
      initialMargin: 100,
      leverage: s.leverage,
      notional: 100 * s.leverage,
      openedAt: baseTime,
      beActive: s.beActive,
      scaledOut: false,
      signalTf: '1h',
      timeStopBars: 10,
    }];
    harness.tradePrices['TESTCOIN'] = s.px;

    // Advance past deadline (10h + 10s)
    harness.setTime(baseTime + holdMs + 10000);
    harness.Autobot.updateActiveTrades();

    if (s.shouldClose) {
      assert.strictEqual(harness.Autobot.trades.length, 0, `Scenario '${s.name}' should have closed trade`);
      assert.strictEqual(harness.Autobot.history.length, 1, `Scenario '${s.name}' should have 1 closed record`);
      assert.strictEqual(harness.Autobot.history[0].reason, 'TIME_STOP_DYNAMIC');
    } else {
      assert.strictEqual(harness.Autobot.trades.length, 1, `Scenario '${s.name}' should have kept trade open`);
      assert.strictEqual(harness.Autobot.history.length, 0, `Scenario '${s.name}' should not have closed trade`);
    }
  }
}

// 3. Fallback Time-Stop Behavior Matrix Test (12-Bar Default)
//    When trade has no timeStopBars property, it MUST fall back to exactly 12 bars.
{
  const baseTime = 1700000000000;
  const tfMinutes = 60; // 1h
  const fallbackBars = 12;
  const exactFallbackMs = fallbackBars * tfMinutes * 60 * 1000; // 12 hours = 43,200,000 ms

  // A. Before 12 bars (e.g. 11.5 hours) -> Trade remains open
  {
    const harness = createTestHarness();
    harness.setTime(baseTime);
    harness.Autobot.trades = [{
      id: 'fallback-trade-11h',
      coin: 'BTCUSDT',
      dir: 1,
      entry: 100,
      initialSl: 90,
      currentSl: 90,
      margin: 100,
      initialMargin: 100,
      leverage: 10,
      notional: 1000,
      openedAt: baseTime,
      beActive: false,
      scaledOut: false,
      signalTf: '1h',
      // timeStopBars is undefined
    }];
    harness.tradePrices['BTCUSDT'] = 99.0; // -10% ROI

    harness.setTime(baseTime + (11.5 * 60 * 60 * 1000));
    harness.Autobot.updateActiveTrades();
    assert.strictEqual(harness.Autobot.trades.length, 1, '12-bar fallback trade at 11.5h must stay open');
  }

  // B. Exactly at 12 bars -> Trade remains open (strict inequality)
  {
    const harness = createTestHarness();
    harness.setTime(baseTime);
    harness.Autobot.trades = [{
      id: 'fallback-trade-12h-exact',
      coin: 'BTCUSDT',
      dir: 1,
      entry: 100,
      initialSl: 90,
      currentSl: 90,
      margin: 100,
      initialMargin: 100,
      leverage: 10,
      notional: 1000,
      openedAt: baseTime,
      beActive: false,
      scaledOut: false,
      signalTf: '1h',
    }];
    harness.tradePrices['BTCUSDT'] = 99.0;

    harness.setTime(baseTime + exactFallbackMs);
    harness.Autobot.updateActiveTrades();
    assert.strictEqual(harness.Autobot.trades.length, 1, '12-bar fallback trade at exactly 12h must stay open');
  }

  // C. At 12 hours + 10s -> Trade MUST close via TIME_STOP_DYNAMIC
  {
    const harness = createTestHarness();
    harness.setTime(baseTime);
    harness.Autobot.trades = [{
      id: 'fallback-trade-12h-after',
      coin: 'BTCUSDT',
      dir: 1,
      entry: 100,
      initialSl: 90,
      currentSl: 90,
      margin: 100,
      initialMargin: 100,
      leverage: 10,
      notional: 1000,
      openedAt: baseTime,
      beActive: false,
      scaledOut: false,
      signalTf: '1h',
    }];
    harness.tradePrices['BTCUSDT'] = 99.0;

    harness.setTime(baseTime + exactFallbackMs + 10000);
    harness.Autobot.updateActiveTrades();
    assert.strictEqual(harness.Autobot.trades.length, 0, '12-bar fallback trade past 12h must close');
    assert.strictEqual(harness.Autobot.history.length, 1);
    assert.strictEqual(harness.Autobot.history[0].reason, 'TIME_STOP_DYNAMIC');
  }
}

console.log('PASS Autobot in-trade monitoring and dynamic time-stop behavior verified across timeframes, PnL states, and fallbacks');
