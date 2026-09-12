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

const context = { Number };
vm.createContext(context);
vm.runInContext(`${extractFunction('canStartHeroPaperTrade')}\nthis.canStartHeroPaperTrade = canStartHeroPaperTrade;`, context);

const goLong = {
  longSig: true,
  shortSig: false,
  btcBlock: false,
  kelly: { hasEdge: true },
  entry: 100,
  sl: 98,
  tp1: 104,
  tp2: 108,
};

assert.strictEqual(context.canStartHeroPaperTrade(goLong), true, 'a complete, unblocked long setup with Kelly edge must pass');
assert.strictEqual(context.canStartHeroPaperTrade({ ...goLong, longSig: false, shortSig: true }), true, 'a complete, unblocked short setup with Kelly edge must pass');

for (const [label, live] of [
  ['missing live object', null],
  ['regime or squeeze block', { ...goLong, blockReason: 'SQUEEZE' }],
  ['BTC veto', { ...goLong, btcBlock: true }],
  ['missing Kelly edge', { ...goLong, kelly: { hasEdge: false } }],
  ['missing signal', { ...goLong, longSig: false }],
  ['NaN entry', { ...goLong, entry: NaN }],
  ['zero stop', { ...goLong, sl: 0 }],
  ['zero target', { ...goLong, tp1: 0 }],
  ['missing second target', { ...goLong, tp2: undefined }],
]) {
  assert.strictEqual(context.canStartHeroPaperTrade(live), false, `${label} must fail closed`);
}

const heroStart = html.indexOf('function renderHero(');
const heroEnd = html.indexOf('\nfunction renderAll(', heroStart);
const heroSource = html.slice(heroStart, heroEnd);
assert(heroStart >= 0 && heroEnd > heroStart, 'renderHero source must be present');
assert(heroSource.includes('notifyHeroState(heroState, L)'), 'renderHero must handle hero state transitions');
assert(heroSource.includes('heroClassMap'), 'renderHero must map state to styling');
const paperStart = html.indexOf('function startPaperTradeFromCockpit()');
const paperEnd = html.indexOf('\nfunction renderTradeProjection()', paperStart);
const paperSource = html.slice(paperStart, paperEnd);
assert(paperStart >= 0 && paperEnd > paperStart, 'Paper start handler source must be present');
assert(!paperSource.includes('canStartHeroPaperTrade('), 'cockpit paper handler must remain intentionally independent from the setup gate documented for v1.2.4');
assert(paperSource.includes('normalizeTrade('), 'Paper start handler must normalize trades defensively');
assert(paperSource.includes('generateDeterministicOid('), 'Paper start handler must use deterministic order IDs');
assert(html.includes('Paper Autobot'), 'visible UI must name the paper-only Autobot');
assert(!html.includes('Vollautonomer Quant-Bot'), 'visible UI must not suggest a fully autonomous execution bot');
assert(html.includes('TECHNISCH BEREIT'), 'radar badge must distinguish technical readiness');
assert(/Vorqualifikation[^<]*keine Order-?\/?Paper-Freigabe/i.test(html), 'radar legend must explain that technical readiness is not Paper approval');
assert(html.includes('MODEL_NO_EVIDENCE'), 'UI must prominently retain the global model verdict');

console.log('PASS cockpit paper trade is intentionally ungated; autobot gates remain fail-closed');
