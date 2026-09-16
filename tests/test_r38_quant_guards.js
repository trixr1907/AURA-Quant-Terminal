'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  const start = html.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`${name}() source not found`);
  const openParen = html.indexOf('(', start);
  let parenDepth = 0;
  let bodyStart = -1;
  for (let i = openParen; i < html.length; i += 1) {
    if (html[i] === '(') parenDepth += 1;
    if (html[i] === ')' && --parenDepth === 0) {
      bodyStart = html.indexOf('{', i);
      break;
    }
  }
  if (bodyStart < 0) throw new Error(`${name}() body not found`);
  let depth = 0;
  let quote = null;
  let escaped = false;
  for (let i = bodyStart; i < html.length; i += 1) {
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
  isFinite,
  SYM: { longTh: 75, shortTh: 25 },
  clamp: (x, a, b) => Math.max(a, Math.min(b, x)),
  squeezeAt: () => false,
};
vm.createContext(context);
vm.runInContext( // NOSONAR: executes only extracted, checked-in repository source.
  [
  extractFunction('regimeOf'),
  extractFunction('classifyRadarTf'),
  extractFunction('evaluateAutobotEdge'),
  'this.regimeOf=regimeOf;',
  'this.classifyRadarTf=classifyRadarTf;',
  'this.evaluateAutobotEdge=evaluateAutobotEdge;',
].join('\n'), context);

// Q-2: A neutral DSR caused by zero variance is not statistical evidence.
for (const count of [6, 12]) {
  const returns = Array(count).fill(1);
  const wf = {
    evidenceStatus: 'OOS',
    stats: { total: count, wr: 1, avgWinR: 1, avgLossR: 1, returns },
    dsr: { dsr: 0.5 },
    setupDsr: { dsr: 0.5 },
    universeDsr: { dsr: 0.5 },
    totalTrials: 18,
    setupTrials: 18,
  };
  assert.strictEqual(
    context.evaluateAutobotEdge(wf, 6, { minDsr: 0.1 }).accepted,
    false,
    `${count} identical +1R returns must fail closed`,
  );
}

// Q-3: sub-nanometric EMA drift on a flat market must remain SIDEWAYS.
const flat = {
  n: 1,
  c: [100],
  e50: [100 + 5e-10],
  e200: [100 + 1e-10],
  adx: [25],
};
assert.strictEqual(context.regimeOf(flat).reg, 0, 'flat series within epsilon must be SIDEWAYS');
assert.strictEqual(context.regimeOf(flat).txt, 'SIDEWAYS');

const lowPriceFlat = {
  n: 1,
  c: [1e-8],
  e50: [1e-8 + 5e-13],
  e200: [1e-8],
  adx: [25],
};
assert.strictEqual(context.regimeOf(lowPriceFlat).reg, 0, 'relative epsilon must keep low-price dust flat');

// UX-01: Autobot profile thresholds must affect fresh classification.
const base = { score: 60, dir: 1, regime: 1, isSqz: false, adx: 25, atrPct: 1 };
assert.strictEqual(
  context.classifyRadarTf({ ...base, longTh: 58, shortTh: 42 }).tradeable,
  true,
  'aggressive minScore=58 must allow score 60',
);
assert.strictEqual(
  context.classifyRadarTf({ ...base, longTh: 75, shortTh: 25 }).tradeable,
  false,
  'strict minScore=75 must block score 60',
);
const shortBase = { ...base, score: 40, dir: -1, regime: -1 };
assert.strictEqual(
  context.classifyRadarTf({ ...shortBase, longTh: 58, shortTh: 42 }).tradeable,
  true,
  'aggressive short threshold 42 must allow score 40',
);
assert.strictEqual(
  context.classifyRadarTf({ ...shortBase, longTh: 75, shortTh: 25 }).tradeable,
  false,
  'strict short threshold 25 must block score 40',
);

assert.strictEqual(
  context.classifyRadarTf({ ...base, score: 65, longTh: 65, shortTh: 35 }).tradeable,
  true,
  'balanced long threshold 65 must allow score 65',
);
assert.strictEqual(
  context.classifyRadarTf({ ...base, score: 64.999, longTh: 65, shortTh: 35 }).tradeable,
  false,
  'balanced long threshold 65 must block lower scores',
);
const balancedShort = { ...base, score: 35, dir: -1, regime: -1 };
assert.strictEqual(
  context.classifyRadarTf({ ...balancedShort, longTh: 65, shortTh: 35 }).tradeable,
  true,
  'balanced short threshold 35 must allow score 35',
);
assert.strictEqual(
  context.classifyRadarTf({ ...balancedShort, score: 35.001, longTh: 65, shortTh: 35 }).tradeable,
  false,
  'balanced short threshold 35 must block higher scores',
);

// Strict universe mode always requires Uni-DSR >= 0.50, independent of profile.
const strictWf = {
  evidenceStatus: 'OOS',
  stats: { total: 12, wr: 0.6, avgWinR: 1.8, avgLossR: 1, returns: [1.8, -1, 1.8, -1, 1.8, -1, 1.8, -1, 1.8, 1.8, -1, 1.8] },
  dsr: { dsr: 0.4 },
  setupDsr: { dsr: 0.8 },
  universeDsr: { dsr: 0.4 },
  totalTrials: 8640,
  setupTrials: 18,
};
assert.strictEqual(
  context.evaluateAutobotEdge(strictWf, 12, { strictUniverseGate: true, minDsr: 0.3 }).accepted,
  false,
  'strict universe gate must reject Uni-DSR below 0.50',
);

console.log('PASS R38 null-variance, regime epsilon, and score-profile guards');
