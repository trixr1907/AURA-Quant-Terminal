'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

// Extract script blocks
const scripts = [];
const scriptRe = /<script\b[^>]*>([\s\S]*?)<\/script>/gi;
let match;
while ((match = scriptRe.exec(html)) !== null) {
  scripts.push(match[1]);
}
const fullJs = scripts.join('\n;\n');

// Build isolated mock context
const sockets = [];
const elementStore = {};
function getMockElement(id) {
  if (!elementStore[id]) {
    elementStore[id] = {
      id,
      textContent: '',
      innerHTML: '',
      title: '',
      className: '',
      style: {},
      clientWidth: 800,
      clientHeight: 500,
      getContext: () => ({
        setTransform: () => {},
        clearRect: () => {},
        fillRect: () => {},
        strokeRect: () => {},
        fillText: () => {},
        beginPath: () => {},
        moveTo: () => {},
        lineTo: () => {},
        stroke: () => {},
        fill: () => {},
        setLineDash: () => {}
      })
    };
  }
  return elementStore[id];
}

const timers = new Map();
let nextTimer = 1;

const context = {
  console,
  Date,
  Math,
  Number,
  String,
  Array,
  Object,
  JSON,
  isFinite,
  isNaN,
  Float64Array,
  Int8Array,
  Int32Array,
  document: {
    getElementById: id => getMockElement(id),
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener: () => {}
  },
  window: {
    devicePixelRatio: 1,
    addEventListener: () => {}
  },
  $: id => getMockElement(id),
  WebSocket: function WebSocketMock(url) {
    this.url = url;
    this.sent = [];
    this.readyState = 1;
    this.send = payload => {
      try { this.sent.push(JSON.parse(payload)); } catch (e) { this.sent.push(payload); }
    };
    this.close = () => { this.readyState = 3; };
    sockets.push(this);
  },
  setTimeout(fn, delay) {
    const id = nextTimer++;
    timers.set(id, { fn, delay });
    return id;
  },
  clearTimeout(id) { timers.delete(id); },
  setInterval(fn, delay) {
    const id = nextTimer++;
    timers.set(id, { fn, delay });
    return id;
  },
  clearInterval(id) { timers.delete(id); },
  requestAnimationFrame(fn) {
    const id = nextTimer++;
    timers.set(id, { fn, delay: 16 });
    return id;
  },
  cancelAnimationFrame(id) { timers.delete(id); }
};

vm.createContext(context);
vm.runInContext(fullJs + '; this.App = App; this.connectWS = connectWS; this.renderChart = renderChart; this.tradePrices = tradePrices; this.analyze = analyze; this.RenderCache = RenderCache;', context);

// Test 1: Bitget WebSocket connection subscribes to both candle and ticker channels
context.App.symbol = 'BTCUSDT';
context.App.chartTF = '1h';
context.App.data.candles = [
  { t: 1700000000000, o: 60000, h: 60500, l: 59800, c: 60200, v: 100, tbv: null }
];
context.App.data.chart = context.analyze(context.App.data.candles);

context.connectWS();
const bitget = sockets[0];
assert(bitget, 'Bitget WebSocket socket must be created');
bitget.onopen();

assert.strictEqual(bitget.sent.length, 1);
assert.deepStrictEqual(bitget.sent[0], {
  op: 'subscribe',
  args: [
    { instType: 'USDT-FUTURES', channel: 'candle1H', instId: 'BTCUSDT' },
    { instType: 'USDT-FUTURES', channel: 'ticker', instId: 'BTCUSDT' }
  ]
}, 'Bitget must subscribe to both candle1H and ticker channels on open');

// Test 2: Ticker tick updates running candle (Close, High, Low) without creating a new timestamp
bitget.onmessage({
  data: JSON.stringify({
    action: 'snapshot',
    arg: { instType: 'USDT-FUTURES', channel: 'ticker', instId: 'BTCUSDT' },
    data: [{ instId: 'BTCUSDT', lastPr: '60650' }]
  })
});

assert.strictEqual(context.App.data.candles.length, 1, 'Candle array length must remain 1 on ticker tick');
assert.strictEqual(context.App.data.candles[0].t, 1700000000000, 'Candle timestamp t must remain unchanged');
assert.strictEqual(context.App.data.candles[0].c, 60650, 'Candle close must update to ticker lastPr');
assert.strictEqual(context.App.data.candles[0].h, 60650, 'Candle high must expand to ticker lastPr');
assert.strictEqual(context.App.data.candles[0].l, 59800, 'Candle low must remain unchanged');
assert.strictEqual(context.App.status.wsSource, 'bitget-ws', 'WS source must remain bitget-ws');
assert.strictEqual(context.tradePrices['BTCUSDT'], 60650, 'tradePrices entry must update to ticker lastPr');

// Test 3: Ticker tick lower price expands Low
bitget.onmessage({
  data: JSON.stringify({
    action: 'update',
    arg: { instType: 'USDT-FUTURES', channel: 'ticker', instId: 'BTCUSDT' },
    data: [{ instId: 'BTCUSDT', lastPr: '59700' }]
  })
});
assert.strictEqual(context.App.data.candles[0].c, 59700, 'Candle close must update to new lower tick');
assert.strictEqual(context.App.data.candles[0].l, 59700, 'Candle low must expand downward to new lower tick');

// Test 4: Chart State Key reacts to live close changes (cache invalidation verified)
const RenderCache = context.RenderCache;
assert(RenderCache, 'RenderCache must be available');
RenderCache.invalidate('chart');

// First render creates cached key with liveClose = 59700
context.renderChart();
assert.strictEqual(RenderCache.isDirty('chart', [
  context.App.symbol,
  context.App.chartTF,
  context.App.visible,
  context.App.chartPanBars,
  context.App.data.chart.n,
  1700000000000,
  59700,
  60650,
  59700,
  context.App.chartOverlays,
  800,
  500
]), false, 'Unchanged state key must return clean (false)');

// When live price ticks to 59750, isDirty returns true
assert.strictEqual(RenderCache.isDirty('chart', [
  context.App.symbol,
  context.App.chartTF,
  context.App.visible,
  context.App.chartPanBars,
  context.App.data.chart.n,
  1700000000000,
  59750,
  60650,
  59700,
  context.App.chartOverlays,
  800,
  500
]), true, 'Updated live close must trigger dirty cache (true)');

// Test 5: Candle transition (t > last.t) appends next candle without duplicates
bitget.onmessage({
  data: JSON.stringify({
    action: 'update',
    arg: { instType: 'USDT-FUTURES', channel: 'candle1H', instId: 'BTCUSDT' },
    data: [['1700003600000', '59750', '60100', '59700', '60000', '80', '4800000']]
  })
});
assert.strictEqual(context.App.data.candles.length, 2, 'New bar must append as second candle');
assert.strictEqual(context.App.data.candles[1].t, 1700003600000, 'Second candle must have new timestamp');
assert.strictEqual(context.App.data.candles[1].c, 60000, 'Second candle close must match incoming candle');

console.log('PASS Bitget ticker channel subscription, live candle updates, and chart liveness verified');
