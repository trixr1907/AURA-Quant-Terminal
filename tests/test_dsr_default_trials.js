'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

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
  Number,
  Math,
  normInv: p => p,
  normCdf: z => 1 / (1 + Math.exp(-z)),
};
vm.createContext(context);
vm.runInContext(`${extractFunction('calcDSR')}\nthis.calcDSR=calcDSR;`, context);

const returns = [0.8, -0.4, 1.3, -0.2, 0.7, 0.1, -0.5, 1.1];
const implicit = context.calcDSR(returns);
const explicit18 = context.calcDSR(returns, 18);
assert.deepStrictEqual(
  JSON.parse(JSON.stringify(implicit)),
  JSON.parse(JSON.stringify(explicit18)),
  'calcDSR default must remain exactly 18 trials',
);
assert.notDeepStrictEqual(
  JSON.parse(JSON.stringify(implicit)),
  JSON.parse(JSON.stringify(context.calcDSR(returns, 100))),
  'the fixture must detect a default mutation from 18 to 100',
);

console.log('PASS calcDSR default trial count is pinned to 18');
