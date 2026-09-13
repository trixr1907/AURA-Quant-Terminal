'use strict';
/**
 * test_pf35_logo_animation.js — PF-35 logo animation with reduced-motion
 *
 * Tests (pure CSS text analysis — no browser needed):
 *  1. A @keyframes rule for the AURA logo animation exists in the HTML.
 *  2. The animation uses only transform and/or opacity (no layout properties).
 *  3. .logo .mark (or equivalent selector) has an animation property applied.
 *  4. The existing prefers-reduced-motion block disables animations (* or .logo .mark).
 *  5. The existing prefers-reduced-motion block does NOT use layout-only CSS.
 *  6. No width/height/margin/padding/top/left/right/bottom in @keyframes body.
 *  7. The animation name used in .logo .mark matches a defined @keyframes name.
 *  8. The prefers-reduced-motion block sets animation to none (or animation-name: none).
 */

'use strict';

const assert = require('assert');
const fs = require('fs');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

// Extract the <style> block (first one — the main CSS)
const styleStart = html.indexOf('<style>');
const styleEnd   = html.indexOf('</style>', styleStart);
assert(styleStart >= 0 && styleEnd >= 0, '<style> block missing');
const css = html.slice(styleStart + 7, styleEnd);

let passed = 0, failed = 0;
function ok(desc, cond) {
  if (cond) { console.log(`  PASS  ${desc}`); passed++; }
  else       { console.error(`  FAIL  ${desc}`); failed++; }
}

console.log('\nPF-35 Logo Animation + prefers-reduced-motion');

// 1. @keyframes for logo animation exists
const keyframesMatches = [...css.matchAll(/@keyframes\s+([\w-]+)\s*\{/g)];
const keyframeNames = keyframesMatches.map(m => m[1]);
// find a keyframes that's NOT toastFade (which already existed)
const logoKeyframes = keyframeNames.filter(n => n !== 'toastFade');
ok('A non-toast @keyframes rule exists (logo animation)',
  logoKeyframes.length >= 1);

// 2. @keyframes body uses only transform/opacity (no layout props)
const LAYOUT_PROPS = /\b(width|height|margin|padding|top|left|right|bottom|font-size|line-height)\b/;
for (const name of logoKeyframes) {
  // Extract the keyframes body
  const kfIdx = css.indexOf(`@keyframes ${name}`);
  if (kfIdx < 0) continue;
  const brace = css.indexOf('{', kfIdx);
  let depth = 0, end = brace;
  for (let i = brace; i < css.length; i++) {
    if (css[i] === '{') depth++;
    else if (css[i] === '}' && --depth === 0) { end = i; break; }
  }
  const body = css.slice(brace, end + 1);
  ok(`@keyframes ${name} does not animate layout properties`, !LAYOUT_PROPS.test(body));
}

// 3. .logo .mark (or .mark) has 'animation' applied
const markBlock = (() => {
  // Find the .logo .mark rule block (collapsed single-line CSS)
  const idx = css.indexOf('.logo .mark{');
  if (idx < 0) return '';
  const end = css.indexOf('}', idx);
  return css.slice(idx, end + 1);
})();
ok('.logo .mark rule exists', markBlock.length > 0);
ok('.logo .mark has animation property', /animation/.test(markBlock));

// 4. prefers-reduced-motion block disables animations
const reducedMotionBlock = (() => {
  const idx = css.indexOf('@media(prefers-reduced-motion:reduce)');
  if (idx < 0) return '';
  const brace = css.indexOf('{', idx);
  let depth = 0, end = brace;
  for (let i = brace; i < css.length; i++) {
    if (css[i] === '{') depth++;
    else if (css[i] === '}' && --depth === 0) { end = i; break; }
  }
  return css.slice(brace, end + 1);
})();
ok('@media(prefers-reduced-motion:reduce) block exists', reducedMotionBlock.length > 0);
ok('reduced-motion block disables animations',
  /animation\s*:\s*none/.test(reducedMotionBlock) ||
  /animation-name\s*:\s*none/.test(reducedMotionBlock) ||
  /animation\s*:\s*none!important/.test(reducedMotionBlock));

// 5. No layout-only props in reduced-motion block (should only be behavioural)
ok('reduced-motion block does not set layout-only properties',
  !LAYOUT_PROPS.test(reducedMotionBlock.replace(/transition/g, '')));

// 6. Sanity: no layout props in any logoKeyframe (repeat check explicit)
for (const name of logoKeyframes) {
  const kfIdx = css.indexOf(`@keyframes ${name}`);
  const brace = css.indexOf('{', kfIdx);
  let depth = 0, end = brace;
  for (let i = brace; i < css.length; i++) {
    if (css[i] === '{') depth++;
    else if (css[i] === '}' && --depth === 0) { end = i; break; }
  }
  const body = css.slice(brace, end + 1);
  ok(`@keyframes ${name}: no width/height/margin/padding/top/left in body`,
    !/\b(width|height|margin|padding|top|left|right|bottom)\b/.test(body));
}

// 7. Animation name in .logo .mark matches a defined @keyframes
const animNameMatch = markBlock.match(/animation(?:-name)?\s*:\s*([\w-]+)/);
if (animNameMatch) {
  const usedName = animNameMatch[1];
  ok(`Animation name "${usedName}" matches a defined @keyframes`,
    keyframeNames.includes(usedName));
} else {
  ok('animation shorthand references a known keyframes name', false);
}

// 8. Reduced-motion block explicitly covers animation (not just transition)
ok('reduced-motion block contains animation rule',
  /animation/.test(reducedMotionBlock));

console.log('\n' + '═'.repeat(60));
console.log(`ERGEBNIS:  ${passed} PASSED  |  ${failed} FAILED  |  ${passed + failed} TOTAL`);
console.log('═'.repeat(60));
if (failed > 0) process.exit(1);
