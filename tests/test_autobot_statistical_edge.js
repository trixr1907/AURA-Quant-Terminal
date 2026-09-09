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

const acceptedWf = {
  evidenceStatus: 'OOS',
  stats: { total: 15, wr: 0.6, avgWinR: 1.8, avgLossR: 1.0 },
  dsr: { dsr: 0.5 },
  totalTrials: 18,
};
assert.deepStrictEqual(JSON.parse(JSON.stringify(context.evaluateAutobotEdge(acceptedWf))),
  { accepted: true, edge: 0.68, sampleSize: 15, dsr: 0.5, effectiveTrials: 18 },
  'only sufficient positive OOS evidence with DSR >= 0.5 may pass');
for (const [label, wf] of [
  ['missing', null],
  ['not OOS', { ...acceptedWf, evidenceStatus: 'INSUFFICIENT_DATA' }],
  ['too few samples', { ...acceptedWf, stats: { ...acceptedWf.stats, total: 14 } }],
  ['negative expectancy', { ...acceptedWf, stats: { ...acceptedWf.stats, wr: 0.35, avgWinR: 1, avgLossR: 1 } }],
  ['missing DSR', { ...acceptedWf, dsr: null }],
  ['low DSR', { ...acceptedWf, dsr: { dsr: 0.49 } }],
  ['non-finite', { ...acceptedWf, stats: { ...acceptedWf.stats, wr: NaN } }],
]) {
  assert.strictEqual(context.evaluateAutobotEdge(wf).accepted, false, `${label} edge must fail closed`);
}


console.log('PASS Autobot requires positive OOS edge on the selected fresh timeframe');
