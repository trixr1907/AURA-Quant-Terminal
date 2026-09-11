'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function functionSource(name, nextMarker) {
  const start = html.indexOf(`function ${name}(`);
  const end = html.indexOf(nextMarker, start);
  if (start < 0 || end < 0) throw new Error(`${name}() source not found`);
  return html.slice(start, end);
}

const rankSource = functionSource('rankRadarCandidates', '\n/**\n * Risk-first broker sizing');
const sortStart = html.indexOf('function sortRadarCandidates(');
const sortEnd = html.indexOf('\nfunction renderRadar()', sortStart);
const sortSource = html.slice(sortStart, sortEnd);

const context = {
  SYM: { mtfNeed: 3, longTh: 75, shortTh: 25 },
  RADAR_TFS: ['15m', '1h', '4h', '1d'],
  isFinite,
};
vm.createContext(context);
vm.runInContext(`${rankSource}\n${sortSource}\nthis.rankRadarCandidates = rankRadarCandidates; this.sortRadarCandidates = sortRadarCandidates; this.groupRadarCandidates = groupRadarCandidates;`, context);

function tf(score, dir, extra = {}) {
  return {
    score,
    dir,
    quality: extra.quality ?? Math.abs(score - 50),
    tradeable: extra.tradeable ?? false,
    candidate: extra.candidate ?? ((dir === 1 && score >= 75) || (dir === -1 && score <= 25)),
    status: extra.status ?? (extra.tradeable ? 'ready' : (dir === 1 && score >= 75) || (dir === -1 && score <= 25) ? 'blocked_squeeze' : 'watch'),
    isSqz: extra.isSqz ?? false,
  };
}

function row(symbol, avgScore, mtfDir, aligned, tfScores, extra = {}) {
  return { symbol, avgScore, mtfDir, aligned, tfScores, btcBlock: false, ...extra };
}

const testRows = [
  row('HOTUSDT', 85, 1, 4, {
    '15m': tf(80, 1), '1h': tf(85, 1, { tradeable: true }), '4h': tf(88, 1, { tradeable: true }), '1d': tf(82, 1),
  }),
  row('CANDIDATEUSDT', 75, 1, 3, {
    '15m': tf(60, 1), '1h': tf(84, 1, { isSqz: true, status: 'blocked_squeeze', candidate: true }), '4h': tf(76, 1), '1d': tf(72, 1),
  }),
  row('WATCHUSDT', 50, 0, 2, {
    '15m': tf(52, 0), '1h': tf(50, 0), '4h': tf(48, 0), '1d': tf(50, 0),
  }),
];

const ranked = context.rankRadarCandidates(testRows, 'all');
const groups = context.groupRadarCandidates(ranked, 'quality');

// In quality mode, Hot Setups and Top Setup Candidates must be grouped distinctly
assert(groups.some(g => g.label.includes('Hot Setups') && g.rows.some(r => r.symbol === 'HOTUSDT')), 'HOTUSDT must be in Hot Setups');
assert(groups.some(g => g.label.includes('Kandidaten') && g.rows.some(r => r.symbol === 'CANDIDATEUSDT')), 'CANDIDATEUSDT must be in Top Candidates group');
assert(groups.some(g => (g.label.includes('Watchlist') || g.label.includes('Universe')) && g.rows.some(r => r.symbol === 'WATCHUSDT')), 'WATCHUSDT must be in Watchlist group');

// Ensure flattening preserves ranked order
const flattened = groups.flatMap(g => g.rows.map(r => r.symbol));
assert.deepStrictEqual(Array.from(flattened), ['HOTUSDT', 'CANDIDATEUSDT', 'WATCHUSDT'], 'grouping must preserve top-to-bottom rank order');

console.log('PASS Radar top candidates grouping and ranking');
