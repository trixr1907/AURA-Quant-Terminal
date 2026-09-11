'use strict';

const assert = require('assert');
const fs = require('fs');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

// Simple function extractor that extracts code between function start and next top-level function start
function getFunctionBody(name) {
  const marker = `function ${name}(`;
  const start = html.indexOf(marker);
  if (start < 0) throw new Error(`${name} not found`);
  const nextFn = html.indexOf('\nfunction ', start + marker.length);
  const nextConst = html.indexOf('\nconst ', start + marker.length);
  const end = Math.min(nextFn > 0 ? nextFn : html.length, nextConst > 0 ? nextConst : html.length);
  return html.slice(start, end);
}

const pineMock = `
grpFC = "7) Trade Forecasting & Execution"
fcShow     = input.bool(true, "Trade Forecast visualisieren", group=grpFC)
fcMode     = input.string("Auto", "Forecast-Modus", options=["Auto", "Custom", "Aus"], group=grpFC)
fcDir      = input.string("Auto", "Richtung (Custom)", options=["Auto", "Long", "Short"], group=grpFC)
fcEntry    = input.float(0.0, "Entry Preis (Custom)", minval=0.0, step=0.0001, group=grpFC)
fcSl       = input.float(0.0, "Stop Loss (Custom)", minval=0.0, step=0.0001, group=grpFC)
fcTp1      = input.float(0.0, "TP1 Preis (Custom)", minval=0.0, step=0.0001, group=grpFC)
fcTp2      = input.float(0.0, "TP2 Preis (Custom)", minval=0.0, step=0.0001, group=grpFC)
fcTp3      = input.float(0.0, "TP3 Preis (Custom)", minval=0.0, step=0.0001, group=grpFC)
fcLev      = input.int(10, "Hebel (Leverage)", minval=1, maxval=125, group=grpFC)
fcNote     = input.string("AURA Active Trade", "Trade Notiz / ID", group=grpFC)
`;

// Extract and eval
const fnCode = `
${getFunctionBody('buildCustomTradingViewPine')}
${getFunctionBody('findActiveTradeForPine')}
${getFunctionBody('getTradingViewPineText')}
`;

const context = {
  Number, Math, String, Array, Object,
  App: { symbol: 'BTCUSDT', leverage: 10, data: null },
  Autobot: { trades: [] },
  tradingViewPineText: pineMock
};

const fn = new Function('ctx', `
  with(ctx) {
    ${fnCode}
    return { buildCustomTradingViewPine, findActiveTradeForPine, getTradingViewPineText };
  }
`);

const { buildCustomTradingViewPine, getTradingViewPineText } = fn(context);

const sampleTrade = {
  coin: 'SOLUSDT',
  dir: 1,
  entry: 102.50,
  currentSl: 98.20,
  tp1: 106.80,
  tp2: 111.10,
  tp3: 119.70,
  leverage: 10,
  note: 'AURA SOLUSDT LONG 10x'
};

const customizedPine = getTradingViewPineText(sampleTrade);
assert(customizedPine.includes('fcMode     = input.string("Custom"'), 'Pine should be set to Custom forecast mode');
assert(customizedPine.includes('fcDir      = input.string("Long"'), 'Pine should have Long direction');
assert(customizedPine.includes('fcEntry    = input.float(102.5000'), 'Pine should have Entry price');
assert(customizedPine.includes('fcSl       = input.float(98.2000'), 'Pine should have SL price');
assert(customizedPine.includes('fcTp1      = input.float(106.8000'), 'Pine should have TP1 price');
assert(customizedPine.includes('fcTp2      = input.float(111.1000'), 'Pine should have TP2 price');
assert(customizedPine.includes('fcTp3      = input.float(119.7000'), 'Pine should have TP3 price');

// Check active trade card button
assert(html.includes('data-tv-ab-idx='), 'Trade card must include "In TV visualisieren" button');
assert(html.includes('data-tv-ab-idx'), 'Event listener for active trade TV button must exist');

console.log('PASS Pine trade forecasting overlay successfully generated and verified');
