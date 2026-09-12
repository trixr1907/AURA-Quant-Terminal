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
  this.send = payload => this.sent.push(JSON.parse(payload));
  this.close = () => {};
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
  status: { ws: '' },
  ws: null,
  wsTimer: null,
  reanaTimer: null,
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

context.connectWS();
const bitget = sockets[0];
assert(bitget, 'Bitget socket missing');
assert.strictEqual(bitget.url, 'wss://ws.bitget.com/v2/ws/public');
bitget.onopen();
assert.deepStrictEqual(bitget.sent[0], {
  op: 'subscribe',
  args: [{ instType: 'USDT-FUTURES', channel: 'candle1H', instId: 'BTCUSDT' }],
});

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

bitget.onclose();
const firstReconnect = [...timers.values()].find(timer => timer.delay === 2500);
assert(firstReconnect, 'Bitget drop must schedule fallback in 2.5 seconds');
firstReconnect.fn();
const binance = sockets[1];
assert(binance, 'Binance fallback socket missing');
assert.strictEqual(binance.url, 'wss://stream.binance.com:9443/ws/btcusdt@kline_1h');

binance.onmessage({ data: JSON.stringify({
  k: { t: 2000, o: '104', h: '107', l: '103', c: '106', v: '8', V: '5' },
}) });
assert.strictEqual(App.data.candles.length, 2, 'new Binance fallback candle should append');
assert.strictEqual(App.data.candles[1].tbv, 5, 'Binance fallback should preserve taker-buy volume');
assert.strictEqual(App.data.ticker.src, 'binance-fallback');

binance.onclose();
const secondReconnect = [...timers.values()].find(timer => timer.delay === 2500);
assert(secondReconnect, 'first Binance failure must advance to mirror without 15 second delay');

console.log('PASS Bitget WebSocket live candle, CVD semantics, and fallback reconnect');
