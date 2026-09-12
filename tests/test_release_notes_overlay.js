'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractDeclaration(prefix) {
  const start = html.indexOf(prefix);
  if (start < 0) throw new Error(`${prefix} not found`);
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
  throw new Error(`${prefix} closing brace not found`);
}

class MockElement {
  constructor(id = '') {
    this.id = id;
    this.children = [];
    this.style = {};
    this.hidden = false;
    this.attributes = {};
    this._textContent = '';
  }
  get textContent() {
    if (this.children.length === 0) return this._textContent;
    return this.children.map(c => (typeof c === 'string' ? c : c.textContent)).join('');
  }
  set textContent(val) {
    this.children = [];
    this._textContent = String(val);
  }
  get firstChild() {
    return this.children[0] || null;
  }
  appendChild(child) {
    this.children.push(child);
    return child;
  }
  removeChild(child) {
    const idx = this.children.indexOf(child);
    if (idx >= 0) this.children.splice(idx, 1);
    return child;
  }
  replaceChildren(...newChildren) {
    this.children = [...newChildren];
    this._textContent = '';
  }
  setAttribute(k, v) {
    this.attributes[k] = String(v);
  }
}

const elements = {
  'release-notes-modal': new MockElement('release-notes-modal'),
  'release-notes-title': new MockElement('release-notes-title'),
  'release-notes-summary': new MockElement('release-notes-summary'),
  'release-notes-list': new MockElement('release-notes-list'),
  'release-notes-older': new MockElement('release-notes-older'),
};
elements['release-notes-modal'].hidden = true;

const storage = new Map();
const context = {
  localStorage: { getItem: k => storage.get(k) || null, setItem: (k, v) => storage.set(k, v) },
  document: {
    getElementById: id => elements[id] || null,
    createElement: tag => new MockElement(tag),
  },
  console,
};
vm.createContext(context);

const codeToRun = `
${extractDeclaration('const AURA_RELEASE_NOTES =')}
${extractDeclaration('function renderReleaseNotesModal(')}
${extractDeclaration('function showReleaseNotesOnce(')}
this.AURA_RELEASE_NOTES = AURA_RELEASE_NOTES;
this.renderReleaseNotesModal = renderReleaseNotesModal;
this.showReleaseNotesOnce = showReleaseNotesOnce;
`;
vm.runInContext(codeToRun, context);

// Test 1: Overlay shows once per version
const currentVersion = fs.readFileSync('VERSION', 'utf8').trim();
assert.strictEqual(context.showReleaseNotesOnce(currentVersion), true, 'new version must open release notes');
assert.strictEqual(elements['release-notes-modal'].hidden, false, 'release notes overlay must become visible');
elements['release-notes-modal'].hidden = true;
assert.strictEqual(context.showReleaseNotesOnce(currentVersion), false, 'same version must not reopen automatically');
assert.strictEqual(elements['release-notes-modal'].hidden, true, 'dismissed current-version overlay must stay hidden');

// Test 2: Release notes structure for current version
const notes = context.AURA_RELEASE_NOTES[currentVersion];
assert(notes, `AURA_RELEASE_NOTES must contain entry for current version ${currentVersion}`);
assert(notes.title && notes.title.length > 0, 'Release notes must have a title');
assert(notes.summary && notes.summary.length > 0, 'Release notes must have a summary');
assert(Array.isArray(notes.highlights) && notes.highlights.length >= 3, 'Release notes must have at least 3 highlights');

// Test 3: renderReleaseNotesModal renders bulletpoints for current version
context.renderReleaseNotesModal(currentVersion);
assert.strictEqual(elements['release-notes-title'].textContent, `Was ist neu in AURA v${currentVersion}?`);
assert.strictEqual(elements['release-notes-summary'].textContent, notes.summary);
assert.strictEqual(elements['release-notes-list'].children.length, notes.highlights.length);
for (let i = 0; i < notes.highlights.length; i += 1) {
  assert.strictEqual(elements['release-notes-list'].children[i].textContent, notes.highlights[i]);
}

// Test 4: Missing version renders prominent fallback placeholder instead of old static text
context.renderReleaseNotesModal('9.9.9');
assert.strictEqual(elements['release-notes-title'].textContent, 'Was ist neu in AURA v9.9.9?');
assert(
  elements['release-notes-summary'].textContent.includes('keine spezifischen Versionshinweise'),
  'missing version must render fallback notice'
);
assert.strictEqual(elements['release-notes-list'].children.length, 0, 'missing version list should be empty');

// Test 5: Static markup requirements in HTML
assert(html.includes('id="release-notes-modal"'), 'release notes modal markup required');
assert(html.includes('id="release-notes-summary"'), 'release notes summary element required');
assert(html.includes('id="release-notes-list"'), 'release notes list element required');
assert(html.includes('id="release-notes-older"'), 'release notes older element required');

console.log('PASS release notes overlay data-driven rendering and once-per-version lifecycle verified');
