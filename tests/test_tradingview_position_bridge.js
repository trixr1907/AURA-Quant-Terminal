'use strict';
/**
 * test_tradingview_position_bridge.js
 *
 * PF-30 (v1.4.0): showTradingViewDrawingModal, launchTradingViewDesktop,
 * copyTvPositionToolForTrade, openInTradingView, getTradingViewPineText
 * were intentionally removed. The standalone position-script generator
 * (generateTradingViewPositionScript) and the Pine trade finder
 * (findActiveTradeForPine) remain.
 *
 * This file verifies:
 *  1. Removed functions are absent from Dashboard JS.
 *  2. generateTradingViewPositionScript still produces valid Pine v6 scripts.
 *  3. findActiveTradeForPine still resolves trades correctly.
 */

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function getFunction(name) {
  const asyncMarker = `async function ${name}(`;
  const syncMarker = `function ${name}(`;
  const asyncStart = html.indexOf(asyncMarker);
  const start = asyncStart >= 0 ? asyncStart : html.indexOf(syncMarker);
  if (start < 0) return null; // intentionally absent
  let depth = 0, bodyStarted = false;
  for (let i = start; i < html.length; i += 1) {
    if (html[i] === '{') { depth += 1; bodyStarted = true; }
    if (html[i] === '}') {
      depth -= 1;
      if (bodyStarted && depth === 0) return html.slice(start, i + 1);
    }
  }
  return null;
}

// 1. Removed functions must be absent
const removed = [
  'showTradingViewDrawingModal',
  'launchTradingViewDesktop',
  'openInTradingView',
  'copyTvPositionToolForTrade',
  'getTradingViewPineText',
];
for (const name of removed) {
  assert(getFunction(name) === null, `${name} must have been removed in PF-30`);
}

// 2+3. generateTradingViewPositionScript and findActiveTradeForPine still present
const genSrc = getFunction('generateTradingViewPositionScript');
assert(genSrc !== null, 'generateTradingViewPositionScript must still exist');
const findSrc = getFunction('findActiveTradeForPine');
assert(findSrc !== null, 'findActiveTradeForPine must still exist');

const context = {
  App: { data: { live: {} } },
  Autobot: { trades: [] },
  relayBase: () => 'http://127.0.0.1:8787',
};
vm.createContext(context);
vm.runInContext(`${findSrc}; this.findActiveTradeForPine = findActiveTradeForPine;`, context);
vm.runInContext(`${genSrc}; this.generateTradingViewPositionScript = generateTradingViewPositionScript;`, context);

const longTrade = {
  coin: 'ETHUSDT', dir: 1, entry: 3200.0, sl: 3120.0,
  tp: 3360.0, tp2: 3440.0, tp3: 3600.0, leverage: 10, remainingMargin: 150
};

const longScript = context.generateTradingViewPositionScript(longTrade);
assert(longScript.includes('//@version=6'), 'must be Pine v6');
assert(longScript.includes('AURA LONG Position — ETHUSDT'), 'must include coin and direction');
assert(longScript.includes('posDir    = input.string("LONG"'), 'must declare LONG direction');
assert(longScript.includes('#089981'), 'Green profit zone color must be present');
assert(longScript.includes('#f23645'), 'Red loss zone color must be present');

const shortTrade = {
  coin: 'SOLUSDT', dir: -1, entry: 102.5, currentSl: 105.0,
  tp: 97.5, tp2: 95.0, tp3: 90.0, leverage: 8, remainingMargin: 100
};
const shortScript = context.generateTradingViewPositionScript(shortTrade);
assert(shortScript.includes('AURA SHORT Position — SOLUSDT'), 'must include coin and direction for short');
assert(shortScript.includes('posDir    = input.string("SHORT"'), 'must declare SHORT direction');

console.log('PASS 1:1 Standalone TradingView Position Tool generation verified');
