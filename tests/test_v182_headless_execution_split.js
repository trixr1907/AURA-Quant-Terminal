'use strict';

const assert = require('assert');
const { EventEmitter } = require('events');
const runner = require('../headless_autobot.js');

function fakeRequest(responseBody, capture) {
  return (options, callback) => {
    capture.options = options;
    const req = new EventEmitter();
    req.payload = '';
    req.setTimeout = () => {};
    req.write = chunk => { req.payload += chunk; capture.payload = req.payload; };
    req.destroy = err => req.emit('error', err);
    req.end = () => {
      const res = new EventEmitter();
      res.statusCode = 200;
      callback(res);
      process.nextTick(() => {
        res.emit('data', JSON.stringify(responseBody));
        res.emit('end');
      });
    };
    return req;
  };
}

(async () => {
  const capture = {};
  const requestImpl = fakeRequest({
    code: '00000',
    data: [{ lastPr: '145.42' }],
  }, capture);
  const originalRequest = require('http').request;
  require('http').request = requestImpl;
  try {
    const ticker = await runner.fetchTickerViaRelay('SOLUSDT');
    assert.strictEqual(ticker.price, 145.42);
    const body = JSON.parse(capture.options ? capture.payload || '{}' : '{}');
    assert.strictEqual(capture.options.path, '/api/public');
    assert.strictEqual(body.path, '/api/v2/mix/market/ticker?symbol=SOLUSDT&productType=usdt-futures');
  } finally {
    require('http').request = originalRequest;
  }

  assert.strictEqual(runner.candleDurationMs('1h'), 3600000);
  assert.strictEqual(runner.candleDurationMs('2h'), 7200000);

  const source = require('fs').readFileSync('headless_autobot.js', 'utf8');
  assert(source.includes("engine.addAutobotReject(funnel, 'STALE_CANDLE')"));
  assert(source.includes('Date.now() - lastCandleTs > 1.5 * candleDurationMs(candidateGate.tf)'));
  assert(
    source.indexOf('const edgeGate = engine.evaluateAutobotEdge') < source.indexOf('const ticker = await fetchTickerViaRelay(c.symbol);'),
    'live ticker must be fetched after the OOS edge gate',
  );
  assert(
    source.indexOf('const kelly    = engine.calcKelly') < source.indexOf('const ticker = await fetchTickerViaRelay(c.symbol);'),
    'live ticker must be fetched after Kelly authorization',
  );
  assert(
    source.indexOf('const ticker = await fetchTickerViaRelay(c.symbol);') < source.indexOf('const slDist  = Math.max(execPrice'),
    'risk levels must be calculated from the just-fetched ticker',
  );
  assert(source.includes('entry:        execPrice, markPrice: execPrice'));
  assert(source.includes('initialSl:    sl, currentSl: sl'));
  assert(source.includes('priceRiskPct   = slDist / execPrice'));
  assert(source.includes("emitTradeEvent(engine, newTrade, 'open', { price: execPrice, signalPrice })"));
  assert(source.includes('using closed-candle fallback'));
  assert(source.includes('slippage=${slippagePct'));

  console.log('v1.8.2 headless execution split: live ticker, risk basis, fallback, stale guard and push detail OK');
})().catch(error => {
  console.error(error);
  process.exit(1);
});
