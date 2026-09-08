'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  const start = html.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`${name}() source not found`);
  const brace = html.indexOf('{', start);
  let depth = 0, quote = null, escaped = false;
  for (let i = brace; i < html.length; i += 1) {
    const ch = html[i];
    if (quote) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "'" || ch === '`') { quote = ch; continue; }
    if (ch === '{') depth += 1;
    if (ch === '}' && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error(`${name}() closing brace not found`);
}

const context = { Number };
vm.createContext(context);
vm.runInContext(`${extractFunction('evaluateAutobotEdge')}\nthis.evaluateAutobotEdge=evaluateAutobotEdge;`, context);

assert.deepStrictEqual(JSON.parse(JSON.stringify(context.evaluateAutobotEdge({ total: 20, wr: 0.6, avgWinR: 1.8, avgLossR: 1.0 }))),
  { accepted: true, edge: 0.68, sampleSize: 20 }, 'positive OOS expectancy with enough trades must pass');
for (const [label, stats] of [
  ['missing', null],
  ['too few samples', { total: 4, wr: 0.8, avgWinR: 2, avgLossR: 1 }],
  ['negative expectancy', { total: 20, wr: 0.35, avgWinR: 1, avgLossR: 1 }],
]) {
  assert.strictEqual(context.evaluateAutobotEdge(stats).accepted, false, `${label} edge must fail closed`);
}

const scanStart = html.indexOf('async scanAndExecuteOpportunities()');
const scanEnd = html.indexOf('\n  render() {', scanStart);
assert(scanStart >= 0 && scanEnd > scanStart, 'Autobot scan source not found');
const scan = html.slice(scanStart, scanEnd);
assert(scan.includes('runWalkForwardBacktest('), 'fresh selected timeframe must receive OOS validation');
assert(scan.includes('evaluateAutobotEdge('), 'entry must gate on positive statistical edge');
assert(scan.includes('edgeGate.accepted'), 'no-edge setup must be rejected before sizing');

console.log('PASS Autobot requires positive OOS edge on the selected fresh timeframe');
