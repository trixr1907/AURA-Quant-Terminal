'use strict';
/**
 * test_pf34_asset_logos.js — PF-34 CDN Asset Logo helpers
 *
 * Tests:
 *  1. coinLogoUrl() builds the correct jsdelivr CDN URL for a given symbol.
 *  2. coinLogoUrl() strips USDT suffix.
 *  3. coinLogoUrl() strips PERP suffix.
 *  4. isCdnLogoKnownBad() returns false for an uncached symbol.
 *  5. markCdnLogoBad() marks a symbol as bad.
 *  6. isCdnLogoKnownBad() returns true after markCdnLogoBad().
 *  7. Cache idempotent — duplicate mark is fine.
 *  8. markCdnLogoBad() normalises USDT suffix when caching.
 *  9. coinLogoInitials() returns first 3 uppercase chars of base symbol.
 * 10. coinLogoInitials() for short symbol like "BTC" returns "BTC".
 * 11. coinLogoUrl() lowercases the base symbol in the URL.
 */

'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  // Match plain `function name(` or arrow assigned as `const name =`
  const sig = `function ${name}(`;
  const start = html.indexOf(sig);
  assert(start >= 0, `${name} source missing in Symbiose_Dashboard.html`);
  const brace = html.indexOf('{', start);
  let depth = 0;
  for (let i = brace; i < html.length; i++) {
    if (html[i] === '{') depth++;
    else if (html[i] === '}' && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error(`${name} source incomplete`);
}

function extractConst(name, source) {
  // Extracts: const NAME = (...
  const sig = `const ${name} = `;
  const start = source.indexOf(sig);
  assert(start >= 0, `const ${name} missing in Symbiose_Dashboard.html`);
  // Find the semicolon that terminates the declaration (after balanced parens/braces)
  let depth = 0, inStr = false, strChar = '', i = start;
  for (; i < source.length; i++) {
    const c = source[i];
    if (inStr) {
      if (c === '\\') { i++; continue; }
      if (c === strChar) inStr = false;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { inStr = true; strChar = c; continue; }
    if (c === '(' || c === '{' || c === '[') depth++;
    else if (c === ')' || c === '}' || c === ']') depth--;
    else if (c === ';' && depth === 0) return source.slice(start, i + 1);
  }
  throw new Error(`const ${name} not terminated`);
}

const sources = [
  extractConst('_cdnLogoBadSet', html),
  extractFunction('_coinBaseSymbol'),
  extractFunction('coinLogoUrl'),
  extractFunction('isCdnLogoKnownBad'),
  extractFunction('markCdnLogoBad'),
  extractFunction('coinLogoInitials'),
].join('\n');

const sandbox = { Map, Set, String, encodeURIComponent,
  // Minimal localStorage stub for the _cdnLogoBadSet IIFE
  localStorage: (() => {
    const store = {};
    return {
      getItem: k => store[k] ?? null,
      setItem: (k, v) => { store[k] = v; },
    };
  })(),
};
vm.createContext(sandbox);
vm.runInContext(`
${sources}
this.coinLogoUrl       = coinLogoUrl;
this.isCdnLogoKnownBad = isCdnLogoKnownBad;
this.markCdnLogoBad    = markCdnLogoBad;
this.coinLogoInitials  = coinLogoInitials;
`, sandbox);

const {
  coinLogoUrl, isCdnLogoKnownBad, markCdnLogoBad, coinLogoInitials
} = sandbox;

let passed = 0, failed = 0;
function ok(desc, cond) {
  if (cond) { console.log(`  PASS  ${desc}`); passed++; }
  else       { console.error(`  FAIL  ${desc}`); failed++; }
}
function eq(desc, a, b) {
  if (a === b) { console.log(`  PASS  ${desc}`); passed++; }
  else { console.error(`  FAIL  ${desc}: got ${JSON.stringify(a)}, expected ${JSON.stringify(b)}`); failed++; }
}

console.log('\nPF-34 CDN Asset Logo helpers');

// 1
eq('coinLogoUrl("BTCUSDT") → jsdelivr btc.svg',
  coinLogoUrl('BTCUSDT'),
  'https://cdn.jsdelivr.net/npm/cryptocurrency-icons@latest/svg/color/btc.svg');

// 2
eq('coinLogoUrl("ETHUSDT") strips USDT',
  coinLogoUrl('ETHUSDT'),
  'https://cdn.jsdelivr.net/npm/cryptocurrency-icons@latest/svg/color/eth.svg');

// 3
eq('coinLogoUrl("SOLPERP") strips PERP',
  coinLogoUrl('SOLPERP'),
  'https://cdn.jsdelivr.net/npm/cryptocurrency-icons@latest/svg/color/sol.svg');

// 4
ok('isCdnLogoKnownBad("XRPUSDT") false initially',
  isCdnLogoKnownBad('XRPUSDT') === false);

// 5+6
markCdnLogoBad('XRPUSDT');
ok('isCdnLogoKnownBad("XRPUSDT") true after mark',
  isCdnLogoKnownBad('XRPUSDT') === true);

// 7
markCdnLogoBad('XRPUSDT');
ok('isCdnLogoKnownBad("XRPUSDT") still true (idempotent)',
  isCdnLogoKnownBad('XRPUSDT') === true);

// 8 — other symbol unaffected
ok('isCdnLogoKnownBad("BNBUSDT") still false',
  isCdnLogoKnownBad('BNBUSDT') === false);

// 8b — USDT suffix normalised when caching
markCdnLogoBad('DOTUSDT');
ok('isCdnLogoKnownBad("DOTUSDT") true after mark with USDT suffix',
  isCdnLogoKnownBad('DOTUSDT') === true);

// 9
eq('coinLogoInitials("BTCUSDT") → "BTC"',
  coinLogoInitials('BTCUSDT'), 'BTC');

// 10
eq('coinLogoInitials("LINKUSDT") capped at 3 chars → "LIN"',
  coinLogoInitials('LINKUSDT'), 'LIN');

// 11
eq('coinLogoUrl("LINKUSDT") lowercases base',
  coinLogoUrl('LINKUSDT'),
  'https://cdn.jsdelivr.net/npm/cryptocurrency-icons@latest/svg/color/link.svg');

console.log('\n' + '═'.repeat(60));
console.log(`ERGEBNIS:  ${passed} PASSED  |  ${failed} FAILED  |  ${passed + failed} TOTAL`);
console.log('═'.repeat(60));
if (failed > 0) process.exit(1);
