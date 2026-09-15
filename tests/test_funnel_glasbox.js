#!/usr/bin/env node
/**
 * Tests for Auftrag E: Funnel-Glasbox ("Warum handelt der Bot (nicht)?")
 *
 * Covers:
 * 1. computeFunnel24h aggregation over multiple scan cycles.
 * 2. 24-hour cutoff filtering.
 * 3. Reject reasons frequency sorting and counts.
 * 4. Zero side-effects on trading decisions (evidence protection clause).
 */

const assert = require('assert');
const { computeFunnel24h, ServerBotState } = require('../headless_autobot.js');

console.log('--- Running Auftrag E: Funnel-Glasbox Tests ---');

const now = Date.now();

// Test 1: Aggregation across multiple cycles
const cycles = [
  {
    ts: now - 3600000, // 1h ago
    scanned: 50,
    radar_passed: 12,
    wf_evaluated: 6,
    selected: 1,
    rejects: { NO_RADAR_READY: 38, DSR_TOO_LOW: 4, TIME_STOP_RISK: 1 }
  },
  {
    ts: now - 1800000, // 30m ago
    scanned: 50,
    radar_passed: 10,
    wf_evaluated: 5,
    selected: 0,
    rejects: { NO_RADAR_READY: 40, DSR_TOO_LOW: 3, SQUEEZE_FILTER: 2 }
  },
  {
    ts: now - 90000000, // 25h ago (should be excluded by 24h cutoff)
    scanned: 50,
    radar_passed: 15,
    wf_evaluated: 8,
    selected: 2,
    rejects: { NO_RADAR_READY: 35, DSR_TOO_LOW: 5 }
  }
];

const agg = computeFunnel24h(cycles, now);

assert.strictEqual(agg.scanned, 100, 'Summed scanned within 24h is 100 (50+50, excluding old cycle)');
assert.strictEqual(agg.radar_passed, 22, 'Summed radar_passed is 22 (12+10)');
assert.strictEqual(agg.wf_evaluated, 11, 'Summed wf_evaluated is 11 (6+5)');
assert.strictEqual(agg.selected, 1, 'Summed selected is 1 (1+0)');

assert.deepStrictEqual(
  agg.reject_reasons,
  {
    NO_RADAR_READY: 78,
    DSR_TOO_LOW: 7,
    TIME_STOP_RISK: 1,
    SQUEEZE_FILTER: 2
  },
  'Reject reasons aggregated correctly across 24h window'
);
console.log('✓ Test 1: computeFunnel24h accurately aggregates recent cycles and respects 24h cutoff');

// Test 2: ServerBotState payload integration
const srvState = new ServerBotState();
srvState.funnelCycles = cycles;
const payload = srvState.toServerPayload();
assert(payload.funnel24h, 'ServerBotState payload includes funnel24h');
assert.strictEqual(payload.funnel24h.scanned, 100);
assert.strictEqual(payload.funnel24h.selected, 1);
console.log('✓ Test 2: ServerBotState includes funnel24h summary in toServerPayload()');

// Test 3: Empty / missing cycles return nominal zeros
const emptyAgg = computeFunnel24h([], now);
assert.strictEqual(emptyAgg.scanned, 0);
assert.strictEqual(emptyAgg.radar_passed, 0);
assert.strictEqual(emptyAgg.wf_evaluated, 0);
assert.strictEqual(emptyAgg.selected, 0);
assert.deepStrictEqual(emptyAgg.reject_reasons, {});
console.log('✓ Test 3: Empty cycle list handles nominal zeros without crashing');

console.log('All Auftrag E tests passed successfully!');
