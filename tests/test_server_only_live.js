'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const autobot = require('../headless_autobot.js');
const { loadFunctions } = require('./r38_vm_helpers');

const engine = loadFunctions(
  ['classifyRadarTf', 'evaluateAutobotEdge'],
  {
    Number,
    Math,
    isFinite,
    SYM: { longTh: 75, shortTh: 25 },
    clamp: (x, a, b) => Math.max(a, Math.min(b, x)),
    squeezeAt: () => false,
  },
);

async function main() {
  const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
  const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1] || '';
  const scanStart = script.indexOf('async scanAndExecuteOpportunities() {');
  const scanEnd = script.indexOf('\n  render() {', scanStart);
  assert(scanStart >= 0 && scanEnd > scanStart, 'dashboard Autobot scan source must be extractable');
  const scanSource = script.slice(scanStart, scanEnd);
  assert(scanSource.includes("App.serverBotActive === true"), 'browser scan must be disabled from /ready server state');
  assert(scanSource.includes('Server-Bot aktiv — Browser-Simulation inaktiv (Server-Only Live)'), 'disabled browser path must explain Server-Only Live');

  const tickStart = script.indexOf('async tick() {');
  const tickEnd = script.indexOf('\n  async updateActiveTrades()', tickStart);
  assert(tickStart >= 0 && tickEnd > tickStart, 'dashboard Autobot tick source must be extractable');
  const tickSource = script.slice(tickStart, tickEnd);
  assert(tickSource.includes("App.serverBotActive === true"), 'browser tick must early-return while server is active');
  assert(!tickSource.includes('await this.updateActiveTrades();'), 'server viewer must not manage or notify browser-owned trades');

  const readyStart = script.indexOf('async function fetchReadyFunnel()');
  const readyEnd = script.indexOf('\nlet _liveTradesRaf', readyStart);
  const readySource = script.slice(readyStart, readyEnd);
  assert(readySource.includes('App.serverBotActive ='), '/ready polling must update the dashboard server activity flag');

  const saveStart = script.indexOf('save() {', script.indexOf('const Autobot = {'));
  const saveEnd = script.indexOf('\n  log(msg)', saveStart);
  const saveSource = script.slice(saveStart, saveEnd);
  assert(!/\btrades\s*:/.test(saveSource), 'browser state save must not publish browser trades as server source data');
  assert(!/\bhistory\s*:/.test(saveSource), 'browser state save must not publish browser history as server source data');

  const bindStart = script.indexOf('bindUI() {', script.indexOf('const Autobot = {'));
  const bindEnd = script.indexOf('\n  async tick()', bindStart);
  const bindSource = script.slice(bindStart, bindEnd);
  const pushConfigStart = script.indexOf('pushServerConfig() {', script.indexOf('const Autobot = {'));
  const pushConfigEnd = script.indexOf('\n  log(msg)', pushConfigStart);
  const pushConfigSource = script.slice(pushConfigStart, pushConfigEnd);
  assert(pushConfigSource.includes("fetch('/api/bot-config'"), 'dashboard config save must use the dedicated server config endpoint');
  assert(pushConfigSource.includes('enabled: this.enabled'), 'server config toggle must be persisted to the server endpoint');
  assert(pushConfigSource.includes('initialEquity: this.initialEquity'), 'server config must include equity');
  assert(pushConfigSource.includes('minScore: this.minScore'), 'server config must include minScore for the next cycle');
  assert(bindSource.includes('this.pushServerConfig();'), 'config save and toggle must push the executable server config');

  const state = new autobot.ServerBotState();
  state.paused = true;
  state.pausedBy = 'browser';

  const result = await autobot.runScanCycle(engine, state, {
    getState: async () => ({
      _rev: 7,
      'aura-autobot-state-v2': { enabled: true, mode: 'browser' },
      'aura-server-bot-config-v1': { minScore: 77 },
    }),
    universe: [],
  });

  assert(result && typeof result === 'object', 'browser enabled state must not short-circuit the server cycle');
  assert.strictEqual(state.paused, false, 'server runner must clear legacy browser pause state');
  assert.strictEqual(state.pausedBy, null, 'server runner must never report a browser pause owner');
  assert.strictEqual(result.configMinScore, 77, 'each server cycle must expose the freshly loaded minScore');

  state.paused = true;
  state.pausedBy = 'browser';
  const payload = state.toServerPayload();
  assert.strictEqual(payload.paused, false, 'server payload must always report paused=false');
  assert.strictEqual(payload.pausedBy, null, 'server payload must always report pausedBy=null');

  for (const minScore of [58, 65, 75]) {
    const classified = engine.classifyRadarTf({
      score: minScore,
      dir: 1,
      regime: 1,
      isSqz: false,
      adx: 25,
      atrPct: 1,
      longTh: minScore,
      shortTh: 100 - minScore,
    });
    assert.strictEqual(classified.tradeable, true, `profile boundary ${minScore} must remain inclusive`);
  }

  const returns = Array(12).fill(1);
  const zeroVariance = engine.evaluateAutobotEdge({
    evidenceStatus: 'OOS',
    stats: { total: 12, wr: 1, avgWinR: 1, avgLossR: 1, returns },
    dsr: { dsr: 0.5 },
    setupDsr: { dsr: 0.5 },
    universeDsr: { dsr: 0.5 },
    totalTrials: 18,
    setupTrials: 18,
  }, 8, { minDsr: 0.1 });
  assert.strictEqual(zeroVariance.accepted, false, 'null-variance OOS returns must remain fail-closed');

  console.log('PASS Server-Only Live ignores legacy browser state and preserves quant guards');
}

main().catch(error => {
  console.error(error.stack || error);
  process.exit(1);
});
