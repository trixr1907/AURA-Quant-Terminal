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
vm.runInContext(
  `${extractFunction('selectAutobotTimeframe')}\n` +
  `${extractFunction('evaluateAutobotCandidate')}\n` +
  `this.selectAutobotTimeframe = selectAutobotTimeframe;\n` +
  `this.evaluateAutobotCandidate = evaluateAutobotCandidate;`,
  context,
);

// 1. Radar row with multi-timeframe scores
const radarRow = {
  symbol: 'INJUSDT',
  executable: true,
  aligned: 4,
  bestTF: '4h',
  bestInfo: { score: 88, dir: 1, status: 'ready', tradeable: true, quality: 95 },
  tfScores: {
    '15m': { score: 61.9, dir: 1, status: 'no_signal', tradeable: false, quality: 35 },
    '1h': { score: 57.3, dir: 1, status: 'no_signal', tradeable: false, quality: 30 },
    '4h': { score: 88.2, dir: 1, status: 'ready', tradeable: true, quality: 96 },
    '1d': { score: 85.3, dir: 1, status: 'ready', tradeable: true, quality: 91 },
  },
};

const radarEval = context.evaluateAutobotCandidate(radarRow, 78, 3);
assert.strictEqual(radarEval.accepted, true);
assert.strictEqual(radarEval.dir, 1);
assert.strictEqual(radarEval.tf, '4h');
assert.strictEqual(radarEval.score, 88.2);

// 2. Fresh candidate object created right before entry
const freshObject = {
  executable: true,
  bestInfo: { score: 88.2, dir: 1, status: 'ready', tradeable: true, quality: 96 },
  aligned: 4,
  bestTF: '4h',
};

const freshEval = context.evaluateAutobotCandidate(freshObject, 78, 3);
assert.strictEqual(freshEval.accepted, true);
assert.strictEqual(freshEval.dir, 1);
assert.strictEqual(freshEval.tf, '4h');
assert.strictEqual(freshEval.score, 88.2);

console.log('PASS evaluateAutobotCandidate accepts both radar rows and fresh revalidated candidate objects');
