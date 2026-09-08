'use strict';

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
if (sortStart < 0) throw new Error('sortRadarCandidates() source not found');
const sortEnd = html.indexOf('\nfunction renderRadar()', sortStart);
if (sortEnd < 0) throw new Error('sortRadarCandidates() end not found');
const sortSource = html.slice(sortStart, sortEnd);

const context = {
  SYM: { mtfNeed: 3 },
  RADAR_TFS: ['15m', '1h', '4h', '1d'],
  isFinite,
};
vm.createContext(context);
vm.runInContext(`${rankSource}\n${sortSource}\nthis.sortRadarCandidates = sortRadarCandidates; this.groupRadarCandidates = groupRadarCandidates;`, context);

function tf(score, dir, extra = {}) {
  return {
    score,
    dir,
    quality: extra.quality ?? Math.abs(score - 50),
    tradeable: extra.tradeable ?? false,
    candidate: extra.candidate ?? true,
    status: extra.status ?? 'watch',
    isSqz: extra.isSqz ?? false,
  };
}

function row(symbol, avgScore, mtfDir, aligned, tfScores, extra = {}) {
  return { symbol, avgScore, mtfDir, aligned, tfScores, btcBlock: false, ...extra };
}

function symbols(rows) {
  return Array.from(rows, r => r.symbol);
}

function assertDeep(actual, expected, label) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) throw new Error(`${label}: expected ${e}, got ${a}`);
}

const fixtures = [
  row('ALPHAUSDT', 90, 1, 4, {
    '15m': tf(88, 1), '1h': tf(20, -1), '4h': tf(85, 1), '1d': tf(86, 1),
  }),
  row('BETAUSDT', 55, -1, 3, {
    '15m': tf(30, -1), '1h': tf(80, 1), '4h': tf(25, -1), '1d': tf(35, -1),
  }),
  row('GAMMAUSDT', 70, 1, 4, {
    '15m': tf(65, 1), '1h': tf(60, 1, { isSqz: true, status: 'blocked_squeeze' }), '4h': tf(72, 1), '1d': tf(75, 1),
  }),
  row('DELTAUSDT', 25, -1, 2, {
    '15m': tf(22, -1, { isSqz: true, status: 'blocked_squeeze' }), '1h': tf(30, -1), '4h': tf(28, -1), '1d': tf(20, -1),
  }),
];

assertDeep(
  symbols(context.sortRadarCandidates(fixtures, '1h', 'score_desc')),
  ['BETAUSDT', 'GAMMAUSDT', 'DELTAUSDT', 'ALPHAUSDT'],
  'score_desc must use the selected timeframe score',
);

assertDeep(
  symbols(context.sortRadarCandidates(fixtures, '1h', 'score_asc')),
  ['ALPHAUSDT', 'DELTAUSDT', 'GAMMAUSDT', 'BETAUSDT'],
  'score_asc must use the selected timeframe score',
);

assertDeep(
  symbols(context.sortRadarCandidates(fixtures, '1h', 'long_only')),
  ['BETAUSDT', 'GAMMAUSDT'],
  'long_only must use the selected timeframe direction',
);

assertDeep(
  symbols(context.sortRadarCandidates(fixtures, '1h', 'short_only')),
  ['ALPHAUSDT', 'DELTAUSDT'],
  'short_only must use the selected timeframe direction',
);

assertDeep(
  symbols(context.sortRadarCandidates(fixtures, '1h', 'squeeze')),
  ['GAMMAUSDT'],
  'squeeze must respect the selected timeframe',
);

assertDeep(
  symbols(context.sortRadarCandidates(fixtures, 'all', 'mtf_aligned')).sort(),
  ['ALPHAUSDT', 'GAMMAUSDT'],
  '4/4 MTF must filter rather than merely sort',
);

assertDeep(
  symbols(context.sortRadarCandidates(fixtures, 'all', 'alpha')),
  ['ALPHAUSDT', 'BETAUSDT', 'DELTAUSDT', 'GAMMAUSDT'],
  'alpha must sort symbols ascending',
);

assertDeep(
  context.groupRadarCandidates(context.sortRadarCandidates(fixtures, 'all', 'alpha'), 'alpha').flatMap(group => symbols(group.rows)),
  ['ALPHAUSDT', 'BETAUSDT', 'DELTAUSDT', 'GAMMAUSDT'],
  'grouping must preserve the selected global sort order',
);

console.log('PASS all Action Radar smart-sort modes');
