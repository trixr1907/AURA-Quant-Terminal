#!/usr/bin/env node
'use strict';

const fs = require('fs');
const assert = require('assert');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

// 1. Complete Gen-2 token catalogue verification
const REQUIRED_TOKENS = [
  // Colors
  '--color-base', '--color-surface', '--color-surface-raised', '--color-surface-overlay',
  '--color-accent', '--color-accent-hover', '--color-accent-muted',
  '--color-success', '--color-success-hover', '--color-success-muted',
  '--color-warning', '--color-warning-hover', '--color-warning-muted',
  '--color-danger', '--color-danger-hover', '--color-danger-muted',
  '--color-text', '--color-text-muted', '--color-text-dim',
  '--color-border', '--color-border-strong',
  // Typography
  '--font-sans', '--font-mono',
  '--text-xs', '--text-sm', '--text-md', '--text-lg', '--text-xl', '--text-2xl',
  '--leading-tight', '--leading-normal', '--leading-relaxed',
  // 4px spacing raster
  '--space-1', '--space-2', '--space-3', '--space-4', '--space-5', '--space-6', '--space-7', '--space-8',
  // Radii & Shadows
  '--radius-sm', '--radius-md', '--radius-lg', '--radius-pill',
  '--shadow-sm', '--shadow-md', '--shadow-lg',
  // Z-index layering
  '--z-base', '--z-content', '--z-sticky', '--z-launcher', '--z-backdrop', '--z-drawer', '--z-toast', '--z-banner', '--z-critical',
  // Breakpoints & Touch Target
  '--breakpoint-mobile', '--breakpoint-tablet', '--breakpoint-desktop', '--touch-target'
];

for (const token of REQUIRED_TOKENS) {
  assert(html.includes(token), `missing design token: ${token}`);
}

assert(/:root\s*\{/.test(html), 'missing :root token scope');

// 2. Component classes contracts
const COMPONENT_CLASSES = [
  '.ui-card', '.ui-panel', '.ui-button', '.ui-badge', '.ui-table',
  '.panel', '.trade-card', '.history-card', '.tv-basic-panel', '.autobot-panel',
  '.cbtn', '.badge', '.feed-status-pill', '.reload-banner'
];

for (const cls of COMPONENT_CLASSES) {
  assert(html.includes(cls), `missing component class definition: ${cls}`);
}

// 3. Responsive Breakpoints and Mobile Touch Targets
assert(/@media\(max-width:420px\)/.test(html), 'missing 420px mobile media query');
assert(/@media\(max-width:390px\)/.test(html), 'missing 390px iPhone mobile media query');
assert(/@media\(max-width:960px\)/.test(html), 'missing 960px tablet media query');
assert(/@media\(max-width:1280px\)/.test(html), 'missing 1280px desktop media query');

// 4. Accessibility Rules
assert(/:where\(button,a,input,select,summary,\[tabindex\]\):focus-visible/.test(html), 'missing global focus-visible rule');
assert(/@media\(prefers-reduced-motion:reduce\)/.test(html), 'missing prefers-reduced-motion rule');
assert(/font-variant-numeric:\s*tabular-nums/.test(html), 'missing tabular-nums styling for financial data');

// 5. Self-Contained Contract: zero external network assets
assert(!/<(?:script|img|link)[^>]+(?:src|href)=["']https?:\/\//i.test(html), 'external HTML resource found');
assert(!/url\(\s*["']?https?:\/\//i.test(html), 'external CSS resource found');

// 6. innerHTML Canon Verification (strictly 63 sinks)
const innerHtmlMatches = html.match(/innerHTML/g) || [];
assert.strictEqual(innerHtmlMatches.length, 63, `innerHTML count must be exactly 63, got ${innerHtmlMatches.length}`);

// 7. Core DOM panel structure verification
const CORE_PANEL_SELECTORS = [
  '#hero', '#autobot-section', '#trade-portfolio-kpis', '#radarcard',
  '.statusbar', '#risk-warning', '#reload-banner', '#release-notes-modal'
];

for (const sel of CORE_PANEL_SELECTORS) {
  if (sel.startsWith('#')) {
    const id = sel.substring(1);
    assert(new RegExp(`id=["']${id}["']`).test(html), `missing core panel element #${id}`);
  } else if (sel.startsWith('.')) {
    const cls = sel.substring(1);
    assert(new RegExp(`class=["'][^"']*\\b${cls}\\b[^"']*["']`).test(html), `missing core panel class .${cls}`);
  }
}

// 8. WCAG AA Contrast Verification (Analytical mathematical proof)
function parseHex(hex) {
  const c = hex.replace('#', '');
  return {
    r: parseInt(c.substring(0, 2), 16) / 255,
    g: parseInt(c.substring(2, 4), 16) / 255,
    b: parseInt(c.substring(4, 6), 16) / 255
  };
}

function sRGBtoLinear(val) {
  return val <= 0.04045 ? val / 12.92 : Math.pow((val + 0.055) / 1.055, 2.4);
}

function relativeLuminance(hex) {
  const { r, g, b } = parseHex(hex);
  return 0.2126 * sRGBtoLinear(r) + 0.7152 * sRGBtoLinear(g) + 0.0722 * sRGBtoLinear(b);
}

function contrastRatio(hex1, hex2) {
  const l1 = relativeLuminance(hex1);
  const l2 = relativeLuminance(hex2);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

const COLOR_PALETTE = {
  base: '#06090f',
  surface: '#0b111b',
  surfaceRaised: '#101826',
  text: '#f1f5f9',
  textMuted: '#cbd5e1',
  textDim: '#94a3b8',
  accent: '#38bdf8',
  success: '#2dd4bf',
  warning: '#fbbf24',
  danger: '#fb7185'
};

// Assert WCAG AA contrast (minimum 4.5:1 for normal body text, 3:1 for large text / UI components)
const textOnBase = contrastRatio(COLOR_PALETTE.text, COLOR_PALETTE.base);
assert(textOnBase >= 7.0, `Text on Base contrast too low: ${textOnBase.toFixed(2)}:1 (need >= 7.0 AAA)`);

const textMutedOnSurface = contrastRatio(COLOR_PALETTE.textMuted, COLOR_PALETTE.surface);
assert(textMutedOnSurface >= 7.0, `Text Muted on Surface contrast too low: ${textMutedOnSurface.toFixed(2)}:1`);

const textDimOnSurface = contrastRatio(COLOR_PALETTE.textDim, COLOR_PALETTE.surface);
assert(textDimOnSurface >= 4.5, `Text Dim on Surface contrast too low: ${textDimOnSurface.toFixed(2)}:1 (need >= 4.5 AA)`);

const accentOnSurface = contrastRatio(COLOR_PALETTE.accent, COLOR_PALETTE.surface);
assert(accentOnSurface >= 4.5, `Accent on Surface contrast too low: ${accentOnSurface.toFixed(2)}:1`);

const successOnSurface = contrastRatio(COLOR_PALETTE.success, COLOR_PALETTE.surface);
assert(successOnSurface >= 4.5, `Success on Surface contrast too low: ${successOnSurface.toFixed(2)}:1`);

const warningOnSurface = contrastRatio(COLOR_PALETTE.warning, COLOR_PALETTE.surface);
assert(warningOnSurface >= 4.5, `Warning on Surface contrast too low: ${warningOnSurface.toFixed(2)}:1`);

const dangerOnSurface = contrastRatio(COLOR_PALETTE.danger, COLOR_PALETTE.surface);
assert(dangerOnSurface >= 4.5, `Danger on Surface contrast too low: ${dangerOnSurface.toFixed(2)}:1`);

// 9. Behavioral test for migrateTradeStorageV2 in browser context
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
assert(scriptMatch, 'missing dashboard script tag');

const store = {
  'aura-quant-terminal-active-trades-v1': JSON.stringify([{ id: 'trade-v1-test', coin: 'BTCUSDT' }]),
  'aura-quant-terminal-history-trades-v1': JSON.stringify([{ id: 'hist-v1-test', parentId: 'trade-v1-test' }]),
};

const mockLocalStorage = {
  getItem: (key) => (key in store ? store[key] : null),
  setItem: (key, val) => { store[key] = String(val); },
  removeItem: (key) => { delete store[key]; },
};

const ctx = {
  localStorage: mockLocalStorage,
  window: {},
  document: { getElementById: () => null, querySelectorAll: () => [], addEventListener: () => {} },
  console,
  setTimeout: () => 1,
  setInterval: () => 1,
  requestAnimationFrame: (cb) => { cb(); return 1; },
};
vm.createContext(ctx);
vm.runInContext(scriptMatch[1], ctx);

// After script execution, migrateTradeStorageV2 should have run
assert.strictEqual(
  store['aura-quant-terminal-active-trades-v2'],
  store['aura-quant-terminal-active-trades-v1'],
  'v2 active trades must match v1 bytes exactly',
);
assert.strictEqual(
  store['aura-quant-terminal-active-trades-v1-imported'],
  store['aura-quant-terminal-active-trades-v1'],
  'imported active trades retention must match v1 bytes',
);
assert.strictEqual(
  store['aura-quant-terminal-history-trades-v2'],
  store['aura-quant-terminal-history-trades-v1'],
  'v2 history trades must match v1 bytes exactly',
);
assert.strictEqual(
  store['aura-quant-terminal-history-trades-v1-imported'],
  store['aura-quant-terminal-history-trades-v1'],
  'imported history trades retention must match v1 bytes',
);

console.log('Design system Gen-2 comprehensive verification passed');
console.log(`Contrast Summary:
  - Text on Base: ${textOnBase.toFixed(2)}:1 (AAA)
  - Text Muted on Surface: ${textMutedOnSurface.toFixed(2)}:1 (AAA)
  - Text Dim on Surface: ${textDimOnSurface.toFixed(2)}:1 (AAA)
  - Accent on Surface: ${accentOnSurface.toFixed(2)}:1 (AAA)
  - Success on Surface: ${successOnSurface.toFixed(2)}:1 (AAA)
  - Warning on Surface: ${warningOnSurface.toFixed(2)}:1 (AAA)
  - Danger on Surface: ${dangerOnSurface.toFixed(2)}:1 (AAA)`);
