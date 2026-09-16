'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  const start = html.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`${name}() source not found`);
  const brace = html.indexOf('{', start);
  let depth = 0;
  let quote = null;
  let escaped = false;
  for (let i = brace; i < html.length; i += 1) {
    const ch = html[i];
    if (quote) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') { quote = ch; continue; }
    if (ch === '{') depth += 1;
    if (ch === '}' && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error(`${name}() closing brace not found`);
}

const context = {
  SYM: { wTrend: 0.30, wMom: 0.25, wVol: 0.25, wStr: 0.20 },
  clamp: (x, a, b) => Math.max(a, Math.min(b, x)),
};
vm.createContext(context);
vm.runInContext( // NOSONAR: executes only extracted, checked-in repository source.
  `${extractFunction('aggregateConfluenceScore')}\nthis.aggregateConfluenceScore=aggregateConfluenceScore;`, context);

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
