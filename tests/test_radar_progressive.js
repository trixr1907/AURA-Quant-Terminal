'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const loadStart = html.indexOf('async function loadRadar(');
const loadEnd = html.indexOf('\nfunction renderRadar()', loadStart);
if (loadStart < 0 || loadEnd < 0) throw new Error('loadRadar() source not found');
const loadRadarSource = html.slice(loadStart, loadEnd);
const rankStart = html.indexOf('function rankRadarCandidates(');
const rankEnd = html.indexOf('\n/**\n * Risk-first broker sizing', rankStart);
if (rankStart < 0 || rankEnd < 0) throw new Error('rankRadarCandidates() source not found');
const rankSource = html.slice(rankStart, rankEnd);

function candleSeries(volume = 1) {
  return Array.from({ length: 80 }, (_, i) => ({
    t: i * 3600000, o: 100 + i, h: 101 + i, l: 99 + i, c: 100.5 + i, v: volume, tbv: null,
  }));
}

function makeContext({ coins, fetchKlines, now = () => Date.now() }) {
  const list = { innerHTML: '' };
  const renderCalls = [];
  const context = {
    App: { symbol: 'BTCUSDT', chartTF: '1h', data: { radar: null, btcRegime: null } },
    Map, Date: { now }, RADAR_TFS: ['15m', '1h', '4h', '1d'],
    fetchKlines,
    analyze(candles) {
      const n = candles.length;
      return { n, c: Float64Array.from(candles.map(x => x.c)),
        last: { score: 80, dir: 1, adx: 30, atr: 2, trend: 80, mom: 75, vol: 70, str: 65 } };
    },
    regimeOf: () => ({ reg: 1, isSqz: false }),
    classifyRadarTf: () => ({ status: 'ready', tradeable: true, quality: 80, candidate: true }),
    rankRadarCandidates: rows => rows.slice().sort((a, b) => b.avgScore - a.avgScore),
    restoreRadarSnapshot: () => null, persistRadarSnapshot() {}, universeSymbols: () => coins,
    isFinite, setTimeout, $: id => id === 'radarlist' ? list : null,
    renderCalls, renderRadar() { renderCalls.push({ rows: context.App.data.radar.length, progress: { ...context.App.radarProgress } }); },
    renderHero() {}, console,
  };
  vm.createContext(context);
  vm.runInContext(
    `const RADAR_BATCH_SIZE = 2; const RADAR_BATCH_DELAY_MS = 0; const RADAR_CONCURRENCY = 1; ${loadRadarSource}; this.loadRadar = loadRadar;`,
    context,
  );
  return { context, list };
}

async function waitUntil(predicate, timeoutMs = 1000) {
  const deadline = Date.now() + timeoutMs;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error('timed out waiting for condition');
    await new Promise(resolve => setTimeout(resolve, 1));
  }
}

async function testProgressTransparencyAndBatchRendering() {
  const coins = ['COIN0USDT', 'COIN1USDT', 'COIN2USDT'];
  let releaseLast;
  const lastGate = new Promise(resolve => { releaseLast = resolve; });
  const { context } = makeContext({
    coins,
    fetchKlines: async symbol => {
      if (symbol === coins[2]) await lastGate;
      return { candles: candleSeries(), source: 'network' };
    },
  });

  const pending = context.loadRadar();
  await waitUntil(() => context.renderCalls.some(call => call.rows === 2));
  const batch = context.renderCalls.find(call => call.rows === 2).progress;
  assert.strictEqual(batch.succeeded, 2, 'successful markets must be counted separately');
  assert.strictEqual(batch.failed, 0, 'failed markets must be counted separately');
  assert.strictEqual(batch.skipped, 0, 'skipped markets must be counted separately');
  assert(Number.isFinite(batch.etaMs) && batch.etaMs >= 0, 'ETA must derive from measured batch duration');
  assert.strictEqual(batch.isRolling, false, 'initial run must be labelled as initial');
  releaseLast();
  await pending;
  assert.strictEqual(context.App.data.radar.length, 3);
}

async function testDataErrorsAreIncompleteNotNoVolume() {
  const { context } = makeContext({
    coins: ['ERRORUSDT'],
    fetchKlines: async (_symbol, tf) => {
      if (tf === '1d') throw new Error('upstream unavailable');
      return { candles: candleSeries(), source: 'network' };
    },
  });
  await context.loadRadar();
  const row = context.App.data.radar[0];
  assert(row && row.skipReason === 'data_error', `D1 failure must be data_error: ${JSON.stringify(row)}`);
  assert.strictEqual(row.incomplete, true, 'D1 failure must mark the market incomplete');
  assert.strictEqual(row.executable, false, 'incomplete market must never be executable');
}

async function testZeroVolumeRemainsSkipped() {
  const calls = [];
  const { context } = makeContext({
    coins: ['NOVOLUSDT'],
    fetchKlines: async (_symbol, tf) => {
      calls.push(tf);
      return { candles: candleSeries(tf === '1d' ? 0 : 1), source: 'network' };
    },
  });
  await context.loadRadar();
  assert(!calls.includes('15m') && !calls.includes('1h'), `lower TFs fetched despite zero daily volume: ${calls.join(',')}`);
  assert.strictEqual(context.App.data.radar[0].skipReason, 'no_volume');
}

async function testConcurrencyLimitsCoinAnalyses() {
  const coins = Array.from({ length: 4 }, (_, i) => `COIN${i}USDT`);
  let active = 0;
  let peak = 0;
  const { context } = makeContext({
    coins,
    fetchKlines: async () => {
      active += 1; peak = Math.max(peak, active);
      await new Promise(resolve => setTimeout(resolve, 5));
      active -= 1;
      return { candles: candleSeries(), source: 'network' };
    },
  });
  await context.loadRadar();
  assert(peak <= 1, `RADAR_CONCURRENCY=1 must serialize coin analyses, got ${peak}`);
}

function testIncompleteCannotRankExecutable() {
  const context = { SYM: { mtfNeed: 3 }, isFinite };
  vm.createContext(context);
  vm.runInContext(`${rankSource}; this.rankRadarCandidates = rankRadarCandidates;`, context);
  const [row] = context.rankRadarCandidates([{
    symbol: 'ERRORUSDT', incomplete: true, aligned: 4, mtfDir: 1, btcBlock: false,
    tfScores: { '1d': { score: 80, dir: 1, status: 'ready', tradeable: true, quality: 90 } },
  }]);
  assert.strictEqual(row.executable, false, 'incomplete rows cannot become executable during ranking');
}

(async () => {
  await testProgressTransparencyAndBatchRendering();
  console.log('PASS radar renders batches with separate counters and measured ETA');
  await testDataErrorsAreIncompleteNotNoVolume();
  console.log('PASS D1 errors are incomplete data_error rows, never executable');
  await testZeroVolumeRemainsSkipped();
  console.log('PASS measured zero liquidity remains no_volume and skips lower TFs');
  await testConcurrencyLimitsCoinAnalyses();
  console.log('PASS RADAR_CONCURRENCY limits concurrent coin analyses');
  testIncompleteCannotRankExecutable();
  console.log('PASS incomplete rows never rank as executable');
})().catch(error => {
  console.error('FAIL', error.stack || error);
  process.exit(1);
});
