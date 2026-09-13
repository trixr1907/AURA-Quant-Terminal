'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
assert(scriptMatch, 'dashboard script missing');

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

const gateContext = { Number, Object, isFinite };
vm.createContext(gateContext);
vm.runInContext(
  `${extractFunction('selectAutobotTimeframe')}\n${extractFunction('evaluateAutobotCandidate')}\n` +
  'this.evaluateAutobotCandidate = evaluateAutobotCandidate;',
  gateContext
);

const alignedOne = {
  symbol: 'MTFUSDT',
  executable: false,
  aligned: 1,
  mtfDir: 1,
  bestTF: '1h',
  bestInfo: { score: 82, dir: 1, status: 'ready', tradeable: true, quality: 90 },
  tfScores: {
    '1h': { score: 82, dir: 1, status: 'ready', tradeable: true, quality: 90 },
  },
};

assert.strictEqual(gateContext.evaluateAutobotCandidate(alignedOne, 50, 1).accepted, true,
  'configured MTF 1/4 must accept an aligned=1 tradeable row even when radar executable uses SYM 3/4');
assert.strictEqual(gateContext.evaluateAutobotCandidate(alignedOne, 50, 3).accepted, false,
  'configured MTF 3/4 must reject the same aligned=1 row');
assert.strictEqual(gateContext.evaluateAutobotCandidate({ ...alignedOne, executable: true, btcBlock: true }, 50, 1).accepted, false,
  'BTC block must reject independently of configured MTF');
const notTradeable = {
  ...alignedOne,
  executable: true,
  bestInfo: { ...alignedOne.bestInfo, status: 'blocked_squeeze', tradeable: false },
  tfScores: {
    '1h': { ...alignedOne.tfScores['1h'], status: 'blocked_squeeze', tradeable: false },
  },
};
assert.strictEqual(gateContext.evaluateAutobotCandidate(notTradeable, 50, 1).accepted, false,
  'non-tradeable best timeframe must reject independently of configured MTF');

const scanContext = {
  console,
  Math,
  Number,
  String,
  Date,
  Array,
  Object,
  Float64Array,
  JSON,
  Boolean,
  RADAR_TFS: ['15m', '1h', '4h', '1d'],
  document: {
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener: () => {},
  },
  localStorage: { getItem: () => null, setItem: () => {} },
};
scanContext.globalThis = scanContext;
vm.createContext(scanContext);
vm.runInContext(scriptMatch[1] + '\nthis.__Autobot = Autobot; this.__App = App;', scanContext);

(async () => {
  const bot = scanContext.__Autobot;
  scanContext.__App.data.radar = [alignedOne];
  scanContext.__App.universe = [{ symbol: alignedOne.symbol, vol: 10000000, liquidityVerified: false }];
  bot.trades = [];
  bot.maxOpenTrades = 5;
  bot.min24hVol = 0;
  bot.minScore = 50;
  bot.save = () => {};
  bot.render = () => {};

  bot.mtfNeed = 1;
  const permissive = await bot.scanAndExecuteOpportunities();
  assert.strictEqual(permissive.radarFiltered, 1,
    'scan funnel must count the candidate when configured MTF is 1/4');

  bot.mtfNeed = 3;
  scanContext.__App.universe[0].liquidityVerified = true;
  const strict = await bot.scanAndExecuteOpportunities();
  assert.strictEqual(strict.radarFiltered, 0,
    'scan funnel must remove only the candidate disallowed by configured MTF 3/4');
  assert.strictEqual(strict.rejects.AUTOBOT_CONFIG, 1,
    'configured MTF rejection must be distinguished from fixed radar rejection');

  bot.mtfNeed = 1;
  scanContext.__App.data.radar = [{ ...alignedOne, btcBlock: true }];
  const btcBlocked = await bot.scanAndExecuteOpportunities();
  assert.strictEqual(btcBlocked.rejects.BTC_CONFLICT, 1,
    'row-level BTC block must be reported as BTC conflict, not as a fixed radar failure');

  scanContext.__App.data.radar = [{ ...alignedOne, incomplete: true }];
  const incomplete = await bot.scanAndExecuteOpportunities();
  assert.strictEqual(incomplete.rejects.RADAR_INCOMPLETE, 1,
    'incomplete radar data must be reported separately from fixed technical criteria');

  console.log('PASS PF-47 Autobot honors configured MTF independently of radar executability');
})().catch(error => {
  console.error(error);
  process.exit(1);
});
