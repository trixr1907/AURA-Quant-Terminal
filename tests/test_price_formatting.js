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
const sandbox = { Number, Math, isFinite };
vm.createContext(sandbox);
// Source comes only from the repository-owned dashboard fixture; no external input is evaluated.
vm.runInContext(`${fmtPxSrc}; this.fmtPx = fmtPx;`, sandbox);
const fmtPx = sandbox.fmtPx;

// 1. Threshold >= 1 (2 decimals)
assert.strictEqual(fmtPx(1.0), '1.00');
assert.strictEqual(fmtPx(1), '1.00');
assert.strictEqual(fmtPx(68500.123), '68500.12');
assert.strictEqual(fmtPx(104.5), '104.50');
assert.strictEqual(fmtPx(-123.456), '-123.46');

// 2. Threshold >= 0.01 (6 decimals for sub-unit prices)
assert.strictEqual(fmtPx(0.5), '0.500000');
assert.strictEqual(fmtPx(0.04282), '0.042820');
assert.strictEqual(fmtPx(0.01), '0.010000');
assert.strictEqual(fmtPx(0.09876), '0.098760');

// 3. Threshold >= 0.0001 (6 decimals)
assert.strictEqual(fmtPx(0.009), '0.009000');
assert.strictEqual(fmtPx(0.0001234), '0.000123');
assert.strictEqual(fmtPx(0.0001), '0.000100');
assert.strictEqual(fmtPx(0.0054321), '0.005432');

// 4. Threshold < 0.0001 (8 decimals)
assert.strictEqual(fmtPx(0.000009), '0.00000900');
assert.strictEqual(fmtPx(0.00000012), '0.00000012');
assert.strictEqual(fmtPx(0.00000001), '0.00000001');

// 5. Invalid & non-finite inputs
assert.strictEqual(fmtPx(null), '—');
assert.strictEqual(fmtPx(undefined), '—');
assert.strictEqual(fmtPx(NaN), '—');
assert.strictEqual(fmtPx(Infinity), '—');

console.log('PASS Adaptive price formatting fmtPx verified across all precision thresholds');
