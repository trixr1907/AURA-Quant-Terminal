'use strict';

const fs = require('fs');
const vm = require('vm');

const csvPath = process.argv[2];
const limit = Number(process.argv[3] || 600);
const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const begin = html.indexOf('// ============================================================================\n//  ==ENGINE_BEGIN==');
const end = html.indexOf('// ==ENGINE_END==');
const engine = html.slice(begin, end);
const context = { console, window: {}, TextEncoder, setTimeout, clearTimeout };
vm.createContext(context);
vm.runInContext(engine, context);

const lines = fs.readFileSync(csvPath, 'utf8').replace(/^\uFEFF/, '').trim().split(/\r?\n/);
const headers = lines[0].split(',').map(x => x.trim().toLowerCase());
const at = name => headers.indexOf(name);
const rows = lines.slice(1).filter(Boolean).slice(-limit).map(line => {
  const col = line.split(',');
  return {
    t: Number(col[at('timestamp')] || col[at('time')] || 0),
    o: Number(col[at('open')]), h: Number(col[at('high')]),
    l: Number(col[at('low')]), c: Number(col[at('close')]),
    v: Number(col[at('volume')]), tbv: -1,
  };
});
const A = context.analyze(rows);
const reg = context.regimeOf(A);
const i = A.n - 1;
process.stdout.write(JSON.stringify({
  base: reg.reg === 1 ? 'BULL' : reg.reg === -1 ? 'BEAR' : 'SIDEWAYS',
  squeeze: reg.isSqz,
  close: A.c[i], ema50: A.e50[i], ema200: A.e200[i], adx: A.adx[i],
}));
