'use strict';

/**
 * test_pf50_trade_card_dom_stability.js
 * PF-50: DOM-stabile Trade-Karten (Zahlen live, Knoten beständig)
 *
 * Verifiziert:
 * (a) Zwei Renders mit identischen Daten -> Karten-Knoten identisch (isSameNode), nur Textinhalte gesetzt
 * (b) Preisänderung -> Textknoten aktualisiert, Karten-Knoten bleibt derselbe
 * (c) Trade öffnen/schließen -> Karte erscheint/verschwindet, übrige Karten behalten ihre Knoten
 * (d) Nach 3 Update-Zyklen funktioniert der data-copy-val-Klick (Delegations-/Handler-Test)
 * (e) Beide Container abgedeckt (#trade-list und #ab-trades-container)
 */

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
assert(scriptMatch, 'Dashboard script block missing');

class MockNode {
  constructor(tagName = 'div') {
    this.tagName = String(tagName).toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.attributes = new Map();
    this.classList = {
      _set: new Set(),
      add: (...cls) => cls.forEach(c => c && this.classList._set.add(c)),
      remove: (...cls) => cls.forEach(c => this.classList._set.delete(c)),
      toggle: (c, force) => {
        if (force === true) this.classList._set.add(c);
        else if (force === false) this.classList._set.delete(c);
        else if (this.classList._set.has(c)) this.classList._set.delete(c);
        else this.classList._set.add(c);
      },
      contains: c => this.classList._set.has(c)
    };
    this.style = {};
    this._dataset = {};
    this._listeners = new Map();
    this._textContent = '';
    this._innerHTML = '';
  }

  get firstElementChild() {
    return this.children.length > 0 ? this.children[0] : null;
  }

  get lastElementChild() {
    return this.children.length > 0 ? this.children[this.children.length - 1] : null;
  }

  isSameNode(other) {
    return this === other;
  }

  get dataset() {
    return this._dataset;
  }

  get className() {
    return Array.from(this.classList._set).join(' ');
  }

  set className(val) {
    this.classList._set.clear();
    if (typeof val === 'string') {
      val.split(/\s+/).filter(Boolean).forEach(c => this.classList._set.add(c));
    }
  }

  get textContent() {
    if (this.children.length > 0) {
      return this.children.map(c => c.textContent).join('');
    }
    return this._textContent;
  }

  set textContent(val) {
    this.children = [];
    this._textContent = String(val == null ? '' : val);
    this._innerHTML = escapeHtmlText(this._textContent);
  }

  get innerHTML() {
    if (this.children.length > 0) {
      return this.children.map(c => c.outerHTML).join('');
    }
    return this._innerHTML;
  }

  set innerHTML(val) {
    this._innerHTML = String(val == null ? '' : val);
    this.children = parseHtmlToNodes(this._innerHTML, this);
    if (this.children.length === 0) {
      this._textContent = stripHtml(this._innerHTML);
    }
  }

  get outerHTML() {
    const tag = this.tagName.toLowerCase();
    const attrs = [];
    if (this.className) attrs.push(`class="${escapeAttr(this.className)}"`);
    for (const [k, v] of this.attributes.entries()) {
      if (k !== 'class') attrs.push(`${k}="${escapeAttr(v)}"`);
    }
    for (const [k, v] of Object.entries(this._dataset)) {
      const dataAttr = 'data-' + k.replace(/[A-Z]/g, m => '-' + m.toLowerCase());
      if (!this.attributes.has(dataAttr)) {
        attrs.push(`${dataAttr}="${escapeAttr(v)}"`);
      }
    }
    const attrStr = attrs.length ? ' ' + attrs.join(' ') : '';
    return `<${tag}${attrStr}>${this.innerHTML}</${tag}>`;
  }

  setAttribute(name, val) {
    const sVal = String(val == null ? '' : val);
    this.attributes.set(name, sVal);
    if (name === 'class') {
      this.className = sVal;
    } else if (name.startsWith('data-')) {
      const camel = name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      this._dataset[camel] = sVal;
    }
  }

  getAttribute(name) {
    if (name === 'class') return this.className || null;
    if (this.attributes.has(name)) return this.attributes.get(name);
    if (name.startsWith('data-')) {
      const camel = name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      return this._dataset[camel] !== undefined ? this._dataset[camel] : null;
    }
    return null;
  }

  removeAttribute(name) {
    this.attributes.delete(name);
    if (name === 'class') this.classList._set.clear();
    if (name.startsWith('data-')) {
      const camel = name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      delete this._dataset[camel];
    }
  }

  hasAttribute(name) {
    return this.getAttribute(name) !== null;
  }

  appendChild(node) {
    if (!node) return node;
    if (node.parentNode) node.parentNode.removeChild(node);
    node.parentNode = this;
    this.children.push(node);
    return node;
  }

  insertBefore(newNode, refNode) {
    if (!newNode) return newNode;
    if (newNode.parentNode) newNode.parentNode.removeChild(newNode);
    newNode.parentNode = this;
    const idx = refNode ? this.children.indexOf(refNode) : -1;
    if (idx >= 0) {
      this.children.splice(idx, 0, newNode);
    } else {
      this.children.push(newNode);
    }
    return newNode;
  }

  removeChild(node) {
    const idx = this.children.indexOf(node);
    if (idx >= 0) {
      this.children.splice(idx, 1);
      node.parentNode = null;
    }
    return node;
  }

  remove() {
    if (this.parentNode) {
      this.parentNode.removeChild(this);
    }
  }

  replaceChildren(...nodes) {
    this.children.forEach(c => { c.parentNode = null; });
    this.children = [];
    nodes.forEach(n => {
      if (n) this.appendChild(n);
    });
  }

  addEventListener(type, handler) {
    if (!this._listeners.has(type)) this._listeners.set(type, []);
    this._listeners.get(type).push(handler);
  }

  dispatchEvent(event) {
    if (!event.target) event.target = this;
    event.currentTarget = this;
    let cur = this;
    while (cur) {
      const handlers = cur._listeners.get(event.type) || [];
      for (const h of handlers) {
        h.call(cur, event);
        if (event._stopped) return;
      }
      cur = cur.parentNode;
    }
  }

  click() {
    const ev = {
      type: 'click',
      target: this,
      currentTarget: this,
      _stopped: false,
      stopPropagation() { this._stopped = true; },
      preventDefault() {}
    };
    this.dispatchEvent(ev);
  }

  querySelector(selector) {
    const all = this.querySelectorAll(selector);
    return all.length > 0 ? all[0] : null;
  }

  querySelectorAll(selector) {
    const results = [];
    const matchFn = parseSelector(selector);
    const walk = node => {
      for (const child of node.children) {
        if (matchFn(child)) results.push(child);
        walk(child);
      }
    };
    walk(this);
    return results;
  }

  closest(selector) {
    const matchFn = parseSelector(selector);
    let cur = this;
    while (cur) {
      if (cur instanceof MockNode && matchFn(cur)) return cur;
      cur = cur.parentNode;
    }
    return null;
  }
}

function escapeHtmlText(str) {
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function escapeAttr(str) {
  return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;');
}
function stripHtml(html) {
  return String(html).replace(/<[^>]*>/g, '');
}

function parseSelector(sel) {
  sel = sel.trim();
  const parts = sel.split(/\s+/).filter(Boolean);
  if (parts.length > 1) {
    const matchers = parts.map(p => parseSimpleSelector(p));
    return node => {
      if (!matchers[matchers.length - 1](node)) return false;
      let currentMatcherIdx = matchers.length - 2;
      let cur = node.parentNode;
      while (cur && currentMatcherIdx >= 0) {
        if (matchers[currentMatcherIdx](cur)) {
          currentMatcherIdx--;
        }
        cur = cur.parentNode;
      }
      return currentMatcherIdx < 0;
    };
  }
  return parseSimpleSelector(sel);
}

function parseSimpleSelector(sel) {
  sel = sel.trim();
  if (sel.startsWith('.')) {
    const cls = sel.slice(1);
    return n => n.classList && n.classList.contains(cls);
  }
  if (sel.startsWith('#')) {
    const id = sel.slice(1);
    return n => n.getAttribute && n.getAttribute('id') === id;
  }
  if (sel.startsWith('[') && sel.endsWith(']')) {
    const inner = sel.slice(1, -1);
    if (inner.includes('=')) {
      const [k, v] = inner.split('=');
      const cleanVal = v.replace(/^['"]|['"]$/g, '');
      return n => n.getAttribute && n.getAttribute(k.trim()) === cleanVal;
    }
    return n => n.hasAttribute && n.hasAttribute(inner.trim());
  }
  return n => n.tagName && n.tagName.toLowerCase() === sel.toLowerCase();
}

function parseHtmlToNodes(html, parent) {
  const root = new MockNode('root');
  const stack = [root];
  const tagRegex = /<!--[\s\S]*?-->|<(\/)?([a-zA-Z0-9\-]+)([^>]*?)(\/)?>|([^<]+)/g;
  let match;

  while ((match = tagRegex.exec(html)) !== null) {
    if (match[0].startsWith('<!--')) {
      continue;
    }
    const isClosing = !!match[1];
    const tagName = match[2];
    const attrString = match[3];
    const isSelfClosing = !!match[4] || ['br', 'hr', 'img', 'input'].includes((tagName || '').toLowerCase());
    const textContent = match[5];

    if (textContent) {
      const top = stack[stack.length - 1];
      if (top) {
        top._textContent += textContent;
      }
      continue;
    }

    if (isClosing) {
      if (stack.length > 1) {
        const top = stack[stack.length - 1];
        if (top.tagName.toLowerCase() === tagName.toLowerCase()) {
          stack.pop();
        } else {
          for (let i = stack.length - 1; i >= 1; i--) {
            if (stack[i].tagName.toLowerCase() === tagName.toLowerCase()) {
              stack.splice(i);
              break;
            }
          }
        }
      }
      continue;
    }

    if (tagName) {
      const node = new MockNode(tagName);
      const top = stack[stack.length - 1];
      if (top) {
        top.appendChild(node);
      }

      if (attrString) {
        const attrRegex = /([a-zA-Z0-9\-]+)(?:=(?:"([^"]*)"|'([^']*)'|([^>\s]+)))?/g;
        let attrMatch;
        while ((attrMatch = attrRegex.exec(attrString)) !== null) {
          const k = attrMatch[1];
          const v = attrMatch[2] !== undefined ? attrMatch[2] : (attrMatch[3] !== undefined ? attrMatch[3] : (attrMatch[4] !== undefined ? attrMatch[4] : ''));
          node.setAttribute(k, v);
        }
      }

      if (!isSelfClosing) {
        stack.push(node);
      }
    }
  }

  for (const child of root.children) {
    child.parentNode = parent;
  }
  return root.children;
}

function createDOMEnvironment() {
  const elements = new Map();
  const getOrCreate = id => {
    if (!elements.has(id)) {
      const el = new MockNode('div');
      el.setAttribute('id', id);
      elements.set(id, el);
    }
    return elements.get(id);
  };

  const document = {
    getElementById: getOrCreate,
    querySelector: sel => parseSelector(sel),
    querySelectorAll: sel => [],
    createElement: tag => new MockNode(tag),
    createDocumentFragment: () => new MockNode('fragment'),
    body: new MockNode('body'),
    addEventListener: () => {},
    removeEventListener: () => {},
    activeElement: null
  };

  const store = {};
  const clipboard = { text: '' };

  const ctx = {
    console, JSON, Math, Date, Promise, Set, Map, Number, String, Array, Object,
    document,
    window: {
      addEventListener: () => {},
      requestAnimationFrame: cb => { cb(); return 1; },
      confirm: () => true
    },
    navigator: {
      clipboard: {
        writeText: async t => { clipboard.text = t; }
      }
    },
    localStorage: {
      getItem: k => store[k] !== undefined ? store[k] : null,
      setItem: (k, v) => { store[k] = String(v); },
      removeItem: k => { delete store[k]; }
    },
    requestAnimationFrame: cb => { cb(); return 1; },
    cancelAnimationFrame: () => {},
    setTimeout: (cb, ms) => { cb(); return 1; },
    clearTimeout: () => {},
    setInterval: () => 1,
    clearInterval: () => {},
    fetch: async () => ({ ok: true, json: async () => ({}) }),
    $: id => getOrCreate(id),
    location: { protocol: 'http:', host: '127.0.0.1:8787' }
  };

  vm.createContext(ctx);
  vm.runInContext(
    scriptMatch[1] +
    '; this.loadTrades = loadTrades; this.saveTrades = saveTrades; this.renderLiveTrades = renderLiveTrades; this.Autobot = Autobot; this.tradePrices = tradePrices; this.TRADE_KEY = TRADE_KEY;',
    ctx
  );

  return { ctx, elements, clipboard, store };
}

(async () => {
  console.log('=== PF-50: DOM-STABLE TRADE CARDS TEST SUITE ===');

  const { ctx, elements, clipboard, store } = createDOMEnvironment();

  // ──────────────────────────────────────────────────────────
  // 1. Live-Tracker (#trade-list) Stability Tests
  // ──────────────────────────────────────────────────────────
  console.log('[1. Live-Tracker: #trade-list Container]');

  const tradeA = {
    id: 't-sol-1',
    coin: 'SOLUSDT',
    dir: 1,
    entry: 100.00,
    initialSl: 95.00,
    currentSl: 95.00,
    tp: 110.00,
    tp1: 105.00,
    margin: 50.00,
    initialMargin: 50.00,
    leverage: 10,
    openedAt: Date.now() - 120000,
    beActive: false,
    trailSl: false
  };

  const tradeB = {
    id: 't-btc-2',
    coin: 'BTCUSDT',
    dir: -1,
    entry: 60000.00,
    initialSl: 62000.00,
    currentSl: 62000.00,
    tp: 56000.00,
    tp1: 58000.00,
    margin: 100.00,
    initialMargin: 100.00,
    leverage: 20,
    openedAt: Date.now() - 300000,
    beActive: false,
    trailSl: false
  };

  // Setup initial trades
  ctx.saveTrades([tradeA, tradeB]);
  ctx.tradePrices['SOLUSDT'] = 102.00;
  ctx.tradePrices['BTCUSDT'] = 59500.00;

  // Cycle 1: First render
  ctx.renderLiveTrades();
  const tradeListEl = elements.get('trade-list');
  const cards1 = tradeListEl.querySelectorAll('.trade-card');
  assert.strictEqual(cards1.length, 2, 'Initial render must have 2 cards');
  const cardNodeA1 = cards1[0];
  const cardNodeB1 = cards1[1];
  assert.strictEqual(cardNodeA1.getAttribute('data-trade-id'), 't-sol-1');
  assert.strictEqual(cardNodeB1.getAttribute('data-trade-id'), 't-btc-2');

  // (a) Test: Two renders with identical data -> card nodes identical (isSameNode)
  ctx.renderLiveTrades();
  const cards2 = tradeListEl.querySelectorAll('.trade-card');
  assert.strictEqual(cards2.length, 2);
  assert(cards2[0].isSameNode(cardNodeA1), 'Card A node must be identical across renders (isSameNode)');
  assert(cards2[1].isSameNode(cardNodeB1), 'Card B node must be identical across renders (isSameNode)');
  console.log('  PASS  (a) Identical data renders preserve DOM card nodes via isSameNode');

  // (b) Test: Price change -> text nodes updated, card node remains the same
  ctx.tradePrices['SOLUSDT'] = 108.00; // price pump
  ctx.renderLiveTrades();
  const cards3 = tradeListEl.querySelectorAll('.trade-card');
  assert(cards3[0].isSameNode(cardNodeA1), 'Card A node must remain same object after price change');
  const priceElA = cards3[0].querySelector('.tc-grid .tc-item:nth-child(2) b') || cards3[0].querySelector('.tc-grid');
  assert(priceElA.textContent.includes('108.00'), 'Price text must reflect updated price 108.00');
  const pnlElA = cards3[0].querySelector('.tc-pnl span');
  assert(pnlElA && pnlElA.textContent.includes('USDT'), 'PnL text must update in-place');
  console.log('  PASS  (b) Price change updates text in-place without rebuilding card nodes');

  // (c) Test: Trade open/close -> card appears/disappears, remaining cards keep their nodes
  const tradeC = {
    id: 't-eth-3',
    coin: 'ETHUSDT',
    dir: 1,
    entry: 3000.00,
    initialSl: 2900.00,
    currentSl: 2900.00,
    tp: 3200.00,
    margin: 80.00,
    initialMargin: 80.00,
    leverage: 10,
    openedAt: Date.now() - 50000
  };
  ctx.tradePrices['ETHUSDT'] = 3050.00;

  // Add Trade C
  ctx.saveTrades([tradeA, tradeB, tradeC]);
  ctx.renderLiveTrades();
  const cardsAfterAdd = tradeListEl.querySelectorAll('.trade-card');
  assert.strictEqual(cardsAfterAdd.length, 3, 'Must have 3 cards after adding trade C');
  assert(cardsAfterAdd[0].isSameNode(cardNodeA1), 'Card A must still keep its original node');
  assert(cardsAfterAdd[1].isSameNode(cardNodeB1), 'Card B must still keep its original node');
  const cardNodeC = cardsAfterAdd[2];
  assert.strictEqual(cardNodeC.getAttribute('data-trade-id'), 't-eth-3');

  // Remove Trade A (close trade)
  ctx.saveTrades([tradeB, tradeC]);
  ctx.renderLiveTrades();
  const cardsAfterRemove = tradeListEl.querySelectorAll('.trade-card');
  assert.strictEqual(cardsAfterRemove.length, 2, 'Must have 2 cards after removing trade A');
  assert(cardsAfterRemove[0].isSameNode(cardNodeB1), 'Card B must retain its node when A is removed');
  assert(cardsAfterRemove[1].isSameNode(cardNodeC), 'Card C must retain its node when A is removed');
  console.log('  PASS  (c) Trade open/close inserts/removes cards while retaining unchanged nodes');

  // (d) Test: Interaction stability (data-copy-val click works after 3 update cycles)
  for (let cycle = 1; cycle <= 3; cycle++) {
    ctx.tradePrices['BTCUSDT'] = 59000.00 - cycle * 100;
    ctx.renderLiveTrades();
  }
  const currentCards = tradeListEl.querySelectorAll('.trade-card');
  assert(currentCards[0].isSameNode(cardNodeB1), 'Card B persists through 3 cycles');
  const copyValSpan = currentCards[0].querySelector('[data-copy-val]');
  assert(copyValSpan, 'Copyable value element must exist on Card B');
  const copyVal = copyValSpan.getAttribute('data-copy-val');
  assert.ok(copyVal, 'data-copy-val must not be empty');
  // Dispatch click on the copyable span
  copyValSpan.click();
  assert.strictEqual(clipboard.text, copyVal, 'Clicking data-copy-val must copy text to clipboard after 3 cycles');
  console.log('  PASS  (d) Interactive data-copy-val click works cleanly after 3 update cycles');

  // ──────────────────────────────────────────────────────────
  // 2. Autobot (#ab-trades-container) Stability Tests
  // ──────────────────────────────────────────────────────────
  console.log('[2. Autobot: #ab-trades-container]');

  const abTrade1 = {
    id: 'ab-sol-1',
    coin: 'SOLUSDT',
    dir: 1,
    entry: 100.00,
    initialSl: 95.00,
    currentSl: 95.00,
    tp1: 105.00,
    tp2: 110.00,
    margin: 50.00,
    initialMargin: 50.00,
    notional: 500.00,
    leverage: 10,
    openedAt: Date.now() - 100000,
    score: 82,
    setupDsr: 0.74,
    timeStopBars: 12,
    signalTf: '1h',
    beActive: false
  };

  const abTrade2 = {
    id: 'ab-eth-2',
    coin: 'ETHUSDT',
    dir: -1,
    entry: 3000.00,
    initialSl: 3100.00,
    currentSl: 3100.00,
    tp1: 2900.00,
    tp2: 2800.00,
    margin: 100.00,
    initialMargin: 100.00,
    notional: 1000.00,
    leverage: 10,
    openedAt: Date.now() - 200000,
    score: 79,
    setupDsr: 0.65,
    timeStopBars: 12,
    signalTf: '1h',
    beActive: false
  };

  ctx.Autobot.trades = [abTrade1, abTrade2];
  ctx.tradePrices['SOLUSDT'] = 101.50;
  ctx.tradePrices['ETHUSDT'] = 2980.00;

  // Cycle 1: Render Autobot
  ctx.Autobot.render();
  const abContainerEl = elements.get('ab-trades-container');
  const abCards1 = abContainerEl.querySelectorAll('.trade-card');
  assert.strictEqual(abCards1.length, 2, 'Initial autobot render must have 2 cards');
  const abCardNode1_1 = abCards1[0];
  const abCardNode2_1 = abCards1[1];
  assert.strictEqual(abCardNode1_1.getAttribute('data-trade-id'), 'ab-sol-1');
  assert.strictEqual(abCardNode2_1.getAttribute('data-trade-id'), 'ab-eth-2');

  // (a) Autobot: 2 Renders with identical data
  ctx.Autobot.render();
  const abCards2 = abContainerEl.querySelectorAll('.trade-card');
  assert.strictEqual(abCards2.length, 2);
  assert(abCards2[0].isSameNode(abCardNode1_1), 'Autobot Card 1 must be identical node (isSameNode)');
  assert(abCards2[1].isSameNode(abCardNode2_1), 'Autobot Card 2 must be identical node (isSameNode)');
  console.log('  PASS  (a) Autobot identical renders preserve DOM card nodes via isSameNode');

  // (b) Autobot: Price change -> text in-place update
  ctx.tradePrices['SOLUSDT'] = 106.00; // TP1 reached
  ctx.Autobot.render();
  const abCards3 = abContainerEl.querySelectorAll('.trade-card');
  assert(abCards3[0].isSameNode(abCardNode1_1), 'Autobot Card 1 must retain node on price change');
  const abPriceA = abCards3[0].querySelector('.tc-grid');
  assert(abPriceA.textContent.includes('106.00'), 'Autobot price must update to 106.00');
  console.log('  PASS  (b) Autobot price change updates text in-place without rebuilding card nodes');

  // (c) Autobot: Trade open/close
  const abTrade3 = {
    id: 'ab-btc-3',
    coin: 'BTCUSDT',
    dir: 1,
    entry: 65000.00,
    initialSl: 64000.00,
    currentSl: 64000.00,
    tp1: 67000.00,
    margin: 200.00,
    initialMargin: 200.00,
    notional: 2000.00,
    leverage: 10,
    openedAt: Date.now() - 30000,
    score: 88,
    setupDsr: 0.81,
    timeStopBars: 12,
    signalTf: '4h'
  };
  ctx.tradePrices['BTCUSDT'] = 65500.00;

  // Add abTrade3
  ctx.Autobot.trades = [abTrade1, abTrade2, abTrade3];
  ctx.Autobot.render();
  const abCardsAdd = abContainerEl.querySelectorAll('.trade-card');
  assert.strictEqual(abCardsAdd.length, 3);
  assert(abCardsAdd[0].isSameNode(abCardNode1_1), 'AB Card 1 retained');
  assert(abCardsAdd[1].isSameNode(abCardNode2_1), 'AB Card 2 retained');
  const abCardNode3 = abCardsAdd[2];
  assert.strictEqual(abCardNode3.getAttribute('data-trade-id'), 'ab-btc-3');

  // Remove abTrade1
  ctx.Autobot.trades = [abTrade2, abTrade3];
  ctx.Autobot.render();
  const abCardsRem = abContainerEl.querySelectorAll('.trade-card');
  assert.strictEqual(abCardsRem.length, 2);
  assert(abCardsRem[0].isSameNode(abCardNode2_1), 'AB Card 2 retained after removing Card 1');
  assert(abCardsRem[1].isSameNode(abCardNode3), 'AB Card 3 retained after removing Card 1');
  console.log('  PASS  (c) Autobot open/close inserts/removes cards while retaining unchanged nodes');

  // (d) Autobot: Interaction stability after 3 update cycles
  for (let cycle = 1; cycle <= 3; cycle++) {
    ctx.tradePrices['ETHUSDT'] = 2950.00 - cycle * 10;
    ctx.Autobot.render();
  }
  const finalAbCards = abContainerEl.querySelectorAll('.trade-card');
  assert(finalAbCards[0].isSameNode(abCardNode2_1), 'AB Card 2 node persisted across all cycles');
  const abCopyValSpan = finalAbCards[0].querySelector('[data-copy-val]');
  assert(abCopyValSpan, 'AB copyable value element must exist');
  const abCopyVal = abCopyValSpan.getAttribute('data-copy-val');
  assert.ok(abCopyVal, 'AB data-copy-val must not be empty');
  abCopyValSpan.click();
  assert.strictEqual(clipboard.text, abCopyVal, 'Clicking data-copy-val on autobot card copies text correctly');
  console.log('  PASS  (d) Interactive copy works cleanly on autobot card after 3 cycles');

  console.log('  PASS  (e) Both containers (#trade-list and #ab-trades-container) fully covered');
  console.log('\n============================================================');
  console.log('ERGEBNIS: PF-50 DOM STABILITY ALL CHECKS PASSED');
  console.log('============================================================');
})().catch(err => {
  console.error('FAIL PF-50:', err);
  process.exitCode = 1;
});
