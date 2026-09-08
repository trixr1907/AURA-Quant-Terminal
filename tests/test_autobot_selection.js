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

const context = { Number, Math };
vm.createContext(context);
vm.runInContext(`${extractFunction('autobotSignalStrength')}\n${extractFunction('sortAutobotCandidates')}\nthis.sortAutobotCandidates = sortAutobotCandidates;`, context);

const fixtures = [
  { symbol: 'FIRSTUSDT', executable: true, aligned: 3, rankScore: 4100, bestInfo: { score: 80, dir: 1, quality: 70, tradeable: true, status: 'ready' } },
  { symbol: 'SHORTUSDT', executable: true, aligned: 4, rankScore: 4200, bestInfo: { score: 12, dir: -1, quality: 91, tradeable: true, status: 'ready' } },
  { symbol: 'STRONGUSDT', executable: true, aligned: 4, rankScore: 4300, bestInfo: { score: 91, dir: 1, quality: 91, tradeable: true, status: 'ready' } },
];

const sorted = JSON.parse(JSON.stringify(context.sortAutobotCandidates(fixtures)));
assert.deepStrictEqual(sorted.map(x => x.symbol), ['STRONGUSDT', 'SHORTUSDT', 'FIRSTUSDT']);
assert.deepStrictEqual(fixtures.map(x => x.symbol), ['FIRSTUSDT', 'SHORTUSDT', 'STRONGUSDT'], 'input order must stay unchanged');

const scanStart = html.indexOf('async scanAndExecuteOpportunities()');
const scanEnd = html.indexOf('\n  render() {', scanStart);
assert(scanStart >= 0 && scanEnd > scanStart, 'Autobot scan source not found');
const scanSource = html.slice(scanStart, scanEnd);
assert(scanSource.includes('sortAutobotCandidates(collectAutobotCandidates(App.data.radar))'), 'Autobot must explicitly sort all valid radar candidates by overall signal strength');
assert(scanSource.includes('this.min24hVol'), 'minimum 24h volume parameter must gate entries');

console.log('PASS Autobot selects the strongest overall valid radar signal and applies liquidity settings');
