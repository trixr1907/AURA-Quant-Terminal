'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  const start = html.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`${name}() source not found`);
  const brace = html.indexOf('{', start);
  let depth = 0, quote = null, escaped = false;
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

const context = { Number, Object, isFinite, console, Math };
vm.createContext(context);
vm.runInContext(
  `${extractFunction('tfToMinutes')}\n` +
  `${extractFunction('tfToHours')}\n` +
  `${extractFunction('formatTimeStopDisplay')}\n` +
  `this.tfToMinutes = tfToMinutes;\n` +
  `this.tfToHours = tfToHours;\n` +
  `this.formatTimeStopDisplay = formatTimeStopDisplay;`,
  context,
);

// 1. Timeframe scaling assertions
assert.strictEqual(context.tfToMinutes('15m'), 15, '15m must scale to 15 minutes');
assert.strictEqual(context.tfToHours('15m'), 0.25, '15m must scale to 0.25 hours');

assert.strictEqual(context.tfToMinutes('1h'), 60, '1h must scale to 60 minutes');
assert.strictEqual(context.tfToHours('1h'), 1.0, '1h must scale to 1.0 hours');

assert.strictEqual(context.tfToMinutes('4h'), 240, '4h must scale to 240 minutes');
assert.strictEqual(context.tfToHours('4h'), 4.0, '4h must scale to 4.0 hours');

assert.strictEqual(context.tfToMinutes('1d'), 1440, '1d must scale to 1440 minutes');
assert.strictEqual(context.tfToHours('1d'), 24.0, '1d must scale to 24.0 hours');

// 2. Formatted display assertions
assert.strictEqual(context.formatTimeStopDisplay(10, '15m'), '10 Bars (2.5h)', '10 bars on 15m must display 2.5h, NOT 10h');
assert.strictEqual(context.formatTimeStopDisplay(10, '1h'), '10 Bars (10h)', '10 bars on 1h must display 10h');
assert.strictEqual(context.formatTimeStopDisplay(10, '4h'), '10 Bars (40h)', '10 bars on 4h must display 40h');
assert.strictEqual(context.formatTimeStopDisplay(10, '1d'), '10 Bars (10d)', '10 bars on 1d must display 10d');

console.log('PASS time-stop timeframe duration correctly scales across 15m, 1h, 4h, and 1d');
