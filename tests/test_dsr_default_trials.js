'use strict';

const { assert, loadFunctions } = require('./r38_vm_helpers');

const context = loadFunctions(['calcDSR'], {
  Number,
  Math,
  normInv: p => p,
  normCdf: z => 1 / (1 + Math.exp(-z)),
});

const returns = [0.8, -0.4, 1.3, -0.2, 0.7, 0.1, -0.5, 1.1];
const implicit = context.calcDSR(returns);
const explicit18 = context.calcDSR(returns, 18);
assert.deepStrictEqual(
  structuredClone(implicit),
  structuredClone(explicit18),
  'calcDSR default must remain exactly 18 trials',
);
assert.notDeepStrictEqual(
  structuredClone(implicit),
  structuredClone(context.calcDSR(returns, 100)),
  'the fixture must detect a default mutation from 18 to 100',
);

console.log('PASS calcDSR default trial count is pinned to 18');
