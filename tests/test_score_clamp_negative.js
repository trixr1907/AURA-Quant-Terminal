'use strict';

const { assert, loadFunctions } = require('./r38_vm_helpers');

const context = loadFunctions(['aggregateConfluenceScore'], {
  SYM: { wTrend: 0.30, wMom: 0.25, wVol: 0.25, wStr: 0.20 },
  clamp: (x, a, b) => Math.max(a, Math.min(b, x)),
});

assert.strictEqual(
  context.aggregateConfluenceScore(-20, -20, -20, -20),
  0,
  'negative subscores must clamp the aggregate at zero',
);
assert.strictEqual(
  context.aggregateConfluenceScore(120, 120, 120, 120),
  100,
  'oversized subscores must clamp the aggregate at 100',
);
assert.strictEqual(
  context.aggregateConfluenceScore(100, 0, 0, 0),
  30,
  'the canonical 30/25/25/20 weights must be applied',
);

console.log('PASS confluence score aggregation clamps negative values to zero');
