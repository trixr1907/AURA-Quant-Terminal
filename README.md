# AURA v1.0.3 — Smart Quant Terminal

Read-only Quant-Research- und Setup-Discovery-Station für Kryptomärkte.
Das System analysiert öffentliche Marktdaten, rankt Setups und validiert das Modell. Es kann keine Orders senden, besitzt keine API-Authentifizierung und verwaltet keine Positionen.

## Architektur

```text
Öffentliche Bitget-Marktdaten
            │
            ▼
Read-only CORS-Proxy (/api/public)
            │
            ▼
Smart Quant Terminal
  ├─ Makro-Wetter
  ├─ Top Opportunity
  ├─ Action Radar
  └─ Chart & Walk-Forward-Validierung
```

Zentrale Artefakte:

| Datei | Zweck |
|---|---|
| `Symbiose_Dashboard.html` | Single-File Smart Quant Terminal |
| `bitget_relay.py` | Lokaler Webserver und Public-Data-CORS-Proxy |
| `Symbiose_Signal_System_v1.pine` | Pine-v6-Spiegel für TradingView-Analyse und Golden Master |
| `SYMBIOSE_Tutorial.html` | Research-Workflow und Modellinterpretation |
| `SYMBIOSE_Model_Validation.md` | Grenzen und statistische Validierung |
| `RELEASE_CHECKLIST.md` | Reproduzierbare Qualitäts-Gates |

## Versionierung

AURA verwendet ab `1.0.0` Semantic Versioning (`MAJOR.MINOR.PATCH`). Die Datei `VERSION` ist die kanonische Versionsquelle.

- `PATCH` (`1.0.0`): kompatible Fehlerbehebung, Dokumentations- oder Sicherheitskorrektur ohne neue Schnittstelle.
- `MINOR` (`1.1.0`): rückwärtskompatible neue Funktion.
- `MAJOR` (`2.0.0`): inkompatible Änderung an Verhalten, Datenformat oder öffentlicher Schnittstelle.

Jedes veröffentlichte Update muss die Version erhöhen, den Release-Check bestehen, als Git-Tag `v<Version>` markiert und zusätzlich als GitHub Release veröffentlicht werden. Der GitHub Release enthält das geprüfte `symbiose.zip` als Download-Artefakt. Der Release-Check blockiert fehlende oder inkonsistente `MAJOR.MINOR.PATCH`-Versionen.

## Start

Windows:

```text
START.bat
```

Linux / WSL:

```text
./start.sh
```

CLI ohne GUI:

```text
python3 start.py --cli
```

Danach läuft das Terminal unter `http://127.0.0.1:8787/`.

Der Relay stellt ausschließlich bereit:

- `GET /` — Dashboard
- `GET /tutorial` — Tutorial
- `GET /serving` — Read-only Health-Status
- `POST /api/public` — transparente öffentliche Bitget-Marktdaten

Andere API-Pfade werden abgewiesen.

## Task-oriented Oberfläche

1. Makro-Wetter: BTC-Regime, Fear & Greed, Funding/OI-Extreme sowie SMC-Session- und Killzone-Kontext (UTC). Killzones sind reine Liquiditäts- und Volatilitätsfenster zur Orientierung, kein automatisches Kauf-/Verkaufssignal und kein eigenes GO-Gate.
2. Top Opportunity: bestes vollständig gegatetes Setup mit Richtung, Entry, Stop, TP1 und Kelly-Edge.
3. Action Radar: vollständiges Exchange-Universum, progressiv in 10er-Batches gerendert und nach Qualität sortiert.
4. Chart & Validation: technische Prüfung, Liquiditätsstruktur und Purged Walk-Forward-Auswertung.

Der Radar überspringt Instrumente früh, wenn Daily- oder 4H-Kerzen kein positives Volumen besitzen. Das spart Requests auf niedrigeren Zeitfenstern. Ein Radar-Ranking ist Orientierung, keine Ausführungsfreigabe. Der Hero nutzt ausschließlich das vollständig gegatete Live-Ergebnis.

## Modell

Core-Score:

```text
Score = 0.30 × Trend + 0.25 × Momentum + 0.25 × Volumen + 0.20 × Struktur
```

Weitere Gates:

- Multi-Timeframe-Konfluenz: mindestens 3 von 4 Zeitfenstern
- Regime: kein Sideways/Squeeze für Trendsetups
- Funding, Open Interest und Basis
- BTC-Regime für Altcoins
- Purged Walk-Forward und Deflated Sharpe Ratio
- Fractional Kelly; negativer Edge ergibt exakt null Research-Sizing

Scores sind keine garantierten Wahrscheinlichkeiten. Backtests beschreiben historische Stichproben, nicht die Zukunft.

## Datenquellen

Der Primärpfad nutzt öffentliche Bitget-Futures-Endpunkte über `/api/public`. Weitere öffentliche Quellen dienen ausschließlich als explizite Analyse-Fallbacks. Es sind keine Schlüssel oder privaten Kontodaten nötig.

## Tests

Vollständiger Check:

```text
python3 scripts/release_check.py
```

Wichtige Einzeltests:

```text
node tests/test_radar_progressive.js
node tests/test_engine_full.js
node tests/test_live_trade_tracker.js
node tests/test_smc_sessions.js
python3 -m unittest tests/test_relay_full.py
python3 -m unittest tests/test_release_sync.py
python3 -m unittest tests/test_launcher.py tests/test_research_cleanup.py
SYM_BROWSER_RUNS=1 python3 tests/browser_research_harness.py
```

Golden-Master-Parität & Authentizität:

```text
node tests/compare_pine_js_golden.js
```

Für den Golden-Master-Nachweis zählen ausschließlich echte, unabhängige TradingView/Pine-Exporte oder separat implementierte Referenzquellen mit maschinenlesbarer Provenance (`provenance.json`). Das zirkuläre Erzeugen erwarteter `GM ... Score`-Werte mit der JavaScript-Engine und anschließender JS-Vergleich ist strikt verboten und wird vom Release-Gate als `GOLDEN_MASTER_UNVERIFIED` abgewiesen. Parität ist erst bei unabhängig verifizierter Provenance belegt.

## Ehrliches Release-Verdict

Die Software-Gates und Pine↔JavaScript-Parität können grün sein, während statistische Edge-Evidenz fehlt. In diesem Fall lautet das Verdict bewusst:

```text
SOFTWARE_GO / MODEL_NO_EVIDENCE
```

Das bedeutet: technisch als Research-Tool nutzbar, aber kein belastbarer Profitabilitätsnachweis.

## Paket bauen

```text
python3 scripts/build_package.py --force
```

`--force` ist nötig, solange das Modell-Gate `MODEL_NO_EVIDENCE` meldet. Der Builder erzeugt `symbiose.zip`, berechnet SHA-256 und testet das entpackte Paket.

## Grenzen

- Keine Order-Ausführung.
- Keine privaten API-Aufrufe oder Schlüssel.
- Kein Positions- oder Kontomanagement.
- Keine Profitabilitätsgarantie.
- Pine kann externe Funding-/OI-Daten nicht selbst abrufen.
- TradingView-Kompilierung bleibt ein externer Prüfpfad; die lokalen Tests ersetzen sie nicht.

AURA v1.0.3 dient ausschließlich Quant Research, Setup Discovery und reproduzierbarer Modellvalidierung. Keine Anlageberatung.
