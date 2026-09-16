'use strict';

const assert = require('assert');
const { normalizeTimestamp, output } = require('./model_evidence_real.js');

console.log('--- Testing Model Evidence Real & Timestamp Normalization ---');

// 1. Unit Test: normalizeTimestamp handles seconds (<10^10) and milliseconds (>=10^10) identically
const tsSec = 1735689600; // 2025-01-01 00:00:00 UTC in seconds
const tsMs = 1735689600000; // in milliseconds

assert.strictEqual(normalizeTimestamp(tsSec), 1735689600000, 'Timestamp in seconds must be converted to milliseconds');
assert.strictEqual(normalizeTimestamp(tsMs), 1735689600000, 'Timestamp in milliseconds must remain unchanged');
assert.strictEqual(normalizeTimestamp(String(tsSec)), 1735689600000, 'String timestamp in seconds must convert to ms');
assert.strictEqual(normalizeTimestamp(String(tsMs)), 1735689600000, 'String timestamp in ms must stay ms');
assert.strictEqual(normalizeTimestamp('invalid', 5), 5 * 3600000, 'Invalid timestamp uses fallback index');
assert.strictEqual(normalizeTimestamp(null, 2), 2 * 3600000, 'Null timestamp uses fallback index');
console.log('  PASS  normalizeTimestamp: seconds and milliseconds normalized identically to ms');

// 2. Integration Test: verify BTCUSDT_1h baseline accounting and ledger-adjusted DSR
// NOTE (v2.3.0): unified cost model (makerFee/takerFee/slippage = 0.001 each).
// With 0.1% all-in costs (3x slippage increase vs old 0.0005), most short-holding
// trades are filtered out → only 2 long-hold trades pass net-positive threshold.
// DSR of 0.5 = neutral Sharpe deflation floor (not a pass — verdict stays NO_EVIDENCE).
assert.strictEqual(output.verdict, 'NO_EVIDENCE', 'Model verdict must fail-closed to NO_EVIDENCE');
const btc = output.per_symbol.find(s => s.symbol === 'BTCUSDT_1h');
assert.ok(btc, 'BTCUSDT_1h must be present in per_symbol output');
assert.strictEqual(btc.trades, 2, `BTC trades must be 2 with unified 0.001 cost model, got ${btc.trades}`);
assert.ok(btc.exp > 0, `BTC expectancy must be positive gross on remaining trades, got ${btc.exp}`);
assert.ok(btc.dsr <= 0.5, `BTC DSR must be at or below 0.5 neutral (NO_EVIDENCE), got ${btc.dsr}`);
assert.ok(btc.trials >= 18, `BTC trials must retain at least the legacy 18-trial floor, got ${btc.trials}`);
console.log('  PASS  BTCUSDT_1h baseline accounting and ledger-adjusted DSR match control measurement');

// 3. All symbols fail-closed
for (const s of output.per_symbol) {
  assert.strictEqual(s.verdict, 'NO_EVIDENCE', `${s.symbol} must report NO_EVIDENCE`);
}
console.log('  PASS  All 5 golden symbols correctly report NO_EVIDENCE');

console.log('ALL MODEL EVIDENCE REAL TESTS PASSED');
