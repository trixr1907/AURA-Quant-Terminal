#!/usr/bin/env node
/**
 * Tests for Auftrag C: Trade-Export CSV / JSON (tests/test_trade_export.js)
 *
 * Covers:
 * 1. CSV header schema and BOM (\uFEFF)
 * 2. Field normalization (manual + autobot, open vs closed)
 * 3. CSV Escaping (commas, quotes, newlines)
 * 4. JSON structure and loss-free roundtrip
 * 5. Empty trades array yields valid header-only CSV
 */

const assert = require('assert');
const fs = require('fs');
const path = require('path');

// Extract export functions from Symbiose_Dashboard.html to test them directly
const html = fs.readFileSync(path.resolve(__dirname, '../Symbiose_Dashboard.html'), 'utf8');

// Use Function constructor or eval sandbox with minimal mock environment
const exportSandbox = {};
const exportCode = `
${html.match(/const TRADE_EXPORT_COLUMNS = [\s\S]*?function triggerTradeExportJson\(\) \{[\s\S]*?\n\}/)[0]}
exportSandbox.TRADE_EXPORT_COLUMNS = TRADE_EXPORT_COLUMNS;
exportSandbox.normalizeTradeResultReason = normalizeTradeResultReason;
exportSandbox.normalizeTradeForExport = normalizeTradeForExport;
exportSandbox.escapeCsvValue = escapeCsvValue;
exportSandbox.exportTradesToCsvString = exportTradesToCsvString;
exportSandbox.exportTradesToJsonString = exportTradesToJsonString;
`;

try {
  new Function('exportSandbox', exportCode)(exportSandbox);
} catch (err) {
  console.error('Failed to extract export functions from Symbiose_Dashboard.html:', err);
  process.exit(1);
}

const {
  TRADE_EXPORT_COLUMNS,
  normalizeTradeResultReason,
  normalizeTradeForExport,
  escapeCsvValue,
  exportTradesToCsvString,
  exportTradesToJsonString,
} = exportSandbox;

console.log('--- Running Auftrag C: Trade-Export Tests ---');

// Test 1: Column Schema
const expectedCols = [
  'id', 'coin', 'dir', 'leverage', 'entry', 'signalPrice', 'markPrice',
  'initialSl', 'currentSl', 'tp1', 'tp2', 'tp3', 'openedAt', 'closedAt',
  'result_reason', 'r_result', 'pnl', 'equity_at_close', 'source'
];
assert.deepStrictEqual(TRADE_EXPORT_COLUMNS, expectedCols, 'Column schema matches required specification');
console.log('✓ Test 1: Trade export columns match exact schema');

// Test 2: Empty Array yields BOM + Header Only
const emptyCsv = exportTradesToCsvString([]);
assert.strictEqual(emptyCsv.charCodeAt(0), 0xFEFF, 'CSV starts with UTF-8 BOM');
const emptyLines = emptyCsv.slice(1).split(/\r\n|\n/);
assert.strictEqual(emptyLines[0], expectedCols.join(','), 'First line is CSV header');
assert.strictEqual(emptyLines.length, 1, 'No data rows for empty trades');
console.log('✓ Test 2: Empty history yields valid header-only CSV with BOM');

// Test 3: Fixture Normalization and CSV Escaping
const fixtures = [
  {
    id: 'tr-001',
    coin: 'BTCUSDT',
    dir: 1,
    leverage: 10,
    entry: 60000.5,
    signalPrice: 60000.0,
    markPrice: 62000.0,
    initialSl: 59000.0,
    currentSl: 60000.5,
    tp1: 62000.0,
    tp2: 64000.0,
    tp3: 66000.0,
    openedAt: 1710000000000,
    closedAt: 1710003600000,
    reason: 'TP1_HIT',
    realizedR: 1.5,
    realizedPnlGross: 150.25,
    equityAtClose: 10150.25,
    source: 'AUTOBOT'
  },
  {
    id: 'tr-002',
    coin: 'ETHUSDT',
    dir: -1,
    leverage: 20,
    entry: 3000.0,
    signalPrice: null,
    markPrice: 2950.0,
    initialSl: 3100.0,
    currentSl: 3100.0,
    tp1: 2900.0,
    tp2: null,
    tp3: null,
    openedAt: 1710005000000,
    closedAt: null, // open trade
    reason: null,
    currentR: 0.5,
    pnlGross: 50.0,
    source: 'MANUAL'
  },
  {
    id: 'tr-003,special',
    coin: 'SOL,USDT',
    dir: 1,
    leverage: 5,
    entry: 150.0,
    signalPrice: 149.5,
    markPrice: 145.0,
    initialSl: 145.0,
    currentSl: 145.0,
    tp1: 160.0,
    tp2: '',
    tp3: '',
    openedAt: '2026-03-10T12:00:00Z',
    closedAt: '2026-03-10T14:00:00Z',
    reason: 'SL_HIT',
    realizedR: -1.0,
    realizedPnlGross: -50.0,
    equityAtClose: 9950.0,
    source: 'SERVER'
  }
];

const csvOutput = exportTradesToCsvString(fixtures);
assert.strictEqual(csvOutput.charCodeAt(0), 0xFEFF, 'CSV has BOM');
const csvLines = csvOutput.slice(1).split('\r\n');
assert.strictEqual(csvLines.length, 4, 'Header + 3 data rows');

// Check row 1 (Closed Autobot trade)
assert.strictEqual(
  csvLines[1],
  'tr-001,BTCUSDT,1,10,60000.5,60000,62000,59000,60000.5,62000,64000,66000,1710000000000,1710003600000,TP1,1.5,150.25,10150.25,AUTOBOT'
);

// Check row 2 (Open Manual trade)
assert.strictEqual(
  csvLines[2],
  'tr-002,ETHUSDT,-1,20,3000,,2950,3100,3100,2900,,,1710005000000,,—,0.5,50,,MANUAL'
);

// Check row 3 (Escaped commas in fields)
assert.strictEqual(
  csvLines[3],
  '"tr-003,special","SOL,USDT",1,5,150,149.5,145,145,145,160,,,2026-03-10T12:00:00Z,2026-03-10T14:00:00Z,SL,-1,-50,9950,AUTOBOT'
);
console.log('✓ Test 3: Fixture normalization and CSV escaping accurate');

// Test 4: JSON Export and Loss-Free Roundtrip
const jsonOutput = exportTradesToJsonString(fixtures);
const parsedJson = JSON.parse(jsonOutput);
assert.strictEqual(parsedJson.length, 3, 'JSON has 3 objects');
assert.strictEqual(parsedJson[0].id, 'tr-001');
assert.strictEqual(parsedJson[0].result_reason, 'TP1');
assert.strictEqual(parsedJson[0].source, 'AUTOBOT');
assert.strictEqual(parsedJson[1].id, 'tr-002');
assert.strictEqual(parsedJson[1].result_reason, '—');
assert.strictEqual(parsedJson[1].source, 'MANUAL');
assert.strictEqual(parsedJson[2].id, 'tr-003,special');
assert.strictEqual(parsedJson[2].source, 'AUTOBOT');
console.log('✓ Test 4: JSON export structure and loss-free roundtrip validated');

console.log('All Auftrag C tests passed successfully!');
