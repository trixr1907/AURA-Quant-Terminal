# AURA v1.1.8 — Smart Quant Terminal

Read-only Quant-Research- und Setup-Discovery-Station für Kryptomärkte.
Das System analysiert öffentliche Marktdaten, rankt Setups und validiert das Modell. Es kann keine Orders senden, besitzt keine API-Authentifizierung und verwaltet keine Positionen.

### v1.1.8 — TradingView Basic Bridge (aktuelle Fassung)

- **Free-only TradingView Bridge:** Öffnet den geladenen Coin und Timeframe auf Bitget Perpetual, Binance Perpetual oder Bitget Spot und kopiert das vollständige AURA-Pine-Script.
- **Gespeichertes AURA-Layout:** Eine optionale TradingView-Layout-ID wird lokal gespeichert, damit der kostenlose Einzel-Chart direkt im eigenen AURA-Layout startet.
- **Radar-Navigation und Top-30-Listen:** Vor-/Zurück-Navigation durch die besten vollständigen Radar-Kandidaten sowie kopierbare Gesamt-, LONG- und SHORT-Symbollisten mit hartem 30-Symbol-Limit.
- **Kostenloser Preisalarm-Assistent:** Kopierbare Entry-, Stop- und TP1-Vorlagen ohne Webhooks oder technische Premium-Alarme.
- **Setup-Notiz und Rücksprung-Link:** Reproduzierbarer Link lädt Symbol und Timeframe zurück in AURA und berechnet den Kontext frisch; `MODEL_NO_EVIDENCE` bleibt unverändert fail-closed.

### v1.1.7 — Setup Discovery, Edge-Auswahl & Radar-Ranking

- **Hero Top-Setups Quick-Picks:** Interaktive 1-Klick-Chips für die bis zu 4 stärksten Radar-Kandidaten direkt in der Hero-Fußzeile. Ein Klick lädt sofort den stärksten Timeframe und rechnet den 1.500-Kerzen Walk-Forward-Backtest sowie den mathematischen Kelly-Edge.
- **Smarte 3-Stufen Radar-Gruppierung:** Saubere Trennung im 🎯 Top-Edge-Modus in *🔥 Hot Setups (Ausführbar)*, *🎯 Top Setup-Kandidaten* (starkes Signal kurz vor Trigger) und *👀 Watchlist & Universum*.
- **Echter Signal-Score in der Radar-Gesamtansicht:** Die Score-Spalte in der Gesamtansicht (`all`) zeigt den tatsächlichen Score des stärksten Timeframes inklusive Timeframe-Kennzeichnung (z. B. `86.0 (4h)`) statt des verwässerten 4-TF-Durchschnitts.
- **Verifizierte Modellintegrität & Release-Gates:** Neuer TDD-Prüfpfad `test_radar_top_candidates.js` im Release-Check; das reale Modellverdikt `MODEL_NO_EVIDENCE` bleibt unverändert fail-closed.

### v1.1.6 — Stabilisierung, Transparenz & Docker-Readiness

- **Ehrliche Produktsemantik & Paper-CTA:** Paper Autobot und Paper-Simulation klar als risikofreie Simulation ohne Orderausführung ausgewiesen; Hero Paper-Trade Button fail-closed gesperrt ohne vollständiges Setup mit statistischem Edge (`MODEL_NO_EVIDENCE`).
- **Fail-Closed Liquidität:** Statische Fallback-Liquidität wird als unüberprüft (`liquidityVerified: false`) markiert und schützt den Paper Autobot vor Scheinausführungen bei fehlenden Marktdaten.
- **Relay-Lastschutz & Singleflight:** Thread-safe Coalescing identischer Cache-Misses (Singleflight), exponentielles Upstream-429-Backoff mit `Retry-After`-Respektierung und getrennter `/ready` Marktdaten-Readiness-Endpunkt neben `/serving`.
- **Radar-Transparenz:** Kontrollierte Parallelität via `RADAR_CONCURRENCY`, getrennte Statuszähler für Erfolg/Fehler/Skipped und gemessene Restzeitschätzung.
- **Docker-Starter & LAN-Sicherheit:** Bounded Readiness-Polling vor Erfolgsmeldung und Browserstart in `docker_start.sh` und `DOCKER_START.bat`; saubere `AURA_ALLOWED_HOSTS`-Konfiguration.

### v1.1.5 — Institutional Audit Patches & UX-Härtung

- **Signal-Integrität:** Hero-Richtung entkoppelt vom Markt-Scoring; BTC-Trend-Veto ('wait') fest verankert; Radar-State-Key berücksichtigt Sortierung & TF.
- **Risk-Management:** Autobot-Position-Sizing vollständig mit dynamischem Fractional Kelly (`calcKelly`) harmonisiert (Fail-closed bei mangelndem Edge).
- **Stabilität & Kausalität:** Look-Ahead-invariantes Warmup für junge Tokens ($N < 295$) fixiert (Metamorphic-Tests verifiziert).
- **Netzwerk & Performance:** WebSocket-Tick-Drosselung via `requestAnimationFrame`, Stale-Data-Guard (`⚠️ STALE`), Relay Token-Bucket auf 15/30 optimiert und Radar-Batchgröße auf 4 reduziert.
- **UI/UX & Accessibility:** RenderCache-State-Keys repariert, CSS-Ausblendung für Mobile-Controls entfernt (Flex-Wrap) und Schriften/Kontraste auf WCAG AA gehärtet.

### v1.1.4 — Zuverlässige Radar-Fokusauswahl

- Radar-Zeilen und Timeframe-Pills wechseln Symbol und Timeframe über einen gemeinsamen atomaren Fokuspfad.
- Setup Validation invalidiert ihren Render-Cache beim Assetwechsel und berücksichtigt nur tatsächlich dargestellte Live-Felder.
- Fokus-Setup, Setup Validation, Symbolfelder und Timeframe-Schalter bleiben damit synchron.
- Der tag-basierte Release-Workflow erlaubt den erwarteten aktuellen Release-Tag, ohne Konsistenz- oder Qualitäts-Gates zu umgehen.
- Scores, OOS-/DSR-Gates und das ehrliche Modellverdikt `MODEL_NO_EVIDENCE` bleiben unverändert.

### v1.1.3 — Laufzeitstabilität und Autobot-Diagnose

- Das Pine-Script hält FVG-Zeichnungen deterministisch begrenzt und läuft auch dann weiter, wenn alle gespeicherten Zonen noch aktiv sind.
- Der Autobot-Funnel zeigt modellneutral an, an welchem technischen, statistischen oder operativen Gate Kandidaten abgelehnt wurden.
- Externe Fehlermeldungen werden weder roh gespeichert noch synchronisiert; persistierte Diagnosecodes sind strikt allowlist-basiert.
- Scores, OOS-/DSR-Gates und das ehrliche Modellverdikt `MODEL_NO_EVIDENCE` bleiben unverändert.

### v1.1.2 — Objektiv-Fix und Research-Abschluss

- Das Walk-Forward-Selektionsobjektiv behandelt kleine Trainingsstichproben ab zwei Trades regularisiert statt sie bis fünf Trades pauschal auszuschließen.
- Die Edge-Forschung A–D ist konsolidiert; das ehrliche Abschlussverdikt bleibt `MODEL_NO_EVIDENCE` (aggregierter OOS-DSR 0.038 bei T=45).
- B3 (TP1/R:R-Tuning) wurde gemäß vorab festgelegter Stopp-Regel nicht durchgeführt.
- Präregistrierungen müssen künftig durch einen eigenen vorausgehenden Git-Commit belegt sein.

### v1.1.1 — Release-Prozess und Messintegrität

- Fail-closed Release-Pipeline ohne Bypass-Flags.
- Kanonische Millisekunden-Zeitstempel und synchronisierte Provenienz.

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
4. Chart & Validation: technische Prüfung, Liquiditätsstruktur und Anchored t1-safe Walk-Forward-Auswertung.

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
- Anchored K=4 Walk-Forward mit exaktem t1-Schutz (300 Train-Bars, mindestens 5 geschlossene Train-Trades), transparenten Train/Test-Stunden und Deflated Sharpe Ratio
- TimeStop- und Autobot-Auswahl verwenden ihre tatsächliche Trialfamilie; Autobot akzeptiert nur OOS-Evidenz mit mindestens 15 geschlossenen Trades, positivem Edge und DSR ≥ 0.5
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
python3 scripts/build_package.py
```

Der Builder prüft das Release-Verdict-Stamp, erzeugt `symbiose.zip`, berechnet SHA-256 und testet das entpackte Paket im Smoke-Test.

## Grenzen

- Keine Order-Ausführung.
- Keine privaten API-Aufrufe oder Schlüssel.
- Kein Positions- oder Kontomanagement.
- Keine Profitabilitätsgarantie.
- Pine kann externe Funding-/OI-Daten nicht selbst abrufen.
- TradingView-Kompilierung bleibt ein externer Prüfpfad; die lokalen Tests ersetzen sie nicht.

AURA v1.1.8 dient ausschließlich Quant Research, Setup Discovery und reproduzierbarer Modellvalidierung. Keine Anlageberatung.
