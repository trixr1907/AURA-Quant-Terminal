'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name, endMarker) {
  const start = html.indexOf(`function ${name}(`);
  assert(start >= 0, `${name} source missing`);
  const end = html.indexOf(endMarker, start);
  assert(end > start, `${name} source incomplete`);
  return html.slice(start, end);
}

const cardSource = extractFunction('renderTradeCard', '\nfunction renderLiveTrades(');
const sandbox = {
  esc: value => String(value).replace(/[<>&"']/g, char => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&#39;' }[char])),
  fmtPx: value => Number(value).toFixed(2),
};
vm.createContext(sandbox);
vm.runInContext(`${cardSource}\nthis.renderTradeCard = renderTradeCard;`, sandbox);

const trade = {
  coin: '<BTCUSDT>',
  dir: 1,
  leverage: 5,
  entry: 100,
  currentSl: 95,
  initialSl: 95,
  tp: 110,
  margin: 100,
  remainingMargin: 100,
  signalTf: '1h',
  openedAt: Date.now() - 60000,
};
const metrics = {
  pnlGross: 10,
  marginRoiPct: 10,
  currentR: 1,
  priceDiffPct: 1,
  distSlPct: 5,
  distTpPct: 9,
  plannedRr: 2,
  mfePriceDiff: 2,
  mfeR: 1,
  maePriceDiff: 1,
  maeR: -0.5,
  initialRiskAmount: 50,
  quantity: 5,
};

const manual = sandbox.renderTradeCard(trade, metrics, 101, 3);
assert(manual.includes('data-close-trade="3"'), 'manual card keeps close action');
assert(manual.includes('data-action-tp25="3"'), 'manual card keeps partial TP action');
assert(manual.includes('data-action-trail="3"'), 'manual card keeps trail action');
assert(manual.includes('data-copy-trade="3"'), 'manual card keeps setup copy action');
assert(manual.includes('data-switch-coin="&lt;BTCUSDT&gt;"'), 'manual card escapes asset-focus input');
assert(manual.includes('data-tv-overlay="3"'), 'manual card keeps TV action');
assert(!manual.includes('Score '), 'manual card must not render Autobot score');
assert(!manual.includes('Bot Management:'), 'manual card must not render bot management');
assert(!manual.includes('Time-Stop'), 'manual card must not render Autobot time stop');

const autobot = sandbox.renderTradeCard(trade, metrics, 101, 4, {
  autobot: true,
  score: 82,
  setupDsr: 0.71,
  timeStopDisplay: '12 Bars',
  botManagement: 'Auto-BE aktiv',
});
assert(autobot.includes('Score 82'), 'Autobot card renders score');
assert(autobot.includes('DSR 0.71'), 'Autobot card renders setup DSR');
assert(autobot.includes('Time-Stop'), 'Autobot card renders time stop');
assert(autobot.includes('Bot Management:'), 'Autobot card renders management details');
assert(autobot.includes('data-close-ab-idx="4"'), 'Autobot card keeps close action');
assert(autobot.includes('data-copy-ab-idx="4"'), 'Autobot card keeps setup copy action');
assert(autobot.includes('data-tv-ab-idx="4"'), 'Autobot card keeps TV action');
assert.strictEqual((autobot.match(/Score 82/g) || []).length, 1, 'Autobot score appears exactly once');
assert.strictEqual((autobot.match(/Time-Stop/g) || []).length, 1, 'Autobot time stop appears exactly once');
assert.strictEqual((autobot.match(/Bot Management:/g) || []).length, 1, 'Autobot management appears exactly once');
assert.strictEqual((autobot.match(/tc-autobot-extras/g) || []).length, 1, 'Autobot uses exactly one extras section');

assert(!/options\.content/.test(cardSource), 'renderTradeCard must not accept HTML passthrough content');
assert(cardSource.includes('tc-grid'), 'renderTradeCard exclusively owns the common card grid');
assert(cardSource.includes('tc-actions'), 'renderTradeCard exclusively owns the common action shell');
assert.strictEqual((cardSource.match(/<div class="trade-card"/g) || []).length, 1, 'renderTradeCard has exactly one shared outer trade-card shell');

const liveSource = extractFunction('renderLiveTrades', '\nfunction bindTradeTracker(');
assert(liveSource.includes('renderTradeCard'), 'Live render path must call renderTradeCard');
assert(!/tradeCardRenderer/.test(liveSource), 'Live render path must not retain a renderer fallback');
assert(!/content\s*:|<div class="trade-card"/.test(liveSource), 'Live caller passes a view model rather than card HTML');

const autobotStart = html.indexOf('const Autobot = {');
const autobotRenderStart = html.indexOf('\n  render()', autobotStart);
const autobotRenderEnd = html.indexOf('\n  renderLogs()', autobotRenderStart);
assert(autobotRenderStart >= 0 && autobotRenderEnd > autobotRenderStart, 'Autobot.render source missing');
const autobotRenderSource = html.slice(autobotRenderStart, autobotRenderEnd);
assert(autobotRenderSource.includes('renderTradeCard('), 'Autobot render path must call renderTradeCard');
assert(!/content\s*:|<div class="trade-card"/.test(autobotRenderSource), 'Autobot caller passes a view model rather than card HTML');

console.log('PASS PF-29 shared trade card');
