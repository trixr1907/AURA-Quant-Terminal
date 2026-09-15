'use strict';
/**
 * AURA Shadow Collector Module (v1.10.1 / Slice C)
 * ===============================================
 * Records trading decisions (ACCEPTED / REJECTED with exact reason) for every
 * considered candidate in the bot funnel. Evaluates forward outcomes after 24
 * setup-TF bars deterministically without modifying trading logic.
 *
 * Cost Model (standard runner defaults):
 * - makerFee = 0.001 (0.1%)
 * - takerFee = 0.001 (0.1%)
 * - slippage = 0.001 (0.1%)
 *
 * Conflict Resolution:
 * - When both SL and TP are touched within the same candle, conservatively SL first.
 */

const fs     = require('fs');
const path   = require('path');
const crypto = require('crypto');

const DEFAULT_SHADOW_LOG_PATH = process.env.AURA_STATE_DIR
  ? path.join(process.env.AURA_STATE_DIR, 'shadow_log.jsonl')
  : '/var/lib/aura/shadow_log.jsonl';

const DEFAULT_RETENTION_DAYS = 180;
const DEFAULT_CAP_BYTES = 20 * 1024 * 1024; // 20 MB

const DEFAULT_COSTS = {
  makerFee: 0.001,
  takerFee: 0.001,
  slippage: 0.001,
};

/**
 * Deterministic canonical SHA-256 hash of configuration / parameters.
 */
function computeParamsSha256(config) {
  if (!config || typeof config !== 'object') {
    return crypto.createHash('sha256').update('{}').digest('hex');
  }
  const sortedKeys = Object.keys(config).sort();
  const canonical = {};
  for (const k of sortedKeys) {
    canonical[k] = config[k];
  }
  return crypto.createHash('sha256').update(JSON.stringify(canonical)).digest('hex');
}

/**
 * Deterministic forward outcome evaluation after up to 24 closed setup-TF bars.
 *
 * @param {Object} record - candidate decision record { signal_price, dir, atrPct, ... }
 * @param {Array<Object>} candles - list of bar objects { o, h, l, c, t }
 * @param {Object} [options] - cost options { makerFee, takerFee, slippage }
 * @returns {Object} outcome result { outcome, rNet, exitBar, exitPrice, exitReason, feeEntryR, feeExitR }
 */
function evaluateDeterministicOutcome(record, candles, options = {}) {
  const costs = Object.assign({}, DEFAULT_COSTS, options);
  const signalPrice = Number(record.signal_price || record.signalPrice || record.price || 0);
  const dir = Number(record.dir || 1) >= 0 ? 1 : -1;
  const atrPct = Number(record.atrPct || 1.5);

  if (!signalPrice || signalPrice <= 0 || !Array.isArray(candles) || candles.length === 0) {
    return {
      outcome: 'pending',
      rNet: 0.0,
      exitBar: 0,
      exitPrice: signalPrice,
      exitReason: 'NO_DATA',
    };
  }

  const atr = (signalPrice * atrPct) / 100.0;
  const slDist = Math.max(signalPrice * 0.005, atr * 1.5);
  const sl = dir === 1 ? signalPrice - slDist : signalPrice + slDist;
  const tp1 = dir === 1 ? signalPrice + slDist * 1.5 : signalPrice - slDist * 1.5;
  const tp2 = dir === 1 ? signalPrice + slDist * 3.0 : signalPrice - slDist * 3.0;

  const entryCostPct = costs.takerFee + costs.slippage;
  const entryCostR = (entryCostPct * signalPrice) / slDist;

  function calcNetR(exitP, exitCostPct, weight = 1.0) {
    const grossR = (dir * (exitP - signalPrice)) / slDist;
    const exitCostR = (exitCostPct * exitP) / slDist;
    return weight * (grossR - entryCostR - exitCostR);
  }

  const maxBars = Math.min(24, candles.length);
  let tp1HitBar = null;
  let tp1Price = tp1;

  for (let barIdx = 0; barIdx < maxBars; barIdx++) {
    const bar = candles[barIdx];
    const high = Number(bar.h != null ? bar.h : bar.high || bar.c || signalPrice);
    const low = Number(bar.l != null ? bar.l : bar.low || bar.c || signalPrice);

    const slTouched = dir === 1 ? low <= sl : high >= sl;
    const tp1Touched = dir === 1 ? high >= tp1 : low <= tp1;
    const tp2Touched = dir === 1 ? high >= tp2 : low <= tp2;

    if (tp1HitBar === null) {
      // Conservative rule: If both SL and TP touched on same candle, SL first
      if (slTouched) {
        const exitCostPct = costs.takerFee + costs.slippage;
        return {
          outcome: 'hit_sl',
          rNet: Number(calcNetR(sl, exitCostPct, 1.0).toFixed(4)),
          exitBar: barIdx + 1,
          exitPrice: sl,
          exitReason: 'SL_HIT',
          feeEntryR: Number(entryCostR.toFixed(4)),
          feeExitR: Number(((exitCostPct * sl) / slDist).toFixed(4)),
        };
      }

      if (tp2Touched) {
        const exitCostPct = costs.makerFee + costs.slippage;
        return {
          outcome: 'hit_tp2',
          rNet: Number(calcNetR(tp2, exitCostPct, 1.0).toFixed(4)),
          exitBar: barIdx + 1,
          exitPrice: tp2,
          exitReason: 'TP2_HIT_DIRECT',
          feeEntryR: Number(entryCostR.toFixed(4)),
          feeExitR: Number(((exitCostPct * tp2) / slDist).toFixed(4)),
        };
      }

      if (tp1Touched) {
        tp1HitBar = barIdx + 1;
        tp1Price = tp1;
      }
    } else {
      // Already hit TP1: remaining 50% trails SL to Break-Even (signalPrice)
      const beTouched = dir === 1 ? low <= signalPrice : high >= signalPrice;

      if (beTouched) {
        // Remainder stopped out at BE
        const tp1ExitCostPct = costs.makerFee + costs.slippage;
        const beExitCostPct = costs.takerFee + costs.slippage;
        const r1 = calcNetR(tp1Price, tp1ExitCostPct, 0.5);
        const r2 = calcNetR(signalPrice, beExitCostPct, 0.5);
        return {
          outcome: 'hit_tp1',
          rNet: Number((r1 + r2).toFixed(4)),
          exitBar: barIdx + 1,
          exitPrice: signalPrice,
          exitReason: 'TP1_HIT_TRAIL_BE',
          feeEntryR: Number(entryCostR.toFixed(4)),
          feeExitR: Number(((tp1ExitCostPct * tp1Price + beExitCostPct * signalPrice) / (2 * slDist)).toFixed(4)),
        };
      }

      if (tp2Touched) {
        // Remainder reached TP2
        const tp1ExitCostPct = costs.makerFee + costs.slippage;
        const tp2ExitCostPct = costs.makerFee + costs.slippage;
        const r1 = calcNetR(tp1Price, tp1ExitCostPct, 0.5);
        const r2 = calcNetR(tp2, tp2ExitCostPct, 0.5);
        return {
          outcome: 'hit_tp2',
          rNet: Number((r1 + r2).toFixed(4)),
          exitBar: barIdx + 1,
          exitPrice: tp2,
          exitReason: 'TP1_THEN_TP2_HIT',
          feeEntryR: Number(entryCostR.toFixed(4)),
          feeExitR: Number(((tp1ExitCostPct * tp1Price + tp2ExitCostPct * tp2) / (2 * slDist)).toFixed(4)),
        };
      }
    }
  }

  // If reached 24 bars without full stop or TP2
  const lastBar = candles[maxBars - 1];
  const closePrice = Number(lastBar.c != null ? lastBar.c : lastBar.close || signalPrice);

  if (tp1HitBar !== null) {
    // 50% at TP1, 50% closed at bar 24 close
    const tp1ExitCostPct = costs.makerFee + costs.slippage;
    const closeExitCostPct = costs.takerFee + costs.slippage;
    const r1 = calcNetR(tp1Price, tp1ExitCostPct, 0.5);
    const r2 = calcNetR(closePrice, closeExitCostPct, 0.5);
    return {
      outcome: 'hit_tp1',
      rNet: Number((r1 + r2).toFixed(4)),
      exitBar: maxBars,
      exitPrice: closePrice,
      exitReason: 'TP1_THEN_TIME_STOP',
      feeEntryR: Number(entryCostR.toFixed(4)),
      feeExitR: Number(((tp1ExitCostPct * tp1Price + closeExitCostPct * closePrice) / (2 * slDist)).toFixed(4)),
    };
  }

  // 100% time_stop exit at bar 24 close
  const exitCostPct = costs.takerFee + costs.slippage;
  return {
    outcome: 'time_stop',
    rNet: Number(calcNetR(closePrice, exitCostPct, 1.0).toFixed(4)),
    exitBar: maxBars,
    exitPrice: closePrice,
    exitReason: 'TIME_STOP_24_BARS',
    feeEntryR: Number(entryCostR.toFixed(4)),
    feeExitR: Number(((exitCostPct * closePrice) / slDist).toFixed(4)),
  };
}

/**
 * In-memory filter enforcing retention days and byte cap (oldest lines dropped first).
 */
function pruneShadowEntries(entries, options = {}) {
  if (!Array.isArray(entries) || entries.length === 0) return [];
  const retentionDays = Number(options.retentionDays || DEFAULT_RETENTION_DAYS);
  const capBytes = Number(options.capBytes || DEFAULT_CAP_BYTES);
  const now = options.now != null ? Number(options.now) : Date.now();
  const maxAgeMs = retentionDays * 86400 * 1000;

  // 1. Retention filter
  let filtered = entries.filter((e) => {
    if (!e || !e.ts) return true;
    const t = new Date(e.ts).getTime();
    return !isNaN(t) && now - t <= maxAgeMs;
  });

  // 2. Cap bytes filter (oldest first)
  let totalBytes = filtered.reduce((acc, e) => acc + Buffer.byteLength(JSON.stringify(e) + '\n', 'utf8'), 0);
  while (filtered.length > 0 && totalBytes > capBytes) {
    const removed = filtered.shift();
    totalBytes -= Buffer.byteLength(JSON.stringify(removed) + '\n', 'utf8');
  }

  return filtered;
}

class ShadowCollector {
  constructor(options = {}) {
    this.logPath = options.logPath || DEFAULT_SHADOW_LOG_PATH;
    const envShadow = process.env.AURA_SHADOW;
    const isExplicitlyDisabled =
      envShadow === '0' || envShadow === 'false' || envShadow === 'off' || envShadow === 'no';
    this.enabled = options.enabled !== undefined ? Boolean(options.enabled) : !isExplicitlyDisabled;
    this.retentionDays = Number(options.retentionDays || process.env.AURA_SHADOW_RETENTION_DAYS || DEFAULT_RETENTION_DAYS);
    this.capBytes = Number(options.capBytes || process.env.AURA_SHADOW_CAP_BYTES || DEFAULT_CAP_BYTES);
  }

  recordDecision(candidateData = {}) {
    if (!this.enabled) return null;
    try {
      const ts = candidateData.ts || new Date().toISOString();
      const symbol = String(candidateData.symbol || 'UNKNOWN').toUpperCase();
      const tf = String(candidateData.tf || '1h');
      const dir = Number(candidateData.dir || 0);
      const score = Number(candidateData.score != null ? candidateData.score : 0);
      const regime = candidateData.regime != null ? candidateData.regime : 0;
      const adx = Number(candidateData.adx != null ? candidateData.adx : 0);
      const atrPct = Number(candidateData.atrPct != null ? candidateData.atrPct : 0);
      const decision = candidateData.decision === 'ACCEPTED' ? 'ACCEPTED' : 'REJECTED';
      const rejectReason = decision === 'ACCEPTED' ? null : String(candidateData.reject_reason || candidateData.rejectReason || 'UNKNOWN');
      const signalPrice = Number(candidateData.signal_price || candidateData.signalPrice || candidateData.price || 0);
      const paramsSha256 = candidateData.params_sha256 || computeParamsSha256(candidateData.config || {});

      const entry = {
        ts,
        symbol,
        tf,
        dir,
        score,
        regime,
        adx,
        atrPct,
        decision,
        reject_reason: rejectReason,
        signal_price: signalPrice,
        params_sha256: paramsSha256,
      };

      this._appendEntry(entry);
      this._updateStatsFile();
      return entry;
    } catch (err) {
      // Fail-soft: never disrupt funnel execution
      return null;
    }
  }

  _appendEntry(entry) {
    const line = JSON.stringify(entry) + '\n';
    const parent = path.dirname(this.logPath);
    if (!fs.existsSync(parent)) {
      try {
        fs.mkdirSync(parent, { recursive: true });
      } catch (_) {}
    }
    fs.appendFileSync(this.logPath, line, 'utf8');
  }

  pruneLog() {
    if (!fs.existsSync(this.logPath)) return;
    try {
      const raw = fs.readFileSync(this.logPath, 'utf8');
      const lines = raw.trim().split('\n').filter(Boolean);
      const entries = lines.map((l) => JSON.parse(l));
      const pruned = pruneShadowEntries(entries, {
        retentionDays: this.retentionDays,
        capBytes: this.capBytes,
      });
      const tempPath = `${this.logPath}.tmp.${Date.now()}`;
      const content = pruned.map((e) => JSON.stringify(e)).join('\n') + (pruned.length > 0 ? '\n' : '');
      fs.writeFileSync(tempPath, content, 'utf8');
      fs.renameSync(tempPath, this.logPath);
    } catch (_) {}
  }

  getStats() {
    if (!this.enabled || !fs.existsSync(this.logPath)) {
      return {
        enabled: this.enabled,
        entries: 0,
        pending_outcomes: 0,
        evaluated: 0,
        accepted_count: 0,
        rejected_count: 0,
        accepted_avg_r: null,
        rejected_avg_r: null,
      };
    }
    try {
      const raw = fs.readFileSync(this.logPath, 'utf8');
      const lines = raw.trim().split('\n').filter(Boolean);
      let entries = 0;
      let evaluated = 0;
      let pending = 0;
      let accCount = 0;
      let accRSum = 0;
      let rejCount = 0;
      let rejRSum = 0;

      for (const line of lines) {
        try {
          const item = JSON.parse(line);
          entries++;
          if (item.outcome) {
            evaluated++;
            const r = Number(item.rNet != null ? item.rNet : item.r_net != null ? item.r_net : 0);
            if (item.decision === 'ACCEPTED') {
              accCount++;
              accRSum += r;
            } else {
              rejCount++;
              rejRSum += r;
            }
          } else {
            pending++;
          }
        } catch (_) {}
      }

      return {
        enabled: this.enabled,
        entries,
        pending_outcomes: pending,
        evaluated,
        accepted_count: accCount,
        rejected_count: rejCount,
        accepted_avg_r: accCount > 0 ? Number((accRSum / accCount).toFixed(2)) : null,
        rejected_avg_r: rejCount > 0 ? Number((rejRSum / rejCount).toFixed(2)) : null,
      };
    } catch (_) {
      return {
        enabled: this.enabled,
        entries: 0,
        pending_outcomes: 0,
        evaluated: 0,
        accepted_count: 0,
        rejected_count: 0,
        accepted_avg_r: null,
        rejected_avg_r: null,
      };
    }
  }

  _updateStatsFile() {
    try {
      const stats = this.getStats();
      const parent = path.dirname(this.logPath);
      const statsPath = path.join(parent, 'shadow_stats.json');
      fs.writeFileSync(statsPath, JSON.stringify(stats, null, 2), 'utf8');
    } catch (_) {}
  }
}

module.exports = {
  ShadowCollector,
  computeParamsSha256,
  evaluateDeterministicOutcome,
  pruneShadowEntries,
  DEFAULT_SHADOW_LOG_PATH,
  DEFAULT_RETENTION_DAYS,
  DEFAULT_CAP_BYTES,
  DEFAULT_COSTS,
};
