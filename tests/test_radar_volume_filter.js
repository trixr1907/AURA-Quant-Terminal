'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
function extractFunction(name) {
  const start = html.indexOf(`function ${name}(`);
  assert(start >= 0, `${name} source missing`);
  const brace = html.indexOf('{', start);
  let depth = 0;
  for (let i = brace; i < html.length; i++) {
    if (html[i] === '{') depth++;
    else if (html[i] === '}' && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error(`${name} source incomplete`);
}

const context = {};
vm.createContext(context);
vm.runInContext(`${extractFunction('filterRadarByVolume')}\n${extractFunction('radarVolumeCounts')}\nthis.api={filterRadarByVolume,radarVolumeCounts};`, context);

const rows = [
  { symbol: 'AUSDT', vol: 100_000 },
  { symbol: 'BUSDT', vol: 500_000 },
  { symbol: 'CUSDT', vol: 999_999 },
  { symbol: 'DUSDT', vol: 1_000_000 },
  { symbol: 'EUSDT', vol: 5_000_000 },
  { symbol: 'FUSDT', vol: null },
];
assert.deepStrictEqual(Array.from(context.api.filterRadarByVolume(rows, 0), r => r.symbol), ['AUSDT', 'BUSDT', 'CUSDT', 'DUSDT', 'EUSDT', 'FUSDT']);
assert.deepStrictEqual(Array.from(context.api.filterRadarByVolume(rows, 500_000), r => r.symbol), ['BUSDT', 'CUSDT', 'DUSDT', 'EUSDT']);
assert.deepStrictEqual(Array.from(context.api.filterRadarByVolume(rows, 1_000_000), r => r.symbol), ['DUSDT', 'EUSDT']);
assert.deepStrictEqual(Array.from(context.api.filterRadarByVolume(rows, 5_000_000), r => r.symbol), ['EUSDT']);
assert.deepStrictEqual({ ...context.api.radarVolumeCounts(rows) }, { all: 6, 500000: 4, 1000000: 2, 5000000: 1 });
assert(html.includes('id="radar-volume-filter"'), 'radar volume selector missing');
assert(html.includes('localStorage.setItem(\'symbiose_radar_volume_filter\''), 'volume choice must persist');
assert(html.includes('id="radar-vol-all"'), 'live all counter missing');
assert(html.includes('id="radar-vol-500k"'), 'live 500k counter missing');
assert(html.includes('id="radar-vol-1m"'), 'live 1m counter missing');
assert(html.includes('id="radar-vol-5m"'), 'live 5m counter missing');

console.log('PASS radar display volume filter and live counters');
