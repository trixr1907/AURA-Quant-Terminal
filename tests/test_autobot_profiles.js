'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');

function extractFunction(name) {
  const start = html.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`${name}() source not found`);
  const paren = html.indexOf(')', start);
  const brace = html.indexOf('{', paren);
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

const context = { Number, Math, Object };
vm.createContext(context);
vm.runInContext(
  `${extractFunction('autobotProfileSettings')}\n` +
  `${extractFunction('evaluateAutobotCandidate')}\n` +
  `this.autobotProfileSettings = autobotProfileSettings;\n` +
  `this.evaluateAutobotCandidate = evaluateAutobotCandidate;`,
  context,
);

assert.deepStrictEqual(
  JSON.parse(JSON.stringify(context.autobotProfileSettings('balanced'))),
  { minScore: 65, mtfNeed: 2, min24hVol: 2000000, minOosSamples: 10, minSetupDsr: 0.35 },
);
assert.deepStrictEqual(
  JSON.parse(JSON.stringify(context.autobotProfileSettings('aggressive'))),
  { minScore: 58, mtfNeed: 1, min24hVol: 1000000, minOosSamples: 8, minSetupDsr: 0.25 },
);
assert.deepStrictEqual(
  JSON.parse(JSON.stringify(context.autobotProfileSettings('strict'))),
  { minScore: 75, mtfNeed: 3, min24hVol: 5000000, minOosSamples: 15, minSetupDsr: 0.5 },
);

const candidate = {
  executable: true,
  aligned: 2,
  bestInfo: { score: 68, dir: 1, status: 'ready', tradeable: true },
  bestTF: '1h',
};
assert.strictEqual(context.evaluateAutobotCandidate(candidate, 65, 2).accepted, true);
assert.strictEqual(context.evaluateAutobotCandidate(candidate, 75, 3).accepted, false);

assert(html.includes('id="ab-cfg-profile"'), 'Autobot config must expose a scan profile');
assert(html.includes('id="ab-cfg-min-oos-samples"'), 'Autobot config must expose minimum OOS samples');
assert(html.includes('id="ab-cfg-min-setup-dsr"'), 'Autobot config must expose setup DSR threshold');
assert(!html.includes('min="65" max="95" value="78"'), 'legacy too-restrictive score control must be replaced');

console.log('PASS Autobot profiles expose transparent adjustable activity gates');
