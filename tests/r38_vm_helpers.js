'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  const marker = `function ${name}`;
  const start = html.indexOf(marker);
  assert(start >= 0, `${name} not found`);
  const openParen = html.indexOf('(', start);
  let parenDepth = 0;
  let bodyStart = -1;
  for (let i = openParen; i < html.length; i += 1) {
    if (html[i] === '(') parenDepth += 1;
    if (html[i] === ')' && --parenDepth === 0) {
      bodyStart = html.indexOf('{', i);
      break;
    }
  }
  assert(bodyStart >= 0, `${name} body not found`);
  let depth = 0;
  let quote = null;
  let escaped = false;
  for (let i = bodyStart; i < html.length; i += 1) {
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
  throw new Error(`${name} closing brace not found`);
}

function loadFunctions(names, context) {
  vm.createContext(context);
  const exports = names.map(name => `this.${name}=${name};`);
  vm.runInContext( // NOSONAR: executes only functions extracted from checked-in repository source.
    [...names.map(extractFunction), ...exports].join('\n'),
    context,
  );
  return context;
}

module.exports = { assert, loadFunctions };
