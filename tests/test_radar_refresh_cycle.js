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

const context = { Number };
vm.createContext(context);
vm.runInContext(`${extractFunction('shouldStartRadarScan')}\nthis.shouldStartRadarScan=shouldStartRadarScan;`, context);

assert.strictEqual(context.shouldStartRadarScan({ scanning: true }, 10, false), false,
  '60-second refresh must not restart an active radar scan');
assert.strictEqual(context.shouldStartRadarScan({ scanning: false }, 764, false), false,
  'completed radar results must stay visible on ordinary dashboard refreshes');
assert.strictEqual(context.shouldStartRadarScan(null, 0, false), true,
  'initial load must start the first radar scan');
assert.strictEqual(context.shouldStartRadarScan({ scanning: false }, 764, true), true,
  'an explicit force request may start a new radar scan');

const loadAllStart = html.indexOf('async function loadAll(');
const loadAllEnd = html.indexOf('\nfunction collectErrs()', loadAllStart);
assert(loadAllStart >= 0 && loadAllEnd > loadAllStart, 'loadAll() source not found');
const loadAllSource = html.slice(loadAllStart, loadAllEnd);
assert(loadAllSource.includes('shouldStartRadarScan('), 'loadAll must guard radar restarts');
assert.strictEqual((loadAllSource.match(/loadRadar\(\)\.catch/g) || []).length, 1,
  'loadAll must have only the guarded radar start');

console.log('PASS dashboard refresh does not restart an active or completed Action Radar scan');
