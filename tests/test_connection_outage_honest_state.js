#!/usr/bin/env node
/**
 * Test fuer Auftrag "Verbindungsunterbrechung ehrlich anzeigen":
 * SyncEngine.pull() darf nach einem Backend-Ausfall (Netzwerkfehler oder
 * HTTP 5xx) NIEMALS den zuletzt bekannten "OPERATOR (Live)" Pill stehen
 * lassen. Er muss auf einen ehrlichen "nicht erreichbar" Zustand wechseln.
 *
 * Deckt zwei Fehlerpfade ab:
 *  1. fetch() wirft (Netzwerkfehler / Connection refused) -> catch-Zweig.
 *  2. fetch() liefert eine Antwort mit res.ok === false und Status != 401/403
 *     (z.B. 502/503 durch einen abgestuerzten/uebergangenen Server) -> else-Zweig.
 *
 * In beiden Faellen darf der Pill-Text NICHT mehr '● OPERATOR (Live)' sein,
 * nachdem er zuvor auf diesen Live-Zustand gesetzt wurde.
 */
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.resolve(__dirname, '../Symbiose_Dashboard.html'), 'utf8');

function extractPull() {
  const start = html.indexOf('async pull() {');
  assert(start >= 0, 'SyncEngine.pull source missing');
  const brace = html.indexOf('{', start);
  let depth = 0;
  for (let i = brace; i < html.length; i++) {
    if (html[i] === '{') depth++;
    else if (html[i] === '}' && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error('pull() source incomplete');
}

class MockPill {
  constructor() { this.textContent = ''; this.className = ''; }
}

function buildEngine(fetchImpl) {
  const pillEl = new MockPill();
  const logoutBtn = { style: {} };
  const elements = { 'auth-status-pill': pillEl, 'btn-logout': logoutBtn };
  const $ = (id) => elements[id] || null;

  const src = extractPull();
  // Minimal harness object mimicking SyncEngine's own methods/state used inside pull().
  const engine = {
    isPulling: false,
    bootstrapped: true,
    pending: [],
    queueCorrupt: false,
    queueOverflow: false,
    setStatus(st, txt) { this.lastStatus = st; this.lastStatusText = txt; },
    hasUnsyncedWork() { return false; },
    applyServerState() {},
    bootstrapIfNeeded: async () => {},
  };

  const fn = new Function('fetch', '$', 'AuraApp', 'Autobot', 'return (async function() ' + src.slice(src.indexOf('{')) + ').call(this)');
  engine.pull = function () {
    return fn.call(this, fetchImpl, $, { isAuthenticated: true }, {
      serverBotActive: false, equity: null, startingEquity: null, initialEquity: null, render() {},
    });
  };
  return { engine, pillEl };
}

async function run() {
  // --- Case 1: Netzwerkfehler (fetch throws) after a prior Live state ---
  {
    const { engine, pillEl } = buildEngine(async () => { throw new TypeError('Failed to fetch'); });
    pillEl.textContent = '● OPERATOR (Live)';
    pillEl.className = 'feed-status-pill live';
    await engine.pull();
    assert.notStrictEqual(pillEl.textContent, '● OPERATOR (Live)',
      'Netzwerkfehler darf den Live-Pill nicht stehen lassen');
    assert(pillEl.textContent.length > 0, 'Pill muss einen erklärenden Text zeigen');
  }

  // --- Case 2: HTTP 502 (Backend down/restarting) after a prior Live state ---
  {
    const { engine, pillEl } = buildEngine(async () => ({ ok: false, status: 502 }));
    pillEl.textContent = '● OPERATOR (Live)';
    pillEl.className = 'feed-status-pill live';
    await engine.pull();
    assert.notStrictEqual(pillEl.textContent, '● OPERATOR (Live)',
      'HTTP 502 darf den Live-Pill nicht stehen lassen');
  }

  // --- Case 3: Anonymous state (pill already showing ANMELDUNG) stays untouched on error ---
  {
    const { engine, pillEl } = buildEngine(async () => { throw new TypeError('Failed to fetch'); });
    pillEl.textContent = '🔒 ANMELDUNG';
    pillEl.className = 'feed-status-pill offline';
    await engine.pull();
    assert.strictEqual(pillEl.textContent, '🔒 ANMELDUNG',
      'Bereits anonymer Zustand darf durch Netzwerkfehler nicht veraendert werden');
  }

  console.log('PASS SyncEngine.pull() never freezes a stale Live pill after backend outage');
}

run().catch((e) => { console.error('FAIL', e); process.exit(1); });
