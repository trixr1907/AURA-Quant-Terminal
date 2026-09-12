'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  const plain = html.indexOf(`function ${name}(`);
  const asyncStart = html.indexOf(`async function ${name}(`);
  const start = asyncStart >= 0 && (plain < 0 || asyncStart < plain) ? asyncStart : plain;
  if (start < 0) throw new Error(`${name}() source not found`);
  const paren = html.indexOf(')', start);
  const brace = html.indexOf('{', paren);
  let depth = 0, quote = null, escaped = false;
  for (let i = brace; i < html.length; i += 1) {
    const ch = html[i];
    if (quote) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') { quote = ch; continue; }
    if (ch === '{') depth += 1;
    if (ch === '}' && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error(`${name}() closing brace not found`);
}

const context = {
  Date,
  Math,
  Number,
  String,
  encodeURIComponent,
  setTimeout,
  clearTimeout,
  AbortController,
  TRADINGVIEW_MARKETS: { bitget_perp: { exchange: 'BITGET', suffix: '.P' } },
  App: { symbol: 'ETHUSDT', chartTF: '15m', tradingView: { market: 'bitget_perp' } },
  tradingViewPineText: '//@version=5\nindicator("Test")',
  preloadTradingViewPine: async () => '',
  findActiveTradeForPine: () => null,
  getTradingViewPineText: () => '',
  launchTradingViewDesktop: () => false,
  relayBase: () => 'http://127.0.0.1:4242',
  fetch: async (url, opts) => {
    // simulate slow/unreachable relay endpoint
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => resolve({ ok: false }), 2000);
      if (opts && opts.signal) {
        opts.signal.addEventListener('abort', () => {
          clearTimeout(timer);
          const err = new Error('aborted');
          err.name = 'AbortError';
          reject(err);
        });
      }
    });
  },
  window: {
    open: (url) => ({ openedUrl: url, opener: null }),
  },
  navigator: {
    clipboard: {
      writeText: async () => {},
    },
  },
};

vm.createContext(context);
vm.runInContext([
  extractFunction('mapTradingViewInterval'),
  extractFunction('normalizeTradingViewSettings'),
  extractFunction('formatTradingViewSymbol'),
  extractFunction('buildTradingViewUrl'),
  extractFunction('buildTradingViewDesktopUrl'),
  extractFunction('openInTradingView'),
  'this.buildTradingViewUrl = buildTradingViewUrl;',
  'this.openInTradingView = openInTradingView;',
].join('\n'), context);

const url = context.buildTradingViewUrl('ETHUSDT', '15m');
assert(url.includes('symbol=BITGET%3AETHUSDT.P'), `TradingView URL must target Bitget perpetual feed: ${url}`);
assert(url.includes('interval=15'), `TradingView URL interval must be 15: ${url}`);

const start = Date.now();
context.openInTradingView('ETHUSDT', '15m').then(res => {
  const duration = Date.now() - start;
  assert.strictEqual(res.target, 'web', 'Target must fallback to web');
  assert(res.url.includes('BITGET%3AETHUSDT.P'), 'Fallback URL must target Bitget perpetual');
  assert(duration < 800, `Relay fallback must complete quickly (took ${duration}ms)`);
  console.log(`PASS TradingView Bitget URL and fast offline fallback (${duration}ms)`);
}).catch(err => {
  console.error(err);
  process.exit(1);
});
