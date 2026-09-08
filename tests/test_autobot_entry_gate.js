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

const context = { Number, console };
vm.createContext(context);
vm.runInContext(`${extractFunction('collectAutobotCandidates')}\n${extractFunction('selectAutobotTimeframe')}\n${extractFunction('evaluateAutobotCandidate')}\nthis.collectAutobotCandidates = collectAutobotCandidates; this.evaluateAutobotCandidate = evaluateAutobotCandidate;`, context);

const readyLong = {
  symbol: 'READYUSDT',
  avgScore: 84,
  mtfDir: 1,
  aligned: 3,
  executable: true,
  bestTF: '4h',
  bestInfo: { score: 84, dir: 1, status: 'ready', tradeable: true, quality: 88 },
  tfScores: {
    '1h': { score: 79, dir: 1, status: 'ready', tradeable: true, quality: 75 },
    '4h': { score: 84, dir: 1, status: 'ready', tradeable: true, quality: 88 },
  },
};

assert.deepStrictEqual(
  JSON.parse(JSON.stringify(context.collectAutobotCandidates([readyLong]))),
  [readyLong],
  'ranked radar rows must remain available to the Autobot',
);
assert.deepStrictEqual(
  JSON.parse(JSON.stringify(context.collectAutobotCandidates([{ label: 'Hot', rows: [readyLong] }]))),
  [readyLong],
  'legacy grouped radar rows must remain compatible',
);

assert.deepStrictEqual(
  JSON.parse(JSON.stringify(context.evaluateAutobotCandidate(readyLong, 78, 3))),
  { accepted: true, dir: 1, tf: '4h', score: 84 },
  'an actual radar Hot Setup must be accepted',
);

for (const [label, candidate] of [
  ['squeeze-blocked', { ...readyLong, executable: false, bestInfo: { ...readyLong.bestInfo, status: 'blocked_squeeze', tradeable: false }, tfScores: { '4h': { ...readyLong.tfScores['4h'], status: 'blocked_squeeze', tradeable: false } } }],
  ['not marked executable', { ...readyLong, executable: undefined }],
  ['zero aligned', { ...readyLong, aligned: 0 }],
  ['missing alignment', { ...readyLong, aligned: undefined }],
  ['weak best timeframe score', { ...readyLong, bestInfo: { ...readyLong.bestInfo, score: 70 }, tfScores: { '4h': { ...readyLong.tfScores['4h'], score: 70 } } }],
]) {
  const result = context.evaluateAutobotCandidate(candidate, 78, 3);
  assert.strictEqual(result.accepted, false, `${label} candidate must fail closed`);
}

const scanStart = html.indexOf('async scanAndExecuteOpportunities()');
const scanEnd = html.indexOf('\n  render() {', scanStart);
assert(scanStart >= 0 && scanEnd > scanStart, 'Autobot scan source not found');
const scanSource = html.slice(scanStart, scanEnd);
assert(!scanSource.includes('.flatMap(g => g.rows || [])'), 'flat ranked radar rows must not be discarded');
assert(scanSource.includes('collectAutobotCandidates(App.data.radar)'), 'Autobot must consume the current flat radar state');
assert(!scanSource.includes('aligned: 3'), 'missing radar evidence must never receive synthetic 3/4 alignment');
assert(!scanSource.includes('(c.aligned || 3)'), 'zero/missing MTF alignment must never default to a passing value');
assert(scanSource.includes('classifyRadarTf('), 'entry must revalidate the latest timeframe against radar gates');
assert(scanSource.includes('freshGate.tradeable'), 'entry must fail closed when fresh data is squeeze/regime blocked');

console.log('PASS Autobot only enters freshly revalidated Action Radar Hot Setups');
