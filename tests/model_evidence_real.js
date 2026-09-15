'use strict';
/**
 * Real Data Model Evidence Gate
 *
 * Runs the purged walk-forward engine on the 5 real TradingView golden master
 * exports (BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT) using standard baseline
 * parameters (makerFee: 0.0002, takerFee: 0.0006, slippage: 0.0005, timeStopBars: 15)
 * on the last 1500 bars of each fixture.
 *
 * Outputs JSON with fail-closed verdict: 'NO_EVIDENCE' unless all symbols achieve
 * DSR >= 0.5 AND positive expectancy.
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { execFileSync } = require('node:child_process');

function loadVerifiedLedgerTrials() {
  try {
    const output = execFileSync(process.env.PYTHON || 'python3', [path.join(__dirname, '..', 'scripts', 'verify_ledger.py')], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    const evidence = JSON.parse(output);
    const trials = evidence.total_model_experiments;
    if (evidence.ok !== true || !Number.isInteger(trials) || trials < 1) throw new Error('invalid verified trial total');
    return trials;
  } catch (error) {
    throw new Error(`TRIALS_LEDGER_INVALID: ${error.message}`);
  }
}

const html = fs.readFileSync(path.join(__dirname, '..', 'Symbiose_Dashboard.html'), 'utf8');
const b = html.indexOf('//  ==ENGINE_BEGIN==');
const e = html.indexOf('// ==ENGINE_END==', b);
const code = html.slice(b, e);
const sandbox = { console, Float64Array, Date, Math, Array, Object, JSON, Number };
vm.createContext(sandbox);
vm.runInContext(code + '\n__E = { analyze, runWalkForwardBacktest, evaluateTrades, calcDSR }; __DSR_TRIALS = DSR_TRIALS;', sandbox);
const { analyze, runWalkForwardBacktest, calcDSR } = sandbox.__E;
const ENGINE_DSR_TRIALS = sandbox.__DSR_TRIALS;
const DSR_TRIALS = Math.max(18, loadVerifiedLedgerTrials(), ENGINE_DSR_TRIALS);

const GOLDEN_DIR = path.join(__dirname, 'fixtures', 'golden');
const GOLDEN_FILES = [
  'BTCUSDT_1h.csv',
  'ETHUSDT_1h.csv',
  'SOLUSDT_1h.csv',
  'XRPUSDT_4h.csv',
  'DOGEUSDT_4h.csv',
];

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

function normalizeTimestamp(val, fallbackIndex) {
  const n = Number(val);
  if (!Number.isFinite(n) || n <= 0) return (fallbackIndex || 0) * 3600000;
  return n < 10_000_000_000 ? n * 1000 : n;
}

function parseCsv(content) {
  const lines = content.trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const headers = splitCsvLine(lines[0]).map(h => h.toLowerCase().trim());
  const tIdx = headers.findIndex(h => ['timestamp', 'time', 'date', 'datetime'].includes(h));
  const oIdx = headers.indexOf('open');
  const hIdx = headers.indexOf('high');
  const lIdx = headers.indexOf('low');
  const cIdx = headers.indexOf('close');
  const vIdx = headers.indexOf('volume');

  if (oIdx < 0 || hIdx < 0 || lIdx < 0 || cIdx < 0) return [];

  const candles = [];
  for (let i = 1; i < lines.length; i++) {
    const row = splitCsvLine(lines[i]);
    if (row.length <= Math.max(oIdx, hIdx, lIdx, cIdx)) continue;
    const rawT = tIdx >= 0 ? row[tIdx] : i * 3600000;
    const t = normalizeTimestamp(rawT, i);
    const o = Number(row[oIdx]);
    const h = Number(row[hIdx]);
    const l = Number(row[lIdx]);
    const c = Number(row[cIdx]);
    const v = vIdx >= 0 ? Number(row[vIdx]) : 0;
    if (Number.isFinite(o) && Number.isFinite(h) && Number.isFinite(l) && Number.isFinite(c)) {
      candles.push({ t, o, h, l, c, v: Number.isFinite(v) ? v : 0 });
    }
  }
  return candles;
}

const perSymbol = [];
let allPassed = true;

for (const f of GOLDEN_FILES) {
  const filePath = path.join(GOLDEN_DIR, f);
  if (!fs.existsSync(filePath)) {
    allPassed = false;
    perSymbol.push({ symbol: f.replace('.csv', ''), error: 'file_missing', verdict: 'NO_EVIDENCE' });
    continue;
  }
  const content = fs.readFileSync(filePath, 'utf8');
  const allCandles = parseCsv(content);
  const nBars = Math.min(1500, allCandles.length);
  const candles = allCandles.slice(allCandles.length - nBars);
  if (candles.length < 500) {
    allPassed = false;
    perSymbol.push({ symbol: f.replace('.csv', ''), error: 'insufficient_bars', n: candles.length, verdict: 'NO_EVIDENCE' });
    continue;
  }
  const A = analyze(candles);
  const wf = runWalkForwardBacktest(candles, A, {
    makerFee: 0.0002,
    takerFee: 0.0006,
    slippage: 0.0005,
    timeStopBars: 15,
  });

  const exp = wf?.stats?.exp || 0;
  const pf = wf?.stats?.pf || 0;
  const wr = wf?.stats?.wr || 0;
  const dsr = (() => {
    const returns = Array.isArray(wf?.stats?.returns) ? wf.stats.returns : [];
    const sourceDsr = Number.isFinite(+wf?.setupDsr?.dsr) ? wf.setupDsr : wf?.dsr;
    return returns.length >= 3 ? calcDSR(returns, DSR_TRIALS).dsr : (Number.isFinite(+sourceDsr?.dsr) ? +sourceDsr.dsr : 0);
  })();
  const total = wf?.stats?.total || 0;
  const trials = Math.max(wf?.totalTrials || 18, DSR_TRIALS);

  const passedSymbol = exp > 0 && dsr >= 0.5 && total >= 15;
  if (!passedSymbol) {
    allPassed = false;
  }

  perSymbol.push({
    symbol: f.replace('.csv', ''),
    n: candles.length,
    trades: total,
    exp,
    pf,
    wr,
    dsr,
    trials,
    verdict: passedSymbol ? 'EVIDENCE_PRESENT' : 'NO_EVIDENCE',
  });
}

const verdict = allPassed && perSymbol.length === GOLDEN_FILES.length ? 'EVIDENCE_PRESENT' : 'NO_EVIDENCE';

const output = {
  verdict,
  per_symbol: perSymbol,
  note: 'real golden fixtures baseline evaluation',
};

if (require.main === module) {
  console.log(JSON.stringify(output, null, 2));
  process.exit(0);
}

module.exports = {
  normalizeTimestamp,
  parseCsv,
  output,
  GOLDEN_FILES,
};
