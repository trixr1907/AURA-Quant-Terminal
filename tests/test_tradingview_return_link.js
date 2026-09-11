'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const start = html.indexOf('function applyTradingViewContextFromUrl(');
const end = html.indexOf('\nasync function loadChartData(', start);
assert(start >= 0 && end > start, 'applyTradingViewContextFromUrl source not found');
const source = html.slice(start, end);

function run(search) {
  const context = {
    URLSearchParams,
    location: { search },
    App: { symbol: 'BTCUSDT', chartTF: '1h' },
  };
  vm.createContext(context);
  vm.runInContext(`${source}\nthis.apply = applyTradingViewContextFromUrl;`, context);
  return { changed: context.apply(search), App: context.App };
}

let result = run('?symbol=solusdt&tf=4h&source=tradingview');
assert.strictEqual(result.changed, true);
assert.deepStrictEqual(JSON.parse(JSON.stringify(result.App)), { symbol: 'SOLUSDT', chartTF: '4h' });

result = run('?symbol=%3Cscript%3E&tf=5m&source=tradingview');
assert.strictEqual(result.changed, false);
assert.deepStrictEqual(JSON.parse(JSON.stringify(result.App)), { symbol: 'BTCUSDT', chartTF: '1h' });

result = run('?symbol=ETHUSDT&tf=1d&source=other');
assert.strictEqual(result.changed, false, 'only explicit TradingView return links may alter startup context');

console.log('PASS TradingView return-link context');
