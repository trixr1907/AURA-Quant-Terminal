'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');

// Load calcKelly directly from Symbiose_Dashboard.html
const html = fs.readFileSync(path.resolve(__dirname, '..', 'Symbiose_Dashboard.html'), 'utf8');

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

const ctx = { Number, Object, isFinite, console, Math };
vm.createContext(ctx);
vm.runInContext(`${extractFunction('calcKelly')}\nthis.calcKelly = calcKelly;`, ctx);
const calcKelly = ctx.calcKelly;

assert.strictEqual(typeof calcKelly, 'function', 'calcKelly must be a function');

function assertNear(actual, expected, eps = 1e-9, msg = '') {
  assert.strictEqual(Math.abs(actual - expected) < eps, true, `${msg} expected ${expected} ± ${eps}, got ${actual}`);
}

// ============================================================================
//  ANALYTICAL KELLY ORACLE VERIFICATION (F-17)
//  Formulas are derived from first mathematical principles:
//    p = win probability
//    q = 1 - p
//    b = avgWinR / avgLossR (win/loss ratio)
//    Expected edge = p * b - q
//    Full Kelly fraction f* = p - q/b = (p*(b+1) - 1)/b
//    Half-Kelly = 0.5 * f*
//    Hard cap = min(0.25, riskPct / 100)
//    Sample multiplier:
//      totalTrades >= 15 or null => 1.0
//      totalTrades < 5 => 0.0
//      5 <= totalTrades < 15 => (totalTrades - 5) / 10
//    finalFrac = min(halfKelly, hardCap) * sampleMultiplier
//    riskAmt = equity * finalFrac
// ============================================================================

function analyticalKellyOracle(probWin, avgWinR, avgLossR, riskPct, equity, totalTrades = null) {
  const noEdge = { edge: 0, fStar: 0, halfKelly: 0, finalFrac: 0, riskAmt: 0, hasEdge: false, b: 0 };
  if (!Number.isFinite(probWin) || probWin < 0 || probWin > 1) return noEdge;
  if (!Number.isFinite(avgWinR) || avgWinR <= 0) return noEdge;
  if (!Number.isFinite(avgLossR) || avgLossR <= 0) return noEdge;
  if (!Number.isFinite(riskPct) || riskPct <= 0) return noEdge;
  if (!Number.isFinite(equity) || equity <= 0) return noEdge;
  if (totalTrades !== null && (!Number.isFinite(totalTrades) || totalTrades < 0)) return noEdge;

  const b = avgWinR / avgLossR;
  const p = probWin;
  const q = 1 - p;
  const edge = p * b - q;
  const fStar = (p * (b + 1) - 1) / b;

  if (fStar <= 0 || edge <= 0) {
    return { ...noEdge, edge: edge * 100, b };
  }

  const halfKelly = 0.5 * fStar;
  const hardCap = Math.min(0.25, riskPct / 100);
  let sampleMultiplier = 1.0;
  if (totalTrades !== null) {
    if (totalTrades < 5) sampleMultiplier = 0.0;
    else if (totalTrades < 15) sampleMultiplier = (totalTrades - 5) / 10;
  }

  const finalFrac = Math.min(halfKelly, hardCap) * sampleMultiplier;
  const riskAmt = equity * finalFrac;
  const hasEdge = finalFrac > 0;

  return {
    edge: edge * 100,
    fStar,
    halfKelly,
    finalFrac,
    riskAmt,
    hasEdge,
    b,
  };
}

// 1. Analytical Test Case 1: Standard Symmetric Odds (b = 1.0)
//    p = 0.60, avgWinR = 1.0, avgLossR = 1.0 => b = 1.0
//    edge = 0.60 * 1 - 0.40 = +0.20 (20%)
//    f* = (0.60 * 2 - 1) / 1 = 0.20
//    halfKelly = 0.10
//    riskPct = 5% => hardCap = 0.05
//    finalFrac = min(0.10, 0.05) = 0.05
//    equity = 10,000 => riskAmt = 500
{
  const actual = calcKelly(0.60, 1.0, 1.0, 5.0, 10000, 20);
  const expected = analyticalKellyOracle(0.60, 1.0, 1.0, 5.0, 10000, 20);
  assert.strictEqual(actual.hasEdge, true);
  assertNear(actual.b, 1.0);
  assertNear(actual.edge, 20.0);
  assertNear(actual.fStar, 0.20);
  assertNear(actual.halfKelly, 0.10);
  assertNear(actual.finalFrac, 0.05);
  assertNear(actual.riskAmt, 500.0);
  assertNear(actual.edge, expected.edge);
}

// 2. Analytical Test Case 2: Asymmetric 2:1 Payoff (b = 2.0) with Kelly-bounded risk
//    p = 0.50, avgWinR = 2.0, avgLossR = 1.0 => b = 2.0
//    edge = 0.50 * 2 - 0.50 = +0.50 (50%)
//    f* = (0.50 * 3 - 1) / 2 = 0.50 / 2 = 0.25
//    halfKelly = 0.125 (12.5%)
//    riskPct = 20% => hardCap = 0.20
//    finalFrac = min(0.125, 0.20) = 0.125
//    equity = 20,000 => riskAmt = 2,500
{
  const actual = calcKelly(0.50, 2.0, 1.0, 20.0, 20000, null);
  const expected = analyticalKellyOracle(0.50, 2.0, 1.0, 20.0, 20000, null);
  assert.strictEqual(actual.hasEdge, true);
  assertNear(actual.b, 2.0);
  assertNear(actual.edge, 50.0);
  assertNear(actual.fStar, 0.25);
  assertNear(actual.halfKelly, 0.125);
  assertNear(actual.finalFrac, 0.125);
  assertNear(actual.riskAmt, 2500.0);
  assertNear(actual.edge, expected.edge);
}

// 3. Analytical Test Case 3: High Win-Rate Scalper with Sample Penalty
//    p = 0.70, avgWinR = 0.8, avgLossR = 1.0 => b = 0.8
//    edge = 0.70 * 0.8 - 0.30 = 0.56 - 0.30 = +0.26 (26%)
//    f* = (0.70 * 1.8 - 1) / 0.8 = (1.26 - 1) / 0.8 = 0.26 / 0.8 = 0.325
//    halfKelly = 0.1625
//    riskPct = 10% => hardCap = 0.10
//    totalTrades = 10 => sampleMultiplier = (10 - 5) / 10 = 0.50
//    finalFrac = min(0.1625, 0.10) * 0.50 = 0.05
//    equity = 50,000 => riskAmt = 2,500
{
  const actual = calcKelly(0.70, 0.8, 1.0, 10.0, 50000, 10);
  const expected = analyticalKellyOracle(0.70, 0.8, 1.0, 10.0, 50000, 10);
  assert.strictEqual(actual.hasEdge, true);
  assertNear(actual.b, 0.8);
  assertNear(actual.edge, 26.0);
  assertNear(actual.fStar, 0.325);
  assertNear(actual.halfKelly, 0.1625);
  assertNear(actual.finalFrac, 0.05);
  assertNear(actual.riskAmt, 2500.0);
  assertNear(actual.edge, expected.edge);
}

// 4. Analytical Test Case 4: Insufficient sample size (N < 5) => zero risk allocation
{
  const actual = calcKelly(0.80, 2.0, 1.0, 5.0, 10000, 4);
  assert.strictEqual(actual.hasEdge, false);
  assert.strictEqual(actual.finalFrac, 0);
  assert.strictEqual(actual.riskAmt, 0);
}

// 5. Analytical Test Case 5: Negative edge (p * b - q <= 0) => no trade
//    p = 0.40, b = 1.0 => edge = -0.20
{
  const actual = calcKelly(0.40, 1.0, 1.0, 5.0, 10000, 50);
  assert.strictEqual(actual.hasEdge, false);
  assert.strictEqual(actual.fStar, 0);
  assert.strictEqual(actual.halfKelly, 0);
  assert.strictEqual(actual.finalFrac, 0);
  assert.strictEqual(actual.riskAmt, 0);
  assertNear(actual.edge, -20.0);
}

// 6. Comprehensive Monte-Carlo matrix across 25 parameter grids
const probGrid = [0.35, 0.45, 0.55, 0.65, 0.75];
const winLossGrid = [0.5, 1.0, 1.5, 2.0, 3.0];
for (const p of probGrid) {
  for (const b of winLossGrid) {
    const res = calcKelly(p, b, 1.0, 8.0, 15000, 25);
    const exp = analyticalKellyOracle(p, b, 1.0, 8.0, 15000, 25);
    assertNear(res.edge, exp.edge, 1e-9, `Edge mismatch at p=${p}, b=${b}`);
    assertNear(res.fStar, exp.fStar, 1e-9, `fStar mismatch at p=${p}, b=${b}`);
    assertNear(res.halfKelly, exp.halfKelly, 1e-9, `halfKelly mismatch at p=${p}, b=${b}`);
    assertNear(res.finalFrac, exp.finalFrac, 1e-9, `finalFrac mismatch at p=${p}, b=${b}`);
    assertNear(res.riskAmt, exp.riskAmt, 1e-9, `riskAmt mismatch at p=${p}, b=${b}`);
  }
}

console.log('PASS calcKelly analytical oracle verification matches exact mathematical probability formulas');
