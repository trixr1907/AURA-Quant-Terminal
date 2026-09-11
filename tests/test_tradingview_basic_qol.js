'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function sourceBetween(startAnchor, endAnchor) {
  const start = html.indexOf(startAnchor);
  const end = html.indexOf(endAnchor, start);
  assert(start >= 0 && end > start, `source not found: ${startAnchor}`);
  return html.slice(start, end);
}

  const source = sourceBetween('function mapTradingViewInterval(', '\nfunction renderPrice(');
  assert(source.indexOf("await fetch('/Symbiose_Signal_System_v1.pine')") === -1, 'click handler must not fetch Pine before clipboard write');
  assert(source.includes('getTradingViewPineText'), 'Pine source must come from a preloaded cache');
  assert(source.indexOf('navigator.clipboard.writeText(pineText)') < source.indexOf("window.open(tvUrl, '_blank')"), 'Pine copy must start before opening TradingView');
const context = {
  URL,
  URLSearchParams,
  console,
  isFinite,
  location: { origin: 'http://127.0.0.1:8765' },
  App: { symbol: 'SOLUSDT', chartTF: '4h', data: {} },
};
vm.createContext(context);
vm.runInContext(`${source}\nthis.api = { normalizeTradingViewSettings, formatTradingViewSymbol, buildTradingViewUrl, selectTradingViewCandidates, buildTradingViewWatchlist, buildAuraReturnUrl, buildTradingViewPriceAlerts, buildTradingViewSetupNote };`, context);
const api = context.api;

assert.deepStrictEqual(
  JSON.parse(JSON.stringify(api.normalizeTradingViewSettings({ market: 'nonsense', layout: '  Ab C-12  ' }))),
  { market: 'bitget_perp', layout: 'AbC-12' },
  'invalid markets must fail closed to Bitget perpetual and layout IDs must be sanitized',
);
assert.strictEqual(api.formatTradingViewSymbol('SOLUSDT', 'bitget_perp'), 'BITGET:SOLUSDT.P');
assert.strictEqual(api.formatTradingViewSymbol('BINANCE:BTCUSDT.P', 'bitget_perp'), 'BITGET:BTCUSDT.P');
assert.strictEqual(api.formatTradingViewSymbol('BITGET:SOLUSDT.P', 'bitget_perp'), 'BITGET:SOLUSDT.P');
assert.strictEqual(
  api.buildTradingViewUrl('SOLUSDT', '4h', { market: 'bitget_perp', layout: 'AbC-12' }),
  'https://www.tradingview.com/chart/AbC-12/?symbol=BITGET%3ASOLUSDT.P&interval=240',
);

const radar = [
  { symbol: 'ETHUSDT', bestTF: '1h', executable: true, rankScore: 4100, bestInfo: { dir: -1 } },
  { symbol: 'SOLUSDT', bestTF: '4h', executable: true, rankScore: 4200, bestInfo: { dir: 1 } },
  { symbol: 'XRPUSDT', bestTF: '15m', executable: false, rankScore: 3100, bestInfo: { candidate: true, dir: 1 } },
  { symbol: 'DOGEUSDT', bestTF: '1d', executable: false, rankScore: 2050, bestInfo: { status: 'watch', dir: -1 } },
  { symbol: 'BADUSDT', bestTF: '1h', executable: false, rankScore: 1000, incomplete: true, bestInfo: { dir: 1 } },
];
const candidates = api.selectTradingViewCandidates(radar, { limit: 30 });
assert.deepStrictEqual(JSON.parse(JSON.stringify(candidates.map(r => r.symbol))), ['SOLUSDT', 'ETHUSDT', 'XRPUSDT', 'DOGEUSDT']);
assert.strictEqual(api.selectTradingViewCandidates(radar, { direction: 1 }).length, 2);
assert.strictEqual(api.selectTradingViewCandidates(radar, { direction: -1 }).length, 2);
assert.deepStrictEqual(
  JSON.parse(JSON.stringify(api.selectTradingViewCandidates([
    { symbol: 'ONLYLONGUSDT', rankScore: 9, bestInfo: { dir: 1 } },
    { symbol: 'ONLYSHORTUSDT', rankScore: 8, bestInfo: { dir: -1 } },
  ], { direction: -1 }).map(r => r.symbol))),
  ['ONLYSHORTUSDT'],
  'fallback lists must preserve the requested direction',
);
assert.strictEqual(api.buildTradingViewWatchlist(candidates, 'bitget_perp'), 'BITGET:SOLUSDT.P\nBITGET:ETHUSDT.P\nBITGET:XRPUSDT.P\nBITGET:DOGEUSDT.P');
assert.strictEqual(api.selectTradingViewCandidates(Array.from({ length: 40 }, (_, i) => ({ symbol: `C${i}USDT`, rankScore: 40 - i, bestInfo: { dir: 1 } }))).length, 30);

assert.strictEqual(
  api.buildAuraReturnUrl('SOLUSDT', '4h', 'http://127.0.0.1:8765'),
  'http://127.0.0.1:8765/?symbol=SOLUSDT&tf=4h&source=tradingview',
);
const live = { longSig: true, entry: 142.5, sl: 138.25, tp1: 148.75, tp2: 155, tp3: 163, total: 82.4, aligned: 4, kelly: { hasEdge: true, edge: 3.2 } };
const alerts = api.buildTradingViewPriceAlerts({ symbol: 'SOLUSDT', timeframe: '4h', live, origin: 'http://127.0.0.1:8765' });
assert.deepStrictEqual(JSON.parse(JSON.stringify(alerts.map(a => [a.kind, a.price]))), [['ENTRY', 142.5], ['STOP', 138.25], ['TP1', 148.75]]);
assert(alerts.every(a => a.message.includes('AURA') && a.message.includes('SOLUSDT') && a.message.includes('http://127.0.0.1:8765/')));
const note = api.buildTradingViewSetupNote({ symbol: 'SOLUSDT', timeframe: '4h', live, origin: 'http://127.0.0.1:8765', nowIso: '2026-09-11T04:00:00.000Z' });
assert(note.includes('AURA · SOLUSDT · 4H'));
assert(note.includes('Richtung: LONG'));
assert(note.includes('Edge: +3.2% (lokal gemessen, keine globale Strategie-Evidenz)'));
assert(note.includes('AURA-Link: http://127.0.0.1:8765/?symbol=SOLUSDT&tf=4h&source=tradingview'));

console.log('PASS TradingView Basic QoL helpers');
