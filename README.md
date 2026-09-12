<p align="center">
  <img src="assets/aura_logo_horizontal.svg" width="520" alt="AURA Confluence Terminal">
</p>

<p align="center">
  <strong>Quantitative Edge · Visual Precision · Pure Execution</strong>
</p>

# AURA v1.2.5 — Confluence Terminal

<p align="center">
  <a href="VERSION"><img src="https://img.shields.io/badge/version-1.2.5-00F5A0?style=for-the-badge&labelColor=080B11" alt="Version 1.2.5"></a>
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

## TradingView-Positionen

TradingView erlaubt externen Programmen nicht, native Maus-Zeichenobjekte direkt in ein Cloud-Layout zu injizieren. AURA bildet das **Long-/Short-Position-Werkzeug deshalb als Pine-Script-Overlay** nach: grüne Gewinnzone, rote Verlustzone, Entry, SL, TP1–TP3, CRV, Risiko und Positionsgröße.

### Einen AURA-Trade im Chart anzeigen

1. Im Dashboard einen aktiven Paper-Trade öffnen.
2. **„In TV visualisieren“** anklicken.
3. AURA öffnet TradingView Desktop auf dem passenden `BITGET:<SYMBOL>.P`-Chart und kopiert das angepasste Pine Script.
4. In TradingView unten **Pine Editor** öffnen.
5. Editor-Inhalt vollständig ersetzen (`Strg+A`, `Strg+V`).
6. **Speichern** und **Zum Chart hinzufügen** auswählen.

> [!NOTE]
> Der Button allein kann das native Werkzeug aus TradingViews Seitenleiste nicht fernsteuern. Das ist eine Plattformgrenze. Nach dem einmaligen Einfügen zeichnet der AURA-Indikator die Trade-Levels selbst; für einen neuen Dashboard-Trade muss der neu kopierte Script-Stand im Pine Editor übernommen werden.

### Wenn nichts eingezeichnet wird

- In den Indikator-Einstellungen muss **„7) Trade Forecasting & Long/Short Position Tool“ → „Position Tool visualisieren“** aktiviert sein.
- Der kopierte Stand muss `Modus = Custom` sowie gültige Werte für Entry und Stop enthalten.
- Alte AURA-Indikatorinstanzen entfernen, das neue Script speichern und erneut zum Chart hinzufügen.
- Der TradingView-Chart muss zum im Dashboard gewählten Bitget-Perpetual passen.

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

## Dokumentation

- [Interaktives Tutorial](SYMBIOSE_Tutorial.html)
- [Modellvalidierung](SYMBIOSE_Model_Validation.md)
- [Brand Design](docs/brand_design.md)
- [Release Notes v1.2.2](RELEASE_v1.2.2.md)
- [Release Checklist](RELEASE_CHECKLIST.md)
- [Security Policy](SECURITY.md)

## Lizenz

Veröffentlicht unter der [MIT License](LICENSE).

---

<p align="center">
  <strong>AURA — Confluence Terminal</strong><br>
  <sub>Research only · No order execution · No financial advice</sub>
</p>
