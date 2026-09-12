'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  const match = html.match(new RegExp(`function\\s+${name}\\s*\\([\\s\\S]*?\\n\\}`, 'm'));
  assert(match, `function ${name} not found in HTML`);
  return match[0];
}

const fmtPxSrc = extractFunction('fmtPx');
const fmtDsrSrc = extractFunction('fmtDsr');
const fmtTrialsSrc = extractFunction('fmtTrials');
const tfToHoursSrc = extractFunction('tfToHours');
const tfToMinutesSrc = extractFunction('tfToMinutes');
const formatTimeStopDisplaySrc = extractFunction('formatTimeStopDisplay');
const formatAutobotEntryLogSrc = extractFunction('formatAutobotEntryLog');

const sandbox = { Number, Math, String, isFinite };
vm.createContext(sandbox);
vm.runInContext(`
  ${fmtPxSrc};
  ${fmtDsrSrc};
  ${fmtTrialsSrc};
  ${tfToHoursSrc};
  ${tfToMinutesSrc};
  ${formatTimeStopDisplaySrc};
  ${formatAutobotEntryLogSrc};
  this.fmtPx = fmtPx;
  this.fmtDsr = fmtDsr;
  this.fmtTrials = fmtTrials;
  this.formatAutobotEntryLog = formatAutobotEntryLog;
`, sandbox);

const { fmtDsr, fmtTrials, formatAutobotEntryLog } = sandbox;

// 1. DSR formatting tests
assert.strictEqual(fmtDsr(0.85), '0.85');
assert.strictEqual(fmtDsr(0.00012), '<0.01');
assert.strictEqual(fmtDsr(0.00), '<0.01');
assert.strictEqual(fmtDsr(0), '<0.01');
assert.strictEqual(fmtDsr(1.234), '1.23');

// 2. Trials formatting tests
assert.strictEqual(fmtTrials(56664), '56.664');
assert.strictEqual(fmtTrials(1000000), '1.000.000');
assert.strictEqual(fmtTrials(18), '18');

// 3. Autobot ALCH Sub-Cent Example (PF-25 & PF-26)
const alchLog = formatAutobotEntryLog({
  symbol: 'ALCHUSDT',
  dir: 1,
  leverage: 5,
  tf: '1h',
  score: 78,
  setupDsr: 0.85,
  universeDsr: 0.00012,
  effectiveTrials: 56664,
  edge: 0.234,
  sampleSize: 42,
  margin: 50,
  timeStopBars: 16,
  entry: 0.04282,
  sl: 0.040493,
  tp2: 0.04585
});

assert.strictEqual(
  alchLog,
  '🚀 [ALCHUSDT] Paper Autobot simuliert LONG 5x (Hot Setup 1h | Score: 78 | Setup-DSR: 0.85 · Uni-DSR: <0.01 (56.664 Trials) | OOS-Edge: 0.234R aus 42 Trades | Margin: 50 USDT | Time-Stop: 16 Bars (16h) | Entry: 0.042820 | SL: 0.040493 | TP2: 0.045850)'
);

// 4. Autobot BTC Standard Asset Example
const btcLog = formatAutobotEntryLog({
  symbol: 'BTCUSDT',
  dir: 'SHORT',
  leverage: 3,
  tf: '4h',
  score: 82,
  setupDsr: 0.92,
  universeDsr: 0.35,
  effectiveTrials: 12500,
  edge: 0.412,
  sampleSize: 85,
  margin: 100,
  timeStopBars: 6,
  entry: 68500.5,
  sl: 69800.25,
  tp2: 66200.0
});

assert.strictEqual(
  btcLog,
  '🚀 [BTCUSDT] Paper Autobot simuliert SHORT 3x (Hot Setup 4h | Score: 82 | Setup-DSR: 0.92 · Uni-DSR: 0.35 (12.500 Trials) | OOS-Edge: 0.412R aus 85 Trades | Margin: 100 USDT | Time-Stop: 6 Bars (24h) | Entry: 68500.50 | SL: 69800.25 | TP2: 66200.00)'
);

console.log('PASS Autobot entry log hygiene, adaptive price format, and time-stop display verified');
