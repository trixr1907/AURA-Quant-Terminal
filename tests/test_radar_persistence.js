'use strict';

const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const start = html.indexOf('async function loadRadar(');
const end = html.indexOf('\n/** Apply user-selected filtering/sorting', start);
if (start < 0 || end < 0) throw new Error('loadRadar() source not found');
const loadRadarSource = html.slice(start, end);

function makeContext() {
  const coins = ['AAAUSDT', 'BBBUSDT'];
  let fetchCalls = 0;
  const persisted = [{
    symbol: 'AAAUSDT', avgScore: 82, mtfDir: 1, aligned: 3, btcBlock: false,
    tfScores: {
      '15m': { score: 78, dir: 1, status: 'ready', tradeable: true, quality: 75, candidate: true },
      '1h': { score: 82, dir: 1, status: 'ready', tradeable: true, quality: 82, candidate: true },
      '4h': { score: 85, dir: 1, status: 'ready', tradeable: true, quality: 88, candidate: true },
      '1d': { score: 70, dir: 1, status: 'watch', tradeable: false, quality: 55, candidate: false },
    }, comps: [], scannedAt: Date.now() - 1000,
  }];
  const context = {
    App: { symbol: 'BTCUSDT', chartTF: '1h', data: { radar: null, btcRegime: 1 }, radarMap: new Map(), radarProgress: null, universe: [] },
    Map,
    RADAR_TFS: ['15m', '1h', '4h', '1d'], RADAR_BATCH_SIZE: 10, RADAR_BATCH_DELAY_MS: 0,
    fetchKlines: async () => { fetchCalls += 1; throw new Error('cache should prevent a full rescan'); },
    analyze: () => { throw new Error('cache should prevent analysis'); },
    regimeOf: () => ({ reg: 1, isSqz: false }), classifyRadarTf: () => ({}),
    rankRadarCandidates: rows => rows, universeSymbols: () => coins,
    restoreRadarSnapshot: () => ({ rows: persisted, progress: { done: 1, total: coins.length, scanning: false, skipped: 0 } }),
    persistRadarSnapshot() {}, renderRadar() {}, renderHero() {}, loadBtcMarketContext: async () => {},
    isFinite, setTimeout, console,
  };
  vm.createContext(context);
  vm.runInContext(`${loadRadarSource}; this.loadRadar = loadRadar;`, context);
  return { context, getFetchCalls: () => fetchCalls };
}

(async () => {
  const { context, getFetchCalls } = makeContext();
  await context.loadRadar();
  if (getFetchCalls() !== 0) throw new Error(`expected cached startup, got ${getFetchCalls()} network calls`);
  if (!Array.isArray(context.App.data.radar) || context.App.data.radar.length !== 1) throw new Error('persisted radar snapshot was not restored');
  if (context.App.radarProgress.scanning) throw new Error('fresh restored snapshot must render as completed');
  console.log('PASS fresh persisted radar snapshot survives a browser reload without restarting the full scan');
})().catch(error => {
  console.error('FAIL', error.stack || error);
  process.exit(1);
});
