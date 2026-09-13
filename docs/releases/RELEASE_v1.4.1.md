# AURA Quant Terminal — Runde 18 Schlussbericht (v1.4.1, PATCH)

## Zusammenfassung

Runde 18 adressiert das Feedback des Systemeigentümers zu v1.4.0 in Form eines fokussierten PATCH-Releases (PF-37 bis PF-40):
1. **PF-37 (Regression):** Behebung fehlender Live-Metriken in den Autobot-Trade-Karten (`renderTradeCard(t, null, …)` → echte `calculateTradeMetrics(t, px)`-Werte mit synchroner Ticker-Kopplung).
2. **PF-38 (Klartext & Tooltips):** Laienverständliche deutsche Übersetzungen und Barrierefreiheits-Attribute (`tabindex="0"`, `aria-describedby`) für das Makro-BTC-Regime und alle Hero-Level-Kacheln.
3. **PF-39 (BTC-Chart Frische & Diagnose):** Kontrollierte Fehlerreproduktion, Ursachenmessprotokoll (Rate-Limits, Socket-Races, Ladeband-Zustände) und Einführung des Sekundentakt-Frische-Badges `#chart-freshness-badge`.
4. **PF-40 (Verifikation & Release-Hygiene):** 100% grüne Gates (236 pytest, 57 Subtests, 67/67 JS-Suiten, innerHTML=51), deterministischer Release-Check `EXIT=0`.

---

## Git- & Release-Belege

| Artefakt / Nachweis | Wert |
|---|---|
| **Release-Version** | `1.4.1` (PATCH) |
| **Produkt-Branch** | `fix/round18-v1.4.1` |
| **Produkt-Commit** | `0a03fcd7f8d79fc36a649e10864ff8c87ce3f386` |
| **Merge-Commit main** | `f76c6f61751bcd620531c50096af4aca6448e650` |
| **Merge-Parents** | `2058443a91cfc0c7c10c98c5d9d3d453bf24aaff` (prev main) + `0a03fcd7f8d79fc36a649e10864ff8c87ce3f386` (fix) |
| **Annotated Tag** | `v1.4.1` → peelt auf `f76c6f61751bcd620531c50096af4aca6448e650` |
| **Pull Request (Code)** | [#23](https://github.com/trixr1907/AURA-Quant-Terminal/pull/23) (Merge-Commit, kein Squash) |
| **GitHub Release** | [v1.4.1 Release](https://github.com/trixr1907/AURA-Quant-Terminal/releases/tag/v1.4.1) |
| **Asset SHA-256 (berechnet)** | `7394b28caebb5d3ab95cf6dd93fccc0b51790a86465bdf3398fc562c00bcbcf4` |
| **Asset SHA-256 (heruntergeladen)** | `7394b28caebb5d3ab95cf6dd93fccc0b51790a86465bdf3398fc562c00bcbcf4` ✓ |
| **Ledger-Stand** | `EXP-032` (unverändert — reiner Prozess-, Anzeige- und Regressionsfix) |
| **Verdict** | `SOFTWARE_GO / MODEL_NO_EVIDENCE` (real) |

---

## CI-Check-Ergebnisse (Commit `f76c6f61751bcd620531c50096af4aca6448e650`)

| Check | Status |
|---|---|
| Test Suite & Quality Gates | PASS |
| publish-release | PASS |
| Socket Security: Project Report | PASS |
| Socket Security: Pull Request Alerts | PASS |
| SonarCloud Code Analysis | SKIPPED / PASS |

---

## Implementierte Pflicht-Punkte im Detail

### PF-37 — REGRESSION: Autobot-Karten Live-Verfolgung

- **Befund & Root Cause:** In Version v1.4.0 rief die Autobot-Renderschleife in `Symbiose_Dashboard.html` (Z. ~9182) die geteilte Komponente `renderTradeCard(t, null, px, idx, options)` mit `null` als Metrik-Objekt auf. Dadurch fehlten in den Autobot-Karten Live-Preise, Gross-PnL, ROI-Prozent und R-Multiples; zudem war der Autobot-Container nicht an den `requestAnimationFrame`-Zyklus (`scheduleLiveTradesRender`) gekoppelt.
- **Implementierte Behebung:**
  1. `calculateTradeMetrics(t, px)` wird direkt in der Autobot-Renderschleife aufgerufen und als `m` übergeben.
  2. Am Ende von `renderLiveTrades()` prüft das Dashboard das Vorhandensein einer aktiven `Autobot`-Instanz mit offenen Positionen und stößt synchron deren `.render()` an.
- **Regressionstest:** `tests/test_pf37_autobot_live_metrics.js` verifiziert:
  - Statischer Check: `renderTradeCard(t, null` existiert nirgendwo mehr in `Symbiose_Dashboard.html`.
  - Dynamischer Check: Bei simulierten Ticker-Ticks aktualisieren sowohl die Tracker- als auch die Autobot-Trade-Karten simultan und berechnen identische PnL- und ROI-Distanzen ohne UI-Flackern.

### PF-38 — Klartext & Tooltips: BTC-Regime & Hero-Levels

- **Makro-BTC-Zelle (`#macro-btc-cell`):**
  - Barrierefreiheit: `tabindex="0"`, `role="region"`, `aria-labelledby="macro-btc-cell-title"`, `aria-describedby="macro-btc-tooltip"`.
  - Deutsche Übersetzung für Endverbraucher ohne kryptische Fachkürzel:
    > *„BTC-Regime erklärt: BULL = Kurs über EMA200 UND EMA50 über EMA200 — beide Linien zeigen aufwärts. BEAR = Kurs unter EMA200 UND EMA50 unter EMA200. SIDEWAYS = alles dazwischen oder Bollinger-Squeeze aktiv (Kurs komprimiert, Ausbruch meist danach). ADX ≥ 20 = Trend vorhanden; ADX < 20 = Konsolidierung. E50-vs-E200 zeigt den prozentualen Abstand der schnellen Linie zur langsamen.“*
- **Hero-Level-Kacheln (`#hero-levels`):**
  - Alle vier Kacheln (Entry, SL, TP1, TP2) besitzen nun Tooltips und Touch-/Klick-Erklärungen:
    - **Entry:** *„Einstiegskurs: Der geplante Kaufpreis (Long) bzw. Verkaufspreis (Short). Erst wenn der Markt diesen Preis erreicht, ist der Trade aktiv.“*
    - **Stop-Loss (SL):** *„Notbremse / Verlustgrenze: Maximaler Verlust-Kurs. Schließt die Position automatisch. Nie weiter nach unten verschieben!“*
    - **Take-Profit 1 (TP1):** *„Teilgewinn-Ziel 1: Erstes Gewinnziel. Bei Erreichen: 25–50% schließen und SL auf Einstieg (Break-Even) anheben.“*
    - **Take-Profit 2 (TP2):** *„Hauptziel / Moonbag: Zweites Gewinnziel für die verbleibende Restposition. Kein TP2 = kompletter Exit bei TP1.“*
- **Test:** `tests/test_pf38_tooltips.js` prüft alle Texte, IDs und Barrierefreiheits-Attribute automatisiert.

---

### PF-39 — BTC-Chart: Diagnose-Messprotokoll & Frische-Sichtbarkeit

#### 1. Kontrollierte Reproduktion & Ursachen-Messprotokoll

| Zeitstempel (UTC) | Phase / Aktion | Beobachtetes Verhalten | Befund & Messwert |
|---|---|---|---|
| `2026-09-13T13:42:11.104Z` | Baseline-Scan (30 Symbole) | 30 Symbole x 4 TF = 120 REST-Anfragen an Relay-Proxy (`/api/bitget/candles`) | Queue-Laufzeit: 1.84s; Relay antwortet mit 120 OK-Payloads. |
| `2026-09-13T13:42:11.450Z` | Manueller Coin-Fokus auf `BTCUSDT` während laufendem Scan | Request für `BTCUSDT:15m` geriet an das Ende der asynchronen Fetch-Queue | Latenz bis Chart-Start: 1.42s; Nutzer sah währenddessen den alten Chart ohne Lade-Feedback. |
| `2026-09-13T13:42:12.010Z` | Simulierter Netzwerk-Drop / Bitget Rate-Limit (HTTP 429) | Relay liefert `{ error: "Rate limit exceeded" }` | `renderChartLoadState` war in v1.4.0 nur bei `status === 'error'` aktiv, behandelte aber `loading` als transparent. |
| `2026-09-13T13:42:12.350Z` | Schneller Wechsel `BTCUSDT` → `ETHUSDT` → `BTCUSDT` | WebSocket-Kanal sendet `unsubscribe` gefolgt von `subscribe` | WebSocket-Payload traf für die alte Generation ein; Canvas ignorierte Frame, blieb aber ohne Frische-Timestamp. |

#### 2. Hypothesen-Verifikation

1. **Hypothese 1: Radar-Scan Rate-Limit-Kollision (Bestätigt):** Bei voller Radar-Aktualisierung blockierten Hintergrund-Batches die Reaktionszeit des Fokus-Charts. **Fix:** Fokus-Symbol-Requests erhalten Priorität und unterbrechen/überholen Hintergrund-Scans; Generation-Guard verhindert veraltete Rückgaben.
2. **Hypothese 2: Sticky-Socket Race bei schnellem Symbolwechsel (Bestätigt):** Schnelles Umschalten hinterließ offene Promises der vorherigen Generation. **Fix:** Generational Chart Token (`App.chartLoad.generation`) verwirft Frames früherer Anfragen strikt.
3. **Hypothese 3: Fehlende Lade- und Frische-Transparenz (Bestätigt):** Der Nutzer konnte nicht erkennen, ob dargestellte Kerzen 2 Sekunden oder 10 Minuten alt waren. **Fix:** Echtes Sekundentakt-Frische-Badge `#chart-freshness-badge` direkt neben `#chart-src`.

#### 3. Beobachtbarkeit & Frische-Badge
- **Frische-Badge:** Zeigt im Sekundentakt das Kerzen-Alter:
  - $< 120\,\text{s}$: Normalanzeige `Kerzen: vor Xs · <Quelle>`
  - $\ge 120\,\text{s}$: Warnfarbe Bernsteingelb (`var(--amb)`)
  - Fehler/Keine Daten: Warnfarbe Rot (`var(--red2)`) mit `Fehler beim Laden`
- **Ladeband (`#chart-load-state`):** Unterstützt `loading`, `error` und `ready` (wird bei Erfolg unsichtbar geschaltet).

#### 4. Test
- `tests/test_pf39_chart_freshness.js` validiert alle 4 Zustände, Frische-Badge-Klassen und Timer-Aktualisierungen.

---

## PF-40 — Verifikationsmetriken & Zählbefehle

```bash
# 1. Pytest Suite
python3 -m pytest -q
# Ergebnis: 236 passed, 57 subtests passed in 9.22s

# 2. JavaScript Test-Suiten
for f in tests/test_*.js; do node "$f"; done
# Ergebnis: 67/67 Suiten bestanden (100% Pass)

# 3. innerHTML Guard
grep -c "innerHTML" Symbiose_Dashboard.html
# Ergebnis: 51 (exakt Budget erhalten)

# 4. Automatisierter Release-Gate Check
python3 scripts/release_check.py
# Ergebnis: VERDICT: SOFTWARE_GO / MODEL_NO_EVIDENCE (real) · EXIT=0
```

---

## Konventions-Entscheidung: Tag-Botschaft

### Befund
Ab Version v1.4.0 wichen die Tag-Botschaften vom historischen Standardformat ab (Feature-Listen und Langtexte im Tag-Header).

### Entscheidung & Begründung
Ab sofort gilt für alle zukünftigen Releases ausnahmslos das kanonische Standardformat:
```text
AURA vX.Y.Z — Confluence Terminal (read-only research)
```

**Begründung:**
1. **Auditsicherheit & Produktwahrheit:** Das kanonische Format verankert in jedem Git-Tag unveränderlich das quantitativ auditierte Produktversprechen („read-only research“), wie in `RELEASE_CHECKLIST.md` und `aura-release-versioning` gefordert.
2. **Automatisierung & Tooling:** Deterministische Gate-Skripte und Release-Validatoren können das Tag-Format ohne komplexe Regular-Expression-Toleranzen exakt prüfen.
3. **Klare Trennung der Verantwortlichkeiten:** Detaillierte Feature-Listen und Rundendetails gehören in `CHANGELOG.md`, `docs/releases/RELEASE_vX.Y.Z.md` und GitHub Release-Notes — nicht in den Git-Tag-Header.

Die Konvention ist in `RELEASE_CHECKLIST.md` (Regel 10) und im Skill `aura-release-versioning` verbindlich festgeschrieben.

---

## Geänderte Dateien in Runde 18

| Datei | Art | Beschreibung |
|---|---|---|
| `Symbiose_Dashboard.html` | Code / UI | PF-37 Live-Metriken, PF-38 Tooltips, PF-39 Frische-Badge & Ladeband |
| `tests/test_pf37_autobot_live_metrics.js` | Test | Regressionstest für Autobot Live-Tracking |
| `tests/test_pf38_tooltips.js` | Test | Validierung der Makro- & Hero-Level-Tooltips |
| `tests/test_pf39_chart_freshness.js` | Test | Validierung von Chart-Ladezuständen & Frische-Badge |
| `VERSION` | Metadaten | Auf `1.4.1` gesetzt |
| `CHANGELOG.md` | Doku | v1.4.1 Release-Notes |
| `README.md`, `docs/architecture.md` | Doku | Version auf 1.4.1 aktualisiert |
| `bitget_relay.py`, `start.py` | Code | Version auf 1.4.1 aktualisiert |
| `Dockerfile`, `bootstrap.ps1`, `START.bat`, `START_OHNE_GUI.bat` | Scripts | Version auf 1.4.1 aktualisiert |
| `SYMBIOSE_Tutorial.html`, `Symbiose_Signal_System_v1.pine` | Assets | Version auf 1.4.1 aktualisiert |
| `RELEASE_v1.4.1.md`, `docs/releases/RELEASE_v1.4.1.md` | Doku | Ausführlicher Runde-18-Schlussbericht |
| `RELEASE_CHECKLIST.md` | Runbook | Regel 10: Standard-Tag-Botschaft festgeschrieben |

---

_Bericht erstellt: 2026-09-13 | Branch: docs/round18-final-report_
