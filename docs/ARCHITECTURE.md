# AURA v3 — Zielarchitektur (evidenzbasierte Neuentwicklung)

**Status:** Entwurf v1, 2026-09-17 · **Autor:** Principal Engineering (R40) · **Basis:** `docs/AUDIT.md`, `docs/research/BASELINE_R40_20260917.md`
**ADRs:** `docs/adr/ADR-0001` bis `ADR-0005` (Stack, Datenbank, Scheduler, Auth, Update-Verfahren)

## 1. Leitprinzipien

1. **Eine kanonische Produktionsimplementierung je Berechnung** (Python-Paket `aura/core`). Browser, Runner und Backtester rufen dieselbe Engine auf. Die JS-Alt-Engine und Pine bleiben als **Referenz-Orakel für Paritätstests**, nicht als zweite Produktionswahrheit.
2. **Server-authoritative state:** Der Server besitzt Konfiguration, Datenstand, Paper-Trades, Historie, Modellversion. Browser sind Clients.
3. **Fail-closed:** Fehlende/uneindeutige Daten blockieren neue Paper-Entries; Schutzmechanismen dürfen Entries blockieren, während Verwaltung bestehender Positionen weiterläuft.
4. **Pragmatik:** Modularer Monolith + ein Worker. Kein Kubernetes, kein Service-Mesh, keine Microservices.

## 2. Zielbild

```text
                       Bitget REST v2 / WebSocket (public)
                                │
                ┌───────────────┴────────────────┐
                ▼                                ▼
   ┌──────────────────────┐        ┌──────────────────────────┐
   │  Container: worker   │        │  Container: app          │
   │  - MarketDataAdapter │        │  - HTTP API v1 (FastAPI) │
   │    (WS+REST, Gaps,   │        │  - AuthN/AuthZ, CSRF     │
   │    Backfill, Dedup)  │        │  - Control Plane         │
   │  - Scanner (Radar)   │        │  - Web UI (responsive)   │
   │  - PaperRunner (FSM) │        │  - SSE für Live-Updates  │
   │  - SignalCenter/ntfy │        │                          │
   └─────────┬────────────┘        └───────────┬──────────────┘
             │          SQLite (WAL) auf Named Volume          │
             └───────────────────┬─────────────────────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │  Persistenz + Migration │
                    │  (Single-Writer-Regeln) │
                    └─────────────────────────┘
```

**Warum zwei Container statt einer:** Trennung von „darf nie blockiert werden" (Datensammlung, Runner) und „darf neu starten ohne Handelslogik zu gefährden" (Web/API). Geteilte SQLite-Datei (WAL) mit dokumentierten Single-Writer-Regeln je Tabelle. Beide Container aus demselben Image, gleiche Engine-Version — keine Versionsdrift.

**Warum kein externer DB-Server:** Single-User, Single-VM. SQLite WAL liefert ACID, lesende parallele Zugriffe und triviale konsistente Backups (`.backup`-API auf Dateiebene). PostgreSQL wäre ein zusätzlicher SPOF und Betriebsaufwand ohne nachgewiesenen Bedarf (ADR-0002).

## 3. Verantwortungsmodule (logisch getrennt, `aura/` Python-Paket)

| Modul | Verantwortung | Behebt Befund |
|---|---|---|
| `aura.core.indicators` | EMA/ATR/ADX/RSI/SuperTrend/VWAP/CVD(Proxy)/SMC — deterministisch, Decimal wo geldkritisch | D-01 |
| `aura.core.scoring` | Confluence-Score, Makro-Adjust, MTF | D-01 |
| `aura.core.risk` | Kelly, Sizing, Leverage-Schätzung (als Schätzung gelabelt), Risk-Gates | Q-06 |
| `aura.core.stats` | DSR, PAVA, Walk-Forward, Sharpe/Sortino (365d-Annualisierung dokumentiert) | Q-05, Q-10 |
| `aura.data.bitget` | REST+WS-Adapter, Rate-Limit, Retries/Backoff/Jitter, Reconnect | — |
| `aura.data.quality` | Schema-Validierung, Gap-Erkennung, Backfill, Dedup, geschlossene vs laufende Kerzen, Provenienz (Quelle, Event-/Empfangszeit, UTC) | D-02 |
| `aura.backtest` | Evidenzpipeline, Kostenmodell inkl. Funding-Carry, Intrabar-Policy (konservativ, dokumentiert) | Q-07 |
| `aura.runner` | Paper-Runner als Zustandsmaschine (STARTING→WARMING_UP→RUNNING→DEGRADED→HALTED→RECOVERING), TP-Exits, Equity-Accounting, Not-Halt | Q-01..Q-04, S-04 |
| `aura.store` | SQLite-Schema, Migrationen, Import aus Alt-State (Pflicht: Bestandsdaten migrieren) | D-03 |
| `aura.api` | Versionierte REST-API v1 + SSE, Auth, CSRF, serverseitige Validierung | S-01..S-03 |
| `aura.notify` | ntfy serverseitig, dedupliziert, Zustellstatus, keine Secrets im Payload | S-03 |
| `aura.ui` | Responsive Weboberfläche (Design-Tokens aus `docs/brand_design.md`) | U-01..U-06 |

## 4. Kanonische Engine & Paritätsstrategie

1. **Phase A (Orakel-Einfrierung):** Die JS-Engine erzeugt Golden-Fixtures (Input-Kerzen → Scores/Signale/Backtest-Trades) mit Hash und Provenienz. Bereits vorhandene Golden-Master (`tests/fixtures/golden/`) werden übernommen.
2. **Phase B (Python-Port):** `aura.core` wird gegen diese Fixtures getestet (absolute/relative Toleranzen fachlich begründet, z. B. Float-Summierungsreihenfolge). Erwartungswerte stammen aus unabhängigen Referenzen (handberechnete Mini-Fixtures, `tests/reference_backtest.py`), nie aus der zu prüfenden Funktion.
3. **Phase C (Cutover):** Erst wenn Parität je Modul bewiesen ist, ersetzt die Python-Engine die JS-Pfade. Pine-Abweichungen (andere Laufzeit, kumulative Indikatoren ab Listing) bleiben dokumentiert und mit Paritätstests begrenzt.

## 5. Laufzeit-Verhalten

- **Zustandsmaschine Runner:** `STARTING → WARMING_UP → RUNNING ⇄ DEGRADED → HALTED`, `RECOVERING` nach Crash. Jeder Übergang wird mit Grund und UTC-Zeit persistiert und in der UI angezeigt.
- **Not-Halt:** Bestätigungspflichtiger Control-Plane-Befehl `POST /api/v1/runner/halt` (idempotent, mit Command-ID). Wirkung: sofort keine neuen Entries; bestehende Positionen werden nach dokumentierter Policy weiter verwaltet (SL/TP-Überwachung läuft). Separater, ebenfalls bestätigungspflichtiger Befehl für „alle Positionen schließen". Kein mehrdeutiges „Stop".
- **Konfiguration:** Serverseitige Schema-Validierung (Allowlist, Typen, Wertebereiche — übernimmt die Anforderungen aus dem Nutzer-WIP-Test `test_bot_config_security.py`). Revisionen + angeforderte vs. aktive Revision in der UI. Unterscheidung: Anzeigeoptionen / neue Strategieparameter (wirken auf neue Entries) / positionswirksame Änderungen (explizit bestätigt, nie rückwirkend).
- **Datenprovenienz:** Jede Kerze/jedes Signal speichert Quelle, Instrument, Event-Zeit, Empfangszeit (UTC), Verarbeitungsversion. Jede Anzeige zeigt as-of-Zeit, Datenalter, Quelle, Modellversion, Blockierungsgrund.
- **Benachrichtigungen:** ntfy serverseitig, dedupliziert (Claims in DB), mit Zustellstatus, ohne Secrets.

## 6. Sicherheitsmodell (Zugriff: LAN + WireGuard/Tailscale, kein offener Port)

- Einziger exponierter Dienst: `app` (Web/API) auf dem Docker-Internen Netz; DB-Datei nur im Volume, kein DB-Port.
- Authentifizierung: Single-User-Login (Erstpasswort beim ersten Start setzen, kein Default), Session-Cookie (HttpOnly, SameSite=Strict), Login-Rate-Limit, CSRF-Token für alle mutierenden Endpunkte; Bearer-Token für nicht-browserfähige Clients. Details: ADR-0004.
- Serverseitige Validierung aller Eingaben; CSP ohne `unsafe-inline` für das neue UI; kein Secret in Git/Logs/URLs/Frontend.
- Internet-Exposition wäre eine separate Sicherheitsabnahme (MFA etc.) — nicht Teil dieses Mandats.

## 7. Migrationsfolge (Bestandsinstallation → v3)

Pflicht: Laufzeit-State der Bestandsinstallation wird übernommen (Stakeholder-Entscheidung 2026-09-17).

1. **M-0:** Bestands-State read-only sichern (`aura_shared_state.json`, `aura_signal_center_state.json`, `shadow_log.jsonl`, `shadow_stats.json`, `runner_health.json`, Ledger-Dateien) mit SHA-256-Provenienz.
2. **M-1:** Importer `aura.store.legacy_import`: JSON-v2-Schema → SQLite (Trades, Historie, Config, Claims, Shadow-Log append-only). Idempotent, mit Dry-Run und Vollständigkeitsreport (Anzahlen, Zeiträume, Hashes).
3. **M-2:** Parallelbetrieb: v3 sammelt Daten, Bestands-v2.5 läuft weiter (kein Doppel-Trading: v3-Runner erst nach Cutover aktiv).
4. **M-3:** Cutover: v2.5-Container stoppen, v3-Runner aktivieren, Verifikation (Positionen/Historie/Equity stimmen mit Import-Report überein).
5. **M-4:** Rollback-Pfad: v2.5-Image und unveränderte Alt-State-Kopie bleiben vorhanden; Rollback = Compose auf altes Tag zurück + Alt-State einspielen. Ledger/Lockbox werden nie angefasst.

## 8. Priorisierter Implementierungsplan (vertikale, testbare Schritte)

| # | Schritt | Abnahme |
|---|---|---|
| P1 | Paket-Gerüst `aura/`, DB-Schema + Migrationen, Legacy-Importer (Dry-Run gegen gesicherten Alt-State) | Import-Report reproduzierbar; Tests grün |
| P2 | `aura.core` Indikatoren + Scoring mit Golden-Parität gegen JS-Engine | Paritätsreport je Modul, Toleranzen begründet |
| P3 | `aura.data` Bitget-Adapter + Qualität (Gaps, Backfill, Dedup, Provenienz) | Offline-Fixture-Tests + gekennzeichnete Online-Integration |
| P4 | `aura.runner` FSM + korrektes Trade-Management (TP-Exits, Equity-PnL, Exit-Gründe, Not-Halt) + Backtest/Replay-Parität | Regressionstests für Q-01..Q-04; deterministische Replay-Parität |
| P5 | `aura.api` + Auth + Control Plane + Config-Validierung | Negative Auth-/Validierungstests (übernimmt WIP-Testfälle) |
| P6 | `aura.ui` responsive Ansichten (Status, Radar, Positionen, Historie, Evidenz, Einstellungen, Audit) | E2E inkl. mobiler Viewports, Touch/Keyboard |
| P7 | Compose-Härtung, Backup/Restore, Runbook, Autoheal, Soak-Harness | Restore-Test in isolierter Umgebung; Soak 24h oder NOT_RUN |
| P8 | Evidenz: Acceptance-Matrix, Release-Evidence, Statusachsen | Jeder Claim mit Befehl+Exit+Artefakt |

## 9. Bewusste Produktänderungen gegenüber v2.5.0

- Browser berechnet **keine** Signale mehr (bisher volle JS-Engine im Browser) → serverseitige Engine; UI wird Client. Pine bleibt externes Visualisierungs-Artefakt.
- Shadow-Collector, Radar, Confluence, Risk-Gates, Paper-Historie, ntfy, TradingView-Bridge, Tutorial: **beibehalten** (Implementierung neu, Funktion erhalten).
- TradingView-Desktop-Bridge entfällt auf dem Server (kein Desktop vorhanden); ersetzt durch kopierbare Links/Overlays mit mobile-fähigem Fallback.
- `MODEL_NO_EVIDENCE` bleibt die Ausgangswahrheit; v3 ändert keine Signal-Logik, nur Korrektheit der Ausführung (Q-01..Q-04 sind Ausführungsbugs, keine Edge-Verbesserung — Ledger-Klassifikation: Prozess-Fix, kein Modellexperiment; dokumentiert bei Umsetzung).
