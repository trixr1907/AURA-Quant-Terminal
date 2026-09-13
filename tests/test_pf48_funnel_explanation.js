'use strict';

const assert = require('assert');
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

const context = { Number, Object, String };
vm.createContext(context);
vm.runInContext(
  `${extractFunction('autobotRejectDetails')}\n${extractFunction('autobotFunnelExplanation')}\n` +
  'this.autobotRejectDetails = autobotRejectDetails; this.autobotFunnelExplanation = autobotFunnelExplanation;',
  context
);

const evidenceFunnel = {
  selected: 0,
  rejects: { MODEL_NO_EVIDENCE: 8, NO_RADAR_READY: 1 },
};
const evidenceText = context.autobotFunnelExplanation(evidenceFunnel);
assert(evidenceText.includes('Alle 8 heute qualifizierten Setups'),
  'zero selected with dominant evidence rejects must explain the affected count');
assert(evidenceText.includes('keine positive Out-of-Sample-Erwartung'),
  'zero selected with dominant evidence rejects must explain the evidence failure');
assert(evidenceText.includes('Keine Einstellung umgeht diese Prüfung'),
  'evidence explanation must state that configuration cannot bypass the gate');
assert.strictEqual(context.autobotFunnelExplanation({ ...evidenceFunnel, selected: 1 }), '',
  'a selected setup must suppress the no-signal explanation');

const radarText = context.autobotFunnelExplanation({ selected: 0, rejects: { NO_RADAR_READY: 5 } });
assert(radarText.includes('Score ≥ 75/≤ 25') && radarText.includes('ADX ≥ 20') && radarText.includes('kein Squeeze'),
  'radar-dominant rejection must explain the fixed radar criteria');
const incompleteText = context.autobotFunnelExplanation({ selected: 0, rejects: { RADAR_INCOMPLETE: 5 } });
assert(incompleteText.includes('Radar-Daten') && incompleteText.includes('unvollständig'),
  'incomplete radar data must not be described as a technical threshold failure');
const configText = context.autobotFunnelExplanation({ selected: 0, rejects: { AUTOBOT_CONFIG: 5 } });
assert(configText.includes('MinScore- oder MTF-Einstellung'),
  'configuration-dominant rejection must not falsely blame fixed radar criteria');

const details = context.autobotRejectDetails({
  rejects: {
    LIQUIDITY: 1,
    NO_RADAR_READY: 1,
    RADAR_INCOMPLETE: 1,
    AUTOBOT_CONFIG: 1,
    BTC_CONFLICT: 1,
    FRESH_GATE: 1,
    MODEL_NO_EVIDENCE: 1,
  },
});
for (const label of ['Liquidität', 'Radar-Gate', 'Radar-Daten', 'Autobot-Konfiguration', 'BTC-Konflikt', 'Fresh-Gate', 'keine OOS-Evidenz']) {
  const item = details.find(entry => entry.label === label);
  assert(item && item.title.length > 20, `${label} must have a user-facing tooltip explanation`);
}

for (const id of ['ab-hint-min-score', 'ab-hint-mtf', 'ab-hint-timestop']) {
  assert(html.includes(`id="${id}"`), `${id} hint must be present in Autobot settings`);
}
assert(html.includes('Der Radar selbst ist bewusst nicht konfigurierbar'),
  'settings must distinguish MinScore/MTF controls from fixed radar criteria');
assert(html.includes('wirkt erst auf offene Positionen, nicht auf die Signalfindung'),
  'TimeStop hint must state that it cannot create signals');

const renderStart = html.indexOf("const funnelEl = $('ab-funnel-summary');");
const renderEnd = html.indexOf('// 2. Metrics & Portfolio KPIs', renderStart);
const renderSource = html.slice(renderStart, renderEnd);
assert(renderSource.includes('autobotFunnelExplanation(f)'),
  'funnel renderer must append the no-signal explanation');
assert(renderSource.includes('explanationEl.textContent = explanation'),
  'funnel explanation must be rendered via textContent');
assert(renderSource.includes('rejectEl.title = detail.title'),
  'reject labels must expose tooltip text in the rendered funnel');

console.log('PASS PF-48 funnel explains zero signals and exposes honest settings hints');
