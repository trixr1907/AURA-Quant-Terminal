# AURA — Documentation & Architecture Master Index

Willkommen im zentralen Dokumentations-Hub von **AURA v1.8.1 — Confluence Terminal**.
Dieses Verzeichnis strukturiert alle Spezifikationen, mathematischen Validierungen, Deployment-Leitfäden, Brand-Assets und Changelogs nach SOTA Best Practices.

---

## Dokumentations-Übersicht

```
docs/
├── README.md                  # Zentraler Dokumentations-Index (diese Datei)
├── architecture.md            # Systemarchitektur & Relay-Pipeline
├── brand_design.md            # Design Tokens, Dark-Mode & Asset-Specs
├── CHANGELOG.md               # Kurzindex (vollständiger Changelog: ROOT/CHANGELOG.md)
├── deployment/                # Deployment & Infrastruktur  [Pflege: Ops/Infra]
│   ├── DOCKER_GUIDE.md        # Docker Compose & Standalone Container
│   ├── SERVER_BOT_GUIDE.md    # Server-Modus & Headless Paper-Autobot (24/7 Signale)
│   ├── PROXMOX_GUIDE.md       # Proxmox VE, LXC & Tailscale Funnel Webhooks
│   ├── NTFY_GUIDE.md          # Push-Benachrichtigungen (Deploy-Alerts, Handy & PC)
│   ├── webhook-incident-20260912.md  # Incidentbericht 2026-09-12
│   └── webhook-incident-20260913.md  # Incidentbericht 2026-09-13 (v1.5.1 Health-Race)
├── releases/                  # Release-Notes aller Versionen (v1.1.0–v1.8.1)  [Pflege: Release-Manager]
│   ├── RELEASE_v1.8.1.md      # Aktuelles Release (v1.8.1, PATCH: Watchdog-Pause-Awareness & Event-Hygiene)
│   ├── RELEASE_v1.8.0.md      # v1.8.0 (MINOR: Runner-Selbstheilung)
│   ├── RELEASE_v1.7.1.md      # v1.7.1 (PATCH: Receiver-Bootstrap & Grace)
│   ├── RELEASE_v1.7.0.md      # v1.7.0 (MINOR: Headless Paper-Autobot)
│   ├── RELEASE_v1.6.0.md      # v1.6.0 (MINOR: Signal-Center & BTC-Guardian)
│   ├── RELEASE_v1.5.4.md      # v1.5.4
│   ├── RELEASE_v1.5.3.md      # v1.5.3
│   ├── RELEASE_v1.5.2.md      # v1.5.2
│   ├── RELEASE_v1.5.1.md      # v1.5.1
│   ├── RELEASE_v1.5.0.md      # v1.5.0
│   └── ...                    # Historische Release Notes (v1.1.0–v1.4.1, 25 Dateien)
└── research/                  # Quantitative Forschung, Validierung & Audits  [Pflege: Quant-Research]
    ├── SYMBIOSE_Model_Validation.md   # Walk-Forward Validierung & DSR (kanonisch)
    ├── RESEARCH_INTEGRITY_GLOSSAR.md  # Statistische Integritätsbegriffe (kanonisch)
    ├── TRIALS_LEDGER.md               # Unveränderliches Backtest-Ledger (kanonisch)
    ├── TRIALS_LEDGER_LEGACY_v1.2.8.md # Historisches Ledger bis v1.2.8
    ├── EDGE_RESEARCH_FINAL.md         # Konfluenz-Analyse & Mathematischer Edge
    ├── GESAMTAUDIT_REPORT.md          # Vollständiger 5-Ebenen Auditbericht
    ├── PWF_FIX_REPORT.md              # Walk-Forward Purging & Leakage-Fixes
    ├── AUDIT_ABSCHLUSS.md             # Abschluss Gesamtaudit (Round 9/10)
    ├── AUDIT_HERMES_20260912*.md      # Hermes-Audit Rev1–Rev3 (2026-09-12)
    ├── AUDIT_RUNDE9_ABSCHLUSS.md      # Round-9-Abschluss
    ├── AUDIT_RUNDE10_ABSCHLUSS.md     # Round-10-Abschluss
    ├── BASELINE_20260912.md           # Freeze-Baseline vor Audit
    ├── PHASE1_REPORT.md               # Phase-1-Diagnosebericht
    ├── round11_*–round16_*.md         # Schlussberichte Round 11–16
    ├── claims.csv                     # Maschinenlesbare Claim-Tabelle
    ├── trials_ledger_chain.jsonl      # Kryptografisch verkettetes Ledger (JSONL)
    ├── diagnostics/                   # 4-Phasen Diagnose-Logs (A–D)
    └── preregistrations/              # Vorregistrierte Hypothesen vor Messung
```

---

## 1. Architektur & Design

- [System-Architektur (docs/architecture.md)](architecture.md): Client-Relay-Architektur, Bitget-REST/WebSocket-Pipeline, In-Memory-State und Origin-Whitelisting.
- [Brand & UI-Design (docs/brand_design.md)](brand_design.md): Farbpalette (#080B11, #00F5A0, #FF3B69), Typografie, SVG-Vektor-Logos und Token-Spezifikationen.
- [Interaktives Tutorial (SYMBIOSE_Tutorial.html)](../SYMBIOSE_Tutorial.html): Vollständiger visueller Leitfaden zur Signalerkennung, MTF-Konfluenz und Risikosteuerung.

---

## 2. Deployment & Betrieb

- [Docker Deployment Guide (docs/deployment/DOCKER_GUIDE.md)](deployment/DOCKER_GUIDE.md): Betrieb im isolierten Docker-Container mit Healthcheck-Probes und persistentem State.
- [Proxmox VE & LXC Guide (docs/deployment/PROXMOX_GUIDE.md)](deployment/PROXMOX_GUIDE.md): Unprivileged LXC-Container, Alpine/Debian-Setup und Tailscale Funnel Webhook-Integration.
- [ntfy Deploy-Benachrichtigungen (docs/deployment/NTFY_GUIDE.md)](deployment/NTFY_GUIDE.md): Push-Alerts bei Deploy-Erfolg/-Fehlschlag auf Handy (Android/iOS) und PC. Topic-Name wird direkt mitgeteilt, nie ins Repo.
- [Incidentbericht 2026-09-12](deployment/webhook-incident-20260912.md): Exited-137-Incident, VERSION-Fehler, Reparatur v1.2.12.
- [Incidentbericht 2026-09-13](deployment/webhook-incident-20260913.md): Health-Race-Condition v1.5.1, Reparatur & ntfy-Integration.

---

## 3. Quant-Research & Mathematische Integrität

- [Modellvalidierung (docs/research/SYMBIOSE_Model_Validation.md)](research/SYMBIOSE_Model_Validation.md): K=4 Walk-Forward-Validierung mit t1-Purging, Deflated Sharpe Ratio (DSR) und OOS-Gating.
- [Integritäts-Glossar (docs/research/RESEARCH_INTEGRITY_GLOSSAR.md)](research/RESEARCH_INTEGRITY_GLOSSAR.md): Definition aller mathematischen Schutzmaßnahmen gegen P-Hacking, Lookahead-Bias und Data-Snooping.
- [Trials-Ledger (docs/research/TRIALS_LEDGER.md)](research/TRIALS_LEDGER.md): Lückenloser Nachweis aller untersuchten Parameterkombinationen (kryptografisch verkettet).
- [Audit-Berichte (docs/research/)](research/GESAMTAUDIT_REPORT.md): Audit-Ergebnisse der statischen/dynamischen Paritätsprüfungen (Pine v6 ↔ Python ↔ JS) und EXP-032-Ledger.

---

## 4. Releases & Versionierung

Alle Release-Notes liegen kanonisch in `docs/releases/`. Root-Stubs wurden in Runde 18 konsolidiert.

| Version | Typ | Datum | Kurzbeschreibung |
| --- | --- | --- | --- |
| **v1.8.1** | PATCH | 2026-09 | Watchdog-Pause-Awareness, P3-Heilungsquittung, Dashboard-Event-Hygiene & Live-Tracking |
| **v1.8.0** | MINOR | 2026-09 | Runner-Selbstheilung, 10-s-Timeouts, Stall-Forensik & Digest-Equity |
| **v1.7.1** | PATCH | 2026-09 | Receiver-Bootstrap, Docs-Wahrheit & P4-Startup-Grace |
| **v1.7.0** | MINOR | 2026-09 | Headless Paper-Autobot (Server-Modus) & 24/7 Signale |
| **v1.6.1** | PATCH | 2026-09 | Infra-Härtung: Universum-Sync-Isolation & CI-Stabilität |
| v1.6.0 | MINOR | 2026-09 | Signal-Center, Trade-Events, BTC-Regime-Guardian, Daily-Digest |
| v1.5.4 | PATCH | 2026-09 | Trade-Karte, TradingView-Links, Autobot-Stabilität |
| v1.5.3 | PATCH | 2026-09 | DOM-stabile Trade-Karten, ntfy Trade-Push-Docs |
| v1.5.2 | PATCH | 2026-09 | wait_for_health()-Timeout-Fix, receiver-originierte ntfy-Alerts |
| v1.5.1 | PATCH | 2026-09 | MTF-Konfigurationsfix & Kein-Signal-Klartext |
| v1.5.0 | MINOR | 2026-09 | Relay-ntfy-Alerts, Trade-Log, Feed-Status |
| v1.4.1 | PATCH | 2026-09 | Autobot-Live-Tracking Regression & Tooltips |
| v1.4.0 | MINOR | 2026-09 | UX-Transparenz & Relay-Benachrichtigungen |
| v1.3.x | PATCH | 2026-09 | Feed-Rotation, CVD-Feed-Invarianz, Ticker-Heartbeat |
| v1.2.x | PATCH/MINOR | 2026-09 | Historische Runden 9–16 |
| v1.1.x | PATCH | 2026-09 | Frühe Releases |

[Alle 32 Release Notes anzeigen](releases/)

- [Changelog (ROOT/CHANGELOG.md)](../CHANGELOG.md): Vollständige Historie nach Keep a Changelog.
- [Release Checklist (ROOT/RELEASE_CHECKLIST.md)](../RELEASE_CHECKLIST.md): Schritt-für-Schritt-Prüfkatalog vor jedem produktiven Tagging.

---

## 5. Test- & Verifikations-Kommandos

```bash
# Gesamte Test-Suite
pytest

# JS-Test-Suite
node tests/test_tradingview_position_bridge.js
node tests/test_pine_forecast_generation.js

# Vollständiger Release-Check
python3 scripts/release_check.py
```
