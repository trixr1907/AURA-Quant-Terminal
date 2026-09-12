'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'Symbiose_Dashboard.html'), 'utf8');
const begin = html.indexOf('//  ==ENGINE_BEGIN==');
const end = html.indexOf('// ==ENGINE_END==');
assert(begin >= 0 && end > begin, 'Engine markers missing in Symbiose_Dashboard.html');

const ctx = {
  console,
  Float64Array,
  Int8Array,
  Uint8Array,
  Math,
  Date,
  isFinite: Number.isFinite,
  isNaN: Number.isNaN,
  Infinity,
  Number,
};
vm.createContext(ctx);
vm.runInContext(`${html.slice(begin, end)}\nthis.__analyze = analyze;\nthis.__cvdSeries = cvdSeries;\nthis.__cvdArr = cvdArr;`, ctx);

const analyze = ctx.__analyze;
const cvdSeries = ctx.__cvdSeries;
const cvdArr = ctx.__cvdArr;

// Generate deterministic synthetic test candles
const sampleSize = 200;
const baseCandles = [];
let price = 50000;
for (let i = 0; i < sampleSize; i++) {
  const o = price;
  const h = price + 20 + (i % 7) * 3;
  const l = price - 15 - (i % 5) * 2;
  const c = price + (i % 2 === 0 ? 5 : -4);
  const v = 100 + (i % 11) * 10;
  price = c;
  baseCandles.push({ t: 1700000000000 + i * 3600000, o, h, l, c, v });
}

// 1. Candles without tbv field
const candlesNoTbv = baseCandles.map(k => ({ ...k }));

// 2. Candles with tbv: null (Bitget format)
const candlesBitget = baseCandles.map(k => ({ ...k, tbv: null }));

// 3. Candles with positive tbv (Binance format: arbitrary taker buy volume)
const candlesBinance = baseCandles.map((k, i) => ({ ...k, tbv: k.v * (0.3 + (i % 5) * 0.1) }));

// 4. Candles with tbv: 0
const candlesTbvZero = baseCandles.map(k => ({ ...k, tbv: 0 }));

// Run full analyze engine
const resNoTbv = analyze(candlesNoTbv);
const resBitget = analyze(candlesBitget);
const resBinance = analyze(candlesBinance);
const resTbvZero = analyze(candlesTbvZero);

// Assert exact numerical equality across all CVD series
assert.strictEqual(resBitget.cvd.length, sampleSize);
assert.strictEqual(resBinance.cvd.length, sampleSize);

for (let i = 0; i < sampleSize; i++) {
  assert.strictEqual(
    resBitget.cvd[i],
    resBinance.cvd[i],
    `CVD must be identical between Bitget (no tbv) and Binance (with tbv) at bar ${i}`
  );
  assert.strictEqual(
    resBitget.cvd[i],
    resNoTbv.cvd[i],
    `CVD must be identical when tbv field is omitted at bar ${i}`
  );
  assert.strictEqual(
    resBitget.cvd[i],
    resTbvZero.cvd[i],
    `CVD must be identical when tbv is 0 at bar ${i}`
  );

  assert.strictEqual(
    resBitget.cvdDelta[i],
    resBinance.cvdDelta[i],
    `CVD Delta must be identical between Bitget and Binance at bar ${i}`
  );
  assert.strictEqual(
    resBitget.emaCvd[i],
    resBinance.emaCvd[i],
    `EMA(CVD) must be identical between Bitget and Binance at bar ${i}`
  );
}

// Direct cvdSeries function checks with varying signatures
const vArr = new Float64Array(baseCandles.map(k => k.v));
const hArr = new Float64Array(baseCandles.map(k => k.h));
const lArr = new Float64Array(baseCandles.map(k => k.l));
const cArr = new Float64Array(baseCandles.map(k => k.c));
const tbvArr = new Float64Array(baseCandles.map((k, i) => k.v * 0.7));

const direct5Args = cvdSeries(vArr, tbvArr, hArr, lArr, cArr);
const direct5Null = cvdSeries(vArr, null, hArr, lArr, cArr);
const direct4Args = cvdSeries(vArr, hArr, lArr, cArr);

for (let i = 0; i < sampleSize; i++) {
  assert.strictEqual(direct5Args.cvd[i], direct5Null.cvd[i], `direct 5-arg with tbv vs null must match at ${i}`);
  assert.strictEqual(direct5Args.cvd[i], direct4Args.cvd[i], `direct 5-arg vs 4-arg must match at ${i}`);
}

console.log('PASS CVD calculation is strictly feed-independent and invariant to taker-buy-volume');
