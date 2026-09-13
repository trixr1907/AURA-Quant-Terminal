'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFn(name) {
  const start = html.indexOf('function ' + name + '(');
  assert(start >= 0, `function ${name}() source not found in Symbiose_Dashboard.html`);
  const end = html.indexOf('\nfunction ', start + 1);
  return html.slice(start, end > 0 ? end : start + 2000);
}

console.log('=== TEST: PF-53 .. PF-57 CARDS, FALLBACKS, TV LINKS & AUTOBOT INTEL ===');

// ----------------------------------------------------------------------------
// 1. PF-55: TradingView URLs with timeframe intervals
// ----------------------------------------------------------------------------
{
  const sandbox = {
    String,
    Number,
    Math,
    encodeURIComponent,
    TRADINGVIEW_MARKETS: { bitget_perp: { exchange: 'BITGET', suffix: '.P' } },
    App: { chartTF: '1h' },
    formatTradingViewSymbol: (sym, market) => `BITGET:${sym}.P`,
    mapTradingViewInterval: (tf) => {
      const tfMap = { '15m': '15', '1h': '60', '4h': '240', '1d': 'D' };
      return tfMap[String(tf || '').toLowerCase()] || '60';
    },
    normalizeTradingViewSettings: (s = {}) => ({ market: 'bitget_perp', layout: '' })
  };
  vm.createContext(sandbox);

  const fnBuildTvUrl = extractFn('buildTradingViewUrl');
  const fnBuildTvChartUrl = extractFn('buildTradingViewChartUrl');
  vm.runInContext(`${fnBuildTvUrl}\n;${fnBuildTvChartUrl}`, sandbox);

  const url15m = sandbox.buildTradingViewChartUrl('BTCUSDT', '15m');
  const url1h = sandbox.buildTradingViewChartUrl('ETHUSDT', '1h');
  const url4h = sandbox.buildTradingViewChartUrl('SOLUSDT', '4h');
  const url1d = sandbox.buildTradingViewChartUrl('XRPUSDT', '1d');

  assert(url15m.includes('interval=15'), `PF-55: 15m must have interval=15: ${url15m}`);
  assert(url1h.includes('interval=60'), `PF-55: 1h must have interval=60: ${url1h}`);
  assert(url4h.includes('interval=240'), `PF-55: 4h must have interval=240: ${url4h}`);
  assert(url1d.includes('interval=D'), `PF-55: 1d must have interval=D: ${url1d}`);
  assert(url15m.includes('BITGET%3ABTCUSDT.P') || url15m.includes('BITGET:BTCUSDT.P'), 'PF-55: Symbol formatted properly');

  console.log('  PASS PF-55: TradingView URLs contain expected interval parameters');
}

// ----------------------------------------------------------------------------
// 2. PF-54: Paper Trade Setup Validation without silent fallbacks
// ----------------------------------------------------------------------------
{
  assert(html.includes('fallbackReason'), 'PF-54: fallbackReason tracking present in dashboard');
  assert(html.includes('Fallback-SL (ATR), Setup-Level fehlten'), 'PF-54: Explicit fallback explanation present');
  
  const src = extractFn('startPaperTradeFromCockpit');
  assert(src.includes('fallbackSl: isFallback'), 'PF-54: fallbackSl flag set in trade');
  assert(src.includes('fallbackReason: isFallback ? fallbackReason : \'\''), 'PF-54: fallbackReason set in trade');
  console.log('  PASS PF-54: Setup validation records explicit fallback reason without silent replacement');
}

// ----------------------------------------------------------------------------
// 3. PF-53 & PF-57: Autobot & Manual Intel, Price Formatting & Multi-TP
// ----------------------------------------------------------------------------
{
  assert(html.includes('tp2Display: t.tp2 ? pFmt(t.tp2) : \'—\'') || html.includes('tp2Display: t.tp2 ? fmtP(t.tp2) : \'—\''), 'PF-53: tp2Display passed');
  assert(html.includes('tp3Display: t.tp3 ? pFmt(t.tp3) : \'—\'') || html.includes('tp3Display: t.tp3 ? fmtP(t.tp3) : \'—\''), 'PF-53: tp3Display passed');
  
  // Check buildTradeIntelAssessment creates full intel block for Autobot as well
  const intelFn = extractFn('buildTradeIntelAssessment');
  assert(intelFn.includes('BTC-Trend'), 'PF-57: BTC-Trend confluence included in intel');
  assert(intelFn.includes('SMC:'), 'PF-57: SMC Session included in intel');
  assert(intelFn.includes('Phase 1: Positionierung') || intelFn.includes('Break-Even aktiv'), 'PF-57: Tactical phases included');
  console.log('  PASS PF-53/PF-57: Full Intel assessment (SMC/BTC/Phases) and Multi-TP support in cards');
}

// ----------------------------------------------------------------------------
// 4. PF-56: Layout Stability & Numeric Font Tabular
// ----------------------------------------------------------------------------
{
  assert(html.includes('font-variant-numeric:tabular-nums') || html.includes('font-variant-numeric: tabular-nums'), 'PF-56: tabular-nums applied for digit width stability');
  assert(html.includes('prefers-reduced-motion'), 'PF-56: prefers-reduced-motion respected in CSS');
  assert(html.includes('.tc-pnl{') && html.includes('tabular-nums'), 'PF-56: Tabular nums for PnL block');
  console.log('  PASS PF-56: Layout stability CSS and prefers-reduced-motion verified');
}

console.log('\n============================================================');
console.log('ERGEBNIS: PF-53..PF-57 VERIFICATION ALL CHECKS PASSED');
console.log('============================================================');
