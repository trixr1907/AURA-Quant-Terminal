'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  const marker = `function ${name}`;
  const start = html.indexOf(marker);
  assert(start >= 0, `${name} not found`);
  const openParen = html.indexOf('(', start);
  let parenDepth = 0;
  let brace = -1;
  for (let i = openParen; i < html.length; i += 1) {
    if (html[i] === '(') parenDepth += 1;
    else if (html[i] === ')') parenDepth -= 1;
    else if (html[i] === '{' && parenDepth === 0) { brace = i; break; }
  }
  assert(brace >= 0, `${name} body not found`);
  let depth = 0;
  for (let i = brace; i < html.length; i += 1) {
    if (html[i] === '{') depth += 1;
    else if (html[i] === '}') {
      depth -= 1;
      if (depth === 0) return html.slice(start, i + 1);
    }
  }
  throw new Error(`${name} end not found`);
}

class Element {
  constructor() {
    this.textContent = '';
    this.title = '';
    this.style = {};
    this.innerHTML = '';
  }
}

function render(strictUniverseGate) {
  const elements = Object.fromEntries([
    'bt-ts', 'bt-tag', 'bt-bars', 'bt-n', 'bt-wr', 'bt-avg', 'bt-pf', 'bt-exp', 'bt-dsr', 'bt-dd', 'bt-folds',
  ].map(id => [id, new Element()]));
  const wf = {
    evidenceStatus: 'OOS',
    method: 'anchored_t1',
    stats: { total: 12, wr: 0.6, grossR: 2, pf: 1.4, exp: 0.2, maxDd: 1 },
    setupDsr: { dsr: 0.2, sharpe: 0.4 },
    universeDsr: { dsr: 0.4, sharpe: 0.4 },
    dsr: { dsr: 0.4, sharpe: 0.4 },
    folds: [],
  };
  const context = {
    App: { symbol: 'BTCUSDT', chartTF: '1h', timeStopBars: 12, data: { chart: { n: 500 }, wf, bt: [] } },
    Autobot: { strictUniverseGate, minSetupDsr: 0.1 },
    RenderCache: { isDirty: () => true },
    $: id => elements[id],
    btStats: () => wf.stats,
    document: { querySelector: () => new Element() },
    fmtDate: () => '',
    fmtP: value => String(value),
    console,
  };
  vm.createContext(context);
  vm.runInContext(`${extractFunction('renderBacktest')}\nthis.renderBacktest=renderBacktest;`, context);
  context.renderBacktest(true);
  return elements['bt-dsr'];
}

const setup = render(false);
assert.strictEqual(setup.textContent, 'Setup-DSR 20.0% (SR 0.40)');
assert.strictEqual(setup.style.color, 'var(--amb)', 'standard mode must color the accepted Setup-DSR');
assert(setup.title.includes('(0.10)'), 'standard tooltip must show the operative profile gate');

const strict = render(true);
assert.strictEqual(strict.textContent, 'Uni-DSR 40.0% (SR 0.40)');
assert.strictEqual(strict.style.color, 'var(--red2)', 'strict mode must reject/color Uni-DSR below 0.50');
assert(strict.title.includes('(0.50)'), 'strict tooltip must show the strict 0.50 gate');

console.log('PASS DSR panel follows the operative Setup/Universe gate');
