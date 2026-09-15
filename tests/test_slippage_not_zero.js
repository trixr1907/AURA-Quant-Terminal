'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm'); // NOSONAR -- executes reviewed repository source in an isolated context.

const root = path.join(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'Symbiose_Dashboard.html'), 'utf8');
const engineStart = html.indexOf('//  ==ENGINE_BEGIN==');
const engineEnd = html.indexOf('// ==ENGINE_END==', engineStart);
assert.ok(engineStart >= 0 && engineEnd > engineStart, 'dashboard engine markers must exist');

const sandbox = { console, Float64Array, Date, Math, Array, Object, JSON, Number };
vm.createContext(sandbox);
vm.runInContext(
  html.slice(engineStart, engineEnd) + '\nthis.__slippageTest = { analyze, simulateRange, runWalkForwardBacktest };',
  sandbox
); // NOSONAR -- fixed local dashboard engine only.

const wfCandles = [];
for (let i = 0; i < 900; i++) {
  const base = 100 + i * 0.02 + Math.sin(i / 9) * 3;
  const close = base + Math.sin(i / 3) * 0.7;
  wfCandles.push({
    t: i * 3600000,
    o: base,
    h: Math.max(base, close) + 1,
    l: Math.min(base, close) - 1,
    c: close,
    v: 1000 + (i % 17) * 25,
    tbv: null,
  });
}
const wfAnalysis = sandbox.__slippageTest.analyze(wfCandles);
const wf = sandbox.__slippageTest.runWalkForwardBacktest(wfCandles, wfAnalysis, {
  makerFee: 0.0002,
  takerFee: 0.0006,
});
assert.ok(wf.folds.length > 0, 'fixture must produce walk-forward folds');
assert.ok(
  wf.folds.every(fold => fold.params.slippage === 0.0005),
  'walk-forward must normalize missing slippage to the non-zero dashboard default'
);

const candles = [
  { t: 0 },
  { t: 3600000 },
  { t: 7200000 },
];
const analysis = {
  score: [80, 50, 50],
  o: [100, 100, 100],
  h: [101, 111, 101],
  l: [99, 99, 99],
  c: [100, 110, 100],
  atr: [1, 1, 1],
  lastPL: [Number.NaN, Number.NaN, Number.NaN],
  lastPH: [Number.NaN, Number.NaN, Number.NaN],
  stLine: [Number.NaN, Number.NaN, Number.NaN],
  stDir: [1, 1, 1],
  fvgActA: [false, false, false],
  fvgDirA: [0, 0, 0],
  fvgBotA: [Number.NaN, Number.NaN, Number.NaN],
  fvgTopA: [Number.NaN, Number.NaN, Number.NaN],
  eqhLvlA: [Number.NaN, Number.NaN, Number.NaN],
  eqlLvlA: [Number.NaN, Number.NaN, Number.NaN],
};
const base = {
  longTh: 75,
  shortTh: 25,
  regimeGate: false,
  atrSl: 1.5,
  cooldown: 10,
  maxHold: 1,
  timeStopBars: 15,
};

const withoutCosts = sandbox.__slippageTest.simulateRange(
  candles,
  analysis,
  0,
  0,
  { ...base, makerFee: 0, takerFee: 0, slippage: 0 }
);
const withDefaultCosts = sandbox.__slippageTest.simulateRange(
  candles,
  analysis,
  0,
  0,
  { ...base, makerFee: 0.0002, takerFee: 0.0006, slippage: 0.0005 }
);

assert.strictEqual(withoutCosts.length, 1, 'fixture must produce one gross trade');
assert.strictEqual(withDefaultCosts.length, 1, 'fixture must produce one net trade');
assert.ok(
  withDefaultCosts[0].rNet < withoutCosts[0].rNet,
  `net R ${withDefaultCosts[0].rNet} must be below gross R ${withoutCosts[0].rNet}`
);

console.log(`SLIPPAGE_NOT_ZERO PASS gross_R=${withoutCosts[0].rNet} net_R=${withDefaultCosts[0].rNet}`);
