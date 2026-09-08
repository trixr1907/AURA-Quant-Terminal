'use strict';

const assert = require('assert');
const fs = require('fs');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

assert(html.includes('function tfToMinutes('), 'tfToMinutes helper required');
assert(html.includes('function tfToHours('), 'tfToHours helper required');
assert(html.includes('function formatTimeStopDisplay('), 'formatTimeStopDisplay helper required');
assert(html.includes('function copyTextToClipboard('), 'copyTextToClipboard helper required');
assert(html.includes('function switchToAsset('), 'switchToAsset helper required');
assert(html.includes('data-copy-val'), 'trade values must include data-copy-val attributes');
assert(html.includes('data-switch-coin'), 'trade asset badges must include data-switch-coin attributes');

console.log('PASS trade cards support clickable data copying and asset focus switching');
