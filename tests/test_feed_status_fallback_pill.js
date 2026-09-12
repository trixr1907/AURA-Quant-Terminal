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
const now = 1_000_000;

const App = {
  status: {
    ws: 'live',
    wsSource: 'bitget-ws',
    wsLastMessageAt: now - 3_000,
    wsOfflineSince: null,
    radarRefreshAt: now - 10_000,
    tradePricesRefreshAt: now - 5_000,
  },
};

const context = {
  App,
  Date: { now: () => now },
  $: id => (id === 'feed-status-pill' ? pill : null),
};

vm.createContext(context);
vm.runInContext([
  extractFunction('formatAgeSeconds'),
  extractFunction('buildFeedStatus'),
  extractFunction('renderFeedStatus'),
  'this.api = { formatAgeSeconds, buildFeedStatus, renderFeedStatus };',
].join('\n'), context);

const api = context.api;

// 1. Primary Bitget Feed: Live (Green)
App.status.ws = 'live';
App.status.wsSource = 'bitget-ws';
App.status.wsLastMessageAt = now - 2_000;
App.status.wsOfflineSince = null;

const liveView = api.buildFeedStatus(App.status, now);
assert.strictEqual(liveView.offline, false);
assert.strictEqual(liveView.fallback, false);
assert.strictEqual(liveView.text, 'LIVE · bitget-ws · vor 2s');

api.renderFeedStatus(now);
assert.strictEqual(pill.textContent, 'LIVE · bitget-ws · vor 2s');
assert.strictEqual(pill.className, 'feed-status-pill live', 'Bitget primary feed must use live CSS class');

// 2. Binance Fallback Feed: Fallback (Yellow) - PF-21
App.status.ws = 'live';
App.status.wsSource = 'binance-fallback';
App.status.wsLastMessageAt = now - 4_000;

const fallbackView = api.buildFeedStatus(App.status, now);
assert.strictEqual(fallbackView.offline, false);
assert.strictEqual(fallbackView.fallback, true, 'source != bitget-ws must flag fallback: true');
assert.strictEqual(fallbackView.text, 'FALLBACK · binance-fallback · vor 4s', 'Pill text must disclose FALLBACK status');

api.renderFeedStatus(now);
assert.strictEqual(pill.textContent, 'FALLBACK · binance-fallback · vor 4s');
assert.strictEqual(pill.className, 'feed-status-pill fallback', 'Binance fallback must use yellow fallback CSS class');
assert.ok(pill.title.includes('FALLBACK'), 'Pill tooltip should disclose fallback feed details');

// 3. Binance Vision Fallback Feed: Fallback (Yellow)
App.status.ws = 'live';
App.status.wsSource = 'binance-vision-fallback';
App.status.wsLastMessageAt = now - 1_000;

const visionView = api.buildFeedStatus(App.status, now);
assert.strictEqual(visionView.offline, false);
assert.strictEqual(visionView.fallback, true);
assert.strictEqual(visionView.text, 'FALLBACK · binance-vision-fallback · vor 1s');

api.renderFeedStatus(now);
assert.strictEqual(pill.textContent, 'FALLBACK · binance-vision-fallback · vor 1s');
assert.strictEqual(pill.className, 'feed-status-pill fallback');

// 4. Offline State: Offline (Red)
App.status.ws = 'off';
App.status.wsOfflineSince = now - 15_000;

const offlineView = api.buildFeedStatus(App.status, now);
assert.strictEqual(offlineView.offline, true);
assert.strictEqual(offlineView.fallback, false);
assert.strictEqual(offlineView.text, 'WS offline seit 15s');

api.renderFeedStatus(now);
assert.strictEqual(pill.textContent, 'WS offline seit 15s');
assert.strictEqual(pill.className, 'feed-status-pill offline', 'Offline state must use offline CSS class');

console.log('PASS Feed-Status-Pill displays LIVE, FALLBACK, and OFFLINE states honestly');
