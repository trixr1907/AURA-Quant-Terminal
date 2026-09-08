'use strict';

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const {
  parseCsv,
  normalizeTimestamp,
  compareRows,
  compareFile,
  parseScoreCell,
  loadAnalyze,
  jsRowsFromPineRows,
  REQUIRED_COLUMNS,
  HARD_FIELDS,
  MIN_TOTAL_ROWS,
  MIN_COMPARED_ROWS,
} = require('./compare_pine_js_golden.js');

const sample = path.join(__dirname, 'fixtures/golden/sample_valid.csv');

// ---- parser + tolerance unit checks (unchanged behavior) ----
const parsed = parseCsv(sample);
assert.strictEqual(parsed.length, 1);
assert.deepStrictEqual(Object.keys(parsed[0]), REQUIRED_COLUMNS);
assert.strictEqual(normalizeTimestamp('1704067200000'), 1704067200000);
assert.strictEqual(normalizeTimestamp('2024-01-01T00:00:00Z'), 1704067200000);

const good = compareRows(
  [{ timestamp: 1, trend: 50, momentum: 60, volume: 70, structure: 80, core: 64.5 }],
  [{ timestamp: 1, trend: 50.05, momentum: 59.95, volume: 70, structure: 80, core: 64.5 }],
  0.1,
);
assert.strictEqual(good.ok, true);
assert.strictEqual(good.comparedRows, 1);

const bad = compareRows(
  [{ timestamp: 1, trend: 50, momentum: 60, volume: 70, structure: 80, core: 64.5 }],
  [{ timestamp: 1, trend: 50.11, momentum: 60, volume: 70, structure: 80, core: 64.5 }],
  0.1,
);
assert.strictEqual(bad.ok, false);
assert.strictEqual(bad.firstMismatch.field, 'trend');
assert.ok(bad.firstMismatch.delta > 0.1);

// ---- warmup NaN handling ----
assert.ok(Number.isNaN(parseScoreCell('')));
assert.ok(Number.isNaN(parseScoreCell('na')));
assert.ok(Number.isNaN(parseScoreCell('NaN')));
assert.strictEqual(parseScoreCell('50'), 50);

// a warmup row (Pine na) must be skipped, not counted and not flagged
const warm = compareRows(
  [{ timestamp: 1, trend: NaN, momentum: NaN, volumeScore: NaN, structure: NaN, core: NaN }],
  [{ timestamp: 1, trend: 50, momentum: 50, volumeScore: 50, structure: 50, core: 50 }],
  0.1,
);
assert.strictEqual(warm.ok, true);
assert.strictEqual(warm.comparedRows, 0);
assert.strictEqual(warm.skippedRows, 1);

// ---- end-to-end round trip: engine self-consistency on a realistic synthetic CSV ----
function synthCandles(n) {
  // deterministic, non-trivial OHLCV so real scores (not neutral 50) are produced
  const candles = [];
  let price = 100;
  for (let i = 0; i < n; i++) {
    const drift = Math.sin(i / 9) * 0.4 + Math.sin(i / 37) * 0.6;
    const o = price;
    const c = price + drift;
    const h = Math.max(o, c) + 0.3 + 0.1 * Math.abs(Math.cos(i / 5));
    const l = Math.min(o, c) - 0.3 - 0.1 * Math.abs(Math.sin(i / 7));
    const v = 500 + 400 * Math.abs(Math.sin(i / 13));
    candles.push({ t: Date.UTC(2024, 0, 1) + i * 3600_000, o, h, l, c, v, tbv: null });
    price = c;
  }
  return candles;
}

const N = 900;
const candles = synthCandles(N);
const analyze = loadAnalyze(path.resolve(__dirname, '..'));
const pineRows = candles.map(c => ({ timestamp: c.t, open: c.o, high: c.h, low: c.l, close: c.c, volume: c.v }));
const jsRows = jsRowsFromPineRows(pineRows, analyze);

// Build a TradingView-style CSV: ISO timestamps, OHLCV, and score cells that are empty
// (na) during warmup and the engine's own values afterwards.
function iso(ms) { return new Date(ms).toISOString(); }
const header = 'time,open,high,low,close,volume,GM Trend Score,GM Momentum Score,GM Volume Score,GM Structure Score,GM Core Score';
const lines = [header];
for (let i = 0; i < N; i++) {
  const r = jsRows[i];
  const score = (v) => (Number.isFinite(v) ? v : '');
  lines.push([
    iso(pineRows[i].timestamp), pineRows[i].open, pineRows[i].high, pineRows[i].low,
    pineRows[i].close, pineRows[i].volume,
    score(r.trend), score(r.momentum), score(r.volumeScore), score(r.structure), score(r.core),
  ].join(','));
}
const tmp = path.join(os.tmpdir(), `golden_roundtrip_${process.pid}.csv`);
fs.writeFileSync(tmp, lines.join('\n') + '\n', 'utf8');

const report = compareFile(tmp);
assert.strictEqual(report.ok, true, JSON.stringify(report));
assert.ok(report.comparedRows >= MIN_COMPARED_ROWS, `comparedRows=${report.comparedRows}`);
assert.ok(report.maxDelta < 1e-9, `maxDelta=${report.maxDelta}`);
fs.unlinkSync(tmp);

// ---- too-short export must fail loudly (not a false green) ----
const short = path.join(os.tmpdir(), `golden_short_${process.pid}.csv`);
fs.writeFileSync(short, lines.slice(0, 100).join('\n') + '\n', 'utf8');
const shortReport = compareFile(short);
assert.strictEqual(shortReport.ok, false);
assert.ok(/too short/.test(shortReport.reason || ''), shortReport.reason);
fs.unlinkSync(short);

// ---- wrong column name must throw (silent 0-fill or dropped column would be worse) ----
const wrongCol = path.join(os.tmpdir(), `golden_wrongcol_${process.pid}.csv`);
const wrongHeader = 'time,open,high,low,close,volume,GM Trend Score,GM Momentum Score,GM Volume Score,GM Structure,GM Core Score';
fs.writeFileSync(wrongCol, [wrongHeader].concat(lines.slice(1)).join('\n') + '\n', 'utf8');
assert.throws(() => parseCsv(wrongCol), /Missing required column for structure/);
fs.unlinkSync(wrongCol);

console.log('test_compare_pine_js_golden.js: ALL ASSERTIONS PASSED');
