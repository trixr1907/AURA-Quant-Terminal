'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
assert(scriptMatch, 'Dashboard script block not found');

function createContext() {
  const store = {};
  const elements = {};
  const makeElement = () => ({
    textContent: '',
    className: '',
    style: {},
    dataset: {},
    children: [],
    appendChild(node) { this.children.push(node); return node; },
    append: () => {},
    replaceChildren(...nodes) { this.children = nodes; },
    querySelectorAll: () => [],
    addEventListener: () => {},
    setAttribute: () => {},
    getAttribute: () => null,
    classList: { add: () => {}, remove: () => {}, toggle: () => {}, contains: () => false },
  });
  const document = {
    getElementById(id) { return elements[id] || (elements[id] = makeElement()); },
    querySelectorAll: () => [],
    addEventListener: () => {},
    createElement: () => makeElement(),
    createDocumentFragment: () => makeElement(),
    body: makeElement(),
  };
  const ctx = {
    console,
    JSON,
    Math,
    Date,
    Promise,
    Set,
    Map,
    Number,
    String,
    Array,
    Object,
    localStorage: {
      getItem: key => store[key] === undefined ? null : store[key],
      setItem: (key, value) => { store[key] = String(value); },
      removeItem: key => { delete store[key]; },
    },
    document,
    window: { addEventListener: () => {}, requestAnimationFrame: callback => { callback(); return 1; } },
    requestAnimationFrame: callback => { callback(); return 1; },
    setInterval: () => 1,
    setTimeout: callback => { callback(); return 1; },
    fetch: async () => ({ ok: true, json: async () => ({ ok: true, data: { _rev: 1 } }) }),
    $: id => document.getElementById(id),
  };
  vm.createContext(ctx);
  vm.runInContext(`${scriptMatch[1]}; this.SyncEngine = SyncEngine; this.Autobot = Autobot; this.AUTOBOT_KEY = AUTOBOT_KEY;`, ctx);
  return { ctx, store };
}

(async () => {
  const { ctx, store } = createContext();
  const trade = { id: 'stable-open-trade', coin: 'BTCUSDT', entry: 100, dir: 1, margin: 10, initialMargin: 10, notional: 100, leverage: 10, initialSl: 90, currentSl: 90 };
  const frames = [];
  ctx.Autobot.trades = [trade];
  ctx.Autobot.render = () => frames.push(ctx.Autobot.trades.map(item => item.id));
  store[ctx.AUTOBOT_KEY] = JSON.stringify({ trades: [trade] });
  ctx.SyncEngine.bootstrapped = true;
  ctx.fetch = async () => ({
    ok: true,
    json: async () => ({ ok: true, data: { _rev: 2, [ctx.AUTOBOT_KEY]: { trades: [] } } }),
  });

  await ctx.SyncEngine.pull();
  ctx.Autobot.render();

  assert.deepStrictEqual(Array.from(ctx.Autobot.trades, item => item.id), [trade.id], 'normal pull must retain an unacknowledged active trade absent from an empty snapshot');
  assert(frames.every(ids => ids.length > 0), 'render must never observe an empty active-position frame during a transient pull');

  ctx.SyncEngine.applyServerState({ _rev: 3, [ctx.AUTOBOT_KEY]: { trades: [] } }, false, { authoritativeAutobot: true });
  assert.strictEqual(ctx.Autobot.trades.length, 0, 'an authoritative ACK/delete must still remove the active trade');

  assert(!/container\.innerHTML\s*=/.test(html.slice(html.indexOf('render() {', html.indexOf('const Autobot')), html.indexOf('renderLogs() {', html.indexOf('const Autobot')))), 'Autobot cards must not use innerHTML replacement');
  assert(/createDocumentFragment\(\)/.test(html) && /replaceChildren\(/.test(html), 'Autobot cards must be replaced atomically with a DocumentFragment');

  console.log('PASS PF-31 zero-transient reconciliation and atomic card rendering');
})().catch(error => {
  console.error(`FAIL PF-31 zero-transient: ${error.message}`);
  process.exitCode = 1;
});
