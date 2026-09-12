#!/usr/bin/env node
'use strict';

/**
 * CVD Dashboard Export Helper
 *
 * Runs the authoritative pure JavaScript engine from Symbiose_Dashboard.html
 * on a given CSV file and outputs JSON with {cvd, ema_cvd, delta}.
 */

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.resolve(__dirname, '..');
const DASHBOARD_HTML = path.join(ROOT, 'Symbiose_Dashboard.html');

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

function parseOhlcvCsv(filePath) {
  const content = fs.readFileSync(filePath, 'utf8').replace(/^\uFEFF/, '');
  const lines = content.split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) throw new Error(`CSV has no rows: ${filePath}`);
  const headers = splitCsvLine(lines[0]);
  const colTime = findColumn(headers, ['timestamp', 'time', 'date', 'datetime']);
  const colOpen = findColumn(headers, ['open']);
  const colHigh = findColumn(headers, ['high']);
  const colLow = findColumn(headers, ['low']);
  const colClose = findColumn(headers, ['close']);
  const colVol = findColumn(headers, ['volume']);

  if (colTime < 0 || colOpen < 0 || colHigh < 0 || colLow < 0 || colClose < 0 || colVol < 0) {
    throw new Error(`Missing OHLCV columns in ${filePath}`);
  }

  const candles = [];
  for (let i = 1; i < lines.length; i++) {
    const cells = splitCsvLine(lines[i]);
    const t = normalizeTimestamp(cells[colTime]);
    const o = Number(cells[colOpen]);
    const h = Number(cells[colHigh]);
    const l = Number(cells[colLow]);
    const c = Number(cells[colClose]);
    const v = Number(cells[colVol]);
    if (![o, h, l, c, v].every(Number.isFinite)) {
      throw new Error(`Non-finite numeric value at row ${i + 1}`);
    }
    candles.push({ t, o, h, l, c, v, tbv: null });
  }
  return candles;
}

function loadAnalyzeEngine() {
  const html = fs.readFileSync(DASHBOARD_HTML, 'utf8');
  const begin = html.indexOf('//  ==ENGINE_BEGIN==');
  const end = html.indexOf('// ==ENGINE_END==');
  if (begin < 0 || end <= begin) throw new Error('Engine markers missing in Symbiose_Dashboard.html');
  const ctx = { console, Float64Array, Int8Array, Uint8Array, Math, Date, isFinite: Number.isFinite, isNaN: Number.isNaN, Infinity, Number };
  vm.createContext(ctx);
  vm.runInContext(`${html.slice(begin, end)}\nthis.__analyze = analyze;`, ctx); // NOSONAR: safe isolated script slice
  return ctx.__analyze;
}

function main() {
  const args = process.argv.slice(2);
  if (!args.length) {
    console.error('Usage: node scripts/cvd_dashboard_export.js <csv-file>');
    process.exit(1);
  }
  const csvPath = path.resolve(args[0]);
  const candles = parseOhlcvCsv(csvPath);
  const analyze = loadAnalyzeEngine();
  const res = analyze(candles);

  const payload = {
    bars: candles.length,
    cvd: Array.from(res.cvd),
    ema_cvd: Array.from(res.emaCvd),
    delta: Array.from(res.cvdDelta),
  };
  process.stdout.write(JSON.stringify(payload));
}

if (require.main === module) {
  main();
}

module.exports = { parseOhlcvCsv, loadAnalyzeEngine };
