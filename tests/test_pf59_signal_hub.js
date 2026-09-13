'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const start = html.indexOf('// ==NTFY_SIGNALS_START==');
const end = html.indexOf('// ==NTFY_SIGNALS_END==');
assert(start >= 0 && end > start, 'PF-59 NtfySignals module markers must exist');

function contextFor(fetchImpl, stored = {}) {
  const ctx = {
    console, JSON, Math, Date, Promise, URL, Number, String, Object, Array, Set, Map,
    localStorage: {
      getItem: key => stored[key] === undefined ? null : stored[key],
      setItem: (key, value) => { stored[key] = String(value); },
      removeItem: key => { delete stored[key]; },
    },
    fetch: fetchImpl,
    setTimeout: cb => { cb(); return 1; },
    SyncEngine: { push: () => {} },
    document: { getElementById: () => null },
  };
  vm.createContext(ctx);
  vm.runInContext(`${html.slice(start, end)}; this.NtfySignals = NtfySignals;`, ctx);
  return ctx;
}

(async () => {
  const calls = [];
  let publishAttempts = 0;
  const ctx = contextFor(async (url, options) => {
    calls.push({ url, options });
    if (url === '/api/state') {
      return { ok: true, status: 200, json: async () => ({ ok: true, claimed: true, rev: 8 }) };
    }
    publishAttempts++;
    if (publishAttempts === 1) return { ok: false, status: 503 };
    return { ok: true, status: 200 };
  });
  ctx.NtfySignals.settings = {
    topicUrl: 'https://ntfy.invalid/runtime-topic',
    open: true, tp1: true, tp2: true, tp3: true, sl_close: true, other_close: true,
  };

  const result = await ctx.NtfySignals.emitTradeEvent(
    { id: 'trade-1', coin: 'XPNUSDT', dir: -1, leverage: 3, entry: 0.000758, initialSl: 0.0008 },
    'tp1',
    { price: 0.000712, managed: 'Bot verwaltet weiter (BE aktiv)' },
  );
  assert.strictEqual(result, true, 'claimed event must publish successfully');
  assert.strictEqual(calls.filter(call => call.url === '/api/state').length, 1, 'event must use one central claim path');
  assert.strictEqual(calls.filter(call => call.url !== '/api/state').length, 2, 'one failed publish must be retried exactly once');
  const claim = JSON.parse(calls[0].options.body);
  assert.strictEqual(claim.signal_claim.key, 'trade-1:tp1');
  const publish = calls[calls.length - 1];
  assert.strictEqual(publish.options.headers.Priority, '3');
  assert.match(publish.options.body, /XPNUSDT SHORT 3x/);
  assert.match(publish.options.body, /TP1 getroffen/);
  assert.match(publish.options.body, /Preis 0\.000712 \(\+6\.1%\)/, 'short performance must be direction-adjusted');
  assert.match(publish.options.body, /Bot verwaltet weiter \(BE aktiv\)/);

  const priorities = { open: '3', tp1: '3', tp2: '3', tp3: '3', sl_close: '4', other_close: '3' };
  for (const [event, expected] of Object.entries(priorities)) {
    assert.strictEqual(ctx.NtfySignals.priorityFor(event), expected, `${event} priority`);
  }

  let disabledCalls = 0;
  const disabled = contextFor(async () => { disabledCalls++; return { ok: true, status: 200, json: async () => ({ claimed: true }) }; });
  disabled.NtfySignals.settings = { topicUrl: '', open: true };
  assert.strictEqual(await disabled.NtfySignals.emitTradeEvent({ id: 'off' }, 'open'), false);
  disabled.NtfySignals.settings = { topicUrl: 'https://ntfy.invalid/runtime-topic', open: false };
  assert.strictEqual(await disabled.NtfySignals.emitTradeEvent({ id: 'off' }, 'open'), false);
  assert.strictEqual(disabledCalls, 0, 'empty topic or disabled toggle must not send or claim');

  let duplicatePublishes = 0;
  const duplicate = contextFor(async (url) => {
    if (url === '/api/state') return { ok: true, status: 200, json: async () => ({ ok: true, claimed: false, rev: 9 }) };
    duplicatePublishes++;
    return { ok: true, status: 200 };
  });
  duplicate.NtfySignals.settings = { topicUrl: 'https://ntfy.invalid/runtime-topic', open: true };
  assert.strictEqual(await duplicate.NtfySignals.emitTradeEvent({ id: 'trade-1' }, 'open'), false);
  assert.strictEqual(duplicatePublishes, 0, 'lost first-writer claim must suppress duplicate publish');

  console.log('PASS PF-59 signal hub: queue, claim dedup, retry and priority matrix');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
