'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
assert(scriptMatch, 'dashboard script missing');

const scanStart = scriptMatch[1].indexOf('async scanAndExecuteOpportunities() {');
const scanEnd = scriptMatch[1].indexOf('function init() {');
assert(scanStart >= 0 && scanEnd > scanStart, 'Autobot scan source missing');

let source = scriptMatch[1];
const scanBody = source.slice(scanStart, scanEnd)
  .replace('computeBtcBias(App.data.btcScore, App.data.btcRegime)', '__computeBtcBias(App.data.btcScore, App.data.btcRegime)')
  .replace('await fetchKlines(c.symbol, candidateGate.tf, 1000)', 'await __fetchKlines(c.symbol, candidateGate.tf, 1000)')
  .replace('const A = analyze(kdata.candles);', 'const A = __analyze(kdata.candles);')
  .replace('const freshGate = classifyRadarTf({', 'const freshGate = __classifyRadarTf({')
  .replace('const freshWalkForward = runWalkForwardBacktest(kdata.candles, A, {', 'const freshWalkForward = __runWalkForward(kdata.candles, A, {')
  .replace(/const edgeGate = evaluateAutobotEdge\([^)]*\);/, 'const edgeGate = __evaluateEdge(freshWalkForward);')
  .replace('const optTimeStop = optimizeTimeStopForAsset(kdata.candles, A, {', 'const optTimeStop = __optimizeTimeStop(kdata.candles, A, {');
source = source.slice(0, scanStart) + scanBody + source.slice(scanEnd);

const ctx = {
  console,
  Math,
  Number,
  String,
  Date,
  Array,
  Object,
  Float64Array,
  JSON,
  Boolean,
  setTimeout,
  clearTimeout,
  RADAR_TFS: ['15m', '1h', '4h', '1d'],
  document: {
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener: () => {},
  },
  localStorage: { getItem: () => null, setItem: () => {} },
};
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(source + '\nthis.__Autobot = Autobot; this.__App = App;', ctx);

const bot = ctx.__Autobot;
const readyCandidate = {
  symbol: 'ALCHUSDT', executable: true, aligned: 3, mtfDir: 1,
  bestInfo: { score: 85, dir: 1, status: 'ready', tradeable: true, quality: 90 },
  tfScores: { '1h': { score: 85, dir: 1, status: 'ready', tradeable: true, quality: 90 } },
};
const candles = Array.from({ length: 50 }, (_, i) => ({ t: i, o: 100, h: 101, l: 99, c: 100, v: 1 }));
const freshA = {
  n: 50,
  last: { score: 85, dir: 1, adx: 25, atr: 1 },
  c: new Float64Array(50).fill(100),
  e50: new Float64Array(50).fill(101),
  e200: new Float64Array(50).fill(100),
  adx: new Float64Array(50).fill(25),
  atr: new Float64Array(50).fill(1),
};

function resetBot() {
  ctx.__App.data.radar = [readyCandidate];
  ctx.__App.universe = [{ symbol: readyCandidate.symbol, vol: 10000000, liquidityVerified: true }];
  ctx.__App.data.btcScore = null;
  ctx.__App.data.btcRegime = null;
  ctx.__App.fees = { maker: 0.0002, taker: 0.0006 };
  ctx.__App.slippage = 0.0005;
  ctx.__App.timeStopBars = 15;
  bot.trades = [];
  bot.equity = 10000;
  bot.initialEquity = 10000;
  bot.min24hVol = 0;
  bot.btcFilter = false;
  bot.minScore = 70;
  bot.mtfNeed = 2;
  bot._scanInProgress = false;
  bot.lastScanFunnel = null;
  bot.lastScanAt = 0;
  bot.save = () => {};
  bot.render = () => {};
  bot.log = () => {};
  ctx.__computeBtcBias = () => ({ available: false });
  ctx.__analyze = () => freshA;
  ctx.__classifyRadarTf = () => ({ tradeable: true, status: 'ready', score: 85, dir: 1 });
  ctx.__runWalkForward = () => ({ evidenceStatus: 'OOS', stats: { wr: 0.65, avgWinR: 2.0, avgLossR: 1.0, total: 20 } });
  ctx.__evaluateEdge = () => ({ accepted: true, edge: 0.35, sampleSize: 20, setupDsr: 0.25, universeDsr: 0.20, effectiveTrials: 18 });
  ctx.__optimizeTimeStop = () => ({ bars: 12, hours: 12, reason: 'opt' });
}

(async () => {
  // --- Test 1: Reentrancy Guard (concurrent scan calls) ---
  resetBot();
  ctx.__fetchKlines = () => new Promise(resolve => setTimeout(() => resolve({ candles }), 40));

  const p1 = bot.scanAndExecuteOpportunities();
  assert.strictEqual(bot._scanInProgress, true, 'bot._scanInProgress must be true while scan is running');

  const p2 = bot.scanAndExecuteOpportunities();
  assert.strictEqual(typeof p2.then, 'function', 'p2 must be thenable/Promise');
  const r2 = await p2;
  assert.strictEqual(r2, null, 'overlapping scan invocation must immediately return null');

  const r1 = await p1;
  assert.strictEqual(bot._scanInProgress, false, 'bot._scanInProgress must be reset to false in finally block');
  assert.ok(r1 && typeof r1 === 'object', 'first scan must return the funnel object');
  assert.strictEqual(r1.selected, 1, 'first scan must successfully select 1 opportunity');
  assert.strictEqual(bot.trades.length, 1, 'exactly 1 trade must be opened (no duplicates)');
  assert.strictEqual(bot.trades[0].coin, 'ALCHUSDT', 'trade must be for ALCHUSDT');
  assert.strictEqual(bot.lastScanFunnel, r1, 'lastScanFunnel must hold the valid funnel, not overwritten by rejected call');

  // --- Test 2: Belt-and-suspenders duplicate check before trade push ---
  resetBot();
  const initialEquity = bot.equity;
  ctx.__fetchKlines = async () => {
    // Inject a concurrent trade for ALCHUSDT into bot.trades while async await is pending
    bot.trades.push({
      id: 'concurrent_alch_1',
      coin: 'ALCHUSDT',
      dir: 1,
      entry: 100,
      margin: 200,
      leverage: 10,
      notional: 2000,
      openedAt: Date.now()
    });
    return { candles };
  };

  const funnelResult = await bot.scanAndExecuteOpportunities();
  assert.strictEqual(bot.trades.length, 1, 'must NOT push a second trade for ALCHUSDT when symbol already exists');
  assert.strictEqual(bot.trades[0].id, 'concurrent_alch_1', 'the existing trade must remain untouched');
  assert.strictEqual(funnelResult.rejects.DUPLICATE_OR_INVALID, 1, 'duplicate detected before push must increment DUPLICATE_OR_INVALID');
  assert.strictEqual(bot.equity, initialEquity, 'equity must not be deducted for rejected duplicate candidate');

  console.log('PASS Autobot scan reentrancy guard and duplicate race protection verified');
})().catch(err => {
  console.error(err);
  process.exit(1);
});
