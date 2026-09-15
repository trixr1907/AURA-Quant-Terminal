#!/usr/bin/env node
'use strict';

const fs = require('fs');
const assert = require('assert');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

// Gen-2 token catalogue
for (const token of [
  '--color-base', '--color-surface', '--color-accent', '--color-success',
  '--color-warning', '--color-danger', '--font-sans', '--font-mono',
  '--space-1', '--space-6', '--radius-sm', '--radius-lg', '--shadow-sm',
  '--z-drawer', '--breakpoint-mobile', '--touch-target',
]) {
  assert(html.includes(token), `missing design token ${token}`);
}

assert(/:root\s*\{/.test(html), 'missing :root token scope');
assert(/@media\(max-width:420px\)/.test(html), 'missing 420px mobile breakpoint');
assert(/@media\(prefers-reduced-motion:reduce\)/.test(html), 'missing reduced-motion rule');
assert(/:focus-visible/.test(html), 'missing focus-visible rule');

// Self-contained contract: no external styles, scripts, fonts, or CSS image URLs.
assert(!/<(?:script|img|link)[^>]+(?:src|href)=["']https?:\/\//i.test(html), 'external HTML resource found');
assert(!/url\(\s*["']?https?:\/\//i.test(html), 'external CSS resource found');

// Core panel structure must remain available.
for (const id of ['hero', 'autobot-section', 'trade-portfolio-kpis', 'radarcard']) {
  assert(new RegExp(`id=["']${id}["']`).test(html), `missing core panel #${id}`);
}

console.log('Design system Gen-2 static checks passed');
