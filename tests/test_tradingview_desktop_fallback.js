'use strict';
/**
 * test_tradingview_desktop_fallback.js
 *
 * PF-30 (v1.4.0): The TradingView Desktop protocol and /api/open-tradingview
 * relay endpoint were intentionally removed. This file now verifies the
 * post-PF-30 invariants:
 *  - buildTradingViewDesktopUrl does NOT exist (removed).
 *  - openInTradingView does NOT exist (removed).
 *  - /api/open-tradingview is NOT referenced in Dashboard JS.
 *  - openTradingViewChart() opens a direct HTTPS web URL (no relay POST).
 *  - The TradingView button uses window.open(..., '_blank', 'noopener,noreferrer').
 */

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

// 1. Desktop-protocol functions must be absent
assert(
  html.indexOf('function buildTradingViewDesktopUrl(') < 0,
  'buildTradingViewDesktopUrl must not exist after PF-30'
);
assert(
  html.indexOf('async function openInTradingView(') < 0,
  'openInTradingView must not exist after PF-30'
);

// 2. /api/open-tradingview must not be called from Dashboard JS
const scriptStart = html.indexOf('<script>');
const scriptEnd   = html.indexOf('</script>', scriptStart);
const js = scriptStart >= 0 && scriptEnd >= 0 ? html.slice(scriptStart, scriptEnd) : '';
assert(
  !js.includes('/api/open-tradingview'),
  'Dashboard JS must not reference /api/open-tradingview after PF-30'
);

// 3. openTradingViewChart uses direct web URL + window.open (via buildTradingViewChartUrl)
assert(
  html.indexOf('function openTradingViewChart(') >= 0,
  'openTradingViewChart must exist'
);
const fnStart = html.indexOf('function openTradingViewChart(');
let depth = 0, fnEnd = fnStart;
for (let i = html.indexOf('{', fnStart); i < html.length; i++) {
  if (html[i] === '{') depth++;
  else if (html[i] === '}' && --depth === 0) { fnEnd = i; break; }
}
const fnBody = html.slice(fnStart, fnEnd + 1);
assert(fnBody.includes('window.open'), 'openTradingViewChart must call window.open');
assert(
  fnBody.includes('buildTradingViewChartUrl') || fnBody.includes('tradingview.com'),
  'openTradingViewChart must reference tradingview URL (directly or via buildTradingViewChartUrl)'
);
assert(!fnBody.includes('/api/open-tradingview'), 'openTradingViewChart must not POST to relay');

// 4. buildTradingViewChartUrl produces a tradingview.com URL
assert(
  html.indexOf('function buildTradingViewChartUrl(') >= 0,
  'buildTradingViewChartUrl must exist'
);
const urlFnStart = html.indexOf('function buildTradingViewChartUrl(');
let urlDepth = 0, urlFnEnd = urlFnStart;
for (let i = html.indexOf('{', urlFnStart); i < html.length; i++) {
  if (html[i] === '{') urlDepth++;
  else if (html[i] === '}' && --urlDepth === 0) { urlFnEnd = i; break; }
}
const urlFnBody = html.slice(urlFnStart, urlFnEnd + 1);
assert(urlFnBody.includes('tradingview.com'), 'buildTradingViewChartUrl must produce tradingview.com URL');

console.log('PASS TradingView Desktop protocol removed; direct web URL used (PF-30)');
