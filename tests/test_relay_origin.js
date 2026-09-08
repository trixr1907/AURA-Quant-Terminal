'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const start = html.indexOf('function isRelayServedOrigin');
const end = html.indexOf('\nasync function bitgetKlines', start);
assert(start >= 0 && end > start, 'Relay-origin source block missing');
const source = html.slice(start, end);

async function runAt(location) {
  const calls = [];
  const context = {
    location,
    fetch: async (...args) => {
      calls.push(args);
      return {
        ok: true,
        status: 200,
        async json() { return { code: '00000', data: [] }; },
      };
    },
    AbortController,
    setTimeout,
    clearTimeout,
    JSON,
    BITGET_BASE: 'https://api.bitget.com',
    jfetch: async url => {
      calls.push([url]);
      return { code: '00000', data: [] };
    },
  };
  vm.createContext(context);
  vm.runInContext(`${source}; this.bgGet = bgGet; this.relayBase = relayBase;`, context);
  await context.bgGet('/api/v2/mix/market/ticker?symbol=BTCUSDT');
  return { calls, relayBase: context.relayBase() };
}

(async () => {
  const lan = await runAt({ protocol: 'http:', hostname: '192.168.8.115' });
  assert.strictEqual(lan.relayBase, '', 'LAN-served dashboard must use its same-origin relay');
  assert.strictEqual(lan.calls[0][0], '/api/public', 'LAN Bitget request must go through /api/public');
  assert.strictEqual(lan.calls[0][1].method, 'POST');

  const httpsHost = await runAt({ protocol: 'https:', hostname: 'aura.internal' });
  assert.strictEqual(httpsHost.relayBase, '', 'HTTPS-served dashboard must use its same-origin relay');
  assert.strictEqual(httpsHost.calls[0][0], '/api/public');

  const file = await runAt({ protocol: 'file:', hostname: '' });
  assert.strictEqual(file.relayBase, 'http://127.0.0.1:8787');
  assert.ok(file.calls[0][0].startsWith('https://api.bitget.com/'), 'file mode retains direct public API fallback');

  console.log('PASS relay origin selection');
})().catch(error => {
  console.error(error);
  process.exit(1);
});
