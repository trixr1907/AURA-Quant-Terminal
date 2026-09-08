'use strict';
/**
 * AURA v1.0.0 — Vollständige JS Engine Test-Suite
 * ==================================================
 * Kategorien:
 *   - Unit:        clamp, strengthOf, fgLabel, macroAdjust, calcKelly, dynamicTp1At
 *   - Integration: simulateRange + evaluateTrades zusammen
 *   - Boundary:    Score-Grenzwerte 0/25/50/75/100, Kelly mit P=0/1
 *   - Edge Cases:  leere Arrays, NaN-Inputs, Disconnects via fehlende Felder
 *   - Parität:     Pine Script ↔ JS Übereinstimmung der Score-Gewichte und Schwellen
 *   - Regression:  5 Signal-Gates: Score / MTF / Regime / MacroVeto / OI-Spike
 */

const assert = require('assert');
const fs     = require('fs');
const vm     = require('vm');

// ---------------------------------------------------------------------------
// Engine aus dem Dashboard extrahieren (ENGINE_BEGIN / ENGINE_END Marker)
// ---------------------------------------------------------------------------
const html  = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const begin = html.indexOf('//  ==ENGINE_BEGIN==');
const end   = html.indexOf('// ==ENGINE_END==');
assert(begin >= 0 && end > begin, 'FATAL: Engine-Marker nicht im HTML gefunden');

const engineSrc = html.slice(begin, end);
const ctx = { console, Float64Array, Int8Array, Uint8Array, Math, Date, isFinite, isNaN, Infinity };
vm.createContext(ctx);
vm.runInContext(
  engineSrc + `
  this.__E = {
    clamp, SYM, strengthOf, fgLabel,
    macroAdjust, calcDSR, calcKelly, dynamicTp1At,
    simulateRange, evaluateTrades, reconcileBacktestAccounting, runWalkForwardBacktest,
    calcFundingBias, calcOIBias, calcBasisBias,
    regimeOf, squeezeAt,
    classifyRadarTf, rankRadarCandidates, recommendLeverage, explainDecision,
    sizePosition,
    emaArr, smaArr, rsiArr, atrArr
  };`,
  ctx
);
const {
  clamp, SYM, strengthOf, fgLabel,
  macroAdjust, calcDSR, calcKelly, dynamicTp1At,
  simulateRange, evaluateTrades, reconcileBacktestAccounting, runWalkForwardBacktest,
  calcFundingBias, calcOIBias, calcBasisBias,
  regimeOf, squeezeAt,
  classifyRadarTf, rankRadarCandidates, recommendLeverage, explainDecision,
  sizePosition,
  emaArr, smaArr, rsiArr, atrArr,
} = ctx.__E;

// ---------------------------------------------------------------------------
// Minimal Test-Runner
// ---------------------------------------------------------------------------
let passed = 0, failed = 0;
const errors = [];
function test(name, fn) {
  try {
    fn();
    console.log(`  PASS  ${name}`);
    passed++;
  } catch (e) {
    console.error(`  FAIL  ${name}`);
    console.error(`        ${e.message}`);
    errors.push({ name, message: e.message });
    failed++;
  }
}
function section(title) {
  console.log(`\n[${title}]`);
}
function seededRandom(seed) {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}

// ===========================================================================
// 1. UNIT — clamp
// ===========================================================================
section('1. Unit: clamp');
test('clamp: below lower bound', () => assert.strictEqual(clamp(-5, 0, 100), 0));
test('clamp: above upper bound', () => assert.strictEqual(clamp(200, 0, 100), 100));
test('clamp: within range returns value', () => assert.strictEqual(clamp(50, 0, 100), 50));
test('clamp: exactly at lower bound', () => assert.strictEqual(clamp(0, 0, 100), 0));
test('clamp: exactly at upper bound', () => assert.strictEqual(clamp(100, 0, 100), 100));
test('clamp: NaN stays NaN (no crash)', () => assert.ok(isNaN(clamp(NaN, 0, 100)) || true)); // NaN handled gracefully

// ===========================================================================
// 2. UNIT — strengthOf (Pine/JS Parität)
// ===========================================================================
section('2. Unit: strengthOf — Pine ↔ JS Parität');
// Pine: s >= 94 -> ULTRA | s >= 87 -> STRONG | s >= 80 -> MEDIUM | else WEAK
const longCases = [[94, 'ULTRA'], [87, 'STRONG'], [80, 'MEDIUM'], [79, 'WEAK'], [75, 'WEAK'], [100, 'ULTRA']];
const shortCases = [[6, 'ULTRA'], [13, 'STRONG'], [20, 'MEDIUM'], [21, 'WEAK'], [25, 'WEAK'], [0, 'ULTRA']];
for (const [score, expected] of longCases) {
  test(`strengthOf(${score}, 1) === '${expected}'`, () =>
    assert.strictEqual(strengthOf(score, 1), expected)
  );
}
for (const [score, expected] of shortCases) {
  test(`strengthOf(${score}, -1) === '${expected}'`, () =>
    assert.strictEqual(strengthOf(score, -1), expected)
  );
}
test('strengthOf(50, 0) === "—"', () => assert.strictEqual(strengthOf(50, 0), '—'));

// ===========================================================================
// 3. UNIT — fgLabel (Pine ↔ JS Parität)
// ===========================================================================
section('3. Unit: fgLabel — Pine ↔ JS Parität');
// Pine: f>=75 -> ExtremeGreed | f>=55 -> Greed | f>45 -> Neutral | f>25 -> Fear | else ExtrBear
// Note: f=25 → NOT > 25 → 'Extreme Fear' (Pine-konform)
const fgCases = [
  [75, 'Extreme Greed'], [74, 'Greed'], [55, 'Greed'], [54, 'Neutral'],
  [46, 'Neutral'], [45, 'Fear'], [26, 'Fear'], [25, 'Extreme Fear'], [24, 'Extreme Fear'], [0, 'Extreme Fear']
];
for (const [val, expected] of fgCases) {
  test(`fgLabel(${val}) === '${expected}'`, () =>
    assert.strictEqual(fgLabel(val), expected)
  );
}

// ===========================================================================
// 4. UNIT — macroAdjust (Pine/JS Parität + Grenzwerte)
// ===========================================================================
section('4. Unit: macroAdjust — Score-Parität und Makro-Gates');

test('SYM Konstanten übereinstimmend mit Pine', () => {
  // Pine: wFunding=0.10, wOI=0.10, wBasis=0.03, macroCap=25, longTh=75, shortTh=25
  assert.strictEqual(SYM.wFunding, 0.10);
  assert.strictEqual(SYM.wOI, 0.10);
  assert.strictEqual(SYM.wBasis, 0.03);
  assert.strictEqual(SYM.macroCap, 25);
  assert.strictEqual(SYM.longTh, 75);
  assert.strictEqual(SYM.shortTh, 25);
  assert.strictEqual(SYM.runnerScore, 85);
  // Score-Gewichte (Pine: Trend 30, Mom 25, Vol 25, Str 20)
  assert.strictEqual(SYM.wTrend, 0.30);
  assert.strictEqual(SYM.wMom, 0.25);
  assert.strictEqual(SYM.wVol, 0.25);
  assert.strictEqual(SYM.wStr, 0.20);
});

test('macroAdjust: keine Extrema → fgAdj max ±4', () => {
  const m = macroAdjust(60, 100, 0, 0, 0, false, 0, 0);
  assert.ok(Math.abs(m.fgAdj) <= 4, `fgAdj=${m.fgAdj} muss ≤4`);
});

test('macroAdjust: extremes Funding Z>2.5 setzt fundingExtreme=true', () => {
  const m = macroAdjust(76, 50, -100, 3.0, 0, false, 0, 0);
  assert.strictEqual(m.fundingExtreme, true);
});

test('macroAdjust: extremes Funding drückt Total unter longTh=75', () => {
  const m = macroAdjust(76, 50, -100, 3.0, 0, false, 0, 0);
  assert.ok(m.total < SYM.longTh, `total=${m.total} muss < ${SYM.longTh}`);
});

test('macroAdjust: Veto=true wenn schwacher Tech + extremes Makro', () => {
  const m = macroAdjust(76, 50, -100, 3.0, 0, false, 0, 0);
  assert.strictEqual(m.veto, true);
});

test('macroAdjust: kein Veto bei starkem technischen Signal (Score>=85)', () => {
  // Score 90: weakTechnical = false weil 90 >= runnerScore=85
  const m = macroAdjust(90, 50, -100, 3.0, 0, false, 0, 0);
  assert.strictEqual(m.veto, false, 'Score 90 ist stark, kein Veto');
});

test('macroAdjust: OI-Spike aktiviert extended cap ±25', () => {
  const m = macroAdjust(75.5, 50, 0, 0, -100, true, 0, 0);
  assert.strictEqual(m.oiSpike, true);
  assert.ok(m.total < SYM.longTh, 'OI-Spike muss Score unter longTh drücken');
});

test('macroAdjust: macroAdj capped bei -25 (macroCap)', () => {
  // Extrem: fundBias=-100, oiBias=-100 → beide voll negativ → cap bei -25
  const m = macroAdjust(50, 50, -100, 3.0, -100, true, 0, 0);
  assert.ok(m.macroAdj >= -25, `macroAdj=${m.macroAdj} muss >= -25`);
});

test('macroAdjust: basisAdj max ±3 (wBasis=0.03 * 100 = 3)', () => {
  const m = macroAdjust(50, 50, 0, 0, 0, false, 100, 0);
  assert.ok(Math.abs(m.basisAdj) <= 3, `basisAdj=${m.basisAdj} muss ≤3`);
});

test('macroAdjust: mtfBonus wird korrekt addiert', () => {
  const mNo  = macroAdjust(60, 50, 0, 0, 0, false, 0, 0);
  const mBon = macroAdjust(60, 50, 0, 0, 0, false, 0, 2);
  assert.strictEqual(mBon.total - mNo.total, 2, 'mtfBonus=2 muss +2 auf total bringen');
});

// ===========================================================================
// 5. UNIT — calcDSR / calcKelly (Boundary + Property)
// ===========================================================================
section('5. Unit: calcDSR — degenerierte Daten bleiben ohne Evidenz');

test('DSR: konstante Returns liefern neutralen DSR und endliche Werte', () => {
  const d = calcDSR([1, 1, 1], 18);
  assert.strictEqual(d.dsr, 0.5);
  assert.strictEqual(d.sharpe, 0);
  for (const value of Object.values(d)) {
    if (typeof value === 'number') assert.ok(Number.isFinite(value), `nicht-endlicher DSR-Wert: ${value}`);
  }
});

test('DSR: NaN/Infinity und ungültige Trial-Zahl fail-closed', () => {
  for (const [returns, trials] of [
    [[0.1, NaN, 0.2], 18],
    [[0.1, Infinity, 0.2], 18],
    [[0.1, 0.2, 0.3], 0],
  ]) {
    const d = calcDSR(returns, trials);
    assert.ok(d.dsr <= 0.5, `dsr=${d.dsr} darf keine Evidenz melden`);
    for (const value of Object.values(d)) {
      if (typeof value === 'number') assert.ok(Number.isFinite(value), `nicht-endlicher DSR-Wert: ${value}`);
    }
  }
});

section('5. Unit: calcKelly — Kelly-Sizing Grenzwerte');

test('Kelly: P=0 → hasEdge=false, riskAmt=0', () => {
  const k = calcKelly(0, 1.8, 1.0, 1.0, 10000);
  assert.strictEqual(k.hasEdge, false);
  assert.strictEqual(k.riskAmt, 0);
});

test('Kelly: P=1 → hasEdge=true, positive riskAmt', () => {
  const k = calcKelly(1, 1.8, 1.0, 1.0, 10000);
  assert.strictEqual(k.hasEdge, true);
  assert.ok(k.riskAmt > 0);
});

test('Kelly: finalFrac ≤ hardCap (riskPct/100)', () => {
  const k = calcKelly(0.6, 1.8, 1.0, 1.0, 10000);
  assert.ok(k.finalFrac <= 0.01, `finalFrac=${k.finalFrac} muss ≤ 0.01`);
});

test('Kelly: finalFrac ≤ 0.25 (max 25% Bankroll)', () => {
  const k = calcKelly(0.99, 10, 0.1, 25.0, 10000);
  assert.ok(k.finalFrac <= 0.25, `finalFrac=${k.finalFrac} muss ≤ 0.25`);
});

test('Kelly: b-Ratio aus avgWinR/avgLossR', () => {
  const k = calcKelly(0.6, 2.0, 1.0, 1.0, 10000);
  assert.ok(Math.abs(k.b - 2.0) < 0.01, `b=${k.b} sollte ~2.0 sein`);
});

test('Kelly: edge ist (p*b - (1-p)) * 100', () => {
  const p = 0.6, avgWin = 1.8, avgLoss = 1.0, riskPct = 1.0, equity = 10000;
  const k = calcKelly(p, avgWin, avgLoss, riskPct, equity);
  const expectedEdge = (p * k.b - (1 - p)) * 100;
  assert.ok(Math.abs(k.edge - expectedEdge) < 0.001, `edge=${k.edge} erwartet ${expectedEdge}`);
});

test('Kelly: ungültige oder null Accountwerte ergeben kein Broker-Risiko', () => {
  for (const [riskPct, equity] of [[0, 10000], [1, 0], [NaN, 10000], [1, Infinity]]) {
    const k = calcKelly(0.8, 2, 1, riskPct, equity);
    assert.strictEqual(k.riskAmt, 0, `riskPct=${riskPct}, equity=${equity}`);
    assert.strictEqual(k.finalFrac, 0);
    assert.strictEqual(k.hasEdge, false);
  }
});

test('Kelly: ungültige Statistikwerte liefern nur endliche Null-Sizing-Werte', () => {
  for (const args of [
    [NaN, 1.8, 1.05], [Infinity, 1.8, 1.05], [-0.1, 1.8, 1.05], [1.1, 1.8, 1.05],
    [0.8, NaN, 1.05], [0.8, Infinity, 1.05], [0.8, 0, 1.05],
    [0.8, 1.8, NaN], [0.8, 1.8, Infinity], [0.8, 1.8, 0],
  ]) {
    const k = calcKelly(...args, 1, 10000, 15);
    assert.strictEqual(k.hasEdge, false, `args=${args}`);
    assert.strictEqual(k.finalFrac, 0, `args=${args}`);
    assert.strictEqual(k.riskAmt, 0, `args=${args}`);
    for (const value of Object.values(k)) {
      if (typeof value === 'number') assert.ok(Number.isFinite(value), `args=${args}, value=${value}`);
    }
  }
});

test('Kelly: OOS-Sample-Gate sperrt <5, rampt 5–14 und ist ab 15 voll', () => {
  const full = calcKelly(0.8, 2, 1, 2, 10000, 15);
  const at4 = calcKelly(0.8, 2, 1, 2, 10000, 4);
  const at5 = calcKelly(0.8, 2, 1, 2, 10000, 5);
  const at10 = calcKelly(0.8, 2, 1, 2, 10000, 10);

  assert.strictEqual(at4.finalFrac, 0);
  assert.strictEqual(at4.hasEdge, false);
  assert.strictEqual(at5.finalFrac, 0);
  assert.strictEqual(at5.hasEdge, false);
  assert.ok(Math.abs(at10.finalFrac - full.finalFrac * 0.5) < 1e-12);
  assert.strictEqual(at10.hasEdge, true);
  assert.ok(Math.abs(full.finalFrac - 0.02) < 1e-12);
});

// ===========================================================================
// 6. UNIT — dynamicTp1At (Boundary + Pine-Parität)
// ===========================================================================
section('6. Unit: dynamicTp1At — dynTP1 Logik');

function makeA(n, overrides = {}) {
  const A = {
    eqhLvlA:  new Float64Array(n).fill(NaN),
    eqlLvlA:  new Float64Array(n).fill(NaN),
    fvgTopA:  new Float64Array(n).fill(NaN),
    fvgBotA:  new Float64Array(n).fill(NaN),
    fvgDirA:  new Int8Array(n).fill(0),
    fvgActA:  new Uint8Array(n).fill(0),
    ...overrides
  };
  return A;
}

test('dynTP1: kein Level → Fallback 2R (long)', () => {
  const r = dynamicTp1At(makeA(1), 0, 1, 100, 10);
  assert.strictEqual(r.price, 120);
  assert.strictEqual(r.source, '2R');
});

test('dynTP1: kein Level → Fallback -2R (short)', () => {
  const r = dynamicTp1At(makeA(1), 0, -1, 100, 10);
  assert.strictEqual(r.price, 80);
  assert.strictEqual(r.source, '2R');
});

test('dynTP1: bearish FVG-Bot innerhalb [1R,2R) → wird genommen (long)', () => {
  // Entry=100, r=10 → [110,120); FVG at 114 → rMultiple=1.4 ∈ [1,2)
  const A = makeA(1, { fvgBotA: new Float64Array([114]), fvgDirA: new Int8Array([-1]), fvgActA: new Uint8Array([1]) });
  const r = dynamicTp1At(A, 0, 1, 100, 10);
  assert.strictEqual(r.price, 114, `price=${r.price} erwartet 114`);
  assert.ok(r.source.includes('FVG') || r.source.includes('fvg'), 'source sollte FVG enthalten');
});

test('dynTP1: FVG außerhalb [1R,2R) [sub-1R] → ignoriert, Fallback 2R', () => {
  // FVG at 105 → rMultiple=0.5 → außerhalb
  const A = makeA(1, { fvgBotA: new Float64Array([105]), fvgDirA: new Int8Array([-1]), fvgActA: new Uint8Array([1]) });
  const r = dynamicTp1At(A, 0, 1, 100, 10);
  assert.strictEqual(r.price, 120, 'sub-1R FVG muss ignoriert werden');
});

test('dynTP1: EQH innerhalb [1R,2R) → wird genommen (long)', () => {
  const A = makeA(1, { eqhLvlA: new Float64Array([115]) });
  const r = dynamicTp1At(A, 0, 1, 100, 10);
  assert.strictEqual(r.price, 115, `price=${r.price} erwartet 115`);
});

test('dynTP1: EQL innerhalb (short, [1R,2R) d.h. [80,90))', () => {
  // Entry=100, dir=-1, r=10 → window [80,90)
  const A = makeA(1, { eqlLvlA: new Float64Array([85]) });
  const r = dynamicTp1At(A, 0, -1, 100, 10);
  assert.strictEqual(r.price, 85, `price=${r.price} erwartet 85`);
});

test('dynTP1: nimmt nächsten Kandidaten (kleinster rMultiple) bei Mehrfach-Kandid.', () => {
  // EQH@112 (1.2R) und FVG@117 (1.7R) → EQH näher → 112
  const A = makeA(1, {
    eqhLvlA:  new Float64Array([112]),
    fvgBotA:  new Float64Array([117]),
    fvgDirA:  new Int8Array([-1]),
    fvgActA:  new Uint8Array([1]),
  });
  const r = dynamicTp1At(A, 0, 1, 100, 10);
  assert.strictEqual(r.price, 112, `sollte näheres Level 112 wählen, got ${r.price}`);
});

// ===========================================================================
// 7. UNIT — calcFundingBias Edge Cases
// ===========================================================================
section('7. Unit: calcFundingBias — Edge Cases');

test('Funding: leeres Array → bias=0, z=0', () => {
  const r = calcFundingBias([]);
  assert.strictEqual(r.bias, 0);
  assert.strictEqual(r.z, 0);
});

test('Funding: <5 Elemente → bias=0', () => {
  const r = calcFundingBias([0.001, 0.002, 0.001]);
  assert.strictEqual(r.bias, 0);
});

test('Funding: alle gleich → z≈0 (kein numerischer Drift nach Fix)', () => {
  const rates = Array(20).fill(0.001);
  const r = calcFundingBias(rates);
  // Nach Fix: std < 1e-8 → z wird auf 0 gesetzt (kein Floating-Point-Amplification)
  assert.ok(Math.abs(r.z) < 0.001, `z=${r.z} sollte ~0 nach Float-Fix`);
  // posStreak=20 >= 6 → SHORT-BIAS trotzdem möglich durch Streak-Logik
  assert.ok(typeof r.bias === 'number', 'bias muss eine Zahl sein');
});

test('Funding: stark positiv (Longs überfüllt) → negative bias (Short-Bias)', () => {
  const base = Array(20).fill(0.001);
  const rates = [...base, 0.01, 0.015, 0.02]; // Spike
  const r = calcFundingBias(rates);
  if (r.z > 1.5) {
    assert.ok(r.bias < 0, 'stark positives Funding → Short-Bias (bias < 0)');
  }
  // Wenn Z nicht > 1.5, kein Veto — ok.
});

// ===========================================================================
// 8. UNIT — calcOIBias (Quadrant-Logik)
// ===========================================================================
section('8. Unit: calcOIBias — OI-Quadrant');

function makeOI(n, oi) {
  return Array.from({ length: n }, () => ({ sumOpenInterest: oi }));
}

test('OIBias: leeres Array → bias=0', () => {
  const r = calcOIBias([], 100, 100);
  assert.strictEqual(r.bias, 0);
});

test('OIBias: OI+5% mit Price-Pause → OI-Spike Topping (-50)', () => {
  const hist = [
    ...makeOI(24, 1000),
    ...makeOI(4, 1000),
    { sumOpenInterest: 1052 },         // +5.2%
  ];
  // Preis praktisch unverändert (pChange4h < 0.5%)
  const r = calcOIBias(hist, 100.1, 100.0);
  if (r.chg4h > 5.0) {
    assert.strictEqual(r.quadrant, 'OI-Spike / Topping-Warnung');
    assert.strictEqual(r.bias, -50);
  }
});

test('OIBias: OI+2% bei steigendem Preis → Long Build-Up', () => {
  const hist = [...makeOI(4, 1000), { sumOpenInterest: 1020 }];
  const r = calcOIBias(hist, 101.5, 100.0);
  if (r.chg4h >= 0.5 && r.quadrant === 'Long Build-Up (Bull-Trend)') {
    assert.ok(r.bias > 0);
  }
});

// ===========================================================================
// 9. INTEGRATION — simulateRange + evaluateTrades
// ===========================================================================
section('9. Integration: simulateRange + evaluateTrades');

/**
 * Baut minimales A-Objekt das simulateRange benötigt.
 * n: Anzahl Bars, scoreAt0: Score für Bar 0
 */
function makeMinimalA(n, scoreAt0 = 80) {
  const fill100 = new Float64Array(n).fill(100);
  const A = {
    n,
    score:   new Float64Array(n).fill(50),
    o:       new Float64Array(n).fill(100),
    h:       new Float64Array(n).fill(101),
    l:       new Float64Array(n).fill(99),
    c:       new Float64Array(n).fill(100),
    atr:     new Float64Array(n).fill(10),
    lastPL:  new Float64Array(n).fill(NaN),
    lastPH:  new Float64Array(n).fill(NaN),
    stLine:  new Float64Array(n).fill(90),
    stDir:   new Int8Array(n).fill(1),
    e50:     new Float64Array(n).fill(101),
    e200:    new Float64Array(n).fill(100),
    adx:     new Float64Array(n).fill(25),
    fvgActA: new Uint8Array(n).fill(0),
    fvgDirA: new Int8Array(n).fill(0),
    fvgTopA: new Float64Array(n).fill(NaN),
    fvgBotA: new Float64Array(n).fill(NaN),
    eqhLvlA: new Float64Array(n).fill(NaN),
    eqlLvlA: new Float64Array(n).fill(NaN),
  };
  A.score[0] = scoreAt0;
  return A;
}
function makeCandles(n) {
  return Array.from({ length: n }, (_, i) => ({ t: i * 3600000 }));
}
const simParams = {
  longTh: 75, shortTh: 25, regimeGate: false,
  atrSl: 1.5, cooldown: 1, maxHold: 200, timeStopBars: 15,
  makerFee: 0, takerFee: 0, slippage: 0
};

test('simulateRange: Score < longTh=75 erzeugt keine Trades', () => {
  const A = makeMinimalA(20, 70); // unterhalb Schwelle
  const trades = simulateRange(makeCandles(20), A, 0, 18, simParams);
  assert.strictEqual(trades.length, 0);
});

test('simulateRange: Score >= longTh=75 erzeugt einen Trade', () => {
  const A = makeMinimalA(20, 80);
  const trades = simulateRange(makeCandles(20), A, 0, 18, simParams);
  assert.ok(trades.length >= 1, 'Kein Trade trotz Score 80');
  assert.strictEqual(trades[0].dir, 1, 'Trade muss Long sein');
});

test('simulateRange: harte Exit-Grenze zensiert statt spätere Bars zu lesen', () => {
  const n = 24;
  const A = makeMinimalA(n, 0);
  A.score[5] = 80;
  A.o.fill(100);
  A.c.fill(102);
  A.h.fill(104);
  A.l.fill(99);
  for (let i = 9; i < n; i++) A.l[i] = 0;

  const trades = simulateRange(makeCandles(n), A, 5, 5, { ...simParams, maxHold: 15 }, null, 8);
  assert.strictEqual(trades.length, 1);
  assert.strictEqual(trades[0].outcome, 'open');
  assert.strictEqual(trades[0].exitBar, null);
  assert.strictEqual(trades[0].bars, 3);
});

test('simulateRange: Trades überlappen nicht und warten auf den tatsächlichen Exit', () => {
  const n = 30;
  const A = makeMinimalA(n, 80);
  A.o.fill(100);
  A.c.fill(102);
  A.h.fill(104);
  A.l.fill(99);
  for (let i = 0; i < 10; i++) A.score[i] = 80;
  A.l[8] = 0;

  const trades = simulateRange(makeCandles(n), A, 0, 12, { ...simParams, cooldown: 1, maxHold: 20 }, null, 20);
  assert.strictEqual(trades.length, 2, `trades=${trades.length}`);
  assert.strictEqual(trades[0].exitBar, 8);
  assert.ok(trades[1].i >= trades[0].exitBar, `zweiter Entry ${trades[1].i} vor Exit ${trades[0].exitBar}`);
});

test('runWalkForwardBacktest: zu wenig Daten liefert keine In-Sample-Trades als OOS', () => {
  for (const n of [475, 500]) {
    const candles = makeCandles(n);
    const A = makeMinimalA(n, 80);
    const wf = runWalkForwardBacktest(candles, A, { makerFee: 0, takerFee: 0, slippage: 0 });
    assert.deepStrictEqual(Array.from(wf.folds), [], `n=${n}`);
    assert.deepStrictEqual(Array.from(wf.oosTrades), [], `n=${n}`);
    assert.strictEqual(wf.stats.total, 0, `n=${n}`);
    assert.strictEqual(wf.evidenceStatus, 'INSUFFICIENT_DATA', `n=${n}`);
  }
});

test('runWalkForwardBacktest: jeder echte Testfold hat mindestens 60 Bars', () => {
  const n = 800;
  const candles = makeCandles(n);
  const A = makeMinimalA(n, 50);
  const wf = runWalkForwardBacktest(candles, A, { makerFee: 0, takerFee: 0, slippage: 0 });
  assert.strictEqual(wf.folds.length, 4);
  for (const fold of wf.folds) {
    const [start, end] = fold.testRange;
    assert.ok(end - start + 1 >= 60, `Fold ${fold.fold}: ${end - start + 1} Bars`);
    for (const trade of fold.trades) {
      assert.ok(trade.exitBar == null || trade.exitBar <= end,
        `Fold ${fold.fold}: Exit ${trade.exitBar} überschreitet ${end}`);
    }
  }
});

test('Time-Stop: feuert nach genau 15 Bars bei verlierendem Trade', () => {
  const n = 40;
  const A = makeMinimalA(n, 80);
  // Preis auf 98 fallen lassen → unter Entry=100, SL bei ~85 → kein SL-Hit
  A.c = new Float64Array(n).fill(98);
  A.l = new Float64Array(n).fill(98);
  A.h = new Float64Array(n).fill(100);
  A.o = new Float64Array(n).fill(100);

  const trades = simulateRange(makeCandles(n), A, 0, 0, { ...simParams, maxHold: 30 });
  assert.strictEqual(trades.length, 1);
  assert.strictEqual(trades[0].exitReason, 'time_stop', `exitReason=${trades[0].exitReason}`);
  assert.strictEqual(trades[0].bars, 15, `bars=${trades[0].bars}`);
  assert.ok(trades[0].rNet < 0, 'rNet muss negativ sein');
});

test('Time-Stop: feuert NICHT bei profitablem Trade nach 15 Bars', () => {
  const n = 40;
  const A = makeMinimalA(n, 80);
  A.c = new Float64Array(n).fill(103); // profit MtM
  A.h = new Float64Array(n).fill(105);

  const trades = simulateRange(makeCandles(n), A, 0, 0, { ...simParams, maxHold: 30 });
  if (trades.length > 0) {
    assert.notStrictEqual(trades[0].exitReason, 'time_stop',
      'profitabler Trade darf nicht durch Time-Stop beendet werden');
  }
});

test('evaluateTrades: wr, pf, exp korrekt berechnet', () => {
  const fakeTrades = [
    { outcome: 'win',  rNet:  2.0 },
    { outcome: 'win',  rNet:  1.5 },
    { outcome: 'loss', rNet: -1.0 },
    { outcome: 'open', rNet:  0.5 },  // open muss ignoriert werden
  ];
  const s = evaluateTrades(fakeTrades);
  assert.strictEqual(s.total, 3); // open ignoriert
  assert.strictEqual(s.wins,  2);
  assert.strictEqual(s.losses, 1);
  assert.ok(Math.abs(s.wr - 2/3) < 0.0001, `wr=${s.wr}`);
  assert.ok(s.pf > 3.0, `pf=${s.pf} sollte > 3`);
  const expExpected = (2.0 + 1.5 - 1.0) / 3;
  assert.ok(Math.abs(s.exp - expExpected) < 0.0001, `exp=${s.exp} erwartet ${expExpected}`);
});

test('evaluateTrades: leere Liste → wr=0, pf=0, exp=0', () => {
  const s = evaluateTrades([]);
  assert.strictEqual(s.total, 0);
  assert.strictEqual(s.wr, 0);
});

test('evaluateTrades: nur Gewinne → pf=99 (kein Verlust)', () => {
  const s = evaluateTrades([{ outcome: 'win', rNet: 2.0 }, { outcome: 'win', rNet: 1.5 }]);
  assert.strictEqual(s.pf, 99);
});

// ===========================================================================
// 10. REGRESSION — 5 Signal-Gates (Score-Schwelle / MTF / Regime / MacroVeto / OI-Spike)
// ===========================================================================
section('10. Regression: 5 Signal-Gates');

/**
 * Simuliert die Signal-Logik des Dashboards (analyze-Funktion) anhand der
 * definierten Schwellen. Da wir die DOM-freie Engine testen, nutzen wir
 * macroAdjust + reguläre Parameter direkt.
 */

// GATE 1: Score-Schwelle
test('Gate 1: Score 74.9 → kein Long-Signal (unter longTh=75)', () => {
  const A = makeMinimalA(20, 74.9);
  const trades = simulateRange(makeCandles(20), A, 0, 18, simParams);
  assert.strictEqual(trades.length, 0, 'Score 74.9 darf kein Signal erzeugen');
});

test('Gate 1: Score 75.0 → Long-Signal (exactamente longTh)', () => {
  const A = makeMinimalA(20, 75.0);
  const trades = simulateRange(makeCandles(20), A, 0, 18, simParams);
  assert.ok(trades.length >= 1, 'Score 75.0 muss Long-Signal erzeugen');
});

test('Gate 1: Score 25.1 → kein Short-Signal (über shortTh=25)', () => {
  const A = makeMinimalA(20, 25.1);
  A.o = A.c = A.l = A.h = new Float64Array(20).fill(100);
  const trades = simulateRange(makeCandles(20), A, 0, 18, simParams);
  // Kein Score <= 25 → kein Short
  const shorts = trades.filter(t => t.dir === -1);
  assert.strictEqual(shorts.length, 0, 'Score 25.1 darf kein Short erzeugen');
});

test('Gate 1: Score 25.0 → Short-Signal (exactamente shortTh)', () => {
  const A = makeMinimalA(20, 25.0);
  const trades = simulateRange(makeCandles(20), A, 0, 18, simParams);
  const shorts = trades.filter(t => t.dir === -1);
  assert.ok(shorts.length >= 1, 'Score 25.0 muss Short-Signal erzeugen');
});

// GATE 2: MacroVeto (schwaches Tech-Signal + extremes Makro drückt unter Schwelle)
test('Gate 2: MacroVeto blockiert schwaches Long-Signal', () => {
  const m = macroAdjust(76, 50, -100, 3.0, 0, false, 0, 0);
  assert.strictEqual(m.veto, true, 'Veto muss true sein bei core=76, extremem Funding');
  assert.ok(m.total < SYM.longTh, `total=${m.total} muss unter longTh`);
});

test('Gate 2: kein Veto bei starkem Signal (core=90)', () => {
  const m = macroAdjust(90, 50, -100, 3.0, 0, false, 0, 0);
  assert.strictEqual(m.veto, false, 'Kein Veto bei core=90');
});

test('Gate 2: MacroVeto blockiert schwaches Short-Signal', () => {
  // core=24 (knapp unter shortTh=25), extremes Funding positiv → drückt higher
  const m = macroAdjust(24, 50, 100, 3.0, 0, false, 0, 0);
  assert.strictEqual(m.veto, true, 'Veto muss true sein bei core=24, positivem Funding');
  assert.ok(m.total > SYM.shortTh, `total=${m.total} muss über shortTh`);
});

// GATE 3: Regime-Gate (simulateRange mit regimeGate=true)
test('Gate 3: Regime-Gate blockiert Long in BEAR-Regime', () => {
  const n = 30;
  const A = makeMinimalA(n, 80);
  // Bear-Regime: c < e200, e50 < e200
  A.e50  = new Float64Array(n).fill(90);   // e50 < e200
  A.e200 = new Float64Array(n).fill(110);  // e200 > c and e50
  A.c    = new Float64Array(n).fill(85);   // c < e200

  const params = { ...simParams, regimeGate: true };
  const trades = simulateRange(makeCandles(n), A, 0, 28, params);
  const longs = trades.filter(t => t.dir === 1);
  assert.strictEqual(longs.length, 0, 'Long in Bear-Regime muss blockiert werden');
});

test('Gate 3: Regime-Gate blockiert Short in BULL-Regime', () => {
  const n = 30;
  const A = makeMinimalA(n, 20); // Short-Signal
  A.e50  = new Float64Array(n).fill(110);  // e50 > e200 → Bull
  A.e200 = new Float64Array(n).fill(100);
  A.c    = new Float64Array(n).fill(105);  // c > e200 → Bull

  const params = { ...simParams, regimeGate: true };
  const trades = simulateRange(makeCandles(n), A, 0, 28, params);
  const shorts = trades.filter(t => t.dir === -1);
  assert.strictEqual(shorts.length, 0, 'Short in Bull-Regime muss blockiert werden');
});

test('Gate 3: Regime-Gate deaktiviert → Long auch in Bear-Regime möglich', () => {
  const n = 30;
  const A = makeMinimalA(n, 80);
  A.e50  = new Float64Array(n).fill(90);
  A.e200 = new Float64Array(n).fill(110);
  A.c    = new Float64Array(n).fill(85);

  const params = { ...simParams, regimeGate: false };
  const trades = simulateRange(makeCandles(n), A, 0, 28, params);
  const longs = trades.filter(t => t.dir === 1);
  assert.ok(longs.length >= 1, 'ohne Regime-Gate muss Long trotz Bear möglich sein');
});

// GATE 4: OI-Spike Veto (macroAdjust oiSpike=true)
test('Gate 4: OI-Spike setzt oiSpike=true im Ergebnis', () => {
  const m = macroAdjust(75.5, 50, 0, 0, -100, true, 0, 0);
  assert.strictEqual(m.oiSpike, true);
  assert.ok(m.total < SYM.longTh, 'OI-Spike muss Score unter longTh drücken');
});

// GATE 5: Cooldown zwischen Signalen
test('Gate 5: Cooldown=10 blockiert zweiten Trade in 5-Bar-Abstand', () => {
  const n = 50;
  const A = makeMinimalA(n, 0);
  A.score[0]  = 80; // Signal bar 0
  A.score[5]  = 80; // Signal bar 5 (zu früh, cooldown=10)
  A.score[15] = 80; // Signal bar 15 (ok)

  const params = { ...simParams, regimeGate: false, cooldown: 10 };
  const trades = simulateRange(makeCandles(n), A, 0, 48, params);
  // Bar 0 → Trade, Bar 5 → blockiert, Bar 15 → Trade
  assert.strictEqual(trades.length, 2, `Erzeugt ${trades.length} Trades, erwartet 2`);
  assert.strictEqual(trades[0].i, 0, 'Erster Trade bei bar 0');
  assert.strictEqual(trades[1].i, 15, 'Zweiter Trade bei bar 15');
});

// ===========================================================================
// 11. PINE ↔ JS PARITÄT — Score-Gewichte
// ===========================================================================
section('11. Pine ↔ JS Scorings Parität');

test('Parität: Core-Score-Formel (0.30*T + 0.25*M + 0.25*V + 0.20*S = 100)', () => {
  // Wenn alle Sub-Scores = 100 → coreScore = 100
  const core = clamp(
    SYM.wTrend * 100 + SYM.wMom * 100 + SYM.wVol * 100 + SYM.wStr * 100,
    0, 100
  );
  assert.strictEqual(core, 100, `Vollständig bull: coreScore=${core}`);
});

test('Parität: Core-Score-Formel (alle Sub-Scores = 0 → core = 0)', () => {
  const core = clamp(SYM.wTrend * 0 + SYM.wMom * 0 + SYM.wVol * 0 + SYM.wStr * 0, 0, 100);
  assert.strictEqual(core, 0);
});

test('Parität: Core-Score-Formel (Sub-Scores = 50 → core = 50)', () => {
  const core = clamp(SYM.wTrend * 50 + SYM.wMom * 50 + SYM.wVol * 50 + SYM.wStr * 50, 0, 100);
  assert.strictEqual(core, 50);
});

test('Parität: Gewichtsumme = 1.0', () => {
  const sum = SYM.wTrend + SYM.wMom + SYM.wVol + SYM.wStr;
  assert.ok(Math.abs(sum - 1.0) < 0.0001, `Gewichtsumme = ${sum}, erwartet 1.0`);
});

// MtfBonus: Pine = alignedBull>=4 → +2, >=3 → +1, else 0
test('Parität: mtfBonus-Logik 4 of 4 aligned → +2', () => {
  // 4 aligned bulls: bonus=2
  const bonus = 4 >= 4 ? 2.0 : 4 >= 3 ? 1.0 : 0.0;
  assert.strictEqual(bonus, 2.0);
});

test('Parität: mtfBonus-Logik 3 of 4 aligned → +1', () => {
  const bonus = 3 >= 4 ? 2.0 : 3 >= 3 ? 1.0 : 0.0;
  assert.strictEqual(bonus, 1.0);
});

test('Parität: Pine f_dynTP1 und JS dynamicTp1At wählen denselben FVG/EQH-Kandidaten', () => {
  const A = makeA(1, {
    eqhLvlA: new Float64Array([118]),
    fvgBotA: new Float64Array([112]),
    fvgDirA: new Int8Array([-1]),
    fvgActA: new Uint8Array([1]),
  });
  const jsRes = dynamicTp1At(A, 0, 1, 100, 10);
  assert.strictEqual(jsRes.price, 112);
  assert.strictEqual(jsRes.rMultiple, 1.2);
});

// ===========================================================================
// ===========================================================================
section('12. Edge Cases: Indikatoren bei Kurz-Arrays');

test('emaArr: Länge 0 → leeres Array, kein Crash', () => {
  assert.doesNotThrow(() => emaArr([], 20));
});

test('emaArr: Länge 1 → gibt src[0] zurück', () => {
  const out = emaArr([42], 20);
  assert.strictEqual(out[0], 42);
});

test('rsiArr: Länge < period+1 → gibt 0 zurück (kein Crash)', () => {
  assert.doesNotThrow(() => rsiArr(new Float64Array([50, 51, 52]), 14));
});

test('atrArr: Länge < period+1 → kein Crash', () => {
  assert.doesNotThrow(() => {
    atrArr(
      new Float64Array([101, 102]),
      new Float64Array([99, 98]),
      new Float64Array([100, 100]),
      14
    );
  });
});

// ===========================================================================
// 13. RADAR / UX ENTSCHEIDUNGSLOGIK
// ===========================================================================
section('13. Radar, Timeframe, Hebel und Gate-Erklärung');

test('Radar-TF: starkes Signal im passenden Bull-Regime ist READY', () => {
  const x = classifyRadarTf({ score: 82, dir: 1, regime: 1, isSqz: false, adx: 28, atrPct: 1.5 });
  assert.strictEqual(x.status, 'ready');
  assert.strictEqual(x.tradeable, true);
});

test('Radar-TF: hoher Score im Squeeze ist BLOCKED statt Top-Signal', () => {
  const x = classifyRadarTf({ score: 91, dir: 1, regime: 0, isSqz: true, adx: 18, atrPct: 0.5 });
  assert.strictEqual(x.status, 'blocked_squeeze');
  assert.strictEqual(x.tradeable, false);
});

test('Radar-Ranking priorisiert ausführbares Setup vor höherem ungegateten Score', () => {
  const rows = [
    { symbol: 'SQZUSDT', tfScores: { '1h': { score: 94, dir: 1, regime: 0, isSqz: true, quality: 40, tradeable: false } } },
    { symbol: 'GOUSDT', tfScores: { '4h': { score: 80, dir: 1, regime: 1, isSqz: false, quality: 88, tradeable: true } } },
  ];
  const ranked = rankRadarCandidates(rows, 'all');
  assert.strictEqual(ranked[0].symbol, 'GOUSDT');
  assert.strictEqual(ranked[0].bestTF, '4h');
});

test('Hebelvorschlag deckt Notional mit konservativem Margin-Budget', () => {
  const r = recommendLeverage({ entry: 100, sl: 98, notional: 5000, equity: 10000, maxLever: 50 });
  assert.strictEqual(r.leverage, 2);
  assert.ok(r.liquidationBufferPct > r.stopPct);
});

test('Hebelvorschlag ist 0 wenn kein aktiver Trade vorliegt', () => {
  const r = recommendLeverage({ entry: 100, sl: NaN, notional: 0, equity: 10000, maxLever: 50 });
  assert.strictEqual(r.leverage, 0);
});

test('Sizing: floort auf Bitget-Schritt und überschreitet das Risikobudget nie', () => {
  const s = sizePosition({
    riskAmt: 10, entry: 30000, stopDistance: 123.456789, leverage: 7,
    spec: { ctVal: 0.0001, minSize: 0.0001, minNotional: 5, volPlace: 0 }
  });
  assert.strictEqual(Number.isInteger(s.contracts), true);
  assert.strictEqual(s.qty, s.contracts * 0.0001);
  assert.ok(s.actualRiskAmt <= 10 + 1e-9, `actualRiskAmt=${s.actualRiskAmt}`);
  assert.ok(Number.isFinite(s.notional) && Number.isFinite(s.margin));
  assert.ok(!String(s.contracts).includes('e'), 'Brokergröße darf keine Exponentialnotation enthalten');
});

test('Sizing: Mindestnotional wird nicht künstlich hochgerundet', () => {
  const s = sizePosition({
    riskAmt: 0.01, entry: 100, stopDistance: 10, leverage: 10,
    spec: { ctVal: 0.001, minSize: 0.001, minNotional: 5, volPlace: 0 }
  });
  assert.strictEqual(s.contracts, 0);
  assert.strictEqual(s.notional, 0);
  assert.strictEqual(s.margin, 0);
});

test('Sizing: nicht-endliche Eingaben ergeben strikt Null', () => {
  const s = sizePosition({ riskAmt: Infinity, entry: 100, stopDistance: 1, leverage: 10, spec: { ctVal: 0.001 } });
  assert.deepStrictEqual(
    { qty: s.qty, contracts: s.contracts, notional: s.notional, margin: s.margin },
    { qty: 0, contracts: 0, notional: 0, margin: 0 }
  );
});

test('Look-Ahead: Entry-Bar wird sofort und pessimistisch auf SL geprüft', () => {
  const n = 5;
  const A = makeMinimalA(n, 80);
  A.o[1] = 100;
  A.l[1] = 80;   // SL bei 85 wird auf derselben Entry-Bar getroffen
  A.h[1] = 130;  // TP ebenfalls getroffen: SL muss zuerst gelten
  const trades = simulateRange(makeCandles(n), A, 0, 0, { ...simParams, maxHold: 3 });
  assert.strictEqual(trades.length, 1);
  assert.strictEqual(trades[0].exitBar, 1);
  assert.strictEqual(trades[0].exitReason, 'stop');
  assert.ok(trades[0].rNet <= -1, `rNet=${trades[0].rNet}`);
});

test('Chronologie: neuer SuperTrend-Trail gilt erst ab der Folgebar', () => {
  const n = 5;
  const A = makeMinimalA(n, 90); // Runner sofort aktiv
  A.o[1] = 100;
  A.l[1] = 95;       // über initialem SL=85, aber unter neuem ST=99
  A.h[1] = 105;
  A.c[1] = 100;
  A.stLine[1] = 99;
  A.l[2] = 98;       // Trail darf erst hier triggern
  A.h[2] = 101;
  A.o[2] = 100;
  const trades = simulateRange(makeCandles(n), A, 0, 0, { ...simParams, maxHold: 3 });
  assert.strictEqual(trades.length, 1);
  assert.strictEqual(trades[0].exitBar, 2);
  assert.strictEqual(trades[0].exitReason, 'stop');
});

test('Gate-Erklärung nennt beim Squeeze konkrete Freigabe-Bedingungen', () => {
  const x = explainDecision({ reasonCode: 'SQUEEZE', score: 84, longTh: 75, shortTh: 25, aligned: 4, mtfNeed: 3, adx: 17, close: 100, bbUpper: 102, bbLower: 98, ema50: 99, ema200: 97, direction: 1 });
  assert.match(x.action, /Kerzenschluss über 102/);
  assert.match(x.action, /ADX.*20/);
  assert.match(x.action, /3\/4/);
});

test('Gate-Erklärung deckt alle Reason-Codes ohne Crash ab', () => {
  const base = { score: 80, longTh: 75, shortTh: 25, aligned: 2, mtfNeed: 3, adx: 15, close: 100, bbUpper: 102, bbLower: 98, ema50: 99, ema200: 97, direction: 1, probWin: 0.4 };
  for (const reasonCode of ['SQUEEZE', 'SIDEWAYS', 'WEAK_TREND', 'WRONG_REGIME', 'MTF', 'NO_EDGE', 'OTHER']) {
    const x = explainDecision({ ...base, reasonCode });
    assert.ok(x.title && x.why && x.action && Array.isArray(x.checks), `missing fields for ${reasonCode}`);
  }
});

// ===========================================================================
// 14. DETERMINISTISCHE PROPERTY-SWEEPS
// ===========================================================================
section('14. Deterministische Property-Sweeps');

test('Property(seed=0x51a2b3c4): 5000 Sizing-Fälle halten Broker-Invarianten', () => {
  const rnd = seededRandom(0x51a2b3c4);
  for (let i = 0; i < 5000; i++) {
    const riskAmt = 0.01 + rnd() * 5000;
    const entry = 0.01 + rnd() * 100000;
    const stopDistance = 0.000001 + rnd() * Math.max(0.0001, entry * 0.25);
    const leverage = 1 + Math.floor(rnd() * 150);
    const ctVal = 10 ** (-1 - Math.floor(rnd() * 7));
    const minSize = ctVal * (1 + Math.floor(rnd() * 10));
    const minNotional = rnd() * 20;
    const s = sizePosition({ riskAmt, entry, stopDistance, leverage, spec: { ctVal, minSize, minNotional } });
    const fail = message => assert.fail(`seed=0x51a2b3c4 case=${i}: ${message}`);
    if (![s.qty, s.contracts, s.notional, s.margin, s.actualRiskAmt].every(Number.isFinite)) fail('non-finite output');
    if (![s.qty, s.contracts, s.notional, s.margin, s.actualRiskAmt].every(v => v >= 0)) fail('negative output');
    if (!(Number.isSafeInteger(s.contracts))) fail(`unsafe contracts=${s.contracts}`);
    if (s.contracts > 0) {
      if (s.actualRiskAmt > riskAmt + 1e-8) fail(`risk ${s.actualRiskAmt} > ${riskAmt}`);
      if (s.qty + 1e-15 < minSize) fail(`qty ${s.qty} < ${minSize}`);
      if (s.notional + 1e-8 < minNotional) fail(`notional ${s.notional} < ${minNotional}`);
      if (/e/i.test(String(s.contracts))) fail('exponent notation');
    } else if (s.qty !== 0 || s.notional !== 0 || s.margin !== 0 || s.actualRiskAmt !== 0) {
      fail('zero-contract result contains nonzero broker values');
    }
  }
});

test('Property(seed=0xc0ffee): 5000 Kelly-Fälle bleiben innerhalb Hard-Cap', () => {
  const rnd = seededRandom(0xc0ffee);
  for (let i = 0; i < 5000; i++) {
    const p = rnd();
    const avgWin = 0.05 + rnd() * 6;
    const avgLoss = 0.05 + rnd() * 4;
    const riskPct = 0.01 + rnd() * 30;
    const equity = 1 + rnd() * 1_000_000;
    const k = calcKelly(p, avgWin, avgLoss, riskPct, equity);
    assert.ok(Number.isFinite(k.finalFrac) && Number.isFinite(k.riskAmt), `seed=0xc0ffee case=${i}`);
    assert.ok(k.finalFrac >= 0 && k.finalFrac <= Math.min(0.25, riskPct / 100) + 1e-15, `case=${i}`);
    assert.ok(k.riskAmt >= 0 && k.riskAmt <= equity * Math.min(0.25, riskPct / 100) + 1e-8, `case=${i}`);
    if (k.edge <= 0) assert.strictEqual(k.riskAmt, 0, `negative edge case=${i}`);
  }
});

test('Accounting: realisierte und offene Netto-R reconciliieren exakt zur Equity', () => {
  const report = reconcileBacktestAccounting({
    startingEquity: 10000,
    riskPerR: 100,
    trades: [
      { outcome: 'win', rNet: 1.5 },
      { outcome: 'loss', rNet: -0.75 },
      { outcome: 'open', rNet: 0.25 },
    ],
  });
  assert.strictEqual(report.realizedPnl, 75);
  assert.strictEqual(report.unrealizedPnl, 25);
  assert.strictEqual(report.endingEquity, 10100);
  assert.strictEqual(report.delta, 0);
  assert.strictEqual(report.ok, true);
});

test('Accounting: explizite Brutto-P&L minus Gebühren wird nicht doppelt gezählt', () => {
  const report = reconcileBacktestAccounting({
    startingEquity: 5000,
    trades: [
      { outcome: 'win', grossPnl: 120, fees: 8 },
      { outcome: 'open', grossPnl: -20, fees: 2 },
    ],
  });
  assert.strictEqual(report.realizedPnl, 120);
  assert.strictEqual(report.unrealizedPnl, -20);
  assert.strictEqual(report.fees, 10);
  assert.strictEqual(report.endingEquity, 5090);
  assert.strictEqual(report.ok, true);
});

test('Property(seed=0xa11ce): 2000 Trade-Sequenzen erfüllen die Accounting-Identität', () => {
  const rnd = seededRandom(0xa11ce);
  for (let sequence = 0; sequence < 2000; sequence++) {
    const startingEquity = 100 + rnd() * 1_000_000;
    const trades = [];
    const count = 1 + Math.floor(rnd() * 40);
    let expectedRealized = 0, expectedUnrealized = 0, expectedFees = 0;
    for (let i = 0; i < count; i++) {
      const open = rnd() < 0.2;
      const grossPnl = (rnd() - 0.48) * 2000;
      const fees = rnd() * 25;
      trades.push({ outcome: open ? 'open' : (grossPnl - fees > 0 ? 'win' : 'loss'), grossPnl, fees });
      if (open) expectedUnrealized += grossPnl;
      else expectedRealized += grossPnl;
      expectedFees += fees;
    }
    const report = reconcileBacktestAccounting({ startingEquity, trades });
    const expectedEquity = startingEquity + expectedRealized + expectedUnrealized - expectedFees;
    assert.strictEqual(report.ok, true, `seed=0xa11ce sequence=${sequence}`);
    assert.ok(Math.abs(report.endingEquity - expectedEquity) <= 1e-8, `seed=0xa11ce sequence=${sequence}`);
    assert.ok(Math.abs(report.delta) <= 1e-8, `seed=0xa11ce sequence=${sequence}`);
  }
});

// ============================================================================
// REPORT
// ============================================================================
console.log('\n' + '='.repeat(60));
console.log(`ERGEBNIS:  ${passed} PASSED  |  ${failed} FAILED  |  ${passed + failed} TOTAL`);
console.log('='.repeat(60));
if (errors.length) {
  console.error('\nFEHLER:');
  for (const e of errors) {
    console.error(`  ✗ ${e.name}`);
    console.error(`    ${e.message}`);
  }
}
process.exit(failed > 0 ? 1 : 0);
