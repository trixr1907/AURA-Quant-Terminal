'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('Symbiose_Dashboard.html', 'utf8');
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
assert(scriptMatch, 'Dashboard script block missing');

// ---------------------------------------------------------------------------
// 0. Standalone DOM-free extraction
// ---------------------------------------------------------------------------
const sessConfigStart = html.indexOf('const SMC_UTC_SESSIONS = [');
assert(sessConfigStart >= 0, 'SMC_UTC_SESSIONS definition not found in HTML');
const sessFuncStart = html.indexOf('function getCurrentSessionInfo(', sessConfigStart);
assert(sessFuncStart >= 0, 'getCurrentSessionInfo definition not found in HTML');
const sessFuncEnd = html.indexOf('\nfunction setStatus(', sessFuncStart);
assert(sessFuncEnd >= 0, 'End of getCurrentSessionInfo not found');
const isolatedSource = html.slice(sessConfigStart, sessFuncEnd);

const ctx = { Date };
vm.createContext(ctx);
vm.runInContext(
  `${isolatedSource}\nthis.SMC_UTC_SESSIONS = SMC_UTC_SESSIONS; this.getCurrentSessionInfo = getCurrentSessionInfo;`,
  ctx,
);
assert.strictEqual(ctx.SMC_UTC_SESSIONS.length, 6, 'Isolated extract must have 6 sessions');
assert.strictEqual(typeof ctx.getCurrentSessionInfo, 'function', 'Isolated extract must have getCurrentSessionInfo');
assert.strictEqual(ctx.getCurrentSessionInfo(new Date(Date.UTC(2026, 8, 4, 8, 0))).code, 'LDN_KZ');

// ---------------------------------------------------------------------------
// 1. Definitionen & Single Source of Truth
// ---------------------------------------------------------------------------
assert(Array.isArray(ctx.SMC_UTC_SESSIONS), 'SMC_UTC_SESSIONS array must be defined');
assert.strictEqual(ctx.SMC_UTC_SESSIONS.length, 6, 'SMC_UTC_SESSIONS must define exactly 6 windows');
assert.strictEqual(typeof ctx.getCurrentSessionInfo, 'function', 'getCurrentSessionInfo must be a function');

// Sessions contiguous & monotonic
let prevEnd = 0.0;
for (const s of ctx.SMC_UTC_SESSIONS) {
  assert.strictEqual(s.start, prevEnd, `Session ${s.code} start must match previous end ${prevEnd}`);
  assert(s.end > s.start, `Session ${s.code} end must be greater than start`);
  assert(typeof s.name === 'string' && s.name.length > 0, `Session ${s.code} must have a name`);
  assert(typeof s.flag === 'string' && s.flag.length > 0, `Session ${s.code} must have a flag`);
  assert(typeof s.phase === 'string' && s.phase.length > 0, `Session ${s.code} must have a phase`);
  assert(typeof s.color === 'string' && s.color.length > 0, `Session ${s.code} must have a color`);
  assert(typeof s.badge === 'string' && s.badge.length > 0, `Session ${s.code} must have a badge`);
  prevEnd = s.end;
}
assert.strictEqual(prevEnd, 24.0, 'Last session must end at 24.0 UTC');

// ---------------------------------------------------------------------------
// 2. Grenztests (10 geforderte Grenzwerte)
// ---------------------------------------------------------------------------
function utcDate(hours, minutes, seconds = 0, ms = 0) {
  return new Date(Date.UTC(2026, 8, 4, hours, minutes, seconds, ms));
}

const boundaryTests = [
  { time: [6, 59], expectedCode: 'ASIA', label: '06:59 -> ASIA' },
  { time: [7, 0], expectedCode: 'LDN_KZ', label: '07:00 -> LDN_KZ' },
  { time: [9, 59], expectedCode: 'LDN_KZ', label: '09:59 -> LDN_KZ' },
  { time: [10, 0], expectedCode: 'PRE_NY', label: '10:00 -> PRE_NY' },
  { time: [12, 29], expectedCode: 'PRE_NY', label: '12:29 -> PRE_NY' },
  { time: [12, 30], expectedCode: 'NY_KZ', label: '12:30 -> NY_KZ' },
  { time: [15, 29], expectedCode: 'NY_KZ', label: '15:29 -> NY_KZ' },
  { time: [15, 30], expectedCode: 'LDN_CLOSE', label: '15:30 -> LDN_CLOSE' },
  { time: [16, 29], expectedCode: 'LDN_CLOSE', label: '16:29 -> LDN_CLOSE' },
  { time: [16, 30], expectedCode: 'OFF_HOURS', label: '16:30 -> OFF_HOURS' },
];

for (const { time, expectedCode, label } of boundaryTests) {
  const d = utcDate(time[0], time[1]);
  const res = ctx.getCurrentSessionInfo(d);
  assert.strictEqual(res.code, expectedCode, `Boundary test failed: ${label} (got ${res ? res.code : 'null'})`);
}

// ---------------------------------------------------------------------------
// 3. Killzone-Semantik & Session-Typen
// ---------------------------------------------------------------------------
const sessionByCode = Object.fromEntries(ctx.SMC_UTC_SESSIONS.map(s => [s.code, s]));

// London & NY Open Killzones
assert.strictEqual(sessionByCode.LDN_KZ.isKillzone, true, 'London Open must have isKillzone === true');
assert.strictEqual(sessionByCode.LDN_KZ.sessionType, 'killzone', 'London Open sessionType must be killzone');
assert.strictEqual(sessionByCode.LDN_KZ.chartShade, 'rgba(34, 197, 94, 0.05)', 'London Open must shade green');

assert.strictEqual(sessionByCode.NY_KZ.isKillzone, true, 'New York Open must have isKillzone === true');
assert.strictEqual(sessionByCode.NY_KZ.sessionType, 'killzone', 'New York Open sessionType must be killzone');
assert.strictEqual(sessionByCode.NY_KZ.chartShade, 'rgba(56, 189, 248, 0.05)', 'New York Open must shade cyan');

// Asia, Pre-NY, London Close, Off-Hours
assert.strictEqual(sessionByCode.ASIA.isKillzone, false, 'Asia session must not be an entry killzone (isKillzone === false)');
assert.strictEqual(sessionByCode.ASIA.chartShade, null, 'Asia session must not shade');

assert.strictEqual(sessionByCode.PRE_NY.isKillzone, false, 'Pre-NY Lunch must not be an entry killzone (isKillzone === false)');
assert.strictEqual(sessionByCode.PRE_NY.chartShade, null, 'Pre-NY Lunch must not shade');

assert.strictEqual(sessionByCode.LDN_CLOSE.isKillzone, false, 'London Close is Session-Close and must not be an entry killzone (isKillzone === false)');
assert.strictEqual(sessionByCode.LDN_CLOSE.sessionType, 'close', 'London Close sessionType must be close');
assert.strictEqual(sessionByCode.LDN_CLOSE.chartShade, null, 'London Close must not shade');

assert.strictEqual(sessionByCode.OFF_HOURS.isKillzone, false, 'Off-Hours must not be an entry killzone (isKillzone === false)');
assert.strictEqual(sessionByCode.OFF_HOURS.chartShade, null, 'Off-Hours must not shade');

// ---------------------------------------------------------------------------
// 4. Chart-Shading: Single Source of Truth, keine duplizierten UTC-Blöcke
// ---------------------------------------------------------------------------
// Extract chart render function or verify chart shading logic
const chartShadeSection = html.slice(html.indexOf('// Session Killzones'), html.indexOf('// Volumen', html.indexOf('// Session Killzones')));
assert(chartShadeSection.includes('getCurrentSessionInfo') || chartShadeSection.includes('SMC_UTC_SESSIONS'),
  'Chart shading must use getCurrentSessionInfo or SMC_UTC_SESSIONS');
assert(chartShadeSection.includes('chartShade'), 'Chart shading must use chartShade property');
assert(!chartShadeSection.includes('7.0'), 'Chart shading must not contain hardcoded 7.0 threshold');
assert(!chartShadeSection.includes('10.0'), 'Chart shading must not contain hardcoded 10.0 threshold');
assert(!chartShadeSection.includes('12.5'), 'Chart shading must not contain hardcoded 12.5 threshold');
assert(!chartShadeSection.includes('15.5'), 'Chart shading must not contain hardcoded 15.5 threshold');

// ---------------------------------------------------------------------------
// 5. Tooltip & Bar-Texte: Pflichtinhalte & Barrierefreiheit
// ---------------------------------------------------------------------------
const requiredPhrases = [
  'UTC bleibt ganzjährig gleich; deutsche Ortszeit verschiebt sich mit Sommer-/Winterzeit.',
  'Killzone = typisches Liquiditäts- und Volatilitätsfenster, kein automatisches Kauf-/Verkaufssignal und kein eigenes GO-Gate.',
  '07:00–10:00',
  '12:30–15:30',
  '15:30–16:30',
];

for (const phrase of requiredPhrases) {
  assert(html.includes(phrase), `Dashboard HTML must contain tooltip phrase: "${phrase}"`);
}

// Accessibility check on the macro session element / tooltip
assert(html.includes('aria-label="Info zu SMC Sessions und Killzones"') || html.includes('aria-label="SMC Session Info"') || html.includes('aria-label="Makro-Wetter"'),
  'Accessible aria label for macro/session info must be present');
assert(html.includes('title="UTC bleibt ganzjährig gleich'), 'Tooltip title attribute must be present');

// ---------------------------------------------------------------------------
// 6. UTC-Uhr & Last Update: Zentraler UTC-Formatter & Zeitzonen-Unabh\u00e4ngigkeit
// ---------------------------------------------------------------------------
const utcTimeFuncStart = html.indexOf('function formatUtcTime(');
assert(utcTimeFuncStart >= 0, 'formatUtcTime definition not found in HTML');
const utcClockFuncStart = html.indexOf('function fmtUTCClock(');
assert(utcClockFuncStart >= 0, 'fmtUTCClock definition not found in HTML');
const utcClockFuncEnd = html.indexOf('\nfunction fmtFullDateTime(', utcClockFuncStart);
assert(utcClockFuncEnd >= 0, 'End of UTC formatting helper functions not found');
const utcSource = html.slice(utcTimeFuncStart, utcClockFuncEnd);

const utcCtx = { Date };
vm.createContext(utcCtx);
vm.runInContext(`${utcSource}\nthis.formatUtcTime = formatUtcTime; this.fmtUTCTime = fmtUTCTime; this.fmtUTCDate = fmtUTCDate; this.fmtUTCClock = fmtUTCClock;`, utcCtx);

assert.strictEqual(typeof utcCtx.formatUtcTime, 'function', 'formatUtcTime must be a function');
assert.strictEqual(typeof utcCtx.fmtUTCTime, 'function', 'fmtUTCTime must be a function');
assert.strictEqual(typeof utcCtx.fmtUTCDate, 'function', 'fmtUTCDate must be a function');
assert.strictEqual(typeof utcCtx.fmtUTCClock, 'function', 'fmtUTCClock must be a function');

// Test fixed timestamps and verify host timezone does not influence result
const fixedDate1 = new Date(Date.UTC(2026, 8, 4, 14, 5, 9)); // 2026-09-04 14:05:09 UTC
assert.strictEqual(utcCtx.formatUtcTime(fixedDate1), '14:05:09', 'formatUtcTime must return exact HH:MM:SS');
assert.strictEqual(utcCtx.fmtUTCTime(fixedDate1), '14:05:09', 'fmtUTCTime must return exact UTC time');
assert.strictEqual(utcCtx.fmtUTCDate(fixedDate1), '04.09.2026', 'fmtUTCDate must return exact UTC date');
assert.strictEqual(utcCtx.fmtUTCClock(fixedDate1), '14:05:09 UTC · 04.09.2026', 'fmtUTCClock must return exact UTC clock format');

// Edge of day transition: 23:59:59 UTC
const fixedDate2 = new Date(Date.UTC(2026, 11, 31, 23, 59, 59));
assert.strictEqual(utcCtx.fmtUTCTime(fixedDate2), '23:59:59', 'fmtUTCTime edge of day UTC time');
assert.strictEqual(utcCtx.fmtUTCDate(fixedDate2), '31.12.2026', 'fmtUTCDate edge of year UTC date');
assert.strictEqual(utcCtx.fmtUTCClock(fixedDate2), '23:59:59 UTC · 31.12.2026', 'fmtUTCClock edge of year format');

// Edge of day start: 00:00:00 UTC
const fixedDate3 = new Date(Date.UTC(2026, 0, 1, 0, 0, 0));
assert.strictEqual(utcCtx.fmtUTCTime(fixedDate3), '00:00:00');
assert.strictEqual(utcCtx.fmtUTCDate(fixedDate3), '01.01.2026');
assert.strictEqual(utcCtx.fmtUTCClock(fixedDate3), '00:00:00 UTC · 01.01.2026');

// Proof with simulated hostile non-UTC Date prototype:
// Even if toTimeString, toLocaleDateString, and getTimezoneOffset return non-UTC values,
// fmtUTCTime and fmtUTCClock must strictly use getUTC* methods and remain immune.
const hostileDate = new Date(Date.UTC(2026, 8, 4, 8, 30, 0));
hostileDate.toTimeString = () => '10:30:00 GMT+0200';
hostileDate.toLocaleDateString = () => '05.09.2026';
hostileDate.getTimezoneOffset = () => -120;
assert.strictEqual(utcCtx.formatUtcTime(hostileDate), '08:30:00', 'Must ignore hostile toTimeString');
assert.strictEqual(utcCtx.fmtUTCTime(hostileDate), '08:30:00', 'Must ignore hostile toTimeString');
assert.strictEqual(utcCtx.fmtUTCDate(hostileDate), '04.09.2026', 'Must ignore hostile toLocaleDateString');
assert.strictEqual(utcCtx.fmtUTCClock(hostileDate), '08:30:00 UTC · 04.09.2026', 'Must ignore hostile local timezone');

// Ensure no toTimeString() is used in dashboard script for clock or lastupd
assert(!html.includes('toTimeString()'), 'Dashboard script must not use toTimeString()');

console.log('PASS SMC UTC sessions and timezone-independent UTC clock suite');
