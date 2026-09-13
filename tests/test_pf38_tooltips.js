'use strict';

// PF-38 Tooltips: Regime-Detail & Hero-Level tile explanations
// Verifies tooltip elements, plain-German texts, and accessibility attributes.

const assert = require('assert');
const fs = require('fs');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

// ── 1. Macro BTC Cell Tooltip & Accessibility
assert(
  html.includes('id="macro-btc-cell" tabindex="0"'),
  'FAIL PF-38: macro-btc-cell must have tabindex="0" for keyboard accessibility'
);
assert(
  html.includes('aria-describedby="macro-btc-tooltip"'),
  'FAIL PF-38: macro-btc-cell must reference macro-btc-tooltip via aria-describedby'
);
assert(
  html.includes('id="macro-btc-tooltip"'),
  'FAIL PF-38: macro-btc-tooltip element must exist'
);

// Verify explanation quality in macro-btc-cell title/tooltip
const btcCellSection = html.slice(
  html.indexOf('id="macro-btc-cell"'),
  html.indexOf('</div>', html.indexOf('class="btc-bias-wrap"'))
);
assert(
  btcCellSection.includes('BULL') && btcCellSection.includes('BEAR') && btcCellSection.includes('SIDEWAYS'),
  'FAIL PF-38: macro-btc tooltip must explain BULL, BEAR, and SIDEWAYS states'
);
assert(
  btcCellSection.includes('EMA200') && btcCellSection.includes('ADX'),
  'FAIL PF-38: macro-btc tooltip must explain EMA200 threshold and ADX'
);

// ── 2. Hero-Level Tiles (Entry, SL, TP1, TP2) Tooltips & Short Labels
const heroLevelsStart = html.indexOf('id="hero-levels"');
const heroLevelsEnd = html.indexOf('</div>', html.indexOf('id="hero-tp2"'));
const heroLevelsSection = html.slice(heroLevelsStart, heroLevelsEnd + 20);

// Entry Tile
assert(
  heroLevelsSection.includes('class="hero-lvl entry" title='),
  'FAIL PF-38: hero-lvl entry tile must have title tooltip attribute'
);
assert(
  heroLevelsSection.includes('Einstieg') || heroLevelsSection.includes('Einstiegskurs'),
  'FAIL PF-38: hero-lvl entry tile must explain Einstieg/Einstiegskurs'
);

// Stop-Loss Tile
assert(
  heroLevelsSection.includes('class="hero-lvl sl" title='),
  'FAIL PF-38: hero-lvl sl tile must have title tooltip attribute'
);
assert(
  heroLevelsSection.includes('Notbremse') || heroLevelsSection.includes('Verlustgrenze'),
  'FAIL PF-38: hero-lvl sl tile must explain Stop-Loss as Notbremse/Verlustgrenze'
);

// TP1 Tile
assert(
  heroLevelsSection.includes('Teilgewinn') || heroLevelsSection.includes('Teilgewinn-Ziel 1'),
  'FAIL PF-38: hero-lvl tp1 tile must explain Take-Profit 1 as Teilgewinn'
);

// TP2 Tile
assert(
  heroLevelsSection.includes('Hauptziel') || heroLevelsSection.includes('Teilgewinn-Ziel 2') || heroLevelsSection.includes('Moonbag'),
  'FAIL PF-38: hero-lvl tp2 tile must explain Take-Profit 2'
);

// ── 3. Info-tip badges inside hero levels for click/touch accessibility
assert(
  (heroLevelsSection.match(/class="info-tip"/g) || []).length >= 4,
  'FAIL PF-38: all 4 hero level tiles must contain an info-tip touch/click icon'
);

console.log('PASS PF-38 Tooltips: Regime-Detail and Hero-Level explanations verified with a11y attributes');
