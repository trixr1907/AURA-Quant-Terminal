'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  const start = html.indexOf(`function ${name}(`);
  assert(start >= 0, `${name}() source not found`);
  const brace = html.indexOf('{', start);
  let depth = 0;
  for (let i = brace; i < html.length; i += 1) {
    if (html[i] === '{') depth += 1;
    else if (html[i] === '}' && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error(`${name}() closing brace not found`);
}

const calls = [];
const context = {
  String,
  encodeURIComponent,
  window: {
    open: (...args) => {
      calls.push(args);
      return { opener: 'unsafe' };
    },
  },
};
vm.createContext(context);
vm.runInContext([
  extractFunction('buildTradingViewChartUrl'),
  extractFunction('openTradingViewChart'),
  'this.buildTradingViewChartUrl = buildTradingViewChartUrl;',
  'this.openTradingViewChart = openTradingViewChart;',
].join('\n'), context);

const url = context.buildTradingViewChartUrl('ethusdt');
assert.strictEqual(url, 'https://www.tradingview.com/chart/?symbol=BITGET%3AETHUSDT.P');
const opened = context.openTradingViewChart('ETHUSDT');
assert.strictEqual(opened.opener, null);
assert.deepStrictEqual(calls, [[url, '_blank', 'noopener,noreferrer']]);
assert(!/\/api\/open-tradingview|launchTradingViewDesktop|tradingview:\/\//.test(html), 'desktop relay and protocol paths must be absent');
console.log('PASS direct TradingView Bitget web link');
