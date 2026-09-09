'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
assert(scriptMatch, 'Dashboard script block missing');

const elements = new Map();
function element(id) {
  if (!elements.has(id)) {
    elements.set(id, {
      id,
      value: '',
      textContent: '',
      innerHTML: '',
      className: '',
      style: {},
      dataset: {},
      classList: { add() {}, remove() {}, toggle() {} },
      addEventListener() {},
      querySelectorAll() { return []; },
      setAttribute() {},
      reset() {},
    });
  }
  return elements.get(id);
}

const storage = new Map();
const document = {
  getElementById: element,
  addEventListener() {},
  querySelectorAll() { return []; },
};
const ctx = {
  console,
  document,
  window: { addEventListener() {}, AudioContext: function () {}, webkitAudioContext: function () {} },
  localStorage: {
    getItem(key) { return storage.has(key) ? storage.get(key) : null; },
    setItem(key, value) { storage.set(key, String(value)); },
  },
  navigator: {},
  location: { protocol: 'http:', host: '127.0.0.1:8787' },
  requestAnimationFrame(fn) { fn(); return 1; },
  cancelAnimationFrame() {},
  setTimeout,
  clearTimeout,
  setInterval() { return 1; },
  clearInterval() {},
  fetch: async () => ({ ok: true, json: async () => null }),
  WebSocket: function () {},
  ResizeObserver: function () { this.observe = () => {}; },
  Float64Array,
  Int8Array,
  Uint8Array,
  Math,
  Date,
  JSON,
  Number,
  String,
  Object,
  Array,
  Promise,
  isFinite,
  isNaN,
  Infinity,
};
ctx.window.document = document;
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(scriptMatch[1] + '\nthis.__Autobot = Autobot;\nthis.__App = App;', ctx);

assert.strictEqual(typeof ctx.calculateTradeProjection, 'function', 'calculateTradeProjection missing');

// RED contracts: the warning must reserve space without an inline display conflict,
// and the tracker must describe leveraged futures PnL rather than spot PnL.
assert(!/id="risk-warning"[^>]*style="[^"]*display\s*:/.test(html), 'risk warning must not have inline display style');
assert(!html.includes('PnL ungehebelt'), 'trade hint must not claim unleveraged PnL');
assert(html.includes('Notional = Margin × Hebel'), 'trade hint must explain futures notional');
assert(html.includes('rw.style.opacity'), 'warning visibility must preserve its reserved layout space');
assert(!html.includes('rw.style.display'), 'warning must not collapse and shift the top bar');
assert(html.includes('dir===1?(sl>=entry||tp<=entry):(sl<=entry||tp>=entry)'), 'directional SL/TP validation missing');

const long = ctx.calculateTradeProjection({ dir: 1, entry: 100, margin: 100, leverage: 10, sl: 98, tp: 105 });
assert.deepStrictEqual(
  { notional: long.notional, tpPnl: long.tpPnl, slPnl: long.slPnl },
  { notional: 1000, tpPnl: 50, slPnl: -20 },
);

const short = ctx.calculateTradeProjection({ dir: -1, entry: 100, margin: 250, leverage: 4, sl: 103, tp: 95 });
assert.deepStrictEqual(
  { notional: short.notional, tpPnl: short.tpPnl, slPnl: short.slPnl },
  { notional: 1000, tpPnl: 50, slPnl: -30 },
);

const live = ctx.calculateTradeProjection({ dir: 1, entry: 100, margin: 100, leverage: 5, sl: 90, tp: 120, current: 110 });
assert.strictEqual(live.pnl, 50);
assert.strictEqual(live.marginRoiPct, 50);

for (const bad of [0, -1, NaN, Infinity]) {
  const result = ctx.calculateTradeProjection({ dir: 1, entry: 100, margin: 100, leverage: bad, sl: 98, tp: 105 });
  assert.strictEqual(result.valid, false, `leverage ${bad} must fail closed`);
}

for (const invalidLevels of [
  { dir: 1, entry: 100, margin: 100, leverage: 2, sl: 101, tp: 105 },
  { dir: 1, entry: 100, margin: 100, leverage: 2, sl: 98, tp: 99 },
  { dir: -1, entry: 100, margin: 100, leverage: 2, sl: 99, tp: 95 },
  { dir: -1, entry: 100, margin: 100, leverage: 2, sl: 103, tp: 101 },
]) {
  assert.strictEqual(ctx.calculateTradeProjection(invalidLevels).valid, false, 'directionally invalid SL/TP must fail closed');
}
assert(!html.includes("+$('trade-leverage').value||1"), 'projection must not silently replace invalid leverage with 1x');

assert(html.includes("setInterval(()=>refreshTradePrices(loadTrades()),15000)"), 'non-focused trades must refresh their live prices periodically');

// ============================================================================
// 1. Contract: v1 -> v2 Migration and Field Normalization
// ============================================================================
assert.strictEqual(typeof ctx.normalizeTrade, 'function', 'normalizeTrade function required');
assert.strictEqual(typeof ctx.normalizeHistoryEvent, 'function', 'normalizeHistoryEvent function required');

// Test active trade v1 normalization
const v1Active = {
  coin: 'BTCUSDT',
  dir: 1,
  entry: 50000,
  margin: 200,
  leverage: 10,
  sl: 49000,
  tp: 53000,
  autoBe: true,
  beActive: false,
  trailSl: false,
  openedAt: 1700000000000,
};
const v2Active = ctx.normalizeTrade(v1Active);
assert.strictEqual(v2Active.schemaVersion, 2, 'active trade schemaVersion must be 2');
assert(v2Active.id && typeof v2Active.id === 'string', 'active trade must have an id');
assert.strictEqual(v2Active.initialMargin, 200, 'initialMargin must equal 200');
assert.strictEqual(v2Active.remainingMargin, 200, 'remainingMargin must equal 200');
assert.strictEqual(v2Active.initialNotional, 2000, 'initialNotional must be margin * leverage = 2000');
assert.strictEqual(v2Active.remainingNotional, 2000, 'remainingNotional must be 2000');
assert.strictEqual(v2Active.quantity, 0.04, 'quantity must be notional / entry = 0.04');
assert.strictEqual(v2Active.initialSl, 49000, 'initialSl must be 49000');
assert.strictEqual(v2Active.currentSl, 49000, 'currentSl must be 49000');
assert.strictEqual(v2Active.initialRiskAmount, 40, 'initialRiskAmount must be |50000-49000| * 0.04 = 40 USDT');
assert.strictEqual(v2Active.plannedRewardAmount, 120, 'plannedRewardAmount must be |53000-50000| * 0.04 = 120 USDT');
assert.strictEqual(v2Active.plannedRr, 3.0, 'plannedRr must be 120 / 40 = 3.0');
assert.strictEqual(v2Active.realizedPnlGross, 0, 'initial realizedPnlGross must be 0');

// Test history v1 normalization with exitPrice / marginRoiPct
const v1HistPartial = {
  id: 'th_123',
  coin: 'ETHUSDT',
  dir: 1,
  entry: 3000,
  exitPrice: 3150,
  margin: 100,
  leverage: 10,
  notional: 1000,
  realizedPnl: 50,
  marginRoiPct: 50,
  reason: 'PARTIAL_TAKE_PROFIT',
  closedAt: 1700000100000,
};
const v2HistPartial = ctx.normalizeHistoryEvent(v1HistPartial);
assert.strictEqual(v2HistPartial.schemaVersion, 2, 'history schemaVersion must be 2');
assert.strictEqual(v2HistPartial.exit, 3150, 'exitPrice must be normalized to exit');
assert.strictEqual(v2HistPartial.realizedPnlGross, 50, 'realizedPnl must be normalized to realizedPnlGross');
assert.strictEqual(v2HistPartial.realizedRoiPct, 50, 'marginRoiPct must be normalized to realizedRoiPct');
assert.strictEqual(v2HistPartial.eventType, 'PARTIAL_CLOSE', 'eventType must be PARTIAL_CLOSE');

// Test history v1 normalization with exit / realizedRoi
const v1HistFull = {
  id: 't_456',
  coin: 'SOLUSDT',
  dir: -1,
  entry: 150,
  exit: 140,
  margin: 50,
  leverage: 5,
  sl: 155,
  tp: 135,
  realizedPnl: 16.67,
  realizedRoi: 33.34,
  reason: 'TP_HIT',
  closedAt: 1700000200000,
};
const v2HistFull = ctx.normalizeHistoryEvent(v1HistFull);
assert.strictEqual(v2HistFull.schemaVersion, 2);
assert.strictEqual(v2HistFull.exit, 140);
assert.strictEqual(v2HistFull.eventType, 'FULL_CLOSE');
assert.strictEqual(v2HistFull.realizedRoiPct, 33.34);

// ============================================================================
// 2. Contract: Full Close Creates Consistent Event
// ============================================================================
storage.set('aura-quant-terminal-active-trades-v1', JSON.stringify([v2Active]));
storage.set('aura-quant-terminal-history-trades-v1', JSON.stringify([]));
ctx.tradePrices = { BTCUSDT: 52000 };

const closeResult = ctx.closeTrade(0, 52000, 'MANUAL');
assert.strictEqual(closeResult, true, 'closeTrade with valid price must return true');
const remainingTrades = ctx.loadTrades();
assert.strictEqual(remainingTrades.length, 0, 'active trades must be empty after full close');

const history = ctx.loadTradeHistory();
assert.strictEqual(history.length, 1, 'history must have 1 event');
const ev = history[0];
assert.strictEqual(ev.eventType, 'FULL_CLOSE', 'event must be FULL_CLOSE');
assert.strictEqual(ev.fractionClosed, 1.0, 'full close fractionClosed must be 1.0');
assert.strictEqual(ev.entry, 50000);
assert.strictEqual(ev.exit, 52000);
assert.strictEqual(ev.marginClosed, 200);
assert.strictEqual(ev.notionalClosed, 2000);
assert.strictEqual(ev.quantityClosed, 0.04);
assert.strictEqual(ev.realizedPnlGross, 80, 'gross PnL must be 0.04 * (52000 - 50000) = 80');
assert.strictEqual(ev.realizedRoiPct, 40, 'gross ROI must be 80 / 200 * 100 = 40%');
assert.strictEqual(ev.initialRiskAmountClosed, 40);
assert.strictEqual(ev.realizedR, 2.0, 'realized R must be 80 / 40 = +2.0R');
assert.strictEqual(ev.reason, 'MANUAL');
assert(typeof ev.holdingMs === 'number' && ev.holdingMs >= 0, 'holdingMs must be non-negative number');

// ============================================================================
// 3. Contract: No Close Without Valid Mark Price (No Silent Zero-Trades)
// ============================================================================
storage.set('aura-quant-terminal-active-trades-v1', JSON.stringify([v2Active]));
storage.set('aura-quant-terminal-history-trades-v1', JSON.stringify([]));
ctx.tradePrices = {}; // No price available for BTCUSDT

const failClose1 = ctx.closeTrade(0, null, 'MANUAL');
assert.strictEqual(failClose1, false, 'closeTrade without valid mark price must fail and return false');
assert.strictEqual(ctx.loadTrades().length, 1, 'active trade must NOT be removed when close fails');
assert.strictEqual(ctx.loadTradeHistory().length, 0, 'history must NOT record invalid zero-trades');

const failClose2 = ctx.closeTrade(0, NaN, 'MANUAL');
assert.strictEqual(failClose2, false, 'closeTrade with NaN price must fail');
const failClose3 = ctx.closeTrade(0, -100, 'MANUAL');
assert.strictEqual(failClose3, false, 'closeTrade with negative price must fail');

// ============================================================================
// 4. Contract: Partial Close (25%, 50%, 75%) with Preserved Identity and Amounts
// ============================================================================
const tradeForPartial = {
  id: 'pt_test_partial',
  coin: 'ETHUSDT',
  dir: 1,
  entry: 3000,
  margin: 100,
  remainingMargin: 100,
  initialMargin: 100,
  leverage: 10,
  initialNotional: 1000,
  remainingNotional: 1000,
  quantity: 1000 / 3000,
  sl: 2900,
  initialSl: 2900,
  currentSl: 2900,
  tp: 3300,
  initialRiskAmount: (1000 / 3000) * 100,
  plannedRewardAmount: (1000 / 3000) * 300,
  plannedRr: 3.0,
  realizedPnlGross: 0,
  highestPrice: 3000,
  lowestPrice: 3000,
  autoBe: true,
  beActive: false,
  trailSl: false,
  openedAt: 1700000000000,
};

// 4a. 25% Partial Close
storage.set('aura-quant-terminal-active-trades-v1', JSON.stringify([tradeForPartial]));
storage.set('aura-quant-terminal-history-trades-v1', JSON.stringify([]));
ctx.tradePrices = { ETHUSDT: 3100 };

const part25 = ctx.takePartialProfit(0, 0.25);
assert.strictEqual(part25, true, 'takePartialProfit 25% must succeed');

let activeAfter25 = ctx.loadTrades();
assert.strictEqual(activeAfter25.length, 1, 'trade must remain active after partial close');
let t25 = activeAfter25[0];
assert.strictEqual(t25.id, 'pt_test_partial', 'trade id must be preserved');
assert.strictEqual(t25.initialMargin, 100, 'initialMargin must remain 100');
assert.strictEqual(t25.initialNotional, 1000, 'initialNotional must remain 1000');
assert.strictEqual(t25.initialRiskAmount, (1000 / 3000) * 100, 'initialRiskAmount basis must remain 100% intact');
assert.strictEqual(t25.remainingMargin, 75, 'remainingMargin must be 75');
assert.strictEqual(t25.remainingNotional, 750, 'remainingNotional must be 750');
assert.strictEqual(t25.quantity, 750 / 3000, 'quantity must be 750 / 3000');
assert.strictEqual(t25.sl, 3000, 'SL must be moved to entry (BE)');
assert.strictEqual(t25.beActive, true, 'beActive must be true after partial take profit');
assert.strictEqual(Math.round(t25.realizedPnlGross * 100) / 100, 8.33, 'accumulated gross realized PnL on remaining trade');

let hist25 = ctx.loadTradeHistory();
assert.strictEqual(hist25.length, 1);
assert.strictEqual(hist25[0].eventType, 'PARTIAL_CLOSE');
assert.strictEqual(hist25[0].tradeId, 'pt_test_partial');
assert.strictEqual(hist25[0].fractionClosed, 0.25);
assert.strictEqual(hist25[0].marginClosed, 25);
assert.strictEqual(hist25[0].notionalClosed, 250);
assert.strictEqual(hist25[0].quantityClosed, 250 / 3000);
assert.strictEqual(Math.round(hist25[0].realizedPnlGross * 100) / 100, 8.33);

// 4b. 50% and 75% options
storage.set('aura-quant-terminal-active-trades-v1', JSON.stringify([tradeForPartial]));
storage.set('aura-quant-terminal-history-trades-v1', JSON.stringify([]));
assert.strictEqual(ctx.takePartialProfit(0, 0.5), true);
assert.strictEqual(ctx.loadTrades()[0].remainingMargin, 50);

storage.set('aura-quant-terminal-active-trades-v1', JSON.stringify([tradeForPartial]));
storage.set('aura-quant-terminal-history-trades-v1', JSON.stringify([]));
assert.strictEqual(ctx.takePartialProfit(0, 0.75), true);
assert.strictEqual(ctx.loadTrades()[0].remainingMargin, 25);

// ============================================================================
// 5. Contract: Long/Short MFE/MAE and Realized R Metrics
// ============================================================================
assert.strictEqual(typeof ctx.calculateTradeMetrics, 'function', 'calculateTradeMetrics function required');

// Long MFE/MAE
const longMetrics = ctx.calculateTradeMetrics({
  dir: 1,
  entry: 100,
  initialMargin: 100,
  margin: 100,
  leverage: 10,
  initialSl: 90,
  highestPrice: 115,
  lowestPrice: 95,
  currentPrice: 110,
});
assert.strictEqual(longMetrics.mfePriceDiff, 15, 'Long MFE price diff: 115 - 100 = 15');
assert.strictEqual(longMetrics.mfeUsdt, 150, 'Long MFE USDT: 15 * 10 qty = 150');
assert.strictEqual(longMetrics.mfeR, 1.5, 'Long MFE R: 150 / 100 initial risk = 1.5R');
assert.strictEqual(longMetrics.maePriceDiff, 5, 'Long MAE price diff: 100 - 95 = 5');
assert.strictEqual(longMetrics.maeUsdt, -50, 'Long MAE USDT: -5 * 10 qty = -50');
assert.strictEqual(longMetrics.maeR, -0.5, 'Long MAE R: -50 / 100 initial risk = -0.5R');

// Short MFE/MAE
const shortMetrics = ctx.calculateTradeMetrics({
  dir: -1,
  entry: 100,
  initialMargin: 100,
  margin: 100,
  leverage: 10,
  initialSl: 110,
  highestPrice: 105,
  lowestPrice: 85,
  currentPrice: 90,
});
assert.strictEqual(shortMetrics.mfePriceDiff, 15, 'Short MFE price diff: 100 - 85 = 15');
assert.strictEqual(shortMetrics.mfeUsdt, 150, 'Short MFE USDT: 15 * 10 qty = 150');
assert.strictEqual(shortMetrics.mfeR, 1.5, 'Short MFE R: 150 / 100 initial risk = 1.5R');
assert.strictEqual(shortMetrics.maePriceDiff, 5, 'Short MAE price diff: 105 - 100 = 5');
assert.strictEqual(shortMetrics.maeUsdt, -50, 'Short MAE USDT: -50');
assert.strictEqual(shortMetrics.maeR, -0.5, 'Short MAE R: -0.5R');

// ============================================================================
// 6. Contract: Initial-R Basis Stability After BE / Trail
// ============================================================================
const beTradeMetrics = ctx.calculateTradeMetrics({
  dir: 1,
  entry: 100,
  initialMargin: 100,
  margin: 100,
  leverage: 10,
  initialSl: 90,
  currentSl: 100, // BE active
  beActive: true,
  currentPrice: 110,
});
assert.strictEqual(beTradeMetrics.currentR, 1.0, 'R-multiple must remain referenced to initial SL risk, not BE distance');
assert(!isNaN(beTradeMetrics.currentR) && isFinite(beTradeMetrics.currentR), 'BE must not cause divide-by-zero in R calculation');

// ============================================================================
// 7. Contract: History Statistics (Wins, Losses, BE, Partials)
// ============================================================================
assert.strictEqual(typeof ctx.calculateHistoryStats, 'function', 'calculateHistoryStats function required');

const sampleHistory = [
  { eventType: 'FULL_CLOSE', realizedPnlGross: 100, realizedRoiPct: 100, realizedR: 2.0, initialRiskAmountClosed: 50, holdingMs: 3600000, reason: 'TP_HIT' },
  { eventType: 'FULL_CLOSE', realizedPnlGross: -50, realizedRoiPct: -50, realizedR: -1.0, initialRiskAmountClosed: 50, holdingMs: 1800000, reason: 'SL_HIT' },
  { eventType: 'FULL_CLOSE', realizedPnlGross: 0, realizedRoiPct: 0, realizedR: 0.0, initialRiskAmountClosed: 50, holdingMs: 7200000, reason: 'BE_HIT' },
  { eventType: 'PARTIAL_CLOSE', realizedPnlGross: 50, realizedRoiPct: 50, realizedR: 2.0, initialRiskAmountClosed: 25, holdingMs: 3600000, reason: 'PARTIAL_TAKE_PROFIT' },
];

const stats = ctx.calculateHistoryStats(sampleHistory);
assert.strictEqual(stats.totalEvents, 4);
assert.strictEqual(stats.wins, 2);
assert.strictEqual(stats.losses, 1);
assert.strictEqual(stats.beCount, 1);
assert.strictEqual(stats.winRatePct, 50.0);
assert.strictEqual(stats.grossPnl, 100.0);
assert.strictEqual(stats.profitFactor, 3.0); // 150 win / 50 loss
assert.strictEqual(stats.avgR, 0.75); // (2.0 - 1.0 + 0 + 2.0) / 4
assert.strictEqual(stats.avgHoldingMs, 4050000);
assert.strictEqual(stats.bestPnl, 100.0);
assert.strictEqual(stats.worstPnl, -50.0);

// ============================================================================
// 8. Contract: BTC Trend Bias Scale
// ============================================================================
assert.strictEqual(typeof ctx.computeBtcBias, 'function', 'computeBtcBias function required');

const btcBull = ctx.computeBtcBias(78.4, 1);
assert.strictEqual(btcBull.available, true);
assert.strictEqual(btcBull.bias, 78);
assert.strictEqual(btcBull.text, 'BULL · 78%');
assert.strictEqual(btcBull.ariaText, 'BULL 78% Trend-Bias');

const btcBear = ctx.computeBtcBias(22.0, -1);
assert.strictEqual(btcBear.available, true);
assert.strictEqual(btcBear.bias, 22);
assert.strictEqual(btcBear.text, 'BEAR · 22%');

const btcNeutral = ctx.computeBtcBias(50.0, 0);
assert.strictEqual(btcNeutral.available, true);
assert.strictEqual(btcNeutral.bias, 50);
assert.strictEqual(btcNeutral.text, 'SIDEWAYS · 50%');

const btcSqueeze = ctx.computeBtcBias(34.0, 0);
assert.strictEqual(btcSqueeze.available, true);
assert.strictEqual(btcSqueeze.bias, 34);
assert.strictEqual(btcSqueeze.text, 'SIDEWAYS · 34%');

const btcUnavailable1 = ctx.computeBtcBias(NaN, null);
assert.strictEqual(btcUnavailable1.available, false);
assert.strictEqual(btcUnavailable1.bias, null, 'unavailable BTC must NOT fake 50');
assert.strictEqual(btcUnavailable1.text, 'nicht verfügbar');

const btcUnavailable2 = ctx.computeBtcBias(null, null);
assert.strictEqual(btcUnavailable2.available, false);
assert.strictEqual(btcUnavailable2.bias, null);

// ============================================================================
// 9. Contract: UI Contracts (Cards, Detail History, Portfolio KPIs, Progressbar, Multi-TP, Single-Item Delete, Autobot)
// ============================================================================
assert(html.includes('class="trade-card"'), 'trade tracker must render .trade-card elements');
assert(!html.includes('class="trade-head"'), 'misleading 7-column table header trade-head must be removed');
assert(html.includes('id="trade-portfolio-kpis"'), 'portfolio KPIs summary bar required');
assert(html.includes('id="trade-history-section"'), 'dedicated history section required');
assert(html.includes('id="trade-hist-filter-dir"'), 'history direction filter required');
assert(html.includes('id="trade-hist-filter-search"'), 'history symbol search required');
assert(html.includes('id="trade-hist-filter-reason"'), 'history exit reason filter required');
assert(html.includes('role="progressbar"'), 'BTC trend bias must expose role="progressbar"');
assert(html.includes('aria-valuemin="0"'), 'progressbar must have aria-valuemin="0"');
assert(html.includes('aria-valuemax="100"'), 'progressbar must have aria-valuemax="100"');
assert(html.includes('id="btn-toggle-more-tps"'), 'multi-TP toggle button required');
assert(html.includes('id="trade-tp2"'), 'trade-tp2 input field required');
assert(html.includes('id="trade-tp3"'), 'trade-tp3 input field required');
assert(html.includes('data-delete-hist-id'), 'single history item delete button required');
assert(html.includes('id="autobot-section"'), 'autobot section required');
assert(html.includes('id="btn-toggle-autobot"'), 'autobot toggle button required');
assert(html.includes('id="btn-config-autobot"'), 'autobot config button required');
assert(html.includes('id="ab-config-box"'), 'autobot config box required');
assert(html.includes('id="ab-equity"'), 'autobot equity display required');

// ============================================================================
// 10. Contract: DOM Rendering & Interactive Contracts (Live Trades & History)
// ============================================================================
// Setup mock DOM elements for render tests
const pkOpen = element('pkpi-open');
const pkMargin = element('pkpi-margin');
const pkNotional = element('pkpi-notional');
const pkPnl = element('pkpi-pnl');
const pkRoi = element('pkpi-roi');
const pkRisk = element('pkpi-risk');
const tradeListEl = element('trade-list');
const histListEl = element('trade-history-list');

// Inject active trades and verify renderLiveTrades() DOM update
storage.set('aura-quant-terminal-active-trades-v1', JSON.stringify([
  v2Active,
  {
    schemaVersion: 2,
    id: 'pt_sol_short',
    coin: 'SOLUSDT',
    dir: -1,
    entry: 150,
    markPrice: 140,
    initialMargin: 100,
    remainingMargin: 100,
    leverage: 5,
    initialSl: 160,
    currentSl: 160,
    tp: 130,
    initialRiskAmount: 33.33,
    plannedRewardAmount: 66.67,
    plannedRr: 2.0,
    realizedPnlGross: 0,
    openedAt: 1700000000000,
    status: 'OPEN'
  }
]));
ctx.tradePrices = { BTCUSDT: 52000, SOLUSDT: 140 };

ctx.renderLiveTrades();
assert.strictEqual(pkOpen.textContent, '2', 'portfolio KPI pkpi-open must reflect 2 open trades');
assert(pkMargin.textContent.includes('300.00'), 'portfolio KPI pkpi-margin must equal 300 USDT');
assert(pkNotional.textContent.includes('2500.00'), 'portfolio KPI pkpi-notional must equal 2500 USDT');
assert(tradeListEl.innerHTML.includes('class="trade-card"'), 'trade list must contain .trade-card elements');
assert(tradeListEl.innerHTML.includes('BTCUSDT'), 'trade list must contain BTCUSDT');
assert(tradeListEl.innerHTML.includes('SOLUSDT'), 'trade list must contain SOLUSDT');
assert(tradeListEl.innerHTML.includes('LONG 10x') || tradeListEl.innerHTML.includes('LONG'), 'trade list must render long direction');
assert(tradeListEl.innerHTML.includes('SHORT 5x') || tradeListEl.innerHTML.includes('SHORT'), 'trade list must render short direction');
assert(tradeListEl.innerHTML.includes('data-action-tp25'), 'trade card must have 25% TP button');
assert(tradeListEl.innerHTML.includes('data-action-tp50'), 'trade card must have 50% TP button');
assert(tradeListEl.innerHTML.includes('data-action-tp75'), 'trade card must have 75% TP button');
assert(tradeListEl.innerHTML.includes('data-action-be'), 'trade card must have Break-Even button');
assert(tradeListEl.innerHTML.includes('data-close-trade'), 'trade card must have Close button');

// Inject history events and verify renderTradeHistory() DOM update
storage.set('aura-quant-terminal-history-trades-v1', JSON.stringify(sampleHistory));
ctx.renderTradeHistory();

const hkCount = element('hkpi-count');
const hkWr = element('hkpi-wr');
assert.strictEqual(hkCount.textContent, '4', 'history count KPI must be 4');
assert(hkWr.textContent.includes('50.0%'), 'history winrate KPI must be 50.0%');
assert(histListEl.innerHTML.includes('class="history-card"'), 'history list must render .history-card elements');
assert(histListEl.innerHTML.includes('data-delete-hist-id'), 'history card must render delete button');

// Test History Filters: direction, symbol, exit reason
const histFilterDir = element('trade-hist-filter-dir');
const histFilterSearch = element('trade-hist-filter-search');
const histFilterReason = element('trade-hist-filter-reason');

// Filter by reason: TP_HIT
histFilterReason.value = 'TP_HIT';
ctx.renderTradeHistory();
assert.strictEqual(element('hkpi-count').textContent, '1', 'filter by TP_HIT should leave 1 event');

// Reset reason filter, test filter by direction: SHORT (-1)
histFilterReason.value = 'all';
histFilterDir.value = '-1';
ctx.renderTradeHistory();
// None of the sampleHistory items have dir=-1 (or they have default 1)
assert.strictEqual(element('hkpi-count').textContent, '0', 'filter by SHORT with no short events should give 0');

// Reset filters
histFilterDir.value = 'all';
histFilterReason.value = 'all';
ctx.renderTradeHistory();
assert.strictEqual(element('hkpi-count').textContent, '4', 'reset filters restores 4 events');

// Test MFE/MAE recorded in partial close history
storage.set('aura-quant-terminal-active-trades-v1', JSON.stringify([tradeForPartial]));
storage.set('aura-quant-terminal-history-trades-v1', JSON.stringify([]));
ctx.tradePrices = { ETHUSDT: 3150 };
ctx.takePartialProfit(0, 0.5);
const histEvents = ctx.loadTradeHistory();
assert.strictEqual(histEvents.length, 1);
assert(histEvents[0].mfe && typeof histEvents[0].mfe === 'object', 'partial close must record mfe');
assert(histEvents[0].mae && typeof histEvents[0].mae === 'object', 'partial close must record mae');
assert.strictEqual(histEvents[0].mfe.priceDiff, 150, 'MFE price diff: 3150 - 3000 = 150');

// ============================================================================
// 11. Contract: Dynamic Time-Stop Optimizer for Autobot
// ============================================================================
assert.strictEqual(typeof ctx.optimizeTimeStopForAsset, 'function', 'optimizeTimeStopForAsset function required');

// Fallback on insufficient data
const fallbackOpt = ctx.optimizeTimeStopForAsset([], null, { fallbackBars: 14, fallbackHours: 14 });
assert.strictEqual(fallbackOpt.bars, 14, 'fallback bars on empty candles');
assert.strictEqual(fallbackOpt.hours, 14, 'fallback hours on empty candles');
assert.strictEqual(fallbackOpt.reason, 'fallback_insufficient_history');

// Mock candles & indicators for optimization
const mockCandles = [];
for (let i = 0; i < 60; i++) {
  const price = 100 + Math.sin(i / 5) * 10;
  mockCandles.push({ t: i * 3600000, o: price, h: price + 2, l: price - 2, c: price + 0.5, v: 1000 });
}
const mockA = ctx.analyze ? ctx.analyze(mockCandles) : null;
const optResult = ctx.optimizeTimeStopForAsset(mockCandles, mockA, { fallbackBars: 12, maxCapHours: 24, minFloorHours: 3 });
assert(Number.isFinite(optResult.bars) && optResult.bars >= 3 && optResult.bars <= 30, 'optimized bars must be within valid range');
assert(Number.isFinite(optResult.hours) && optResult.hours >= 3 && optResult.hours <= 24, 'optimized hours must be within bounds');
assert.strictEqual(optResult.effectiveTrials, 18 * 20,
  'asset TimeStop must use its actual inclusive 5..24 candidate family under a 24h cap');

// Selection must be DSR-first, not raw expectancy*sqrt(sample count).
const originalWalkForward = ctx.runWalkForwardBacktest;
const seenDsrSweep = [];
ctx.runWalkForwardBacktest = (_candles, _A, options) => {
  seenDsrSweep.push(options);
  return options.timeStopBars === 5
    ? { dsr: { dsr: 0.55 }, stats: { exp: 10, total: 100 } }
    : { dsr: { dsr: 0.75 }, stats: { exp: 0.01, total: 2 } };
};
const dsrFirst = ctx.optimizeTimeStopForAsset(mockCandles, mockA, {
  timeframe: '1h', timeframeHours: 1, minBars: 5, maxBars: 6, maxCapHours: 24, minFloorHours: 1,
});
assert.strictEqual(dsrFirst.bars, 6, 'higher deflated DSR must beat higher unadjusted score');
assert.deepStrictEqual(seenDsrSweep.map(x => x.trialMultiplier), [2, 2], 'two evaluated candidates imply exactly two trial-family members');

// A 12-hour 15m fallback is 48 bars and must occur in the actual sweep.
const seenFallbackSweep = [];
ctx.runWalkForwardBacktest = (_candles, _A, options) => {
  seenFallbackSweep.push(options);
  return { dsr: { dsr: 0.5 }, stats: { exp: 0, total: 0 } };
};
ctx.optimizeTimeStopForAsset(mockCandles.concat(mockCandles), mockA, {
  timeframe: '15m', timeframeHours: 0.25, fallbackBars: 48, fallbackHours: 12,
  maxCapHours: 24, minFloorHours: 0.5,
});
assert(seenFallbackSweep.some(x => x.timeStopBars === 48), '15m/12h fallback must be an evaluated candidate');
assert.strictEqual(seenFallbackSweep[0].trialMultiplier, seenFallbackSweep.length,
  'trial multiplier must equal the actual inclusive evaluated candidate count');
ctx.runWalkForwardBacktest = originalWalkForward;

console.log('PASS all Live Trade Tracker & BTC Trend contracts validated');



// ============================================================================
// 12. Behavior: Autobot fresh-WF evidence integration
// ============================================================================
(async () => {
  const scanCtx = { ...ctx };
  scanCtx.globalThis = scanCtx;
  vm.createContext(scanCtx);

  const scanStart = scriptMatch[1].indexOf('  async scanAndExecuteOpportunities() {');
  const scanEnd = scriptMatch[1].indexOf('\n  },\n\n  render()', scanStart);
  assert(scanStart >= 0 && scanEnd > scanStart, 'Autobot scan source missing');
  let scanSource = scriptMatch[1];
  const scanBody = scanSource.slice(scanStart, scanEnd)
    .replace('computeBtcBias(App.data.btcScore, App.data.btcRegime)', '__scanComputeBtcBias(App.data.btcScore, App.data.btcRegime)')
    .replace('await fetchKlines(c.symbol, candidateGate.tf, 1000)', 'await __scanFetchKlines(c.symbol, candidateGate.tf, 1000)')
    .replace('const A = analyze(kdata.candles);', 'const A = __scanAnalyze(kdata.candles);')
    .replace('const freshGate = classifyRadarTf({', 'const freshGate = __scanClassifyRadarTf({')
    .replace('const freshWalkForward = runWalkForwardBacktest(kdata.candles, A, {', 'const freshWalkForward = __scanRunWalkForward(kdata.candles, A, {')
    .replace('const edgeGate = evaluateAutobotEdge(freshWalkForward);', 'const edgeGate = __scanEvaluateEdge(freshWalkForward);')
    .replace('const optTimeStop = optimizeTimeStopForAsset(kdata.candles, A, {', 'const optTimeStop = __scanOptimizeTimeStop(kdata.candles, A, {');
  scanSource = scanSource.slice(0, scanStart) + scanBody + scanSource.slice(scanEnd);
  vm.runInContext(scanSource + '\nthis.__Autobot = Autobot;\nthis.__App = App;', scanCtx);

  const bot = scanCtx.__Autobot;
  const candles = Array.from({ length: 50 }, (_, i) => ({ t: i, o: 100, h: 101, l: 99, c: 100, v: 1 }));
  const freshA = {
    n: 50, last: { score: 80, dir: 1, adx: 25, atr: 1 },
    c: new Float64Array(50).fill(100), e50: new Float64Array(50).fill(101),
    e200: new Float64Array(50).fill(100), adx: new Float64Array(50).fill(25),
    atr: new Float64Array(50).fill(1),
  };
  const candidate = {
    symbol: 'EDGEUSDT', executable: true, aligned: 3,
    bestInfo: { score: 80, dir: 1, status: 'ready', tradeable: true },
  };
  scanCtx.__App.data.radar = [candidate, { ...candidate, symbol: 'SECONDUSDT' }];
  scanCtx.__App.universe = [];
  scanCtx.__App.data.btcScore = null; scanCtx.__App.data.btcRegime = null;
  scanCtx.__App.fees = { maker: 0, taker: 0 }; scanCtx.__App.slippage = 0; scanCtx.__App.timeStopBars = 15;
  bot.trades = []; bot.equity = 10000; bot.min24hVol = 0; bot.btcFilter = false; bot.minScore = 78; bot.mtfNeed = 3;
  bot.save = () => {}; bot.render = () => {}; bot.log = () => {};
  scanCtx.__scanFetchKlines = async () => ({ candles });
  scanCtx.__scanAnalyze = () => freshA;
  scanCtx.__scanClassifyRadarTf = () => ({ tradeable: true, status: 'ready', score: 80, dir: 1 });
  scanCtx.__scanComputeBtcBias = () => ({ available: false });
  scanCtx.__scanOptimizeTimeStop = () => ({ bars: 12, hours: 12, reason: 'stub' });

  let receivedWf = null, receivedOptions = null;
  const rejectedWf = { evidenceStatus: 'OOS', stats: { total: 15, wr: 0.6, avgWinR: 1.8, avgLossR: 1 }, dsr: { dsr: 0.49 }, totalTrials: 36 };
  scanCtx.__scanRunWalkForward = (_c, _a, options) => { receivedOptions = options; return rejectedWf; };
  scanCtx.__scanEvaluateEdge = wf => { receivedWf = wf; return { accepted: false, edge: 0, sampleSize: 0, dsr: 0, effectiveTrials: 0 }; };
  await bot.scanAndExecuteOpportunities();
  assert.strictEqual(receivedWf, rejectedWf, 'full fresh walk-forward object must reach evidence gate');
  assert.strictEqual(receivedOptions.trialMultiplier, 2, 'trial multiplier must equal actual candidates');
  assert.strictEqual(receivedOptions.tfMinutes, 60, 'fresh selected 1h timeframe must pass 60 minutes');
  assert.strictEqual(bot.trades.length, 0, 'rejected OOS/DSR evidence must not reach trade creation');

  const acceptedWf = { ...rejectedWf, dsr: { dsr: 0.7 } };
  scanCtx.__scanRunWalkForward = (_c, _a, options) => { receivedOptions = options; return acceptedWf; };
  scanCtx.__scanEvaluateEdge = wf => {
    receivedWf = wf;
    return { accepted: true, edge: 0.68, sampleSize: 15, dsr: 0.7, effectiveTrials: wf.totalTrials };
  };
  await bot.scanAndExecuteOpportunities();
  assert.strictEqual(receivedWf, acceptedWf, 'accepted path must also receive full fresh walk-forward object');
  assert.strictEqual(bot.trades.length, 1, 'accepted evidence must permit one trade');
  assert.strictEqual(bot.trades[0].effectiveTrials, 36, 'accepted trade must persist effective trials');
  console.log('PASS Autobot scan uses fresh WF evidence, blocks rejected evidence, and persists effective trials');
})().catch(error => { console.error(error); process.exitCode = 1; });
