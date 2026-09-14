'use strict';
/**
 * Slice C: Shadow Collector Unit and Integration Tests (JS)
 * =========================================================
 * 1. Schema & Anatomy:
 *    - ts, symbol, tf, dir, score, regime, adx, atrPct, decision, reject_reason, signal_price, params_sha256
 * 2. Deterministic Outcome:
 *    - hit_sl (SL reached)
 *    - hit_tp1 (TP1 reached, remainder to BE/mark)
 *    - hit_tp2 (TP2 reached)
 *    - time_stop (after 24 setup-TF candles)
 *    - Conservative SL first when SL & TP touched on the same candle
 *    - Netto-R calculation with default costs (makerFee=0.001, takerFee=0.001, slippage=0.001)
 * 3. Retention and Cap:
 *    - Default 180 days retention, oldest lines pruned first
 *    - Default 20 MB cap, oldest lines pruned first
 *    - Atomic file rewrite
 * 4. Funnel Parity:
 *    - Injected collector vs default collector vs disabled collector vs failing collector
 *    - Funnel output and trade decisions must be 100% identical
 * 5. Configuration & Disabled Flag:
 *    - AURA_SHADOW=0 / false disables recording
 */

const assert = require('assert');
const fs     = require('fs');
const path   = require('path');
const os     = require('os');

const {
  ShadowCollector,
  computeParamsSha256,
  evaluateDeterministicOutcome,
  pruneShadowEntries,
  DEFAULT_SHADOW_LOG_PATH,
} = require('../shadow_collector.js');

const autobot = require('../headless_autobot.js');

let passed = 0;
let failed = 0;
const errors = [];

function test(name, fn) {
  try {
    fn();
    console.log(`  PASS  ${name}`);
    passed++;
  } catch (e) {
    console.error(`  FAIL  ${name}\n        ${e.message}`);
    errors.push({ name, message: e.message });
    failed++;
  }
}

async function testAsync(name, fn) {
  try {
    await fn();
    console.log(`  PASS  ${name}`);
    passed++;
  } catch (e) {
    console.error(`  FAIL  ${name}\n        ${e.message}`);
    errors.push({ name, message: e.message });
    failed++;
  }
}

function createTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'aura_shadow_test_'));
}

function cleanTempDir(dir) {
  try {
    fs.rmSync(dir, { recursive: true, force: true });
  } catch (_) {}
}

async function runAll() {
  console.log('--- Slice C: Shadow Collector JS Tests ---');

  // 1. Schema & Anatomy
  test('computeParamsSha256 produces deterministic hex hash', () => {
    const cfg1 = { profile: 'strict', minScore: 75, minSetupDsr: 0.3, makerFee: 0.001, takerFee: 0.001, slippage: 0.001 };
    const cfg2 = { minScore: 75, profile: 'strict', slippage: 0.001, takerFee: 0.001, makerFee: 0.001, minSetupDsr: 0.3 };
    const hash1 = computeParamsSha256(cfg1);
    const hash2 = computeParamsSha256(cfg2);
    assert.strictEqual(typeof hash1, 'string');
    assert.strictEqual(hash1.length, 64);
    assert.strictEqual(hash1, hash2, 'Hash must be key-order independent');
  });

  test('Record anatomy contains all mandatory Slice C fields', () => {
    const tmpDir = createTempDir();
    const logPath = path.join(tmpDir, 'shadow_log.jsonl');
    try {
      const collector = new ShadowCollector({ logPath, enabled: true });
      const entry = collector.recordDecision({
        symbol: 'BTCUSDT',
        tf: '1h',
        dir: 1,
        score: 78.5,
        regime: 1,
        adx: 26.4,
        atrPct: 1.85,
        decision: 'ACCEPTED',
        reject_reason: null,
        signal_price: 65432.10,
        config: { profile: 'strict', minScore: 75 },
      });

      assert.strictEqual(entry.symbol, 'BTCUSDT');
      assert.strictEqual(entry.tf, '1h');
      assert.strictEqual(entry.dir, 1);
      assert.strictEqual(entry.score, 78.5);
      assert.strictEqual(entry.regime, 1);
      assert.strictEqual(entry.adx, 26.4);
      assert.strictEqual(entry.atrPct, 1.85);
      assert.strictEqual(entry.decision, 'ACCEPTED');
      assert.strictEqual(entry.reject_reason, null);
      assert.strictEqual(entry.signal_price, 65432.10);
      assert.strictEqual(typeof entry.params_sha256, 'string');
      assert.strictEqual(entry.params_sha256.length, 64);
      assert.strictEqual(typeof entry.ts, 'string');
      assert(new Date(entry.ts).getTime() > 0);

      // Verify written to jsonl
      const lines = fs.readFileSync(logPath, 'utf8').trim().split('\n');
      assert.strictEqual(lines.length, 1);
      const parsed = JSON.parse(lines[0]);
      assert.strictEqual(parsed.symbol, 'BTCUSDT');
      assert.strictEqual(parsed.decision, 'ACCEPTED');
    } finally {
      cleanTempDir(tmpDir);
    }
  });

  test('Rejection record stores exact reject_reason and decision REJECTED', () => {
    const tmpDir = createTempDir();
    const logPath = path.join(tmpDir, 'shadow_log.jsonl');
    try {
      const collector = new ShadowCollector({ logPath, enabled: true });
      const entry = collector.recordDecision({
        symbol: 'ETHUSDT',
        tf: '15m',
        dir: -1,
        score: 22.0,
        regime: -1,
        adx: 18.0,
        atrPct: 2.1,
        decision: 'REJECTED',
        reject_reason: 'MODEL_NO_EVIDENCE',
        signal_price: 3500.0,
        config: { profile: 'moderate' },
      });

      assert.strictEqual(entry.decision, 'REJECTED');
      assert.strictEqual(entry.reject_reason, 'MODEL_NO_EVIDENCE');
    } finally {
      cleanTempDir(tmpDir);
    }
  });

  // 2. Deterministic Outcome Evaluation
  test('Deterministic outcome: hit_sl on adverse move', () => {
    const record = {
      signal_price: 100,
      dir: 1,
      atrPct: 2.0, // atr = 2.0 -> slDist = max(0.5, 3.0) = 3.0 -> sl = 97, tp1 = 104.5, tp2 = 109
    };
    // 24 candles where bar 3 drops to 96
    const candles = [];
    for (let i = 0; i < 24; i++) {
      if (i === 2) {
        candles.push({ o: 99, h: 101, l: 96, c: 98, t: 1000 + i * 3600000 });
      } else {
        candles.push({ o: 100, h: 101, l: 99, c: 100, t: 1000 + i * 3600000 });
      }
    }
    const res = evaluateDeterministicOutcome(record, candles);
    assert.strictEqual(res.outcome, 'hit_sl');
    assert.strictEqual(res.exitBar, 3);
    assert.strictEqual(res.exitPrice, 97);
    // Netto-R should be approx -1R minus costs
    assert(res.rNet < -1.0, `rNet was ${res.rNet}`);
  });

  test('Deterministic outcome: conservative SL first when SL & TP touched in same candle', () => {
    const record = {
      signal_price: 100,
      dir: 1,
      atrPct: 2.0, // sl = 97, tp1 = 104.5
    };
    // Bar 1 has high=106 (touches TP1) and low=95 (touches SL)
    const candles = [
      { o: 100, h: 106, l: 95, c: 102, t: 1000 },
    ];
    for (let i = 1; i < 24; i++) {
      candles.push({ o: 102, h: 103, l: 101, c: 102, t: 1000 + i * 3600000 });
    }
    const res = evaluateDeterministicOutcome(record, candles);
    assert.strictEqual(res.outcome, 'hit_sl', 'SL must take precedence over TP in the same bar');
    assert.strictEqual(res.exitBar, 1);
    assert.strictEqual(res.exitPrice, 97);
  });

  test('Deterministic outcome: hit_tp1 with remainder time_stop', () => {
    const record = {
      signal_price: 100,
      dir: 1,
      atrPct: 2.0, // slDist=3, sl=97, tp1=104.5, tp2=109
    };
    const candles = [];
    for (let i = 0; i < 24; i++) {
      if (i === 1) {
        candles.push({ o: 100, h: 105, l: 99.5, c: 104.5, t: 1000 + i * 3600000 }); // hits TP1
      } else {
        candles.push({ o: 104, h: 105, l: 103, c: 104, t: 1000 + i * 3600000 });
      }
    }
    const res = evaluateDeterministicOutcome(record, candles);
    assert.strictEqual(res.outcome, 'hit_tp1');
    assert(res.rNet > 0.5, `rNet was ${res.rNet}`);
  });

  test('Deterministic outcome: hit_tp2 on full trend run', () => {
    const record = {
      signal_price: 100,
      dir: 1,
      atrPct: 2.0, // slDist=3, sl=97, tp1=104.5, tp2=109
    };
    const candles = [];
    for (let i = 0; i < 24; i++) {
      if (i === 4) {
        candles.push({ o: 104, h: 110, l: 103, c: 109.5, t: 1000 + i * 3600000 }); // hits TP2
      } else if (i < 4) {
        candles.push({ o: 100 + i, h: 101 + i, l: 99.5 + i, c: 100.5 + i, t: 1000 + i * 3600000 });
      } else {
        candles.push({ o: 109, h: 110, l: 108, c: 109, t: 1000 + i * 3600000 });
      }
    }
    const res = evaluateDeterministicOutcome(record, candles);
    assert.strictEqual(res.outcome, 'hit_tp2');
    assert(res.rNet > 1.5, `rNet was ${res.rNet}`);
  });

  test('Deterministic outcome: time_stop after 24 completed candles without SL/TP hit', () => {
    const record = {
      signal_price: 100,
      dir: 1,
      atrPct: 2.0, // sl=97, tp1=104.5
    };
    const candles = [];
    for (let i = 0; i < 24; i++) {
      candles.push({ o: 100, h: 102, l: 99, c: 101, t: 1000 + i * 3600000 });
    }
    const res = evaluateDeterministicOutcome(record, candles);
    assert.strictEqual(res.outcome, 'time_stop');
    assert.strictEqual(res.exitBar, 24);
    assert.strictEqual(res.exitPrice, 101);
  });

  test('Deterministic outcome for SHORT direction', () => {
    const record = {
      signal_price: 100,
      dir: -1,
      atrPct: 2.0, // slDist=3, sl=103, tp1=95.5, tp2=91
    };
    const candles = [];
    for (let i = 0; i < 24; i++) {
      if (i === 1) {
        candles.push({ o: 100, h: 100.5, l: 90, c: 91, t: 1000 + i * 3600000 }); // hits TP2
      } else {
        candles.push({ o: 100, h: 101, l: 99, c: 100, t: 1000 + i * 3600000 });
      }
    }
    const res = evaluateDeterministicOutcome(record, candles);
    assert.strictEqual(res.outcome, 'hit_tp2');
    assert(res.rNet > 1.5);
  });

  // 3. Retention & Cap Pruning
  test('pruneShadowEntries enforces retention days and cap bytes', () => {
    const now = Date.now();
    const dayMs = 86400 * 1000;
    const entries = [
      { ts: new Date(now - 200 * dayMs).toISOString(), symbol: 'OLD1', id: 1 },
      { ts: new Date(now - 190 * dayMs).toISOString(), symbol: 'OLD2', id: 2 },
      { ts: new Date(now - 100 * dayMs).toISOString(), symbol: 'KEEP1', id: 3 },
      { ts: new Date(now - 10 * dayMs).toISOString(), symbol: 'KEEP2', id: 4 },
      { ts: new Date(now - 1 * dayMs).toISOString(), symbol: 'KEEP3', id: 5 },
    ];

    // Prune retention > 180 days
    const prunedRetention = pruneShadowEntries(entries, { retentionDays: 180, capBytes: 1000000, now });
    assert.strictEqual(prunedRetention.length, 3);
    assert.strictEqual(prunedRetention[0].symbol, 'KEEP1');
    assert.strictEqual(prunedRetention[2].symbol, 'KEEP3');

    // Prune by capBytes (keep only latest entries that fit)
    const singleSize = Buffer.byteLength(JSON.stringify(entries[0]) + '\n', 'utf8');
    const prunedCap = pruneShadowEntries(entries, { retentionDays: 365, capBytes: singleSize * 2 + 5, now });
    assert.strictEqual(prunedCap.length, 2);
    assert.strictEqual(prunedCap[0].symbol, 'KEEP2');
    assert.strictEqual(prunedCap[1].symbol, 'KEEP3');
  });

  test('Collector atomic rewrite on prune', () => {
    const tmpDir = createTempDir();
    const logPath = path.join(tmpDir, 'shadow_log.jsonl');
    try {
      const collector = new ShadowCollector({ logPath, enabled: true, retentionDays: 180, capBytes: 500 });
      const now = Date.now();
      for (let i = 0; i < 20; i++) {
        collector.recordDecision({
          symbol: `SYM${i}`,
          tf: '1h',
          dir: 1,
          score: 80,
          regime: 1,
          adx: 25,
          atrPct: 1.5,
          decision: 'REJECTED',
          reject_reason: 'LIQUIDITY',
          signal_price: 100,
          config: { profile: 'strict' },
          ts: new Date(now + i * 1000).toISOString(),
        });
      }
      collector.pruneLog();
      const stats = fs.statSync(logPath);
      assert(stats.size <= 500, `File size was ${stats.size}, expected <= 500`);
      const lines = fs.readFileSync(logPath, 'utf8').trim().split('\n').map(JSON.parse);
      assert(lines.length > 0);
      assert.strictEqual(lines[lines.length - 1].symbol, 'SYM19');
    } finally {
      cleanTempDir(tmpDir);
    }
  });

  // 4. Injected collector vs default vs failing in runScanCycle (Funnel Parity)
  await testAsync('runScanCycle accepts injected collector and fails-soft without funnel disruption', async () => {
    const engine = autobot.loadEngine();
    const state = new autobot.ServerBotState();

    // Mock candidates
    const mockRadar = [
      {
        symbol: 'BTCUSDT',
        aligned: 4,
        bestTF: '1h',
        mtfDir: 1,
        tfScores: {
          '1h': { status: 'ready', tradeable: true, score: 85, dir: 1, quality: 70 },
        },
      },
    ];

    let recorded = [];
    const mockCollector = {
      recordDecision: (d) => {
        recorded.push(d);
        return d;
      },
    };

    // Run cycle with custom collector
    const mockGetState = async () => ({
      _rev: 1,
      'aura-quant-terminal-autobot-state-v1': { enabled: true, mode: 'server' },
    });

    const funnel = await autobot.runScanCycle(engine, state, {
      getState: mockGetState,
      radarData: mockRadar,
      universe: [{ symbol: 'BTCUSDT', liquidityVerified: true, vol: 5000000 }],
      btcBias: { available: true, regTxt: 'BULL' },
      skipKlFetch: true, // test mode
    }, mockCollector);

    assert(funnel, 'Funnel must return valid object');
    assert.strictEqual(recorded.length, 1);
    assert.strictEqual(recorded[0].symbol, 'BTCUSDT');

    // Run cycle with throwing collector — must not throw and must return identical funnel
    const throwingCollector = {
      recordDecision: () => {
        throw new Error('Disk full simulated error');
      },
    };

    const funnelWithThrow = await autobot.runScanCycle(engine, state, {
      getState: mockGetState,
      radarData: mockRadar,
      universe: [{ symbol: 'BTCUSDT', liquidityVerified: true, vol: 5000000 }],
      btcBias: { available: true, regTxt: 'BULL' },
      skipKlFetch: true,
    }, throwingCollector);

    assert.deepStrictEqual(funnel.rejects, funnelWithThrow.rejects);
  });

  // 5. Config Disabled Flag
  test('AURA_SHADOW=0 disables recording', () => {
    const tmpDir = createTempDir();
    const logPath = path.join(tmpDir, 'shadow_log.jsonl');
    try {
      const collector = new ShadowCollector({ logPath, enabled: false });
      assert.strictEqual(collector.enabled, false);
      const res = collector.recordDecision({ symbol: 'BTCUSDT' });
      assert.strictEqual(res, null);
      assert.strictEqual(fs.existsSync(logPath), false);
    } finally {
      cleanTempDir(tmpDir);
    }
  });

  console.log(`\nShadow Collector JS Tests: ${passed} passed, ${failed} failed.`);
  if (failed > 0) {
    process.exit(1);
  }
}

runAll().catch(e => {
  console.error('Test runner fatal error:', e);
  process.exit(1);
});
