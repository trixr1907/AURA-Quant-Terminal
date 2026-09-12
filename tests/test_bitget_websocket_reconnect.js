'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const start = html.indexOf('const BITGET_CANDLE_CHANNELS = {');
const end = html.indexOf('\nfunction resetMarketState()', start);
assert(start >= 0 && end > start, 'WebSocket feed block missing');
const source = html.slice(start, end);

const sockets = [];
const timers = new Map();
let nextTimer = 1;
const prices = {};

function WebSocket(url) {
  this.url = url;
  this.sent = [];
  this.readyState = 1;
  this.send = payload => {
    try {
      this.sent.push(JSON.parse(payload));
    } catch (e) {
      this.sent.push(payload);
    }
  };
  this.close = () => {
    this.readyState = 3;
  };
  sockets.push(this);
}

const App = {
  gen: 3,
  symbol: 'BTCUSDT',
  chartTF: '1h',
  data: {
    candles: [{ t: 1000, o: 100, h: 101, l: 99, c: 100, v: 5, tbv: 2 }],
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
  Date,
  tradePrices: prices,
  setTimeout(fn, delay) {
    const id = nextTimer++;
    timers.set(id, { fn, delay });
    return id;
  },
  clearTimeout(id) { timers.delete(id); },
  setInterval(fn, delay) {
    const id = nextTimer++;
    timers.set(id, { fn, delay, interval: true });
    return id;
  },
  clearInterval(id) { timers.delete(id); },
  setWs(st) { App.status.ws = st; },
  renderFeedStatus() {},
  analyze() { return { ok: true }; },
  backtest() { return []; },
  renderPrice() {},
  renderChart() {},
  scheduleLiveTradesRender() {},
  renderAll() {},
};
vm.createContext(context);
vm.runInContext(`${source}; this.connectWS = connectWS; this.WS_FEEDS = WS_FEEDS;`, context);

// 1. Initial Connection: picks Bitget
context.connectWS();
const bitget = sockets[0];
assert(bitget, 'Bitget socket missing');
assert.strictEqual(bitget.url, 'wss://ws.bitget.com/v2/ws/public');
bitget.onopen();
assert.deepStrictEqual(bitget.sent[0], {
  op: 'subscribe',
  args: [{ instType: 'USDT-FUTURES', channel: 'candle1H', instId: 'BTCUSDT' }],
});

// 2. Incoming Bitget message updates live candle and ticker
bitget.onmessage({ data: JSON.stringify({
  action: 'update',
  arg: { instType: 'USDT-FUTURES', channel: 'candle1H', instId: 'BTCUSDT' },
  data: [['1000', '100', '106', '98', '104', '12', '1248']],
}) });
assert.strictEqual(App.data.candles.length, 1, 'live candle should replace matching timestamp');
assert.strictEqual(App.data.candles[0].c, 104, 'Bitget close should update live candle');
assert.strictEqual(App.data.candles[0].v, 12, 'Bitget base volume should update live candle');
assert.strictEqual(App.data.candles[0].tbv, null, 'Bitget must leave taker-buy volume empty for range CVD');
assert.strictEqual(App.data.ticker.price, 104, 'ticker should follow Bitget live close');
assert.strictEqual(App.data.ticker.src, 'bitget-ws');
assert.strictEqual(prices.BTCUSDT, 104, 'selected trade price should follow WebSocket');

// 3. PF-20: Sticky-Socket on Symbol Switch with open Bitget connection
App.symbol = 'ETHUSDT';
context.connectWS();
assert.strictEqual(sockets.length, 1, 'sticky-socket must reuse existing Bitget connection without reconnect churn');
assert.deepStrictEqual(bitget.sent[1], {
  op: 'unsubscribe',
  args: [{ instType: 'USDT-FUTURES', channel: 'candle1H', instId: 'BTCUSDT' }],
}, 'sticky-socket must unsubscribe previous symbol');
assert.deepStrictEqual(bitget.sent[2], {
  op: 'subscribe',
  args: [{ instType: 'USDT-FUTURES', channel: 'candle1H', instId: 'ETHUSDT' }],
}, 'sticky-socket must subscribe new symbol');

// 4. Bitget drops; retry attempt to Bitget fails, advancing to Binance fallback
bitget.onclose();
const firstReconnect = [...timers.values()].find(timer => timer.delay === 2500);
assert(firstReconnect, 'Bitget drop must schedule reconnect in 2.5 seconds');
timers.delete(1);
firstReconnect.fn();
const bitgetRetry = sockets[1];
assert.strictEqual(bitgetRetry.url, 'wss://ws.bitget.com/v2/ws/public', 'first reconnect attempt after drop tries Bitget');

// Bitget retry fails to connect
bitgetRetry.onclose();
const secondReconnect = [...timers.values()].find(timer => timer.delay === 2500);
assert(secondReconnect, 'failed Bitget retry must schedule next fallback in 2.5 seconds');
secondReconnect.fn();
const binance = sockets[2];
assert(binance, 'Binance fallback socket missing');
assert.strictEqual(binance.url, 'wss://stream.binance.com:9443/ws/ethusdt@kline_1h');

// Binance message handling
binance.onmessage({ data: JSON.stringify({
  k: { s: 'ETHUSDT', i: '1h', t: 2000, o: '104', h: '107', l: '103', c: '106', v: '8', V: '5' },
}) });
assert.strictEqual(App.data.candles.length, 2, 'new Binance fallback candle should append');
assert.strictEqual(App.data.candles[1].tbv, 5, 'Binance fallback should preserve taker-buy volume');
assert.strictEqual(App.data.ticker.src, 'binance-fallback');

// 5. Successful open on fallback resets wsTry (PF-18)
binance.onopen();
assert.strictEqual(App.status.wsSource, 'binance-fallback');

// If a clean restart / new connection happens after successful open, it starts back at Bitget
binance.onclose();
App.ws = null;
App.status.ws = 'off';
context.connectWS();
const reconnectedBitget = sockets[3];
assert(reconnectedBitget, 'clean reconnect after successful fallback open must select Bitget as 1st choice');
assert.strictEqual(reconnectedBitget.url, 'wss://ws.bitget.com/v2/ws/public');

console.log('PASS Bitget WebSocket live candle, CVD semantics, and fallback reconnect');
