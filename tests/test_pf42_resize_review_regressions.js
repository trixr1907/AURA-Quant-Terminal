'use strict';
const assert = require('assert');
const fs = require('fs');
const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

const resize = html.match(/function initChartResize\(\)[\s\S]*?\n}\n\nfunction initChartDrawingTools/);
assert(resize, 'PF-42: resize initializer missing');
assert(resize[0].includes('try {'), 'PF-42: storage access must be guarded');
assert(resize[0].includes("handle.addEventListener('pointerdown'"), 'PF-42: pointer resize path missing');
assert(!resize[0].includes("handle.addEventListener('touchstart'"), 'PF-42: duplicate touch listener must not coexist with pointer path');
assert(resize[0].includes('scheduleChartRender()'), 'PF-42: drag redraw must use 4-fps scheduler');
console.log('PASS PF-42 review regressions: safe storage, one pointer path, throttled redraw');
