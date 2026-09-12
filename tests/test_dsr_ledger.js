const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm'); // NOSONAR -- executes a fixed repository function slice in an isolated test context.

const root = path.join(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'tools', 'edge_diagnostic_phase_d.js'), 'utf8');
const dashboard = fs.readFileSync(path.join(root, 'Symbiose_Dashboard.html'), 'utf8');
const begin = dashboard.indexOf('<script>') + '<script>'.length;
const end = dashboard.indexOf('</script>', begin);
const script = dashboard.slice(begin, end);
const calcBegin = script.indexOf('function erf(');
const calcEnd = script.indexOf('\n// ============================================================================', calcBegin + 1);
const sandbox = { console, Float64Array, Date, Math, Array, Object, JSON, Number };
vm.createContext(sandbox);
vm.runInContext(script.slice(calcBegin, calcEnd) + '\n__calcDSR = calcDSR;', sandbox);

assert.match(source, /const LEDGER_TRIALS = loadVerifiedLedgerTrials\(\)/);
assert.match(source, /Math\.max\(LEGACY_PHASE_D_TRIALS, LEDGER_TRIALS\)/);
assert.match(source, /Math\.max\(currentSearchTrials, DSR_TRIALS\)/);
assert.match(source, /TRIALS_LEDGER_INVALID/);

const returns = [-0.9, 0.4, 1.1, -0.2, 0.8, 0.3, -0.5, 0.7, 1.2, -0.1, 0.6, 0.2];
const oldTrials = 45;
const ledgerTrials = 120;
const oldDsr = sandbox.__calcDSR(returns, oldTrials).dsr;
const newDsr = sandbox.__calcDSR(returns, Math.max(oldTrials, ledgerTrials)).dsr;
assert.ok(newDsr <= oldDsr, `new DSR ${newDsr} must not exceed old DSR ${oldDsr}`);
console.log(`DSR_LEDGER_MONOTONIC PASS old_N=${oldTrials} ledger_N=${ledgerTrials} old_DSR=${oldDsr} new_DSR=${newDsr}`);
