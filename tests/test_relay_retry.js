
'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const start = html.indexOf('function isRelayServedOrigin');
const end = html.indexOf('\nasync function bitgetKlines', start);
assert(start >= 0 && end > start, 'Relay API source block missing');
const source = html.slice(start, end);

async function run({ responses, aborted = false }) {
  const calls = [];
  const waits = [];
  const controller = new AbortController();
  if (aborted) controller.abort();
  const context = {
    location: { protocol: 'http:', hostname: 'localhost' },
    App: { abortCtrl: controller },
    AbortController,
    DOMException,
    JSON,
    Math,
    setTimeout,
    clearTimeout,
    fetch: async (_url, options) => {
      calls.push(options);
      const next = responses.shift();
      return {
        ok: next.status >= 200 && next.status < 300,
        status: next.status,
        async json() { return next.body; },
      };
    },
    __relayWait: async ms => { waits.push(ms); },
  };
  vm.createContext(context);
  vm.runInContext(`${source}; this.relayCall = relayCall;`, context);
  try {
    const result = await context.relayCall('/api/public', { method: 'GET', path: '/api/v2/test' });
    return { result, calls, waits, error: null };
  } catch (error) {
    return { calls, waits, error };
  }
}

(async () => {
  const retried = await run({
    responses: [
      { status: 429, body: { code: 'RELAY_BUSY', msg: 'busy' } },
      { status: 503, body: { code: 'MARKET_DATA_STALE', msg: 'stale' } },
      { status: 200, body: { code: '00000', data: [] } },
    ],
  });
  assert.strictEqual(retried.error, null);
  assert.strictEqual(retried.calls.length, 3, '429/503 must use a bounded relay retry');
  assert.strictEqual(retried.waits.length, 2, 'each retry must back off');
  assert.strictEqual(retried.result.code, '00000');

  const aborted = await run({ responses: [{ status: 200, body: { code: '00000' } }], aborted: true });
  assert(aborted.error && aborted.error.name === 'AbortError', 'an aborted scan must not start relay retries');
  assert.strictEqual(aborted.calls.length, 0);

  console.log('PASS relayCall retries relay overload in a bounded, abort-aware way');
})().catch(error => {
  console.error(error);
  process.exit(1);
});
