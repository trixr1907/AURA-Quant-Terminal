'use strict';

const assert = require('assert');
const fs = require('fs');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function getFunctionBody(name) {
  const marker = `function ${name}(`;
  const start = html.indexOf(marker);
  if (start < 0) throw new Error(`${name} not found`);
  let depth = 0;
  let bodyStarted = false;
  for (let i = start; i < html.length; i += 1) {
    if (html[i] === '{') { depth += 1; bodyStarted = true; }
    if (html[i] === '}') {
      depth -= 1;
      if (bodyStarted && depth === 0) return html.slice(start, i + 1);
    }
  }
  throw new Error(`${name} is incomplete`);
}

const fnCode = `
${getFunctionBody('generateTradingViewPositionScript')}
`;

const context = {
  Number, Math, String, Array, Object,
  App: { symbol: 'BTCUSDT', leverage: 10, data: null }
};

const fn = new Function('ctx', `
  with(ctx) {
    ${fnCode}
    return { generateTradingViewPositionScript };
  }
`);

const { generateTradingViewPositionScript } = fn(context);

const sampleTradeLong = {
  coin: 'BTCUSDT',
  dir: 1,
  entry: 60000.0,
  currentSl: 59000.0,
  tp: 62000.0,
  tp2: 63000.0,
  tp3: 65000.0,
  margin: 200,
  leverage: 10
};

const sampleTradeShort = {
  coin: 'ETHUSDT',
  dir: -1,
  entry: 3000.0,
  currentSl: 3060.0,
  tp: 2880.0,
  tp2: 2820.0,
  tp3: 2700.0,
  margin: 150,
  leverage: 15
};

const longScript = generateTradingViewPositionScript(sampleTradeLong);
assert(longScript.includes('posDir    = input.string("LONG"'), 'Must have LONG direction');
assert(longScript.includes('posEntry  = input.float(60000.0000'), 'Must have Entry price');
assert(longScript.includes('posSl     = input.float(59000.0000'), 'Must have SL price');
assert(longScript.includes('posTp     = input.float(63000.0000'), 'Must have TP2 price as primary target');
assert(longScript.includes('boxProfit := box.new('), 'Must draw profit box');
assert(longScript.includes('boxLoss   := box.new('), 'Must draw loss box');
assert(longScript.includes('43000517002'), 'Must reference Long tool');

const shortScript = generateTradingViewPositionScript(sampleTradeShort);
assert(shortScript.includes('posDir    = input.string("SHORT"'), 'Must have SHORT direction');
assert(shortScript.includes('posEntry  = input.float(3000.0000'), 'Must have Entry price');
assert(shortScript.includes('posSl     = input.float(3060.0000'), 'Must have SL price');
assert(shortScript.includes('posTp     = input.float(2820.0000'), 'Must have TP2 price as primary target');
assert(shortScript.includes('43000516992'), 'Must reference Short tool');

// Verify trade card action in HTML
assert(html.includes('data-tv-overlay='), 'Trade card must include 1:1 TV Position Tool button');
assert(html.includes('data-tv-overlay'), 'Event listener for trade TV position overlay must exist');

console.log('PASS 1:1 Standalone TradingView Position Tool generation verified');
