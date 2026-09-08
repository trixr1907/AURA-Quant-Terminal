'use strict';

const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const start = html.indexOf('async function loadRadar(');
const end = html.indexOf('\nfunction renderRadar()', start);
if (start < 0 || end < 0) throw new Error('loadRadar() source not found');
const loadRadarSource = html.slice(start, end);

function candleSeries(volume = 1) {
  return Array.from({ length: 80 }, (_, i) => ({
    t: i * 3600000,
    o: 100 + i,
    h: 101 + i,
    l: 99 + i,
    c: 100.5 + i,
    v: volume,
    tbv: null,
  }));
}

function makeContext({ coins, fetchKlines }) {
  const list = { innerHTML: '' };
  const renderCalls = [];
  const context = {
    App: {
      symbol: 'BTCUSDT',
      chartTF: '1h',
      data: { radar: null, btcRegime: null },
    },
    RADAR_TFS: ['15m', '1h', '4h', '1d'],
    fetchKlines,
    analyze(candles) {
      const n = candles.length;
      return {
        n,
        c: Float64Array.from(candles.map(x => x.c)),
        last: { score: 80, dir: 1, adx: 30, atr: 2, trend: 80, mom: 75, vol: 70, str: 65 },
      };
    },
    regimeOf: () => ({ reg: 1, isSqz: false }),
    classifyRadarTf: () => ({ status: 'ready', tradeable: true, quality: 80, candidate: true }),
    rankRadarCandidates: rows => rows.slice().sort((a, b) => b.avgScore - a.avgScore),
    restoreRadarSnapshot: () => null,
    persistRadarSnapshot() {},
    universeSymbols: () => coins,
    isFinite,
    setTimeout,
    $: id => id === 'radarlist' ? list : null,
    renderCalls,
    renderRadar() { renderCalls.push(context.App.data.radar.length); },
    renderHero() {},
    console,
  };
  vm.createContext(context);
  vm.runInContext(
    `const RADAR_BATCH_SIZE = 10; const RADAR_BATCH_DELAY_MS = 0; ${loadRadarSource}; this.loadRadar = loadRadar;`,
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

async function testProgressiveBatchRendering() {
  const coins = Array.from({ length: 11 }, (_, i) => `COIN${i}USDT`);
  let releaseLast;
  const lastGate = new Promise(resolve => { releaseLast = resolve; });
  const { context } = makeContext({
    coins,
    fetchKlines: async symbol => {
      if (symbol === coins[10]) await lastGate;
      return { candles: candleSeries(), source: 'test' };
    },
  });

  const pending = context.loadRadar();
  await waitUntil(() => Array.isArray(context.App.data.radar) && context.App.data.radar.length === 10);
  if (!context.renderCalls.includes(10)) {
    throw new Error(`first batch was not rendered progressively: ${JSON.stringify(context.renderCalls)}`);
  }
  releaseLast();
  await pending;
  if (context.App.data.radar.length !== 11) {
    throw new Error(`expected 11 final rows, got ${context.App.data.radar.length}`);
  }
}

async function testDailyOrFourHourZeroVolumeSkipsLowerTimeframes() {
  const calls = [];
  const { context } = makeContext({
    coins: ['NOVOLUSDT'],
    fetchKlines: async (symbol, tf) => {
      calls.push(tf);
      return { candles: candleSeries(tf === '1d' ? 0 : 1), source: 'test' };
    },
  });

  await context.loadRadar();
  if (calls.includes('15m') || calls.includes('1h')) {
    throw new Error(`lower timeframes fetched despite zero daily volume: ${calls.join(',')}`);
  }
  const row = context.App.data.radar[0];
  if (!row || row.skipReason !== 'no_volume') {
    throw new Error(`missing no_volume skip reason: ${JSON.stringify(row)}`);
  }
}

(async () => {
  await testProgressiveBatchRendering();
  console.log('PASS radar renders each completed 10-coin batch');
  await testDailyOrFourHourZeroVolumeSkipsLowerTimeframes();
  console.log('PASS zero D1/4H volume skips lower-timeframe analysis');
})().catch(error => {
  console.error('FAIL', error.stack || error);
  process.exit(1);
});
