<p align="center">
  <img src="assets/aura_logo_horizontal.svg" width="520" alt="AURA Confluence Terminal">
</p>

<p align="center">
  <strong>Quantitative Edge · Visual Precision · Pure Execution</strong>
</p>

# AURA v1.2.13 — Confluence Terminal

<p align="center">
  <a href="VERSION"><img src="https://img.shields.io/badge/version-1.2.13-00F5A0?style=for-the-badge&labelColor=080B11" alt="Version 1.2.13"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-00F2FE?style=for-the-badge&labelColor=080B11" alt="MIT License"></a>
  <a href="https://www.tradingview.com/pine-script-docs/"><img src="https://img.shields.io/badge/Pine%20Script-v6-B026FF?style=for-the-badge&labelColor=080B11" alt="Pine Script v6"></a>
  <img src="https://img.shields.io/badge/market-Bitget%20USDT--M-F23645?style=for-the-badge&labelColor=080B11" alt="Bitget USDT-M">
</p>

<p align="center">
  <a href="#schnellstart">Schnellstart</a> ·
  <a href="#tradingview-positionen">TradingView</a> ·
  <a href="#architektur">Architektur</a> ·
  <a href="#qualitaet-und-grenzen">Qualität</a>
</p>

---

## Was ist AURA?

AURA ist ein lokales, read-only Research-Terminal für Bitget USDT-M Perpetual Futures. Es reduziert Marktrauschen durch Multi-Timeframe-Confluence, Liquiditäts- und Regime-Gates, bewertet Setups und visualisiert Entry, Stop sowie Ziele in TradingView.

> [!IMPORTANT]
> AURA platziert keine echten Orders und benötigt keine privaten Exchange-Zugangsdaten. Scores und Backtests sind Research-Ergebnisse, keine Gewinnversprechen oder Anlageberatung.

| Bereich | Aufgabe |
| --- | --- |
| **Action Radar** | Durchsucht aktive Bitget USDT-M Perpetuals und priorisiert vollständige Setups. |
| **Confluence Engine** | Verbindet Trend, Momentum, Volumen, Marktstruktur und vier Zeitfenster. |
| **Risk Gates** | Prüft Regime, Liquidität, Funding/OI, BTC-Kontext und OOS-Evidenz fail-closed. |
| **Paper Autobot** | Simuliert qualifizierte Trades lokal inklusive SL, TP1–TP3 und Time-Stop. |
| **TradingView Bridge** | Öffnet den passenden Bitget-Chart und kopiert ein Pine-v6-Overlay mit konkreten Trade-Levels. |

## Schnellstart

### Windows

1. Aktuelles Paket aus den [GitHub Releases](https://github.com/trixr1907/AURA-Quant-Terminal/releases/latest) herunterladen und entpacken.
2. `START.bat` ausführen.
3. Das Dashboard unter `http://127.0.0.1:8787` öffnen.

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 start.py --no-gui
```

Das Terminal läuft anschließend lokal unter `http://127.0.0.1:8787`.

<details>
<summary><strong>Weitere Startvarianten</strong></summary>

| Variante | Befehl |
| --- | --- |
| Windows ohne Launcher-GUI | `START_OHNE_GUI.bat` |
| Unix Shell | `./start.sh --no-gui` |
| Docker | `docker compose up --build` |
| Manueller Relay-Start | `python3 bitget_relay.py` |

</details>

## TradingView Native Position Tool Assist

TradingView erlaubt externen Programmen nicht, native Maus-Zeichenobjekte aus der linken Werkzeugleiste direkt in ein Cloud-Chart zu zeichnen. AURA v1.2.5 löst dies über einen **Zero-Slot Zeichentool-Assistenten**:

### Einen AURA-Trade in TradingView einzeichnen

1. Im Dashboard unter **„Aktive Trades“** auf **`📐 TV Zeichentool`** klicken.
2. AURA öffnet direkt die TradingView Desktop App auf dem exakten Bitget-Perpetual-Chart (`BITGET:<SYMBOL>.P`) und im passenden Timeframe.
3. Gleichzeitig öffnet AURA das **Zeichentool Quick-Copy HUD** mit den exakten Parametern des Trades:
   * **Entry-Kurs:** 1-Klick-Kopieren `[📋]`
   * **Take Profit (TP1 / TP2 / TP3):** 1-Klick-Kopieren `[📋]`
   * **Stop-Loss (SL):** 1-Klick-Kopieren `[📋]`
   * **CRV, Hebel, Risiko & Notional-Positionsgröße**
4. In TradingView links in der Toolbar das **Long-Position**- bzw. **Short-Position**-Werkzeug auswählen und auf den Chart setzen.
5. Keine Verschwendung wertvoller Indikator-Plätze und sauberes Chartbild.

## Workflow

```text
Bitget Public Market Data
          │
          ▼
Action Radar ──► Confluence Score ──► Risk & OOS Gates
                                           │
                               ┌───────────┴───────────┐
                               ▼                       ▼
                         Rejected Setup          Paper Candidate
                                                       │
                                        ┌──────────────┴──────────────┐
                                        ▼                             ▼
                                  Local Tracker             TradingView Overlay
```

1. **Scannen:** Der Radar lädt das aktive USDT-M-Perpetual-Universum progressiv.
2. **Bewerten:** Der Core-Score kombiniert Trend, Momentum, Volumen und Struktur.
3. **Gaten:** MTF, Regime, Liquidität, BTC-Kontext und OOS-Evidenz können ein Setup ablehnen.
4. **Validieren:** Anchored Walk-Forward und DSR trennen technische Qualität von statistischer Evidenz.
5. **Visualisieren:** Qualifizierte Paper-Trades werden lokal verfolgt und optional nach TradingView übertragen.

## Modell

```text
Core Score = 0.30 × Trend
           + 0.25 × Momentum
           + 0.25 × Volumen
           + 0.20 × Struktur
```

Zusätzliche Freigaben:

- Multi-Timeframe-Konfluenz auf `15m`, `1h`, `4h` und `1d`
- Regime- und Squeeze-Gate
- Mindestliquidität und aktive Bitget-USDT-M-Kontrakte
- Funding-, Open-Interest- und Basis-Kontext
- BTC-Regime für Altcoin-Setups
- Anchored Walk-Forward mit t1-Schutz
- Positiver OOS-Edge und Deflated Sharpe Ratio
- Fractional Kelly; negativer Edge ergibt null Research-Sizing

## Architektur

```text
Symbiose_Dashboard.html          Browser UI, Radar, Modell und Paper-Trades
bitget_relay.py                  Lokaler Relay, Public-API-Proxy, Desktop-Bridge
Symbiose_Signal_System_v1.pine   Pine-v6-Indikator und Position-Overlay
start.py                         Plattformübergreifender Launcher
scripts/                         Release-, Paket- und Datensynchronisation
assets/                          AURA Brand Assets
```

Die Runtime ist bewusst lokal und read-only. Der Relay erlaubt nur öffentliche Marktdatenpfade und stellt Dashboard, Tutorial und Pine Script bereit.

## Entwicklung

```bash
python3 -m pytest -q
node tests/test_tradingview_position_bridge.js
node tests/test_pine_forecast_generation.js
python3 tests/pine_static_check.py
```

Release-Prüfung und reproduzierbares Paket:

```bash
python3 scripts/release_check.py
python3 scripts/build_package.py
```

## Qualitaet und Grenzen

| Verifiziert | Bewusste Grenze |
| --- | --- |
| Lokale Python-, Node- und Pine-Static-Tests | Lokale Tests ersetzen keine Kompilierung auf TradingViews Servern. |
| Deterministische Golden-Master-Fixtures mit Provenance | Historische Ergebnisse beweisen keine zukünftige Profitabilität. |
| Fail-closed OOS-, Edge- und Liquiditäts-Gates | Keine echte Order-Ausführung oder Kontoverwaltung. |
| Öffentliche Bitget-Daten ohne API-Schlüssel | Pine kann externe Funding-/OI-REST-Daten nicht selbst laden. |

Ein technisch grünes Release kann weiterhin `MODEL_NO_EVIDENCE` melden. Das bedeutet: Die Software funktioniert als Research-Werkzeug, aber die geprüfte Stichprobe liefert keinen belastbaren Profitabilitätsnachweis.

## Dokumentation & SOTA Index

- [**📚 Dokumentations-Hub (docs/README.md)**](docs/README.md) — Vollständiger SOTA-Index aller Leitfäden und Reports.
- [**📜 Changelog**](CHANGELOG.md) — Lückenlose Release-Historie nach Keep a Changelog.
- [**🎨 Brand Design**](docs/brand_design.md) — Design Tokens, Typography und SVG-Assets.
- [**🏗️ Architektur & Pipeline**](docs/architecture.md) — Datenpfade, State-Management und Relay-Routing.
- [**🚀 Proxmox & Docker Deployment**](docs/deployment/PROXMOX_GUIDE.md) — Multi-Node-, LXC- und Container-Betrieb.
- [**🔬 Quant-Modellvalidierung**](docs/research/SYMBIOSE_Model_Validation.md) — Walk-Forward Validierung & Deflated Sharpe Ratio.
- [**🎓 Interaktives Tutorial**](SYMBIOSE_Tutorial.html) — Schritt-für-Schritt Dashboard- & Signal-Guide.

## Lizenz

Veröffentlicht unter der [MIT License](LICENSE).

---

<p align="center">
  <strong>AURA — Confluence Terminal</strong><br>
  <sub>Research only · No order execution · No financial advice</sub>
</p>
