'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  const plain = html.indexOf(`function ${name}(`);
  const asyncStart = html.indexOf(`async function ${name}(`);
  const start = asyncStart >= 0 && (plain < 0 || asyncStart < plain) ? asyncStart : plain;
  assert(start >= 0, `${name} source missing`);
  const brace = html.indexOf('{', start);
  let depth = 0;
  for (let i = brace; i < html.length; i++) {
    if (html[i] === '{') depth++;
    else if (html[i] === '}' && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error(`${name} source incomplete`);
}

const context = {
  Date,
  Math,
  Number,
  Array,
  generateDeterministicOid: prefix => `${prefix}_test`,
};
vm.createContext(context);
vm.runInContext([
  extractFunction('normalizeHistoryEvent'),
  extractFunction('calculateHistoryStats'),
  'this.api = { normalizeHistoryEvent, calculateHistoryStats };',
].join('\n'), context);

const api = context.api;

// 1. Partial TP hit with open runner: 50% TP1 hit gives positive realized win rate
const partialOnly = [
  { eventType: 'PARTIAL_CLOSE', fractionClosed: 0.5, realizedPnlGross: 40, realizedRoiPct: 40, realizedR: 1.5, reason: 'PARTIAL_TAKE_PROFIT_TP1' },
];
const statsPartial = api.calculateHistoryStats(partialOnly);
assert.strictEqual(statsPartial.totalEvents, 1);
assert.strictEqual(statsPartial.wins, 1);
assert.strictEqual(statsPartial.winRatePct, 100.0);
assert.strictEqual(statsPartial.realizedWinRatePct, 100.0, '50% profitable partial must show 100% realized win rate');
assert.strictEqual(statsPartial.tpHits, 1, 'profitable partial close must count as TP hit');
assert.strictEqual(statsPartial.partialWins, 1);

// 2. 50% TP1 hit followed by 50% runner SL hit at loss
const partialPlusRunnerLoss = [
  { eventType: 'PARTIAL_CLOSE', fractionClosed: 0.5, realizedPnlGross: 50, realizedRoiPct: 50, realizedR: 2.0, reason: 'PARTIAL_TAKE_PROFIT_TP1' },
  { eventType: 'FULL_CLOSE', fractionClosed: 0.5, realizedPnlGross: -20, realizedRoiPct: -20, realizedR: -0.8, reason: 'SL_HIT' },
];
const statsCombined = api.calculateHistoryStats(partialPlusRunnerLoss);
assert.strictEqual(statsCombined.totalEvents, 2);
assert.strictEqual(statsCombined.wins, 1);
assert.strictEqual(statsCombined.losses, 1);
assert.strictEqual(statsCombined.winRatePct, 50.0);
assert.strictEqual(statsCombined.realizedWinRatePct, 50.0, 'tranche-weighted win rate for equal 50/50 tranches');
assert.strictEqual(statsCombined.grossPnl, 30.0);
assert.strictEqual(statsCombined.tpHits, 1);

// 3. Backward compatibility: legacy history without fractionClosed or eventType
const legacyHistory = [
  { id: 'old_1', coin: 'BTCUSDT', dir: 1, entry: 50000, exit: 52000, realizedPnl: 100, realizedRoi: 20, reason: 'TP_HIT' },
  { id: 'old_2', coin: 'ETHUSDT', dir: -1, entry: 3000, exit: 3100, realizedPnl: -50, realizedRoi: -10, reason: 'SL_HIT' },
];
const normalizedLegacy = legacyHistory.map(api.normalizeHistoryEvent);
assert.strictEqual(normalizedLegacy[0].eventType, 'FULL_CLOSE');
assert.strictEqual(normalizedLegacy[0].fractionClosed, 1.0);
assert.strictEqual(normalizedLegacy[0].realizedPnlGross, 100);
const statsLegacy = api.calculateHistoryStats(normalizedLegacy);
assert.strictEqual(statsLegacy.totalEvents, 2);
assert.strictEqual(statsLegacy.wins, 1);
assert.strictEqual(statsLegacy.losses, 1);
assert.strictEqual(statsLegacy.winRatePct, 50.0);
assert.strictEqual(statsLegacy.realizedWinRatePct, 50.0);

console.log('PASS partial close win-rate semantics and legacy tolerance');
