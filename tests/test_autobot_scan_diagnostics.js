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
vm.runInContext(source + '\nthis.__Autobot = Autobot; this.__App = App; this.__autobotRejectSummary = autobotRejectSummary;', ctx);

const bot = ctx.__Autobot;
const readyCandidate = {
  symbol: 'EDGEUSDT', executable: true, aligned: 3, mtfDir: 1,
  bestInfo: { score: 82, dir: 1, status: 'ready', tradeable: true, quality: 90 },
  tfScores: { '1h': { score: 82, dir: 1, status: 'ready', tradeable: true, quality: 90 } },
};
const candles = Array.from({ length: 50 }, (_, i) => ({ t: i, o: 100, h: 101, l: 99, c: 100, v: 1 }));
const freshA = {
  n: 50,
  last: { score: 82, dir: 1, adx: 25, atr: 1 },
  c: new Float64Array(50).fill(100),
  e50: new Float64Array(50).fill(101),
  e200: new Float64Array(50).fill(100),
  adx: new Float64Array(50).fill(25),
  atr: new Float64Array(50).fill(1),
};

function resetBot() {
  ctx.__App.data.radar = [readyCandidate];
  ctx.__App.universe = [{ symbol: readyCandidate.symbol, vol: 10000000 }];
  ctx.__App.data.btcScore = null;
  ctx.__App.data.btcRegime = null;
  ctx.__App.fees = { maker: 0, taker: 0 };
  ctx.__App.slippage = 0;
  ctx.__App.timeStopBars = 15;
  bot.trades = [];
  bot.equity = 10000;
  bot.min24hVol = 0;
  bot.btcFilter = false;
  bot.minScore = 78;
  bot.mtfNeed = 3;
  bot.save = () => {};
  bot.render = () => {};
  bot.log = () => {};
  ctx.__computeBtcBias = () => ({ available: false });
  ctx.__fetchKlines = async () => ({ candles });
  ctx.__analyze = () => freshA;
  ctx.__classifyRadarTf = () => ({ tradeable: true, status: 'ready', score: 82, dir: 1 });
  ctx.__runWalkForward = () => ({ evidenceStatus: 'OOS' });
  ctx.__evaluateEdge = () => ({ accepted: false, edge: -0.1, sampleSize: 9, setupDsr: 0.1, universeDsr: 0.05 });
  ctx.__optimizeTimeStop = () => ({ bars: 12, hours: 12, reason: 'stub' });
}

(async () => {
  resetBot();
  const rejected = await bot.scanAndExecuteOpportunities();
  assert.strictEqual(rejected.selected, 0);
  assert.strictEqual(rejected.rejects.MODEL_NO_EVIDENCE, 1,
    'failed OOS evidence must remain fail-closed and expose its reject reason');
  assert.strictEqual(rejected.lastError, null, 'ordinary rejection must not be reported as an error');

  for (const sensitiveMessage of [
    '&lt;img src=x onerror=alert(1)&gt; Authorization: Bearer secret-value https://api.test/x?token=query-secret',
    '{"Authorization":"Bearer json-secret"}',
    'Authorization: "Bearer quoted-secret"',
  ]) {
    resetBot();
    ctx.__fetchKlines = async () => { throw new Error(sensitiveMessage); };
    const failed = await bot.scanAndExecuteOpportunities();
    assert.strictEqual(failed.rejects.REFETCH_ERROR, 1,
      'fetch failure must be visible instead of disappearing in an empty catch');
    assert(failed.lastError && !failed.lastError.includes('<') && !failed.lastError.includes('>') && !failed.lastError.includes('&lt;'),
      'last error must be safely escaped before UI rendering');
    assert(!/secret/i.test(failed.lastError),
      'last error must redact raw, quoted, JSON, and query-string credentials');
  }

  const maliciousSummary = ctx.__autobotRejectSummary({
    rejects: { '<img src=x onerror=alert(1)>': 9, MODEL_NO_EVIDENCE: 1 },
  });
  assert.strictEqual(maliciousSummary, '1× keine OOS-Evidenz',
    'unknown persisted reject keys must be discarded by the display allowlist');

  const renderStart = html.indexOf("const funnelEl = $('ab-funnel-summary');");
  const renderEnd = html.indexOf('// 2. Metrics & Portfolio KPIs', renderStart);
  const renderSource = html.slice(renderStart, renderEnd);
  assert(!renderSource.includes('${f.lastError}</span>'),
    'untrusted provider errors must never be interpolated into innerHTML');
  assert(renderSource.includes('errorEl.textContent = f.lastError'),
    'provider error text must be assigned through textContent');

  console.log('PASS Autobot scan reports fail-closed rejection diagnostics');
})().catch(error => {
  console.error(error);
  process.exit(1);
});
