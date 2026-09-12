'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  const plain = html.indexOf(`function ${name}(`);
  const asyncStart = html.indexOf(`async function ${name}(`);
  const start = asyncStart >= 0 && (plain < 0 || asyncStart < plain) ? asyncStart : plain;
  assert(start >= 0, `${name} source missing`);
  const brace = html.indexOf('{', start);
  let depth = 0;
  for (let i = brace; i < html.length; i++) {
    if (html[i] === '{') depth++;
    if (html[i] === '}') {
      depth--;
      if (depth === 0) return html.slice(start, i + 1);
    }
  }
  throw new Error(`${name} source incomplete`);
}

const pill = { textContent: '', className: '', title: '' };
let loads = 0;
let renders = 0;
let reconnects = 0;
const listeners = {};
const now = 1_000_000;
const App = {
  lastRefreshAt: now - 61_000,
  status: {
    ws: 'live',
    wsSource: 'bitget-ws',
    wsLastMessageAt: now - 4_000,
    wsOfflineSince: null,
    radarRefreshAt: now - 12_000,
    tradePricesRefreshAt: now - 8_000,
  },
};
const context = {
  App,
  Date: { now: () => now },
  document: {
    hidden: false,
    addEventListener(name, fn) { listeners[name] = fn; },
  },
  window: { addEventListener(name, fn) { listeners[name] = fn; } },
  $: id => id === 'feed-status-pill' ? pill : null,
  loadAll: async () => { loads++; App.lastRefreshAt = now; },
  renderAll: () => { renders++; },
  connectWS: () => { reconnects++; },
};
vm.createContext(context);
vm.runInContext([
  extractFunction('formatAgeSeconds'),
  extractFunction('buildFeedStatus'),
  extractFunction('renderFeedStatus'),
  extractFunction('shouldRefreshAfterResume'),
  extractFunction('refreshAfterResume'),
  extractFunction('bindResumeRefresh'),
  'this.api = { formatAgeSeconds, buildFeedStatus, renderFeedStatus, shouldRefreshAfterResume, refreshAfterResume, bindResumeRefresh };',
].join('\n'), context);

const api = context.api;
assert.strictEqual(api.shouldRefreshAfterResume(now - 60_001, 60_000, now), true);
assert.strictEqual(api.shouldRefreshAfterResume(now - 59_999, 60_000, now), false);
assert.strictEqual(api.buildFeedStatus(App.status, now).text, 'LIVE · bitget-ws · vor 4s');
assert.strictEqual(api.buildFeedStatus(App.status, now).offline, false);

api.renderFeedStatus(now);
assert.strictEqual(pill.textContent, 'LIVE · bitget-ws · vor 4s');
assert.strictEqual(pill.className, 'feed-status-pill live');
assert(pill.title.includes('Radar vor 12s'), 'pill tooltip should disclose radar age');
assert(pill.title.includes('Trade-Preise vor 8s'), 'pill tooltip should disclose trade-price age');

App.status.ws = 'off';
App.status.wsOfflineSince = now - 9_000;
assert.strictEqual(api.buildFeedStatus(App.status, now).text, 'WS offline seit 9s');
api.renderFeedStatus(now);
assert.strictEqual(pill.className, 'feed-status-pill offline');

App.status.ws = 'live';
App.status.wsOfflineSince = null;
api.bindResumeRefresh();
assert.strictEqual(typeof listeners.visibilitychange, 'function');
assert.strictEqual(typeof listeners.focus, 'function');

(async () => {
  App.lastRefreshAt = now - 61_000;
  await listeners.visibilitychange();
  assert.strictEqual(loads, 1, 'stale visible tab must catch up immediately');
  assert.strictEqual(renders, 1, 'catch-up must redraw after refresh');

  App.lastRefreshAt = now - 10_000;
  await listeners.focus();
  assert.strictEqual(loads, 1, 'fresh focus must not duplicate API refresh');

  App.status.ws = 'off';
  App.lastRefreshAt = now - 61_000;
  await listeners.focus();
  assert.strictEqual(reconnects, 1, 'offline feed must reconnect on focus');
  console.log('PASS data-age pill and stale-tab catch-up');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
