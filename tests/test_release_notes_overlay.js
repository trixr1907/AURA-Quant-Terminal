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

const storage = new Map();
const modal = { hidden: true, style: {}, setAttribute() {} };
const context = {
  localStorage: { getItem: k => storage.get(k) || null, setItem: (k, v) => storage.set(k, v) },
  document: { getElementById: id => id === 'release-notes-modal' ? modal : null },
};
vm.createContext(context);
vm.runInContext(`${extractFunction('showReleaseNotesOnce')}\nthis.showReleaseNotesOnce=showReleaseNotesOnce;`, context);

assert.strictEqual(context.showReleaseNotesOnce('1.0.8'), true, 'new version must open release notes');
assert.strictEqual(modal.hidden, false, 'release notes overlay must become visible');
modal.hidden = true;
assert.strictEqual(context.showReleaseNotesOnce('1.0.8'), false, 'same version must not reopen automatically');
assert.strictEqual(modal.hidden, true, 'dismissed current-version overlay must stay hidden');
assert(html.includes('id="release-notes-modal"'), 'release notes modal markup required');
assert(html.includes('Was ist neu in AURA v1.0.8?'), 'release notes need plain-language version heading');

console.log('PASS release notes overlay opens exactly once per installed version');
