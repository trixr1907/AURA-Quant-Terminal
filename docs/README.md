# AURA — Documentation & Architecture Master Index

Willkommen im zentralen Dokumentations-Hub von **AURA — Confluence Terminal**.
Dieses Verzeichnis strukturiert alle Spezifikationen, mathematischen Validierungen, Deployment-Leitfäden, Brand-Assets und Changelogs nach **SOTA Best Practices**.

---

## 📂 Dokumentations-Übersicht

```
docs/
├── README.md                 # Zentraler Dokumentations-Index
├── architecture.md           # Systemarchitektur & Relay-Pipeline
├── brand_design.md           # Design Tokens, Dark-Mode & Asset-Specs
├── CHANGELOG.md              # Vollständige Versionshistorie (Keep a Changelog)
├── deployment/               # Deployment & Infrastruktur
│   ├── DOCKER_GUIDE.md       # Docker Compose & Standalone Container
│   ├── PROXMOX_GUIDE.md      # Proxmox VE, LXC & Tailscale Funnel Webhooks
│   ├── NTFY_GUIDE.md         # Push-Benachrichtigungen (Deploy-Alerts, Handy & PC)
│   ├── webhook-incident-20260912.md  # Incidentbericht 2026-09-12
│   └── webhook-incident-20260913.md  # Incidentbericht 2026-09-13 (v1.5.1 Health-Race)
├── releases/                 # Release-Notes aller Versionen (v1.1.0 – v1.5.1, 27 Dateien)
│   ├── RELEASE_v1.5.1.md     # Aktuelles Release (v1.5.1)
│   ├── RELEASE_v1.5.0.md     # v1.5.0 Release Notes
│   └── ...                   # Historische Release Notes (v1.1.0 – v1.4.1)
└── research/                 # Quantitative Forschung, Validierung & Audits
    ├── SYMBIOSE_Model_Validation.md  # Walk-Forward Backtesting & DSR
    ├── RESEARCH_INTEGRITY_GLOSSAR.md # Statistische Integritätsbegriffe
    ├── EDGE_RESEARCH_FINAL.md        # Konfluenz-Analyse & Mathematischer Edge
    ├── GESAMTAUDIT_REPORT.md         # Vollständiger 5-Ebenen Auditbericht
    ├── PWF_FIX_REPORT.md             # Walk-Forward Purging & Leakage-Fixes
    ├── TRIALS_LEDGER.md              # Unveränderliches Backtest-Ledger
    └── diagnostics/                  # 4-Phasen Diagnose-Logs (Phasen A–D)
```

---

## 🏗️ 1. Architektur & Design

* [**System-Architektur (`docs/architecture.md`)**](architecture.md): Detaillierte Beschreibung der Client-Relay-Architektur, Bitget-REST/WebSocket-Pipeline, In-Memory-State und Origin-Whitelisting.
* [**Brand & UI-Design (`docs/brand_design.md`)**](brand_design.md): Farbpalette (`#080B11`, `#00F5A0`, `#FF3B69`), Typografie, SVG-Vektor-Logos und Token-Spezifikationen.
* [**Interaktives Tutorial (`SYMBIOSE_Tutorial.html`)**](../SYMBIOSE_Tutorial.html): Vollständiger visueller Leitfaden zur Signalerkennung, MTF-Konfluenz und Risikosteuerung.

---

## 🚀 2. Deployment & Betrieb

* [**Docker Deployment Guide (`docs/deployment/DOCKER_GUIDE.md`)**](deployment/DOCKER_GUIDE.md): Betrieb im isolierten Docker-Container mit Healthcheck-Probes und persistentem State.
* [**Proxmox VE & LXC Guide (`docs/deployment/PROXMOX_GUIDE.md`)**](deployment/PROXMOX_GUIDE.md): Unprivileged LXC-Container, Alpine/Debian-Setup und Tailscale Funnel Webhook-Integration.
* [**ntfy Deploy-Benachrichtigungen (`docs/deployment/NTFY_GUIDE.md`)**](deployment/NTFY_GUIDE.md): Push-Alerts bei Deploy-Erfolg/-Fehlschlag — Einrichtung auf Handy (Android/iOS) und PC.
* [**Webhook → Receiver → ntfy Kette:**](deployment/NTFY_GUIDE.md) GitHub Release → Tailscale Funnel → Deploy-Receiver (beide VMs) → ntfy Push. Deploy-Relay (`bitget_relay.py`) sendet zusätzlich ntfy-Alerts bei Trade-Schluss (PF-33, via `AURA_NTFY_URL`).
* [**Incidentbericht 2026-09-12**](deployment/webhook-incident-20260912.md): Exited-137-Incident, VERSION-Fehler, Reparatur v1.2.12.
* [**Incidentbericht 2026-09-13**](deployment/webhook-incident-20260913.md): Health-Race-Condition v1.5.1, Reparatur & ntfy-Integration.

---

## 🔬 3. Quant-Research & Mathematische Integrität

* [**Modellvalidierung (`docs/research/SYMBIOSE_Model_Validation.md`)**](research/SYMBIOSE_Model_Validation.md): Wissenschaftliche Dokumentation von $K=4$ Walk-Forward-Validierung mit $t_1$-Purging, Deflated Sharpe Ratio (DSR) und OOS-Gating.
* [**Integritäts-Glossar (`docs/research/RESEARCH_INTEGRITY_GLOSSAR.md`)**](research/RESEARCH_INTEGRITY_GLOSSAR.md): Definition aller mathematischen Schutzmaßnahmen gegen P-Hacking, Lookahead-Bias und Data-Snooping.
* [**Trials-Ledger (`docs/research/TRIALS_LEDGER.md`)**](research/TRIALS_LEDGER.md): Lückenloser Nachweis aller untersuchten Parameterkombinationen zur Verhinderung von Multiple-Testing-Verzerrungen.
* [**Audit-Berichte (`docs/research/`)**](research/GESAMTAUDIT_REPORT.md): Audit-Ergebnisse der statischen und dynamischen Paritätsprüfungen (Pine Script v6 ↔ Python ↔ JS).

---

## 📦 4. Changelogs & Versionierung

* [**Changelog (`CHANGELOG.md`)**](../CHANGELOG.md): Komplette Historie nach dem [Keep a Changelog](https://keepachangelog.com/) Standard.
* [**Release Notes v1.5.1 (`docs/releases/RELEASE_v1.5.1.md`)**](releases/RELEASE_v1.5.1.md): Aktuelles Release — MTF-Konfigurationsfix & Kein-Signal-Klartext (Runde 20).
* [**Alle Release Notes**](releases/): v1.1.0 – v1.5.1 (27 Dateien), kanonisch in `docs/releases/`. Root-Level-Stubs wurden in Runde 18 in `docs/releases/` konsolidiert.
* [**Release Checklist (`RELEASE_CHECKLIST.md`)**](../RELEASE_CHECKLIST.md): Schritt-für-Schritt Prüfkatalog vor jedem produktiven Tagging.

---

## 🧪 Test- & Verifikations-Kommandos

```bash
# Gesamte Test-Suite ausführen
pytest

# Vollständiger Release-Check & Smoke Test
python3 scripts/release_check.py
```
