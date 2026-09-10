'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const start = html.indexOf('async function loadRadar(');
const end = html.indexOf('\nfunction renderRadar()', start);
if (start < 0 || end < 0) throw new Error('loadRadar() source not found');
const loadRadarSource = html.slice(start, end);

function candleSeries(volume = 1) {
  return Array.from({ length: 80 }, (_, i) => ({
    t: i * 3600000, o: 100 + i, h: 101 + i, l: 99 + i, c: 100.5 + i, v: volume, tbv: null
  }));
}

function makeContinuousContext(coins) {
  const renderCounts = [];
  const context = {
    App: {
      symbol: 'BTCUSDT', chartTF: '1h',
      data: { radar: null, btcRegime: 1 },
      radarMap: new Map(), radarProgress: null,
      radarScanning: false, radarLoopActive: false,
    },
    RADAR_TFS: ['15m', '1h', '4h', '1d'],
    RADAR_BATCH_SIZE: 5,
    RADAR_BATCH_DELAY_MS: 0,
    RADAR_CYCLE_DELAY_MS: 0,
    RADAR_CONCURRENCY: 2,
    fetchKlines: async () => ({ candles: candleSeries(), source: 'test' }),
    analyze: candles => ({ n: candles.length, c: Float64Array.from(candles.map(x => x.c)), last: { score: 85, dir: 1, adx: 30, atr: 2, trend: 80, mom: 75, vol: 70, str: 65 } }),
    regimeOf: () => ({ reg: 1, isSqz: false }),
    classifyRadarTf: () => ({ status: 'ready', tradeable: true, quality: 85, candidate: true }),
    rankRadarCandidates: rows => rows.slice().sort((a, b) => b.avgScore - a.avgScore),
    restoreRadarSnapshot: () => null,
    persistRadarSnapshot() {},
    universeSymbols: () => coins,
    renderRadar() { renderCounts.push(context.App.data.radar ? context.App.data.radar.length : 0); },
    renderHero() {},
    isFinite, setTimeout, console,
  };
  vm.createContext(context);
  vm.runInContext(`${loadRadarSource}; this.loadRadar = loadRadar;`, context);
  return { context, renderCounts };
}

(async () => {
  const coins = Array.from({ length: 15 }, (_, i) => `COIN${i}USDT`);
  const { context, renderCounts } = makeContinuousContext(coins);

  // Run first cycle (continuous mode runs 1 pass when stopAfterOneCycle option or test hook is used)
  await context.loadRadar({ singleCycle: true });

  assert.strictEqual(context.App.data.radar.length, 15, 'first cycle must analyze all 15 coins');
  assert.strictEqual(context.App.radarMap.size, 15, 'radarMap must retain all 15 coins');

  // Now simulate a rolling update pass
  await context.loadRadar({ singleCycle: true, rolling: true });
  assert.strictEqual(context.App.data.radar.length, 15, 'rolling pass must maintain all 15 coins without dropping to 0');
  assert.strictEqual(context.App.radarMap.size, 15, 'radarMap must maintain all 15 coins during rolling pass');

  console.log('PASS continuous Action Radar cycle maintains full universe and refreshes rolling in background');
})().catch(err => {
  console.error('FAIL', err.stack || err);
  process.exit(1);
});
