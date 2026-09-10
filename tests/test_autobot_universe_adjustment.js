// tests/test_autobot_universe_adjustment.js
// Acceptance test suite for Phase 1: Universe-Adjusted DSR, Trial Multiplier & Gate Mechanics

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const htmlPath = path.join(__dirname, '..', 'Symbiose_Dashboard.html');
const html = fs.readFileSync(htmlPath, 'utf8');

const scriptMatch = html.match(/<script(?:\s+type="text\/javascript")?>([\s\S]*?)<\/script>/i);
assert(scriptMatch, 'HTML inline script missing');

const context = {
  console,
  setTimeout,
  clearTimeout,
  setInterval,
  clearInterval,
  Date,
  Math,
  Number,
  String,
  Array,
  Object,
  Float64Array,
  Uint8Array,
  Int32Array,
  JSON,
  Boolean,
  RegExp,
  document: {
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener: () => {},
  },
  window: {
    addEventListener: () => {},
  },
  localStorage: {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {},
  },
};

vm.createContext(context);
vm.runInContext(scriptMatch[1], context);

console.log('--- Testing Acceptance Criteria 1: Kein Doppelzählen ---');
{
  const candles = Array.from({ length: 1000 }, (_, i) => ({
    t: i * 3600000,
    o: 100 + (i % 10),
    h: 105 + (i % 10),
    l: 95 + (i % 10),
    c: 100 + ((i + 1) % 10),
    v: 1000
  }));
  const A = context.analyze(candles);
  assert(A && A.n, 'Candle analysis must succeed');

  // Multiplier = 1 -> totalTrials = 18 * 1 = 18
  const wf1 = context.runWalkForwardBacktest(candles, A, { trialMultiplier: 1 });
  assert.strictEqual(wf1.setupTrials, 18, 'setupTrials must be exactly 18 (internal paramGrid.length)');
  assert.strictEqual(wf1.totalTrials, 18, 'totalTrials must be 18 when trialMultiplier = 1');
  assert.strictEqual(wf1.trialMultiplier, 1, 'trialMultiplier must equal 1');

  // Multiplier = 480 -> totalTrials = 18 * 480 = 8640 (No double counting of 18)
  const wf480 = context.runWalkForwardBacktest(candles, A, { trialMultiplier: 480 });
  assert.strictEqual(wf480.setupTrials, 18, 'setupTrials remains 18');
  assert.strictEqual(wf480.totalTrials, 18 * 480, 'totalTrials must be exactly 18 * 480 = 8640');
  assert.strictEqual(wf480.trialMultiplier, 480, 'trialMultiplier must equal 480');
  assert(Number.isFinite(wf480.setupDsr.dsr), 'setupDsr must be calculated');
  assert(Number.isFinite(wf480.universeDsr.dsr), 'universeDsr must be calculated');
  assert(wf480.setupDsr.dsr >= wf480.universeDsr.dsr, 'setupDsr (18 trials) must be >= universeDsr (8640 trials)');
}
console.log('PASS Acceptance Criteria 1: Kein Doppelzählen verified');

console.log('--- Testing Acceptance Criteria 2: Kein Survivor-Bias ---');
(async () => {
  // Setup synthetic radar with 120 markets, where only 6 pass radar filtering
  const radar120 = [];
  for (let i = 0; i < 120; i++) {
    const isSurvivor = i < 6;
    radar120.push({
      symbol: `COIN${i}USDT`,
      executable: isSurvivor,
      aligned: isSurvivor ? 3 : 1,
      bestTF: '1h',
      bestInfo: {
        score: isSurvivor ? 82 : 45,
        dir: 1,
        status: isSurvivor ? 'ready' : 'neutral',
        tradeable: isSurvivor
      }
    });
  }

  const scanCtx = {
    console,
    setTimeout,
    clearTimeout,
    Date,
    Math,
    Number,
    String,
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
    localStorage: {
      getItem: () => null,
      setItem: () => {},
    },
  };
  vm.createContext(scanCtx);

  const scanStart = scriptMatch[1].indexOf('async scanAndExecuteOpportunities() {');
  const scanEnd = scriptMatch[1].indexOf('function init() {');
  assert(scanStart >= 0 && scanEnd > scanStart, 'Autobot scan source missing');
  let scanSource = scriptMatch[1];
  const scanBody = scanSource.slice(scanStart, scanEnd)
    .replace('computeBtcBias(App.data.btcScore, App.data.btcRegime)', '__scanComputeBtcBias(App.data.btcScore, App.data.btcRegime)')
    .replace('await fetchKlines(c.symbol, candidateGate.tf, 1000)', 'await __scanFetchKlines(c.symbol, candidateGate.tf, 1000)')
    .replace('const A = analyze(kdata.candles);', 'const A = __scanAnalyze(kdata.candles);')
    .replace('const freshGate = classifyRadarTf({', 'const freshGate = __scanClassifyRadarTf({')
    .replace('const freshWalkForward = runWalkForwardBacktest(kdata.candles, A, {', 'const freshWalkForward = __scanRunWalkForward(kdata.candles, A, {')
    .replace(/const edgeGate = evaluateAutobotEdge\([^)]*\);/, 'const edgeGate = __scanEvaluateEdge(freshWalkForward);')
    .replace('const optTimeStop = optimizeTimeStopForAsset(kdata.candles, A, {', 'const optTimeStop = __scanOptimizeTimeStop(kdata.candles, A, {');
  scanSource = scanSource.slice(0, scanStart) + scanBody + scanSource.slice(scanEnd);
  vm.runInContext(scanSource + '\nthis.__Autobot = Autobot;\nthis.__App = App;', scanCtx);

  const bot = scanCtx.__Autobot;
  scanCtx.__App.data.radar = radar120;
  scanCtx.__App.universe = radar120.map(r => ({ symbol: r.symbol, vol: 10000000 }));
  scanCtx.__App.data.btcScore = null;
  scanCtx.__App.data.btcRegime = null;
  scanCtx.__App.fees = { maker: 0, taker: 0 };
  scanCtx.__App.slippage = 0;
  scanCtx.__App.timeStopBars = 15;
  bot.trades = [];
  bot.equity = 10000;
  bot.min24hVol = 0;
  bot.btcFilter = false;
  bot.minScore = 78;
  bot.mtfNeed = 3;
  bot.save = () => {};
  bot.render = () => {};
  bot.log = () => {};

  const candles = Array.from({ length: 50 }, (_, i) => ({ t: i, o: 100, h: 101, l: 99, c: 100, v: 1 }));
  const freshA = {
    n: 50, last: { score: 82, dir: 1, adx: 25, atr: 1 },
    c: new Float64Array(50).fill(100), e50: new Float64Array(50).fill(101),
    e200: new Float64Array(50).fill(100), adx: new Float64Array(50).fill(25),
    atr: new Float64Array(50).fill(1),
  };
  scanCtx.__scanFetchKlines = async () => ({ candles });
  scanCtx.__scanAnalyze = () => freshA;
  scanCtx.__scanClassifyRadarTf = () => ({ tradeable: true, status: 'ready', score: 82, dir: 1 });
  scanCtx.__scanComputeBtcBias = () => ({ available: false });
  scanCtx.__scanOptimizeTimeStop = () => ({ bars: 12, hours: 12, reason: 'stub' });

  let capturedOptions = null;
  scanCtx.__scanRunWalkForward = (_c, _a, options) => {
    capturedOptions = options;
    return {
      evidenceStatus: 'OOS',
      stats: { total: 20, wr: 0.65, avgWinR: 1.8, avgLossR: 1.0 },
      dsr: { dsr: 0.35 },
      setupDsr: { dsr: 0.85 },
      universeDsr: { dsr: 0.35 },
      totalTrials: 18 * options.trialMultiplier,
      setupTrials: 18
    };
  };
  scanCtx.__scanEvaluateEdge = (wf) => {
    return {
      accepted: true,
      edge: 0.8,
      sampleSize: 20,
      dsr: 0.85,
      setupDsr: 0.85,
      universeDsr: 0.35,
      effectiveTrials: wf.totalTrials,
      setupTrials: 18,
      strictApplied: false
    };
  };

  const funnel = await bot.scanAndExecuteOpportunities();
  assert(funnel, 'Scan must produce a funnel report');
  assert.strictEqual(funnel.scanned, 120 * 4, 'scanned must equal 120 markets * 4 timeframes = 480');
  assert.strictEqual(funnel.radarFiltered, 6, 'radarFiltered must equal 6 surviving candidates');
  assert.strictEqual(funnel.wfEvaluated, 480, 'wfEvaluated must equal full tested hypotheses family (480), NOT 6');
  assert.strictEqual(capturedOptions.trialMultiplier, 480, 'Walk-forward trialMultiplier must be 480, eliminating survivor bias');

  // Dynamic Universe tests: 35 markets -> 140 hypotheses; 150 markets -> 600 hypotheses
  scanCtx.__App.data.radar = radar120.slice(0, 35);
  scanCtx.__App.universe = scanCtx.__App.data.radar.map(r => ({ symbol: r.symbol, vol: 10000000 }));
  const funnel35 = await bot.scanAndExecuteOpportunities();
  assert.strictEqual(funnel35.scanned, 35 * 4, 'dynamic universe 35 markets * 4 TFs must equal 140');
  assert.strictEqual(funnel35.wfEvaluated, 140, 'wfEvaluated must equal 140');

  scanCtx.__App.data.radar = Array.from({ length: 150 }, (_, i) => ({
    symbol: `COIN${i}USDT`, executable: false, aligned: 1, bestTF: '1h', bestInfo: { score: 40, dir: 1, status: 'neutral', tradeable: false }
  }));
  scanCtx.__App.universe = scanCtx.__App.data.radar.map(r => ({ symbol: r.symbol, vol: 10000000 }));
  const funnel150 = await bot.scanAndExecuteOpportunities();
  assert.strictEqual(funnel150.scanned, 150 * 4, 'dynamic universe 150 markets * 4 TFs must equal 600');
  assert.strictEqual(funnel150.wfEvaluated, 600, 'wfEvaluated must equal 600');

  console.log('PASS Acceptance Criteria 2: Kein Survivor-Bias & dynamisches Universum verified');
})().then(() => {
  console.log('--- Testing Acceptance Criteria 3: Provenance Lockbox ---');
  const provPath = path.join(__dirname, 'fixtures', 'golden', 'provenance.json');
  const prov = JSON.parse(fs.readFileSync(provPath, 'utf8'));
  assert(prov.lockbox, 'provenance.json must contain lockbox object');
  assert.strictEqual(prov.lockbox.cutoff_time, '2026-09-10T00:00:00Z', 'Lockbox cutoff must be 2026-09-10T00:00:00Z');
  assert.strictEqual(prov.lockbox.locked_span_days, 60, 'Locked span must be 60 days');
  assert.strictEqual(prov.lockbox.status, 'LOCKED', 'Lockbox status must be LOCKED');
  assert.strictEqual(prov.lockbox.mode, 'forward_holdout', 'Lockbox mode must be forward_holdout');
  console.log('PASS Acceptance Criteria 3: Provenance Lockbox verified');

  console.log('--- Testing Acceptance Criteria 4: Option B (Default) vs Option A (Strict) ---');
  const candidateWf = {
    evidenceStatus: 'OOS',
    stats: { total: 18, wr: 0.6, avgWinR: 2.0, avgLossR: 1.0 },
    dsr: { dsr: 0.31 },
    setupDsr: { dsr: 0.92 },
    universeDsr: { dsr: 0.31 },
    totalTrials: 8640,
    setupTrials: 18
  };

  // Option B (Default: strictUniverseGate = false)
  const evalOptB = context.evaluateAutobotEdge(candidateWf, 15, { strictUniverseGate: false });
  assert.strictEqual(evalOptB.accepted, true, 'Option B default must accept trade based on setupDsr >= 0.5');
  assert.strictEqual(evalOptB.setupDsr, 0.92, 'Must report setupDsr 0.92');
  assert.strictEqual(evalOptB.universeDsr, 0.31, 'Must report universeDsr 0.31');
  assert.strictEqual(evalOptB.effectiveTrials, 8640, 'Must report effectiveTrials 8640');
  assert.strictEqual(evalOptB.strictApplied, false, 'strictApplied must be false');

  // Option A (Strict: strictUniverseGate = true)
  const evalOptA = context.evaluateAutobotEdge(candidateWf, 15, { strictUniverseGate: true });
  assert.strictEqual(evalOptA.accepted, false, 'Option A must reject trade because universeDsr (0.31) < 0.5');
  assert.strictEqual(evalOptA.strictApplied, true, 'strictApplied must be true');

  console.log('PASS Acceptance Criteria 4: Option B vs Option A Gate verified');
  console.log('\nALL ACCEPTANCE CRITERIA 1-4 PASSED SUCCESSFULLY.');
}).catch(err => {
  console.error('FAIL:', err);
  process.exit(1);
});
