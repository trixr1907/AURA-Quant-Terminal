'use strict';

const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  const start = html.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`${name}() source not found`);
  const brace = html.indexOf('{', start);
  let depth = 0, quote = null, escaped = false;
  for (let i = brace; i < html.length; i += 1) {
    const ch = html[i];
    if (quote) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') { quote = ch; continue; }
    if (ch === '{') depth += 1;
    if (ch === '}' && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error(`${name}() closing brace not found`);
}

let stored = null;
const storage = new Map();
const context = {
  Date, JSON, Number,
  localStorage: {
    getItem: key => storage.get(key) || null,
    setItem: (key, value) => storage.set(key, value),
  },
  RADAR_TFS: ['15m', '1h', '4h', '1d'],
  rankRadarCandidates: rows => rows.slice(),
};
vm.createContext(context);
vm.runInContext(
  `${extractFunction('radarSnapshotPayload')}\n${extractFunction('persistRadarSnapshot')}\n${extractFunction('restoreRadarSnapshot')}\nconst RADAR_CACHE_KEY='aura-action-radar-cache-v1';const RADAR_CACHE_MAX_AGE_MS=15*60*1000;this.persistRadarSnapshot=persistRadarSnapshot;this.restoreRadarSnapshot=restoreRadarSnapshot;`,
  context,
);

const row = {
  symbol: 'AAAUSDT', avgScore: 82, mtfDir: 1, aligned: 3, btcBlock: false,
  tfScores: {
    '15m': { score: 78, dir: 1, status: 'ready', tradeable: true, quality: 75, candidate: true },
    '1h': { score: 82, dir: 1, status: 'ready', tradeable: true, quality: 82, candidate: true },
    '4h': { score: 85, dir: 1, status: 'ready', tradeable: true, quality: 88, candidate: true },
    '1d': { score: 70, dir: 1, status: 'watch', tradeable: false, quality: 55, candidate: false },
  }, comps: [], scannedAt: Date.now(),
};
context.persistRadarSnapshot([row], { done: 1, total: 1, scanning: false, skipped: 0 });
stored = storage.get('aura-action-radar-cache-v1');
if (!stored) throw new Error('radar snapshot was not persisted');
const restored = JSON.parse(JSON.stringify(context.restoreRadarSnapshot(['AAAUSDT'], 15 * 60 * 1000)));
if (!restored || restored.rows.length !== 1 || restored.rows[0].symbol !== 'AAAUSDT') throw new Error('fresh radar snapshot did not restore');

const old = JSON.parse(stored);
old.savedAt = Date.now() - 16 * 60 * 1000;
storage.set('aura-action-radar-cache-v1', JSON.stringify(old));
if (context.restoreRadarSnapshot(['AAAUSDT'], 15 * 60 * 1000) !== null) throw new Error('stale radar snapshot must be rejected');

console.log('PASS Action Radar persists a fresh reload snapshot and rejects stale cache');
