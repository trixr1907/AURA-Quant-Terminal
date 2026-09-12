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
const intervals = new Map();
let nextInterval = 1;
const timers = new Map();
let nextTimer = 1;

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
  gen: 1,
  symbol: 'BTCUSDT',
  chartTF: '1h',
  data: {
    candles: [{ t: 1000, o: 100, h: 101, l: 99, c: 100, v: 5, tbv: null }],
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
  tradePrices: {},
  setTimeout(fn, delay) {
    const id = nextTimer++;
    timers.set(id, { fn, delay });
    return id;
  },
  clearTimeout(id) { timers.delete(id); },
  setInterval(fn, delay) {
    const id = nextInterval++;
    intervals.set(id, { fn, delay });
    return id;
  },
  clearInterval(id) {
    intervals.delete(id);
  },
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

// 1. Bitget WebSocket connection starts 25s keepalive ping interval
context.connectWS();
const bitget = sockets[0];
assert(bitget, 'Bitget socket missing');
assert.strictEqual(bitget.url, 'wss://ws.bitget.com/v2/ws/public');

assert.strictEqual(App.wsPingTimer, null, 'keepalive timer should not start before open');
bitget.onopen();
assert.ok(App.wsPingTimer != null, 'keepalive interval timer must be set on Bitget open');
const pingInterval = intervals.get(App.wsPingTimer);
assert(pingInterval, 'interval entry must exist in timers');
assert.strictEqual(pingInterval.delay, 25000, 'Bitget keepalive ping must fire every 25 seconds');

// 2. Interval trigger sends application-level 'ping' string (Bitget protocol)
pingInterval.fn();
assert.ok(bitget.sent.includes('ping'), "ws.send('ping') must be executed on keepalive tick");

// 3. Bitget responds with 'pong' — must be handled without throwing JSON parse error
assert.doesNotThrow(() => {
  bitget.onmessage({ data: 'pong' });
}, 'raw pong message must not throw SyntaxError');

assert.doesNotThrow(() => {
  bitget.onmessage({ data: '{"data":"pong"}' });
}, 'json pong message must not throw');

// 4. On socket close, keepalive interval is cleared
const timerIdBeforeClose = App.wsPingTimer;
bitget.onclose();
assert.strictEqual(intervals.has(timerIdBeforeClose), false, 'keepalive interval must be cleared on close');
assert.strictEqual(App.wsPingTimer, null, 'App.wsPingTimer must be reset to null on close');

// 5. Test error cleanup: reopen and trigger error
context.connectWS();
const bitgetErrorSocket = sockets[1];
bitgetErrorSocket.onopen();
assert.ok(App.wsPingTimer != null, 'keepalive interval timer set on reopen');
const errTimerId = App.wsPingTimer;
bitgetErrorSocket.onerror();
assert.strictEqual(intervals.has(errTimerId), false, 'keepalive interval must be cleared on error');
assert.strictEqual(App.wsPingTimer, null, 'App.wsPingTimer must be reset to null on error');

// 6. Binance fallback connections do NOT start application-level ping timer
// Advance wsTry to Binance
bitgetErrorSocket.onclose();
const fallbackTimer = [...timers.values()].find(t => t.delay === 2500);
if (fallbackTimer) fallbackTimer.fn();
const binanceSocket = sockets[2];
if (binanceSocket && binanceSocket.url.includes('binance')) {
  binanceSocket.onopen();
  assert.strictEqual(App.wsPingTimer, null, 'Binance connection must not start App.wsPingTimer');
}

console.log('PASS Bitget Keepalive ping timer lifecycle and message handling verified');
