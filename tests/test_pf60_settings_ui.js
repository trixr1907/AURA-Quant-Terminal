'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
assert.match(html, /id="ntfy-settings-panel"/, 'PF-60 settings panel must exist near Autobot');
assert.match(html, /<label[^>]*for="ntfy-topic-url"/, 'topic input needs an explicit label');
assert.match(html, /id="ntfy-topic-url"[^>]*type="url"/, 'topic must use a URL input');
for (const event of ['open', 'tp1', 'tp2', 'tp3', 'sl_close', 'other_close']) {
  assert.match(html, new RegExp(`id="ntfy-toggle-${event}"`), `${event} toggle missing`);
}
assert.match(html, /id="ntfy-test-button"/, 'test button missing');
assert.match(html, /BTC.*Digest.*Deploy[\s\S]*ENV/, 'relay-side signal hint must name BTC, Digest, Deploy and ENV');
assert.match(html, /Mindestpriorität/, 'ntfy device priority hint missing');

const start = html.indexOf('// ==NTFY_SIGNALS_START==');
const end = html.indexOf('// ==NTFY_SIGNALS_END==');
function context(stored = {}) {
  const ctx = {
    console, JSON, Math, Date, Promise, URL, Number, String, Object, Array, Set, Map,
    localStorage: {
      getItem: key => stored[key] === undefined ? null : stored[key],
      setItem: (key, value) => { stored[key] = String(value); },
      removeItem: key => { delete stored[key]; },
    },
    fetch: async () => ({ ok: true, status: 200, json: async () => ({ claimed: true }) }),
    setTimeout: cb => { cb(); return 1; },
    SyncEngine: { pushed: [], push(key, value) { this.pushed.push({ key, value }); } },
    document: { getElementById: () => null },
  };
  vm.createContext(ctx);
  vm.runInContext(`${html.slice(start, end)}; this.NtfySignals=NtfySignals; this.NTFY_SETTINGS_KEY=NTFY_SETTINGS_KEY;`, ctx);
  return ctx;
}

const store = {};
const first = context(store);
assert.strictEqual(first.NtfySignals.save({ topicUrl: 'https://ntfy.invalid/runtime-topic', open: false, tp1: true }), true);
assert.strictEqual(first.SyncEngine.pushed.length, 1, 'settings must join shared-state sync');
const second = context(store);
const loaded = second.NtfySignals.load();
assert.strictEqual(loaded.topicUrl, 'https://ntfy.invalid/runtime-topic');
assert.strictEqual(loaded.open, false);
assert.strictEqual(loaded.tp1, true);

assert.match(html, /NtfySignals\.testPush\(/, 'test button must call central testPush path');
console.log('PASS PF-60 settings UI: accessible controls, persistence, sync and test path');
