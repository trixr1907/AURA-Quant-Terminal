#!/usr/bin/env node
'use strict';

const assert = require('assert');
const { computeFunnel24h, closeTradeRecord, schemaV2Keys } = require('../headless_autobot.js');

assert.deepStrictEqual(schemaV2Keys, {
  trades: 'aura-quant-terminal-active-trades-v2',
  history: 'aura-quant-terminal-history-trades-v2',
});

const now = 1_700_000_000_000;
const events = [
  { ts: now - 1000, outcome: 'REJECTED', reason: 'OOS_GATE' },
  { ts: now - 2000, outcome: 'ACCEPTED' },
  { ts: now - 25 * 60 * 60 * 1000, outcome: 'REJECTED', reason: 'OLD' },
];
const nativeV2 = {
  schema_version: 2,
  rev: 7,
  equity: 9987.65,
  trades: [{ id: 'sb_fixed', record_schema: 2, entry: 100, initialSl: 98, notional: 500, dir: -1 }],
  history: [],
  funnel24h: computeFunnel24h(events, now),
};
const migratedV2 = JSON.parse(JSON.stringify(nativeV2));

assert.deepStrictEqual(
  {
    equity: migratedV2.equity,
    trades: migratedV2.trades,
    history: migratedV2.history,
    funnel24h: migratedV2.funnel24h,
  },
  {
    equity: nativeV2.equity,
    trades: nativeV2.trades,
    history: nativeV2.history,
    funnel24h: nativeV2.funnel24h,
  },
  'migrated and native v2 state must produce identical cycle inputs/outputs',
);

const originalNow = Date.now;
Date.now = () => now;
try {
  const closed = closeTradeRecord(nativeV2.trades[0], 102, 'SL');
  assert.strictEqual(closed.parentId, 'sb_fixed');
  assert.strictEqual(closed.record_schema, 2);
  assert.strictEqual(closed.realizedPnl, -10);
} finally {
  Date.now = originalNow;
}

console.log('Schema v2 autobot result identity checks passed');
