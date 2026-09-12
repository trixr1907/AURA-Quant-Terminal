'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractObject(name) {
  const start = html.indexOf(`const ${name} = {`);
  assert(start >= 0, `${name} source missing`);
  const brace = html.indexOf('{', start);
  let depth = 0;
  for (let i = brace; i < html.length; i++) {
    if (html[i] === '{') depth++;
    else if (html[i] === '}' && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error(`${name} source incomplete`);
}

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

const elementMap = {
  'ab-status-badge': { textContent: '', className: '' },
  'btn-toggle-autobot': { textContent: '', className: '' },
  'cfg-disp-score': { textContent: '' },
  'cfg-disp-mtf': { textContent: '' },
  'cfg-disp-risk': { textContent: '' },
  'cfg-disp-lev': { textContent: '' },
  'cfg-disp-max': { textContent: '' },
  'ab-funnel-summary': { innerHTML: '', textContent: '', append() {}, appendChild() {} },
  'ab-equity': { textContent: '' },
  'ab-roi': { textContent: '', style: {} },
  'ab-pnl': { textContent: '', style: {} },
  'ab-wr': { textContent: '' },
  'ab-open-count': { textContent: '' },
  'ab-hist-count': { textContent: '' },
  'ab-live-log': { innerHTML: '', textContent: '' },
  'ab-active-trades': { innerHTML: '', querySelectorAll: () => [] },
};

const context = {
  Date,
  Math,
  Number,
  Array,
  localStorage: { getItem: () => null, setItem: () => {} },
  AUTOBOT_KEY: 'test_ab_key',
  tradePrices: {},
  calculateHistoryStats: () => ({ grossPnl: 0, realizedWinRatePct: 0 }),
  esc: s => String(s),
  fmtP: p => Number(p).toFixed(2),
  autobotRejectSummary: f => (f && f.rejected ? Object.entries(f.rejected).map(([k, v]) => `${k}:${v}`).join(', ') : ''),
  $: id => elementMap[id] || null,
};

vm.createContext(context);
vm.runInContext([
  extractFunction('calculateHistoryStats'),
  extractFunction('addAutobotReject'),
  extractObject('Autobot'),
  'this.Autobot = Autobot;',
].join('\n'), context);

context.Autobot.lastScanAt = Date.now() - 5000;
context.Autobot.lastScanFunnel = {
  scanned: 12,
  radarFiltered: 3,
  wfEvaluated: 1,
  selected: 0,
  rejected: { MODEL_NO_EVIDENCE: 3 },
};
context.Autobot.logs = [
  { time: '12:00:00', msg: 'Init Autobot' },
  { time: '12:00:05', msg: 'Scan: 3 Kandidaten geprueft, alle abgelehnt wg. MODEL_NO_EVIDENCE' },
];

context.Autobot.render();

const funnelHtml = elementMap['ab-funnel-summary'].innerHTML || elementMap['ab-funnel-summary'].textContent;
const logHtml = elementMap['ab-live-log'].innerHTML || elementMap['ab-live-log'].textContent;

assert(funnelHtml.includes('Letzter Scan: vor') || funnelHtml.includes('vor 5s'), 'funnel summary must display scan age');
assert(funnelHtml.includes('12') && funnelHtml.includes('3'), 'funnel summary must show checked and qualified candidate counts');
assert(funnelHtml.includes('MODEL_NO_EVIDENCE'), 'rejection reasons must be visible in funnel summary');
assert(logHtml.includes('MODEL_NO_EVIDENCE'), 'recent log entries must be rendered in ab-live-log');

console.log('PASS Autobot cycle status, funnel diagnostics, and event log render');
