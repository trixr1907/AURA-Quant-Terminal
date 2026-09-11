
'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  const plainStart = html.indexOf(`function ${name}(`);
  const asyncStart = html.indexOf(`async function ${name}(`);
  const start = asyncStart >= 0 ? asyncStart : plainStart;
  if (start < 0) throw new Error(`${name}() source not found`);
  const brace = html.indexOf('{', start);
  let depth = 0;
  let quote = null;
  let escaped = false;
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

const fallbackContext = {
  STATIC_TOP_UNIVERSE: ['BTCUSDT', 'ETHUSDT'],
  fetch: async () => { throw new Error('offline'); },
};
vm.createContext(fallbackContext);
vm.runInContext(`${extractFunction('fetchUniverseFallback')}
this.fetchUniverseFallback = fetchUniverseFallback;`, fallbackContext);

(async () => {
  const staticRows = await fallbackContext.fetchUniverseFallback();
  assert.deepStrictEqual(
    JSON.parse(JSON.stringify(staticRows)),
    [
      { symbol: 'BTCUSDT', quoteCoin: 'USDT', productType: 'USDT-FUTURES', contractType: 'perpetual', symbolStatus: 'normal', vol: null, funding: null, marketDataSource: 'static_bitget_usdt_futures', liquidityVerified: false },
      { symbol: 'ETHUSDT', quoteCoin: 'USDT', productType: 'USDT-FUTURES', contractType: 'perpetual', symbolStatus: 'normal', vol: null, funding: null, marketDataSource: 'static_bitget_usdt_futures', liquidityVerified: false },
    ],
    'static fallback must not invent volume or funding and must be explicitly unverified',
  );

  const scanStart = html.indexOf('async scanAndExecuteOpportunities()');
  const scanEnd = html.indexOf('\n  render() {', scanStart);
  const scanSource = html.slice(scanStart, scanEnd);
  assert(scanSource.includes('universeRow.liquidityVerified !== true'),
    'Paper Autobot must reject rows without verified liquidity before any entry work');
  assert(!/STATIC_TOP_UNIVERSE\.map\([^)]*vol:\s*\d/.test(html),
    'no static universe fallback may manufacture numeric volume');
  assert(!/STATIC_TOP_UNIVERSE\.map\([^)]*funding:\s*0(?:\.0+)?(?:[,\}])/.test(html),
    'no static universe fallback may manufacture funding');
  assert(html.includes('marketDataSource'), 'universe rows must declare market-data provenance');
  assert(html.includes('nicht verfügbar'), 'Market Pulse must make missing fallback data explicit');

  console.log('PASS static fallback liquidity is unverified and Paper Autobot is fail-closed');
})().catch(error => {
  console.error(error);
  process.exit(1);
});
