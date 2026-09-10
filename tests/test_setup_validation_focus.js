'use strict';

const assert = require('assert');
const fs = require('fs');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const start = html.indexOf('function renderSignal(');
const end = html.indexOf('\nfunction renderMTF(', start);
assert(start >= 0 && end > start, 'renderSignal source not found');
const source = html.slice(start, end);
const keyMatch = source.match(/const stateKey = \[([\s\S]*?)\];/);
assert(keyMatch, 'renderSignal cache key not found');
const key = keyMatch[1];

assert(key.includes('App.symbol'), 'Setup Validation cache must be scoped by selected symbol');
assert(key.includes('App.chartTF'), 'Setup Validation cache must be scoped by selected timeframe');
assert(key.includes('L.total'), 'Setup Validation cache must track the displayed adjusted score');
assert(key.includes('L.probWin'), 'Setup Validation cache must track displayed OOS win rate');
assert(key.includes('L.kelly?.hasEdge'), 'Setup Validation cache must track the displayed edge gate');
assert(!key.includes('L.score'), 'cache must not rely on nonexistent L.score');
assert(!key.includes('L.qual'), 'cache must not rely on nonexistent L.qual');
assert(!key.includes('L.gate'), 'cache must not rely on nonexistent L.gate');

console.log('PASS Setup Validation cache follows the selected asset and displayed live fields');
