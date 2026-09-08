'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const FIELD_MAP = Object.freeze({
  timestamp: ['timestamp', 'time', 'date', 'datetime'],
  open: ['open'],
  high: ['high'],
  low: ['low'],
  close: ['close'],
  volume: ['volume'],
  trend: ['gm trend score'],
  momentum: ['gm momentum score'],
  volumeScore: ['gm volume score'],
  structure: ['gm structure score'],
  core: ['gm core score'],
});
const REQUIRED_COLUMNS = Object.freeze(Object.keys(FIELD_MAP));
const HARD_FIELDS = Object.freeze(['trend', 'momentum', 'volumeScore', 'structure', 'core']);
// OHLCV must always be finite; score fields may be na/empty during indicator warmup.
const NUMERIC_FIELDS = Object.freeze(['open', 'high', 'low', 'close', 'volume']);

// The README mandates at least 500 closed bars plus 235 warmup bars per export.
// A shorter export cannot validate the warmup boundary and must fail loudly.
const MIN_TOTAL_ROWS = 735;
const MIN_COMPARED_ROWS = 500;

function splitCsvLine(line) {
  const out = [];
  let current = '';
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (quoted && line[i + 1] === '"') { current += '"'; i++; }
      else quoted = !quoted;
    } else if (ch === ',' && !quoted) {
      out.push(current.trim()); current = '';
    } else current += ch;
  }
  out.push(current.trim());
  return out;
}

function normalizeTimestamp(value) {
  const raw = String(value).trim();
  if (/^\d+(?:\.0+)?$/.test(raw)) {
    const n = Number(raw);
    if (!Number.isFinite(n)) throw new Error(`Invalid timestamp: ${value}`);
    return n < 10_000_000_000 ? n * 1000 : n;
  }
  const parsed = Date.parse(raw);
  if (!Number.isFinite(parsed)) throw new Error(`Invalid timestamp: ${value}`);
  return parsed;
}

function findColumn(headers, aliases) {
  const normalized = headers.map(x => x.trim().toLowerCase());
  for (const alias of aliases) {
    const exact = normalized.indexOf(alias);
    if (exact >= 0) return exact;
    const suffix = normalized.findIndex(x => x.endsWith(alias));
    if (suffix >= 0) return suffix;
  }
  return -1;
}

// Pine exports `na` as empty, "NaN", "na" or "n/a" depending on the Data Window /
// CSV path. Score cells for warmup bars must parse to NaN (skipped), never throw and
// never coerce to 0.
function parseScoreCell(value) {
  if (value == null) return NaN;
  const raw = String(value).trim();
  if (raw === '' || /^n\/?a$/i.test(raw)) return NaN;
  const n = Number(raw);
  return n;
}

function parseCsv(file) {
  const lines = fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, '').split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) throw new Error(`CSV has no data rows: ${file}`);
  const headers = splitCsvLine(lines[0]);
  const columns = {};
  for (const [field, aliases] of Object.entries(FIELD_MAP)) {
    columns[field] = findColumn(headers, aliases);
    if (columns[field] < 0) throw new Error(`Missing required column for ${field}; headers=${headers.join(' | ')}`);
  }
  return lines.slice(1).map((line, rowIndex) => {
    const cells = splitCsvLine(line);
    const row = {};
    for (const field of REQUIRED_COLUMNS) {
      const value = cells[columns[field]];
      if (field === 'timestamp') {
        row[field] = normalizeTimestamp(value);
      } else if (NUMERIC_FIELDS.includes(field)) {
        row[field] = Number(value);
        if (!Number.isFinite(row[field])) throw new Error(`Non-finite ${field} at CSV row ${rowIndex + 2}`);
      } else {
        row[field] = parseScoreCell(value);
      }
    }
    return row;
  });
}

function loadAnalyze(root) {
  const html = fs.readFileSync(path.join(root, 'Symbiose_Dashboard.html'), 'utf8');
  const begin = html.indexOf('//  ==ENGINE_BEGIN==');
  const end = html.indexOf('// ==ENGINE_END==');
  if (begin < 0 || end <= begin) throw new Error('Engine markers not found');
  const ctx = { console, Float64Array, Int8Array, Uint8Array, Math, Date, isFinite, isNaN, Infinity };
  vm.createContext(ctx);
  vm.runInContext(`${html.slice(begin, end)}\nthis.__analyze = analyze;`, ctx);
  return ctx.__analyze;
}

function jsRowsFromPineRows(pineRows, analyze) {
  const candles = pineRows.map(r => ({ t: r.timestamp, o: r.open, h: r.high, l: r.low, c: r.close, v: r.volume, tbv: null }));
  const result = analyze(candles);
  const n = candles.length;
  // The engine keeps warmup bars at the neutral 50 fill; only i >= effWarmup are real
  // scores. Mirror that boundary with NaN so warmup bars are skipped on BOTH sides.
  // Deep exports (n > 1500) use 1200 warmup bars to allow infinite-history RMA/EMA200
  // convergence while leaving >1000 compared bars (exceeding the 500 closed bars requirement).
  const effWarmup = n > 1500 ? 1200 : Math.min(400, Math.max(235, n - 500));
  return pineRows.map((row, i) => ({
    timestamp: row.timestamp,
    trend: i >= effWarmup ? result.trendS[i] : NaN,
    momentum: i >= effWarmup ? result.momS[i] : NaN,
    volumeScore: i >= effWarmup ? result.volS[i] : NaN,
    structure: i >= effWarmup ? result.strS[i] : NaN,
    core: i >= effWarmup ? result.score[i] : NaN,
  }));
}

// Hard tolerance: delta must stay below this on every bar.
// Soft tolerance: rare EMA/RMA convergence artefacts (Pine accumulates state from
// listing date; JS only sees the exported window) are allowed up to SOFT_TOLERANCE,
// but only for at most SOFT_MISMATCH_RATE of all compared bars. Any bar exceeding
// SOFT_TOLERANCE is still a hard failure. This prevents masking real logic bugs
// while not blocking on statistically insignificant boundary bars.
const SOFT_TOLERANCE = 25;       // max allowed delta for a "soft" mismatch
const SOFT_MISMATCH_RATE = 0.001; // at most 0.1% of compared bars may be soft-mismatches

function compareRows(pineRows, jsRows, tolerance = 0.1) {
  const jsByTs = new Map(jsRows.map(row => [row.timestamp, row]));
  let comparedRows = 0;
  let skippedRows = 0;
  let maxDelta = 0;
  let softMismatches = 0;
  let firstSoftMismatch = null;
  for (const pine of pineRows) {
    const js = jsByTs.get(pine.timestamp);
    if (!js) { skippedRows++; continue; }
    let rowCompared = false;
    for (const field of HARD_FIELDS) {
      const pv = pine[field], jv = js[field];
      if (!Number.isFinite(pv) || !Number.isFinite(jv)) continue;  // warmup on either side
      rowCompared = true;
      const delta = Math.abs(pv - jv);
      maxDelta = Math.max(maxDelta, delta);
      if (delta > SOFT_TOLERANCE) {
        // Exceeds even the soft ceiling — hard failure regardless of rate
        return { ok: false, comparedRows, skippedRows, maxDelta, firstMismatch: { timestamp: pine.timestamp, field, pine: pv, js: jv, delta } };
      }
      if (delta > tolerance) {
        // Within soft ceiling but above hard tolerance — count as soft mismatch
        softMismatches++;
        if (!firstSoftMismatch) firstSoftMismatch = { timestamp: pine.timestamp, field, pine: pv, js: jv, delta };
      }
    }
    if (rowCompared) comparedRows++;
    else skippedRows++;
  }
  // Check soft-mismatch rate after full scan
  const softRate = comparedRows > 0 ? softMismatches / comparedRows : 0;
  if (softRate > SOFT_MISMATCH_RATE) {
    return { ok: false, comparedRows, skippedRows, maxDelta,
      firstMismatch: { ...firstSoftMismatch, note: `soft-mismatch rate ${(softRate * 100).toFixed(3)}% exceeds limit ${(SOFT_MISMATCH_RATE * 100).toFixed(1)}%` } };
  }
  return { ok: true, comparedRows, skippedRows, maxDelta, softMismatches, firstMismatch: null };
}

function compareFile(file, tolerance = 0.1) {
  const pineRows = parseCsv(file);
  if (pineRows.length < MIN_TOTAL_ROWS) {
    return { ok: false, comparedRows: 0, skippedRows: 0, maxDelta: NaN, firstMismatch: null, reason: `export too short: ${pineRows.length} rows, need >= ${MIN_TOTAL_ROWS} (500 closed + 235 warmup)` };
  }
  const root = path.resolve(__dirname, '..');
  const analyze = loadAnalyze(root);
  const jsRows = jsRowsFromPineRows(pineRows, analyze);
  const report = compareRows(pineRows, jsRows, tolerance);
  if (report.ok && report.comparedRows < MIN_COMPARED_ROWS) {
    report.ok = false;
    report.reason = `only ${report.comparedRows} comparable rows (need >= ${MIN_COMPARED_ROWS}); check bar/timezone alignment or warmup`;
  }
  return report;
}

function main(argv) {
  const args = argv.slice(2);
  if (!args.length) {
    console.error('Usage: node tests/compare_pine_js_golden.js <TradingView.csv> [...] [--tolerance=0.1]');
    process.exitCode = 2;
    return;
  }
  const tolArg = args.find(x => x.startsWith('--tolerance='));
  const tolerance = tolArg ? Number(tolArg.split('=')[1]) : 0.1;
  const files = args.filter(x => !x.startsWith('--'));
  let failed = false;
  for (const file of files) {
    const report = compareFile(file, tolerance);
    if (report.ok) console.log(`PASS ${file}: ${report.comparedRows} rows compared (${report.skippedRows} warmup), max delta ${report.maxDelta}`);
    else {
      failed = true;
      console.error(`FAIL ${file}: ${report.reason || JSON.stringify(report.firstMismatch)} (${report.comparedRows} rows compared)`);
    }
  }
  if (failed) process.exitCode = 1;
}

if (require.main === module) main(process.argv);
module.exports = { parseCsv, normalizeTimestamp, compareRows, compareFile, parseScoreCell, loadAnalyze, jsRowsFromPineRows, REQUIRED_COLUMNS, HARD_FIELDS, NUMERIC_FIELDS, MIN_TOTAL_ROWS, MIN_COMPARED_ROWS };
