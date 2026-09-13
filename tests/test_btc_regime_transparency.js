'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const htmlPath = path.join(__dirname, '..', 'Symbiose_Dashboard.html');
const html = fs.readFileSync(htmlPath, 'utf8');

assert.match(html, /function updateBtcRegimeChangedAt\(/,
  'PF-28 must provide the pure BTC regime-change timestamp helper');
assert.match(html, /function formatBtcRegimeTransparency\(/,
  'PF-28 must provide the pure BTC regime-transparency formatter');

const start = html.indexOf('function updateBtcRegimeChangedAt(');
const end = html.indexOf('\n// ==ENGINE_END==', start);
assert(start >= 0 && end > start, 'PF-28 helper source must be located before ENGINE_END');

const sandbox = { Number, String, Math, isFinite };
vm.createContext(sandbox);
vm.runInContext(`${html.slice(start, end)}\nthis.updateBtcRegimeChangedAt = updateBtcRegimeChangedAt;\nthis.formatBtcRegimeTransparency = formatBtcRegimeTransparency;`, sandbox);

const first = sandbox.updateBtcRegimeChangedAt(null, { reg: 1, txt: 'BULL' }, 1000);
assert.strictEqual(first, 1000, 'first valid regime must initialize changedAt');

const unchanged = sandbox.updateBtcRegimeChangedAt({ reg: 1, txt: 'BULL', changedAt: first }, { reg: 1, txt: 'BULL' }, 2000);
assert.strictEqual(unchanged, first, 'identical regime state must preserve changedAt');

const changed = sandbox.updateBtcRegimeChangedAt({ reg: 1, txt: 'BULL', changedAt: first }, { reg: -1, txt: 'BEAR' }, 3000);
assert.strictEqual(changed, 3000, 'regime change must update changedAt');

assert.strictEqual(
  sandbox.updateBtcRegimeChangedAt({ reg: 1, txt: 'BULL', changedAt: first }, null, 4000),
  first,
  'invalid next state must defensively preserve the previous timestamp'
);
assert.strictEqual(
  sandbox.updateBtcRegimeChangedAt(null, { reg: 7, txt: 'UNKNOWN' }, 4000),
  null,
  'invalid first state must not initialize a timestamp'
);

assert.strictEqual(
  sandbox.formatBtcRegimeTransparency({ ema50: 105, ema200: 100, adx: 20, isSqz: true }),
  'E50-vs-E200: +5.00% · ADX: 20.0 (≥20) · Squeeze: aktiv'
);
assert.strictEqual(
  sandbox.formatBtcRegimeTransparency({ ema50: 95, ema200: 100, adx: 19.4, isSqz: false }),
  'E50-vs-E200: -5.00% · ADX: 19.4 (<20) · Squeeze: inaktiv'
);

assert.match(html, /id="macro-btc-regime-detail"/, 'UI must expose the regime distance detail');
assert.match(html, /id="macro-btc-regime-since"/, 'UI must expose when the regime last changed');
assert.match(html, /grün=BULL, rot=BEAR, orange=SIDEWAYS/, 'UI must include the required color legend');
assert.match(html, /BULL = Kurs &gt; EMA200 und E50 &gt; E200; BEAR analog; SIDEWAYS = sonst\/Squeeze\./,
  'UI tooltip must state the unchanged regime rule');

console.log('PASS BTC regime transparency');
