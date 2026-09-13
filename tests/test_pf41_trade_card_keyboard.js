'use strict';
const assert = require('node:assert');
const fs = require('node:fs');
const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

const binders = html.match(/function bindAssetSwitchControls\([\s\S]*?\n}/);
assert(binders, 'PF-41: shared asset-switch binder missing');
assert(html.includes("e.key !== 'Enter' && e.key !== ' '"), 'PF-41: Enter and Space must activate role=button symbols');
assert((html.match(/bindAssetSwitchControls\(/g) || []).length >= 3, 'PF-41: shared binder must serve tracker and Autobot');
console.log('PASS PF-41 keyboard activation for shared trade cards');
