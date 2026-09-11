'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  const start = html.indexOf(`function ${name}(`);
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
  URLSearchParams,
  TRADINGVIEW_MARKETS: { bitget_perp: { exchange: 'BITGET', suffix: '.P' } },
};
vm.createContext(context);
vm.runInContext(
  `${extractFunction('mapTradingViewInterval')}\n` +
  `${extractFunction('normalizeTradingViewSettings')}\n` +
  `${extractFunction('formatTradingViewSymbol')}\n` +
  `${extractFunction('buildTradingViewUrl')}\n` +
  `${extractFunction('buildTradingViewDesktopUrl')}\n` +
  `this.buildTradingViewDesktopUrl = buildTradingViewDesktopUrl;`,
  context,
);

assert.strictEqual(
  context.buildTradingViewDesktopUrl('SOLUSDT', '4h'),
  'tradingview://www.tradingview.com/chart/?symbol=BITGET%3ASOLUSDT.P&interval=240',
);

const openSource = extractFunction('openInTradingView');
assert(openSource.includes('/api/open-tradingview'), 'PC should first ask the local relay to open TradingView Desktop');
assert(openSource.includes('window.open(tvUrl'), 'web URL must remain as fallback');

console.log('PASS TradingView opens Desktop first and keeps a web fallback');
