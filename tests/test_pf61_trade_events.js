'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function createContext(initialTrades = []) {
  const store = { 'aura-quant-terminal-active-trades-v1': JSON.stringify(initialTrades) };
  const emitted = [];
  const ctx = {
    console, JSON, Math, Date, Promise, Set, Map, Number, String, Array, Object,
    localStorage: {
      getItem: key => store[key] === undefined ? null : store[key],
      setItem: (key, value) => { store[key] = String(value); },
      removeItem: key => { delete store[key]; },
    },
    document: { getElementById: () => null, querySelectorAll: () => [], addEventListener: () => {}, body: { classList: { toggle: () => {} } } },
    window: { addEventListener: () => {}, requestAnimationFrame: cb => { cb(); return 1; } },
    requestAnimationFrame: cb => { cb(); return 1; },
    setInterval: () => 1,
    setTimeout: cb => { cb(); return 1; },
    clearTimeout: () => {},
    fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }),
    location: { search: '' },
    $: () => null,
  };
  vm.createContext(ctx);
  vm.runInContext(`${script}; this.normalizeTrade=normalizeTrade; this.detectTradeEvents=detectTradeEvents; this.loadTrades=loadTrades; this.NtfySignals=NtfySignals; this.emitTradeEvents=emitTradeEvents; this.notifyTradeCloseOnce=notifyTradeCloseOnce;`, ctx);
  ctx.NtfySignals.emitTradeEvent = async (trade, event, detail) => { emitted.push({ trade, event, detail }); return true; };
  return { ctx, store, emitted };
}

(async () => {
  const base = {
    id: 'trade-once', coin: 'XPNUSDT', dir: -1, leverage: 3, entry: 0.000758,
    initialSl: 0.0008, currentSl: 0.0008, tp1: 0.00072, tp2: 0.00070, tp3: 0.00068,
    margin: 100, initialMargin: 100, openedAt: 1,
  };
  const { ctx, store, emitted } = createContext([base]);
  let trades = ctx.loadTrades();
  assert.strictEqual(trades[0].tp1Hit, false);
  assert.strictEqual(trades[0].tp2Hit, false);
  assert.strictEqual(trades[0].tp3Hit, false);
  assert.strictEqual(trades[0].closeNotified, false);
  assert.strictEqual(trades[0].openNotified, false);

  assert.deepStrictEqual(Array.from(ctx.detectTradeEvents(trades[0], 0.000712)), ['tp1']);
  await ctx.emitTradeEvents(trades[0], 0.000712);
  store['aura-quant-terminal-active-trades-v1'] = JSON.stringify(trades);
  trades = ctx.loadTrades();
  assert.strictEqual(trades[0].tp1Hit, true, 'TP1 once flag must survive reload');
  assert.deepStrictEqual(Array.from(ctx.detectTradeEvents(trades[0], 0.000712)), [], 'same price must not emit TP1 twice');

  await ctx.emitTradeEvents(trades[0], 0.000675);
  assert.deepStrictEqual(emitted.map(item => item.event), ['tp1', 'tp2', 'tp3']);
  assert.strictEqual(trades[0].tp2Hit, true);
  assert.strictEqual(trades[0].tp3Hit, true);

  const closeTrade = ctx.normalizeTrade({ ...base, id: 'close-once' });
  assert.strictEqual(ctx.notifyTradeCloseOnce(closeTrade, 0.0008, 'SL_HIT'), true);
  await Promise.resolve();
  assert.strictEqual(emitted[3].event, 'sl_close', 'close helper must emit before its once flag suppresses the event');
  assert.strictEqual(ctx.notifyTradeCloseOnce(closeTrade, 0.0008, 'SL_HIT'), false);
  assert.strictEqual(emitted.length, 4, 'PF-33-compatible close path must emit only once');

  const slTrade = ctx.normalizeTrade({ ...base, id: 'sl', dir: 1, entry: 100, initialSl: 95, currentSl: 97, tp1: 105 });
  assert.deepStrictEqual(Array.from(ctx.detectTradeEvents(slTrade, 97)), ['sl_close']);
  assert.deepStrictEqual(Array.from(ctx.detectTradeEvents(slTrade, 96)), ['sl_close'], 'long currentSl touch is direction aware');
  const shortSl = ctx.normalizeTrade({ ...base, id: 'short-sl', dir: -1, entry: 100, initialSl: 105, currentSl: 103, tp1: 95 });
  assert.deepStrictEqual(Array.from(ctx.detectTradeEvents(shortSl, 103)), ['sl_close']);

  assert.match(html, /NtfySignals\.emitTradeEvent\(newTrade, 'open'/, 'manual and autobot open paths must emit');
  assert.match(html, /text\.includes\('TIME_STOP'\)[\s\S]*other_close/, 'Time-Stop must be an other_close reason');
  assert.match(html, /closeNotified/, 'close flag must be persisted on trade objects');

  console.log('PASS PF-61 trade events: once flags, reload, direction-aware SL and all open/close paths');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
