# OpenHands Task-Brief: Cross-Device Sync + FVG lifecycle + v1.0.7

Workspace: `/workspace/AURA_Quant_Terminal` (verify actual runtime path before editing)
Host source of truth: `/home/ivo/projects/AURA_Quant_Terminal`
Branch: `main`

## User intent

1. Paper trades must be shared across devices at `http://192.168.8.115:8787/`: a create, close, partial close, single delete, or bulk delete on phone must appear on PC and vice versa.
2. Autobot state/history/config currently included in the existing sync contract must remain synchronized.
3. Fix misleading/overlong FVG rendering. Clarify the "3 bars" rule: it is the three-candle detection pattern, not a universal three-bar lifespan. A detected FVG should be represented once from its formation bar and remain only while unmitigated; its chart box ends at mitigation (or at the latest chart bar when still active), rather than redrawing a duplicate rectangle from every later active bar to the right edge.
4. Prepare semantic patch release v1.0.7, but DO NOT commit, push, tag, or publish a release. Hermes handles review/release/deploy.

## Evidence / diagnosed root causes

### Live sync failure

Live VM responds:

- `GET /serving` -> 200, version `1.0.6`.
- `GET /api/state` with `Host: 192.168.8.115:8787` and `Origin: http://192.168.8.115:8787` -> 403 `ERR_FORBIDDEN_HOST`.
- Same endpoint with loopback Host/Origin -> 200.

The server code in `bitget_relay.py` protects `/api/state` with exact allowed-host validation. Deployment scripts/config have the intended named volume and `AURA_ALLOWED_HOSTS`, but the running v1.0.6 container is missing the LAN allowlist. Code changes must preserve the secure fail-closed behavior; do NOT accept arbitrary Host or Origin. Improve diagnostics/client behavior so sync failures are visible and deterministic, and ensure release/deployment contracts keep the real LAN IP allowlisted.

Current frontend issues:

- `SyncEngine.pull()` silently returns on non-2xx and swallows errors.
- `SyncEngine.push()` is fire-and-forget and swallows all failures.
- Pull only applies `remote[key]` when truthy. Empty arrays are truthy in JS, so trade deletion works if the key exists, but absent server keys need safe bootstrap semantics.
- There is no explicit revision/write coordination. Two devices can race: a slow stale pull or overlapping push can overwrite newer state. Implement robust last-write/revision handling without inventing user accounts or a database.

### FVG issue

Dashboard engine currently detects standard three-candle FVGs correctly:

- Bullish: `low[i] > high[i - 2]`
- Bearish: `high[i] < low[i - 2]`

But it stores only latest active gap into per-bar arrays and renderer loops every bar where that state remains active, drawing each copy from that bar to the chart's right edge. Result: many stacked/overlong rectangles for one zone.

`zones` already exists but age/mitigation lifecycle is incomplete/inaccurate and renderer does not use it. Pine draws fixed `bar_index + 25` boxes and never updates/deletes on mitigation, also misleading. Align JS and Pine semantics where practical.

Research conclusion:

- The "three bars" rule defines formation using candles 1 and 3 around displacement candle 2.
- It does NOT mean every FVG automatically expires after the next 3 bars.
- Common tools track fill/mitigation and often expose a configurable maximum age. For this task, implement lifecycle as: one zone per detection, persist while unmitigated, mark/end on full mitigation; cap retained historical zone objects only for memory/render clarity, not because of a fake universal 3-bar rule.

Sources reviewed by Hermes:

- TrendSpider Learning Center, Fair Value Gap Trading Strategy: https://trendspider.com/learning-center/fair-value-gap-trading-strategy/
- LuxAlgo, Fair Value Gap Market Imbalance Trading Hack: https://www.luxalgo.com/blog/fair-value-gap-market-imbalance-trading-hack/
- TradingView script search descriptions showing three-candle structure, active gap tracking, fill/age controls: https://www.tradingview.com/scripts/search/fair%20value%20gap/

## Required workflow: strict TDD

Do one vertical slice at a time. For every behavior:

1. Add a minimal regression test first.
2. Run it and capture expected RED caused by missing behavior.
3. Implement minimal production change.
4. Run targeted test GREEN.
5. Only then proceed.

Do not weaken tests to make them pass.

## Required changes

### A. State sync correctness and observability

Files likely involved:

- `Symbiose_Dashboard.html`
- `bitget_relay.py`
- `tests/test_relay_full.py`
- add focused JS test(s), preferably `tests/test_cross_device_sync.js`
- `scripts/release_check.py` and `scripts/build_package.py` so new tests are release/package gates
- deployment scripts only if their current contract is incomplete

Acceptance criteria:

1. `/api/state` remains exact same-origin + explicit-host allowlisted; foreign/malformed Host/Origin remain 403.
2. LAN Host/Origin works when `AURA_ALLOWED_HOSTS=192.168.8.115` (existing relay test must remain).
3. Every accepted state write atomically increments `_rev` and returns it.
4. Add optimistic concurrency or equivalent revision-aware merge that prevents a stale client from silently overwriting a newer server key. Keep key-level state contract. A stale expected revision should return a clear conflict response (prefer HTTP 409 with current state/revision), and client should pull/reconcile then retry only when safe.
5. Client startup pulls server state before treating local data as authoritative. If server state is empty for a key and local has meaningful existing data, bootstrap that key to server once; if server key exists as `[]`, remote deletion must win and local must become `[]`.
6. Create/update/delete for active trades and history propagate through the centralized endpoint and render on another polling client. Cover empty-array deletion.
7. Autobot state remains synchronized; avoid a pull calling behavior that pushes the same state back in a loop.
8. Stop silent failure: show a small non-blocking sync status in UI (`verbunden`, `synchronisiert`, `Konflikt`, `offline` or equivalent), but do not expose internals or spam toasts every 2 seconds. Console warning may complement, not replace, visible status.
9. Keep standalone/offline fallback: localStorage still works when backend endpoint is absent.
10. Do not introduce authentication, WebSockets, external services, dependencies, or a database.

Prefer extracting the pure sync decision/merge functions inside engine markers or another testable DOM-free area so Node tests exercise real production logic.

### B. FVG lifecycle/rendering

Files:

- `Symbiose_Dashboard.html`
- `Symbiose_Signal_System_v1.pine`
- focused tests in `tests/test_engine_full.js` or a new focused test, wired into gates

Acceptance criteria:

1. Detection remains exact three-candle pattern.
2. Each detected FVG is stored exactly once with at least: direction, top, bottom, formation/start index or timestamp, active/mitigated state, and mitigation/end index when filled.
3. Full mitigation semantics match current engine boundaries:
   - bullish gap mitigated when a later low reaches/crosses bottom
   - bearish gap mitigated when a later high reaches/crosses top
4. Formation candle itself must not immediately mitigate its own newly created gap.
5. Renderer draws one box per zone from formation index to mitigation index, or latest visible bar while active. Do not draw one duplicate per active state bar. Clip to visible range.
6. Keep a bounded zone collection (existing 8 may remain if intentional) and ensure scoring/dynamic TP consume latest active valid gap, not a mitigated one.
7. Pine visual boxes follow the same lifecycle: extend the active box, stop/delete/mark it upon full mitigation rather than leaving a fixed 25-bar rectangle. Avoid repaint/lookahead.
8. Add deterministic bullish and bearish tests for formation, persistence >3 bars while unmitigated, and ending on mitigation. This specifically proves that "3 bars" is formation, not forced lifespan.

### C. Patch release metadata

Bump all version-bearing artifacts consistently to `1.0.7`, including at least:

- `VERSION`
- `bitget_relay.py` docs, `/serving`, log strings
- `README.md`
- `Symbiose_Dashboard.html` footer and release-notes overlay
- `SYMBIOSE_Tutorial.html`
- `Dockerfile`
- version-specific tests

Update release notes to describe cross-device synchronization reliability and corrected FVG lifecycle. Keep claims factual; no profitability claim.

## Non-goals / constraints

- No trade execution. App remains read-only research + paper simulation.
- No unrelated UI redesign or refactor.
- No changes to personal Tailscale/webhook/private deployment receiver files outside repo.
- Never read/print secrets or `.env` values.
- Do not commit, push, tag, or publish.
- Keep dependencies unchanged unless absolutely required (expected: none).

## Verification commands

Run targeted tests during TDD, then at minimum:

```bash
pytest
node tests/test_engine_full.js
python3 scripts/release_check.py
python3 scripts/build_package.py --force
```

If browser gate is expensive, still run exact release gate once. Report any known `MODEL_NO_EVIDENCE` honestly; it is not permission to claim market edge.

## Final report required

Return:

- exact files changed
- RED tests observed and why they failed
- GREEN commands and actual counts/exit codes
- design explanation for sync conflicts/bootstrap/deletion
- design explanation for FVG lifetime versus 3-candle formation
- anything still unverified
