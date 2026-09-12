'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const start = html.indexOf('const BITGET_CANDLE_CHANNELS = {');
const end = html.indexOf('\nfunction buildSymbols()', start);
assert(start >= 0 && end > start, 'WebSocket source block missing');
const source = html.slice(start, end);

const sockets = [];
const timers = new Map();
let nextTimer = 1;
const renderCalls = { price: 0, chart: 0, trades: 0, all: 0 };

function WebSocket(url) {
  this.url = url;
  this.close = () => {};
  sockets.push(this);
}

const App = {
  gen: 7,
  symbol: 'BTCUSDT',
  chartTF: '1h',
  data: {
    candles: [{ t: 1, o: 100, h: 101, l: 99, c: 100, v: 1, tbv: 0 }],
    ticker: { price: 100 },
    chart: null,
    bt: [],
  },
  status: { ws: '', wsSource: '' },
  ws: null,
  wsTimer: null,
  reanaTimer: null,
  wsPingTimer: null,
  wsSub: null,
  wsFeedKind: null,
};

const context = {
  App,
  WebSocket,
  JSON,
  setTimeout(fn) {
    const id = nextTimer++;
    timers.set(id, fn);
    return id;
  },
  clearTimeout(id) { timers.delete(id); },
  setInterval(fn) {
    const id = nextTimer++;
    timers.set(id, fn);
    return id;
  },
  clearInterval(id) { timers.delete(id); },
  setWs() {},
  renderFeedStatus() {},
  analyze() { return { ok: true }; },
  backtest() { return []; },
  renderPrice() { renderCalls.price++; },
  renderChart() { renderCalls.chart++; },
  scheduleLiveTradesRender() { renderCalls.trades++; },
  renderAll() { renderCalls.all++; },
};
vm.createContext(context);
vm.runInContext(`${source}; this.connectWS = connectWS; this.resetMarketState = resetMarketState;`, context);

context.connectWS();
const oldSocket = sockets[0];
assert(oldSocket, 'first socket missing');

oldSocket.close();
App.ws = null;
App.gen += 1;
App.symbol = 'ETHUSDT';
App.chartTF = '4h';
context.connectWS();
const currentSocket = sockets[1];
assert(currentSocket, 'second socket missing');

const staleEvent = {
  data: JSON.stringify({
    k: { t: 2, o: '999', h: '1001', l: '998', c: '1000', v: '5', V: '2' },
  }),
};
oldSocket.onmessage(staleEvent);

assert.strictEqual(App.data.candles.length, 1, 'stale socket must not append a candle');
assert.strictEqual(App.data.ticker.price, 100, 'stale socket must not overwrite ticker');
assert.deepStrictEqual(renderCalls, { price: 0, chart: 0, trades: 0, all: 0 }, 'stale socket must not render');
assert.strictEqual(timers.size, 0, 'stale socket must not schedule reanalysis');

assert.strictEqual(typeof context.resetMarketState, 'function', 'resetMarketState missing');
App.data = {
  chart: { stale: true }, candles: [{ t: 9 }], ticker: { price: 999 },
  mtf: { '1h': { ok: true } }, crypto: { stale: true }, wf: { stale: true },
  bt: [{ stale: true }], probMap: { stale: true }, live: { longSig: true },
  chartSrc: 'OLD_SOURCE',
};
App.spec = { symbol: 'BTCUSDT' };
App.specSym = 'BTCUSDT';
App.status = { bin: 'OLD', ws: 'live' };
context.resetMarketState();
assert.strictEqual(App.data.chart, null, 'chart must clear before symbol/TF reload');
assert.strictEqual(App.data.candles, null, 'candles must clear before symbol/TF reload');
assert.strictEqual(App.data.ticker, null, 'ticker must clear before symbol/TF reload');
assert.strictEqual(Object.keys(App.data.mtf).length, 0, 'MTF state must clear before symbol/TF reload');
assert.strictEqual(App.data.crypto, null, 'crypto state must clear before symbol/TF reload');
assert.strictEqual(App.data.wf, null, 'walk-forward state must clear before symbol/TF reload');
assert.strictEqual(App.data.bt.length, 0, 'backtest trades must clear before symbol/TF reload');
assert.strictEqual(App.data.probMap, null, 'probability map must clear before symbol/TF reload');
assert.strictEqual(App.data.live, null, 'live decision must clear before symbol/TF reload');
assert.strictEqual(App.data.chartSrc, null, 'chart source must clear before symbol/TF reload');
assert.strictEqual(App.spec, null, 'contract spec must clear before symbol reload');
assert.strictEqual(App.specSym, null, 'contract spec symbol must clear before symbol reload');
assert.strictEqual(App.status.bin, 'DATA_LOADING');
assert.strictEqual(App.status.ws, 'DATA_LOADING');

console.log('PASS WebSocket generation guard and market-state reset');
