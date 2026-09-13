# AURA Quant Terminal — Runde 17 Schlussbericht (v1.4.0)

## Zusammenfassung

Runde 17 umfasst 8 UX- und Infrastruktur-Verbesserungen (PF-28 bis PF-35) ohne
Score-, Sizing- oder Gate-Änderungen. Alle Software-Gates bestehen; das Quant-Modell
bleibt unverändert (MODEL_NO_EVIDENCE wie erwartet).

---

## Git-Belege

| Artifact | Wert |
|----------|------|
| Produkt-Branch | `feat/round17-v1.4.0` |
| Produkt-Commit | `3e09b9a` |
| Merge-Commit main | `c4701c9` |
| Merge-Parents | `438e883` (prev main) + `3e09b9a` (feature) |
| Tag | `v1.4.0` → peelt auf `c4701c9` |
| PR | [#21](https://github.com/trixr1907/AURA-Quant-Terminal/pull/21) |
| GitHub Release | [v1.4.0](https://github.com/trixr1907/AURA-Quant-Terminal/releases/tag/v1.4.0) |
| Asset SHA-256 | `b402cd08a48eb283f899d94f4cfb37ff7100ca03df0dde54dc058350a1410377` |
| Asset (heruntergeladen) | `b402cd08a48eb283f899d94f4cfb37ff7100ca03df0dde54dc058350a1410377` ✓ |

---

## CI-Check-Ergebnisse

| Check | Status |
|-------|--------|
| Test Suite & Quality Gates | PASS |
| Socket Security: Project Report | PASS |
| Socket Security: Pull Request Alerts | PASS |
| SonarCloud Code Analysis | FAIL (kein required check, historisch) |
| Sourcery review | SKIPPING |

---

## Implementierte Features (PF-28 bis PF-35)

### PF-28 — BTC Makro-Regime-Transparenz

- BTC-Trend und Regime-Score dauerhaft im Dashboard sichtbar
- Konfidenz-Badges mit Quell-Transparenz
- Test: `tests/test_btc_regime_transparency.js` — 4/4 PASS

### PF-29 — Gemeinsame Trade-Karte

- `renderTradeCard(t, m, px, index, options)` als einheitliche Komponente
- Autobot-Extras (Score, DSR, Time-Stop, Bot-Management) als optionale Sektion
- Kein doppelter HTML-Template-String mehr
- Test: `tests/test_pf29_trade_card.js` — PASS

### PF-30 — Canvas-Positionslinien + direkter TradingView-Webchart

- Entry (neutral), SL (rot), TP1-3 (grün abgestuft) auf eigenem Canvas
- `buildTradingViewChartUrl()` → `https://www.tradingview.com/chart/?symbol=BITGET:<SYM>.P`
- `openTradingViewChart()` öffnet via `window.open` direkt, kein Relay-POST
- Desktop-Protokoll (`buildTradingViewDesktopUrl`, `launchTradingViewDesktop`, `openInTradingView`) entfernt
- Test: `tests/test_pf30_chart_positions.js` — PASS

### PF-31 — Zero-Transient-Fix

- Root Cause: `applyServerState()` überschrieb aktive Trades blind mit Remote-Leerstand
- Fix: ID-basiertes Reconcile; DOM-Karten atomisch mit `replaceChildren`, nie clear+fill
- Test: `tests/test_pf31_zero_transient.js` — PASS
- Cross-Device-Sync: 25/25 PASS

### PF-32 — Fokus-Chart-Retry mit Fehlerband

- `App.chartLoad` State: idle / loading / error / ready
- Stale-while-revalidate: alter Chart bleibt bis neues Laden erfolgreich
- Sichtbares Fehlerband mit Button „Erneut laden"
- Backoff-Retry mit `.unref()` und Generationsschutz
- Test: `tests/test_pf32_focus_chart_retry.js` — PASS

### PF-33 — Opt-in ntfy Push-Benachrichtigungen

- `AURA_NTFY_URL` ENV-Variable (leer = deaktiviert)
- `_ntfy_notify(title, body)`: fire-and-forget Daemon-Thread
- `notify_trade_closed(trade)`: bei delete-Mutation auf aktive Trades
- Nur http/https-URLs akzeptiert; Fehler nur als `log.debug`
- Deployment-Runbook: `docs/deployment/DOCKER_GUIDE.md` ergänzt
- Test: `tests/test_pf33_ntfy.py` — 12/12 PASS

### PF-34 — CDN-Asset-Logos mit Fallback-Cache

- CDN: `https://cdn.jsdelivr.net/npm/cryptocurrency-icons@latest/svg/color/<base>.svg`
- `markCdnLogoBad()` / `isCdnLogoKnownBad()` — localStorage-Cache für 404s
- `applyCoinLogo(imgEl, badgeEl, symbol)` — Progressive Enhancement
- Kein blockierender Netzwerkaufruf im Renderpfad
- Test: `tests/test_pf34_asset_logos.js` — 11/11 PASS

### PF-35 — Logo-Animation mit prefers-reduced-motion

- `@keyframes auraGlow { 0%,100% { opacity:1; transform:scale(1) } 50% { opacity:.82; transform:scale(1.03) } }`
- Nur `opacity` und `transform` — keine Layout-Properties
- `@media(prefers-reduced-motion:reduce) { * { animation:none!important } }` ergänzt
- Test: `tests/test_pf35_logo_animation.js` — 10/10 PASS

---

## Verifikationsmetriken

| Metrik | Wert |
|--------|------|
| pytest | 236 passed, 57 subtests |
| JS-Suiten | alle 0 failures |
| `innerHTML` count | 51 (Budget eingehalten) |
| `git diff --check` | sauber |
| `release_check.py` | SOFTWARE_GO / MODEL_NO_EVIDENCE |
| Pre-Commit-Review | PASS (kein Secret, kein eval, kein neues innerHTML) |
| Symbiose_Dashboard.html SHA-256 | `ceb0d80b77644269e03a44034f551b8bb52c463bca1d2117d03c1cccc6dbf253` |

---

## Quant-Guard-Attestierung

Keine der folgenden Kategorien wurde verändert:

- Score-Berechnung oder Score-Gates
- Sizing-Logik oder Kelly-Formeln
- Walk-Forward-Parameter oder Fold-Geometrie
- Autobot-Einstiegsbedingungen oder DSR-Schwellenwerte
- Ledger-Einträge oder Trial-Zählungen

Alle neuen Features sind rein UX- und Infrastruktur-seitig (PF-28 bis PF-35).

---

## Geänderte Dateien (Auszug)

| Datei | Änderung |
|-------|----------|
| `Symbiose_Dashboard.html` | PF-28–PF-35 Implementierungen |
| `bitget_relay.py` | PF-33 ntfy + v1.4.0 Docstring |
| `docs/deployment/DOCKER_GUIDE.md` | ntfy-Deployment-Runbook |
| `VERSION` | 1.3.2 → 1.4.0 |
| `tests/test_pf{28–35}*.{js,py}` | Neue TDD-Tests |
| `tests/test_tradingview_*.js` | Updates für PF-30 (Desktop entfernt) |
| `tests/test_chart_liveness_ticker.js` | positionState im RenderCache-Key |
| `tests/test_dirty_flag_rendering.js` | Canvas-Mock erweitert (save/restore) |

---

_Bericht erstellt: 2026-09-13 | Branch: docs/round17-final-report_
