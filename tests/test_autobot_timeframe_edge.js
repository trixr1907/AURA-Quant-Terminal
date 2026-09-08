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
    if (ch === '"' || ch === "'" || ch === '`') { quote = ch; continue; }
    if (ch === '{') depth += 1;
    if (ch === '}' && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error(`${name}() closing brace not found`);
}

const context = { Number, Object, isFinite, console };
vm.createContext(context);
vm.runInContext(`${extractFunction('selectAutobotTimeframe')}\nthis.selectAutobotTimeframe=selectAutobotTimeframe;`, context);

const row = {
  mtfDir: 1,
  tfScores: {
    '15m': { score: 61.9, dir: 1, status: 'no_signal', tradeable: false, quality: 35 },
    '1h': { score: 57.3, dir: 1, status: 'no_signal', tradeable: false, quality: 30 },
    '4h': { score: 88.2, dir: 1, status: 'ready', tradeable: true, quality: 96 },
    '1d': { score: 85.3, dir: 1, status: 'ready', tradeable: true, quality: 91 },
  },
};
const selected = JSON.parse(JSON.stringify(context.selectAutobotTimeframe(row, 78)));
assert.deepStrictEqual(selected, { tf: '4h', score: 88.2, dir: 1, status: 'ready', tradeable: true, quality: 96 },
  'INJ-like MTF setup must select the strongest valid 4h edge, never the chart default 1h');

const noReadyEdge = context.selectAutobotTimeframe({
  mtfDir: 1,
  tfScores: {
    '1h': { score: 84, dir: 1, status: 'blocked_squeeze', tradeable: false, quality: 90 },
    '4h': { score: 88, dir: 1, status: 'blocked_regime', tradeable: false, quality: 95 },
  },
}, 78);
assert.strictEqual(noReadyEdge, null, 'score without a tradeable READY edge must fail closed');

const gateStart = html.indexOf('function evaluateAutobotCandidate(');
const gateEnd = html.indexOf('\nfunction evaluateAutobotEdge(', gateStart);
assert(gateStart >= 0 && gateEnd > gateStart, 'evaluateAutobotCandidate source not found');
assert(html.slice(gateStart, gateEnd).includes('selectAutobotTimeframe('),
  'Autobot gate must independently select the strongest valid timeframe');

console.log('PASS Autobot selects strongest valid MTF edge and rejects score-only setups');
