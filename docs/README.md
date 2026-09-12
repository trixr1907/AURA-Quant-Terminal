# AURA — Documentation & Architecture Index

Willkommen in der offiziellen Dokumentation von **AURA — Confluence Terminal**. Dieses Verzeichnis bündelt alle technischen Spezifikationen, mathematischen Validierungen, Deployment-Leitfäden und Release-Dokumente.

---

## 📚 Inhaltsübersicht

### 1. 🏗️ Architektur & Design
* [**docs/architecture.md**](architecture.md) — Vollständige Datenpfad-, Pipeline- und Relay-Architektur.
* [**docs/brand_design.md**](brand_design.md) — Brand Identity Token Spec (`DESIGN.md`), Farbpaletten und SVG-Asset-Richtlinien.
* [**SYMBIOSE_Tutorial.html**](../SYMBIOSE_Tutorial.html) — Interaktives Visual Tutorial für Setup Discovery, Signal Engine und Risikomanagement.

### 2. 🚀 Deployment & Infrastruktur
* [**PROXMOX_GUIDE.md**](../PROXMOX_GUIDE.md) — Automatisierte Bereitstellung auf Proxmox VE (Docker, LXC, Tailscale Funnel Webhooks).
* [**DOCKER_GUIDE.md**](../DOCKER_GUIDE.md) — Container-Betrieb via Docker Compose und Standalone Container.
* [**PROXMOX_DEPLOY.bat**](../PROXMOX_DEPLOY.bat) — 1-Klick SCP/SSH Scanner und Deployment-Skript für Windows.

### 3. 🔬 Quant-Research & Mathematische Integrität
* [**SYMBIOSE_Model_Validation.md**](../SYMBIOSE_Model_Validation.md) — Walk-Forward Validierung, Deflated Sharpe Ratio und Leakage-Freiheit.
* [**RESEARCH_INTEGRITY_GLOSSAR.md**](../RESEARCH_INTEGRITY_GLOSSAR.md) — Statistische Begriffe, OOS-Gates, Anti-P-Hacking Richtlinien.
* [**docs/EDGE_RESEARCH_FINAL.md**](EDGE_RESEARCH_FINAL.md) — Konfluenz-Analyse und mathematischer Edge-Report.
* [**docs/EDGE_DIAGNOSTIC_PHASEA-D.md**](EDGE_DIAGNOSTIC_PHASEA.md) — 4-Phasen Diagnose-Logs der Signalgenerierung.

### 4. 📦 Releases & Changelogs
* [**RELEASE_v1.2.5.md**](../RELEASE_v1.2.5.md) — Aktuelles Release: Natives TradingView Zeichentool Assist, Paper Trade Freedom, Zero Indicator Slots.
* [**RELEASE_v1.2.4.md**](../RELEASE_v1.2.4.md) — 1:1 Position Tool Precision & Paper Trade Unlock.
* [**RELEASE_v1.2.3.md**](../RELEASE_v1.2.3.md) — Brand Identity & Visual Precision.
* [**RELEASE_CHECKLIST.md**](../RELEASE_CHECKLIST.md) — Release Gates, Static Checks und Test-Pipelines.

---

## 🛠️ Entwickler- & Test-Befehle

```bash
# Gesamte Test-Suite ausführen
pytest

# Pine Script statische Syntax- & Paritätsprüfung
python3 tests/pine_static_check.py

# TradingView Bridge & Position Tool Tests
node tests/test_tradingview_position_bridge.js
node tests/test_tradingview_basic_qol.js

# Vollständiger Release-Check & Audit Gate
python3 scripts/release_check.py
```
