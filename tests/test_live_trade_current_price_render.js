'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  const plain = html.indexOf(`function ${name}(`);
  const asyncStart = html.indexOf(`async function ${name}(`);
  const start = asyncStart >= 0 && (plain < 0 || asyncStart < plain) ? asyncStart : plain;
  assert(start >= 0, `${name} source missing`);
  const brace = html.indexOf('{', start);
  let depth = 0;
  for (let i = brace; i < html.length; i++) {
    if (html[i] === '{') depth++;
    else if (html[i] === '}' && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error(`${name} source incomplete`);
}

const container = { innerHTML: '', querySelectorAll: () => [] };
const elementMap = {
  'trade-list': container,
  'pkpi-open': { textContent: '' },
  'pkpi-margin': { textContent: '' },
  'pkpi-notional': { textContent: '' },
  'pkpi-pnl': { textContent: '', style: {} },
  'pkpi-roi': { textContent: '', style: {} },
  'pkpi-risk': { textContent: '' },
  'paper-trade-summary-tag': { textContent: '', className: '' },
};

const trades = [
  {
    id: 'pt_sol',
    coin: 'SOLUSDT',
    dir: 1,
    entry: 100,
    margin: 100,
    remainingMargin: 100,
    leverage: 10,
    initialSl: 95,
    currentSl: 95,
    tp: 110,
    openedAt: Date.now() - 60000,
    markPrice: 100,
    markUpdatedAt: Date.now() - 45000, // > 30s stale
  },
];

const prices = { SOLUSDT: 108 };
const context = {
  Date,
  Math,
  Number,
  Array,
  App: { symbol: 'BTCUSDT', data: { btcScore: 60, btcRegime: 1 } },
  tradePrices: prices,
  loadTrades: () => trades,
  calculateTradeMetrics(t, px) {
    const notional = (t.remainingMargin || t.margin) * t.leverage;
    const diff = px - t.entry;
    const pnlGross = (notional / t.entry) * t.dir * diff;
    const priceDiffPct = ((px - t.entry) / t.entry) * 100;
    return {
      notional,
      pnlGross,
      marginRoiPct: (pnlGross / (t.remainingMargin || t.margin)) * 100,
      currentR: 1.6,
      priceDiffPct,
      distSlPct: 5,
      distTpPct: 2,
      plannedRr: 2,
      mfePriceDiff: 8,
      mfeR: 1.6,
      maePriceDiff: 0,
      maeR: 0,
      initialRiskAmount: 50,
      quantity: 10,
    };
  },
  clamp: (v, min, max) => Math.min(max, Math.max(min, v)),
  esc: s => s,
  fmtDuration: () => '1m',
  computeBtcBias: () => ({ available: false }),
  getCurrentSessionInfo: () => null,
  renderTradeHistory: () => {},
  $: id => elementMap[id] || null,
};
vm.createContext(context);
vm.runInContext([
  extractFunction('fmtPx'),
  extractFunction('renderLiveTrades'),
  'this.renderLiveTrades = renderLiveTrades;',
].join('\n'), context);

context.renderLiveTrades();
const htmlOutput = container.innerHTML;
assert(htmlOutput.includes('SOLUSDT'), 'trade card must render coin');
assert(htmlOutput.includes('Aktuell'), 'dedicated Aktuell price header required in trade row');
assert(htmlOutput.includes('108.00'), 'updated price of non-selected symbol must render');
assert(htmlOutput.includes('+8.00%'), 'color-coded delta % must render');
assert(htmlOutput.includes('stale-price-dot') || htmlOutput.includes('data-price-stale="true"') || htmlOutput.includes('title="Daten älter als 30s"'), 'price older than 30s must be visually flagged');

console.log('PASS trade row current price, delta %, and age indicator');
