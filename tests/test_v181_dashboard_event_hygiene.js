'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

class FakeElement {
  constructor(id = '', tag = 'div') {
    this.id = id;
    this.tagName = tag.toUpperCase();
    this.value = '';
    this.checked = false;
    this.disabled = false;
    this.textContent = '';
    this.innerHTML = '';
    this.style = {};
    this.dataset = {};
    this.classList = {
      _classes: new Set(),
      add(c) { this._classes.add(c); },
      remove(c) { this._classes.delete(c); },
      contains(c) { return this._classes.has(c); },
      toggle(c, force) { if (force !== undefined) { if (force) this.add(c); else this.remove(c); } else { if (this.contains(c)) this.remove(c); else this.add(c); } },
    };
    this._listeners = {};
    this._attributes = {};
    this.children = [];
    this.parentElement = null;
  }

  getAttribute(name) {
    if (this._attributes[name] !== undefined) return this._attributes[name];
    if (name.startsWith('data-')) {
      const prop = name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      return this.dataset[prop] !== undefined ? this.dataset[prop] : null;
    }
    return null;
  }

  setAttribute(name, val) {
    this._attributes[name] = String(val);
    if (name.startsWith('data-')) {
      const prop = name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      this.dataset[prop] = String(val);
    }
  }

  addEventListener(type, handler) {
    if (!this._listeners[type]) this._listeners[type] = [];
    this._listeners[type].push(handler);
  }

  removeEventListener(type, handler) {
    if (this._listeners[type]) {
      this._listeners[type] = this._listeners[type].filter(h => h !== handler);
    }
  }

  async dispatchEvent(type, eventObj = {}) {
    const ev = {
      type,
      target: this,
      stopPropagation: () => { ev._stopped = true; },
      preventDefault: () => { ev._prevented = true; },
      _stopped: false,
      _prevented: false,
      ...eventObj,
    };
    const handlers = this._listeners[type] || [];
    for (const h of handlers) {
      await h(ev);
    }
    return ev;
  }

  closest(selector) {
    if (matchesSelector(this, selector)) return this;
    return this.parentElement ? this.parentElement.closest(selector) : null;
  }

  querySelector(selector) {
    const list = this.querySelectorAll(selector);
    return list.length > 0 ? list[0] : null;
  }

  querySelectorAll(selector) {
    const results = [];
    for (const child of this.children) {
      if (matchesSelector(child, selector)) results.push(child);
      results.push(...child.querySelectorAll(selector));
    }
    return results;
  }

  appendChild(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }
}

function matchesSelector(el, selector) {
  if (!el || !selector) return false;
  const parts = selector.split(',').map(s => s.trim());
  for (const part of parts) {
    if (part.startsWith('#') && el.id === part.slice(1)) return true;
    if (part.startsWith('.') && el.classList.contains(part.slice(1))) return true;
    if (part.startsWith('[') && part.endsWith(']')) {
      const attr = part.slice(1, -1);
      if (el.getAttribute(attr) !== null) return true;
    }
  }
  return false;
}

function createDOMContext() {
  const elements = new Map();
  function getEl(id, tag = 'div') {
    if (!elements.has(id)) elements.set(id, new FakeElement(id, tag));
    return elements.get(id);
  }

  const store = {};
  const openedUrls = [];
  const publishedPushes = [];

  const ctx = {
    console, JSON, Math, Date, Promise, Set, Map, Number, String, Array, Object,
    localStorage: {
      getItem: k => store[k] === undefined ? null : store[k],
      setItem: (k, v) => { store[k] = String(v); },
      removeItem: k => { delete store[k]; },
    },
    document: {
      getElementById: id => getEl(id),
      querySelector: sel => null,
      querySelectorAll: sel => [],
      addEventListener: () => {},
      body: getEl('body'),
    },
    window: {
      open: (url, target, features) => {
        openedUrls.push({ url, target, features });
        return { focus: () => {} };
      },
      addEventListener: () => {},
      requestAnimationFrame: cb => { cb(); return 1; },
    },
    openTradingViewChart: (symbol, tf = '1h') => {
      openedUrls.push({ symbol, tf });
    },
    requestAnimationFrame: cb => { cb(); return 1; },
    setInterval: () => 1,
    setTimeout: (cb, ms) => {
      // Execute synchronously in test if immediate or short
      if (ms === undefined || ms <= 0) cb();
      return 1;
    },
    clearTimeout: () => {},
    fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }),
    location: { search: '' },
    $: () => null,
  };

  vm.createContext(ctx);
  vm.runInContext(
    `${script};
    this.NtfySignals = NtfySignals;
    this.Autobot = Autobot;
    this.bindAutobotContainerEvents = bindAutobotContainerEvents;
    this.refreshTradePrices = refreshTradePrices;
    this.loadTrades = loadTrades;
    this.saveTrades = saveTrades;
    this.tradePrices = tradePrices;
    `,
    ctx
  );

  return { ctx, getEl, openedUrls, publishedPushes, store };
}

(async () => {
  console.log('--- Test 1: Auftrag D — Idempotent NtfySignals.bindUI() and Rate Limiting ---');
  {
    const { ctx, getEl } = createDOMContext();
    const topicInput = getEl('ntfy-topic-url', 'input');
    const testBtn = getEl('ntfy-test-button', 'button');
    const testStatus = getEl('ntfy-test-status', 'span');

    ctx.NtfySignals.save({ topicUrl: 'https://ntfy.sh/test-topic-v181' });

    let publishCount = 0;
    ctx.NtfySignals.publish = async (title, body, priority) => {
      publishCount++;
      return true;
    };

    // Call bindUI 20 times consecutively (simulating 20 sync-pulls)
    for (let i = 0; i < 20; i++) {
      ctx.NtfySignals.bindUI();
    }

    // 1 click should fire exactly 1 test-push
    await testBtn.dispatchEvent('click');
    assert.strictEqual(publishCount, 1, 'Calling bindUI 20 times must produce exactly 1 push on click');

    // Immediate second click must be rate-limited (< 10s cooldown)
    await testBtn.dispatchEvent('click');
    assert.strictEqual(publishCount, 1, 'Immediate second click within 10s must be throttled');

    // After 10s, another click should succeed
    ctx.NtfySignals._lastTestPushAt = Date.now() - 10001;
    await testBtn.dispatchEvent('click');
    assert.strictEqual(publishCount, 2, 'Click after 10s cooldown must succeed');
    console.log('✓ Auftrag D PASS: Idempotent binding (20x bindUI -> 1 click = 1 push) & 10s rate-limit verified.');
  }

  console.log('--- Test 2: Auftrag E — Single TV-Open & Stable Trade-ID Addressing ---');
  {
    const { ctx, openedUrls } = createDOMContext();
    const container = new FakeElement('autobot-trades-list');

    ctx.Autobot.trades = [
      { id: 'bot-trade-1', coin: 'BTCUSDT', dir: 1, entry: 60000, currentSl: 58000, tp1: 63000, signalTf: '4h' },
      { id: 'bot-trade-2', coin: 'ETHUSDT', dir: -1, entry: 3000, currentSl: 3100, tp1: 2800, signalTf: '15m' },
    ];

    ctx.bindAutobotContainerEvents(container);

    const card1 = new FakeElement('card-1');
    const tvBtn1 = new FakeElement('tv-btn-1', 'button');
    tvBtn1.setAttribute('data-tv-ab-id', 'bot-trade-1');
    tvBtn1.setAttribute('data-tv-ab-idx', '0');
    card1.appendChild(tvBtn1);
    container.appendChild(card1);

    // Simulate click on TV button
    await container.dispatchEvent('click', { target: tvBtn1 });
    assert.strictEqual(openedUrls.length, 1, 'TV button click must trigger exactly 1 open call');
    assert.match(openedUrls[0].url, /BITGET%3ABTCUSDT\.P/, 'TV URL must target BTCUSDT');
    assert.match(openedUrls[0].url, /interval=240/, 'TV URL must have 4h interval');

    // Mutate / reorder trades array (ETH becomes index 0, BTC becomes index 1)
    ctx.Autobot.trades = [
      { id: 'bot-trade-2', coin: 'ETHUSDT', dir: -1, entry: 3000, currentSl: 3100, tp1: 2800, signalTf: '15m' },
      { id: 'bot-trade-1', coin: 'BTCUSDT', dir: 1, entry: 60000, currentSl: 58000, tp1: 63000, signalTf: '4h' },
    ];

    // Click on tvBtn1 (which still has data-tv-ab-id="bot-trade-1" but stale data-tv-ab-idx="0")
    await container.dispatchEvent('click', { target: tvBtn1 });
    assert.strictEqual(openedUrls.length, 2);
    assert.match(openedUrls[1].url, /BITGET%3ABTCUSDT\.P/, 'Must resolve BTCUSDT by stable Trade-ID even after array reorder');
    assert.match(openedUrls[1].url, /interval=240/);

    // Test close trade by stable Trade ID
    let closedIndex = null;
    ctx.Autobot.closeTrade = (idx, px, reason) => { closedIndex = idx; };
    const closeBtn1 = new FakeElement('close-btn-1', 'button');
    closeBtn1.setAttribute('data-close-ab-id', 'bot-trade-1');
    closeBtn1.setAttribute('data-close-ab-idx', '0'); // stale index
    card1.appendChild(closeBtn1);

    await container.dispatchEvent('click', { target: closeBtn1 });
    assert.strictEqual(closedIndex, 1, 'Close action must find trade index 1 for bot-trade-1 after array reordering');

    console.log('✓ Auftrag E PASS: Single TV open, uniform timeframe, and stable Trade-ID resolution verified.');
  }

  console.log('--- Test 3: Auftrag F — 5s Live Price Refresh for Autobot Trades ---');
  {
    const { ctx } = createDOMContext();

    ctx.Autobot.trades = [
      {
        id: 'ab-live-1',
        coin: 'SOLUSDT',
        dir: 1,
        entry: 100.0,
        currentSl: 90.0,
        sl: 90.0,
        tp1: 120.0,
        margin: 100.0,
        leverage: 1,
        markPrice: 100.0,
      }
    ];

    // Mock fetchTicker returning live price of 110.0 (+1.0R for long with entry 100, SL 90)
    ctx.fetchTicker = async (coin) => {
      if (coin === 'SOLUSDT') return { symbol: 'SOLUSDT', price: 110.0 };
      return null;
    };

    let updatedMetricsCalled = false;
    ctx.Autobot.updateActiveTrades = async () => {
      updatedMetricsCalled = true;
      for (const t of ctx.Autobot.trades) {
        if (t.coin === 'SOLUSDT') {
          const riskPerUnit = Math.abs(t.entry - t.sl);
          t.currentR = (t.markPrice - t.entry) / riskPerUnit;
        }
      }
    };

    await ctx.refreshTradePrices([]);

    assert.strictEqual(ctx.tradePrices['SOLUSDT'], 110.0, 'Live price must be saved in tradePrices');
    assert.strictEqual(ctx.Autobot.trades[0].markPrice, 110.0, 'Autobot trade markPrice must update on 5s refresh');
    assert.strictEqual(updatedMetricsCalled, true, 'Autobot.updateActiveTrades must be called during 5s price refresh');
    assert.strictEqual(ctx.Autobot.trades[0].currentR, 1.0, 'R-multiple must update to +1.0R (no frozen +0.0R)');

    console.log('✓ Auftrag F PASS: Bot trades refreshed on 5s cadence with updated mark price and R-Multiple.');
  }

  console.log('ALL v1.8.1 EVENT HYGIENE & LIVE TRACKING TESTS PASSED!');
})();
