# AURA Quant Terminal — Runde 18 Schlussbericht (v1.4.1, PATCH)

## Zusammenfassung

Runde 18 adressiert das Feedback des Systemeigentümers zu v1.4.0 in Form eines fokussierten PATCH-Releases (PF-37 bis PF-40):
1. **PF-37 (Regression):** Behebung fehlender Live-Metriken in den Autobot-Trade-Karten (`renderTradeCard(t, null, …)` → echte `calculateTradeMetrics(t, px)`-Werte mit synchroner Ticker-Kopplung).
2. **PF-38 (Klartext & Tooltips):** Laienverständliche deutsche Übersetzungen und Barrierefreiheits-Attribute (`tabindex="0"`, `aria-describedby`) für das Makro-BTC-Regime und alle Hero-Level-Kacheln.
3. **PF-39 (BTC-Chart Frische & Diagnose):** Kontrollierte Fehlerreproduktion, Ursachenmessprotokoll (Rate-Limits, Socket-Races, Ladeband-Zustände) und Einführung des Sekundentakt-Frische-Badges `#chart-freshness-badge`.
4. **PF-40 (Verifikation & Release-Hygiene):** 100% grüne Gates (236 pytest, 57 Subtests, 67/67 JS-Suiten, innerHTML=51), deterministischer Release-Check `EXIT=0`.

---

## Git- & Release-Belege (mit Befehl & Ausgabe)

Alle Hashes und Artefakt-Nachweise wurden direkt aus der Git-Historie und dem Dateisystem ausgelesen:

```bash
# 1. Release Merge-Commit (PR #23)
git rev-parse v1.4.1^{commit}
# -> f76c6f61751bcd620531c50096af4aca6448e650

# 2. Release Merge-Parents
git log -1 --format="%H %P" f76c6f61751bcd620531c50096af4aca6448e650
# -> f76c6f61751bcd620531c50096af4aca6448e650 2058443a91cfc0c7c10c98c5d9d3d453bf24aaff 0a03fcd7f8d79fc36a649e10864ff8c87ce3f386

# 3. Docs Merge-Commit (PR #24)
git log -1 --format="%H" origin/main
# -> 8828e50b1bd3bbf50909ab6ed08d9def80fe81de

# 4. Docs PR-Commit
git log -1 --format="%H" ed8d692965832937339d012cb10885a41fe0ad07
# -> ed8d692965832937339d012cb10885a41fe0ad07

# 5. Asset-SHA-256 (nach Download von GitHub Release)
sha256sum /tmp/symbiose_downloaded.zip
# -> 7394b28caebb5d3ab95cf6dd93fccc0b51790a86465bdf3398fc562c00bcbcf4  /tmp/symbiose_downloaded.zip
```

| Artefakt / Nachweis | Wert |
|---|---|
| **Release-Version** | `1.4.1` (PATCH) |
| **Produkt-Branch** | `fix/round18-v1.4.1` |
| **Produkt-Commit** | `0a03fcd7f8d79fc36a649e10864ff8c87ce3f386` |
| **Merge-Commit main (Code, PR #23)** | `f76c6f61751bcd620531c50096af4aca6448e650` |
| **Merge-Parents (PR #23)** | `2058443a91cfc0c7c10c98c5d9d3d453bf24aaff` + `0a03fcd7f8d79fc36a649e10864ff8c87ce3f386` |
| **Annotated Tag** | `v1.4.1` → peelt auf `f76c6f61751bcd620531c50096af4aca6448e650` |
| **Docs-Branch** | `docs/round18-final-report` |
| **Docs-Merge-Commit (main, PR #24)** | `8828e50b1bd3bbf50909ab6ed08d9def80fe81de` |
| **Pull Request (Code)** | [#23](https://github.com/trixr1907/AURA-Quant-Terminal/pull/23) (Merge-Commit, kein Squash) |
| **Pull Request (Docs)** | [#24](https://github.com/trixr1907/AURA-Quant-Terminal/pull/24) (Merge-Commit, kein Squash) |
| **GitHub Release** | [v1.4.1 Release](https://github.com/trixr1907/AURA-Quant-Terminal/releases/tag/v1.4.1) |
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

#### 2. Hypothesen-Status & Transparenz

1. **Hypothese 1: Radar-Scan Rate-Limit-Kollision (Bestätigt & Sichtbar gemacht):**
   - *Status in v1.4.1:* Durch das neue Frische-Badge `#chart-freshness-badge` und das sichtbare Ladeband `#chart-load-state` wird dieser Zustand dem Nutzer sofort ehrlich offengelegt („Lade Chart-Daten …“ bzw. Frische-Alter in Sekunden).
   - *Offener Punkt & Plan für v1.5.0:* Eine dedizierte Vorrang-Queue / Unterbrechung des Hintergrund-Radar-Scans bei manuellem Fokus-Symbol-Wechsel ist im aktuellen Relay/Dashboard noch nicht als Scheduling-Logik implementiert und wird als Architekturverbesserung in v1.5.0 umgesetzt.
2. **Hypothese 2: Sticky-Socket Race bei schnellem Symbolwechsel (Bestätigt & abgesichert):**
   - *Status in v1.4.1:* Der generationsbasierte Schutz über `App.gen` (in `Symbiose_Dashboard.html` Z. ~6520) stellt sicher, dass asynchrone Chart-Rückgaben und Socket-Frames verworfen werden, wenn der Nutzer zwischenzeitlich auf ein anderes Symbol gewechselt hat (`if (gen !== App.gen) return;`).
3. **Hypothese 3: Fehlende Lade- und Frische-Transparenz (Behoben):**
   - *Status in v1.4.1:* Gelöst durch das Sekundentakt-Frische-Badge `#chart-freshness-badge` und das korrigierte `#chart-load-state`-Band.

#### 3. Beobachtbarkeit & Frische-Badge
- **Frische-Badge (`#chart-freshness-badge`):** Zeigt im Sekundentakt das Kerzen-Alter:
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

## Konventions-Entscheidungen

### 1. Tag-Botschaft: Standardformat festgeschrieben
Ab sofort gilt für alle zukünftigen Releases ausnahmslos das kanonische Standardformat:
```text
AURA vX.Y.Z — Confluence Terminal (read-only research)
```
**Begründung:**
- **Auditsicherheit:** Verankert das quantitativ auditierte Produktversprechen („read-only research“) unveränderlich im Git-Objekt.
- **Deterministische Automation:** Release-Gates können das Tag-Format ohne Freitext-Toleranzen prüfen.
- **Klare Trennung:** Feature-Listen gehören in `CHANGELOG.md` und `docs/releases/RELEASE_vX.Y.Z.md` — nicht in den Tag-Header.
- Verankert in `RELEASE_CHECKLIST.md` (Regel 10) und Skill `aura-release-versioning`.

### 2. Berichts-Hashes: Verbindliche Befehl+Ausgabe-Zitierregel
Jeder Git-Hash in Berichten und Dokumenten wird als ausgeführter Terminalbefehl mit zugehöriger Ausgabe zitiert (`git rev-parse`, `git log`, `sha256sum`), um jegliche Rekonstruktions- oder Übertragungsfehler auszuschließen (verankert in `RELEASE_CHECKLIST.md`, Regel 2).

### 3. Dokumentationsablage unter `docs/releases/`
Das vollständige Diagnose- und Messprotokoll wurde bewusst direkt im Release-Dokument `docs/releases/RELEASE_v1.4.1.md` integriert, da es den genauen Zustand, die Fehlerreproduktion und den verifizierten Funktionsumfang von v1.4.1 als unteilbare Einheit auditierbar dokumentiert.

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
| `RELEASE_v1.4.1.md`, `docs/releases/RELEASE_v1.4.1.md` | Doku | Ausführlicher Runde-18-Schlussbericht inkl. Messprotokoll & Konventionen |
| `RELEASE_CHECKLIST.md` | Runbook | Regel 2 (Hash-Zitierpflicht) & Regel 10 (Tag-Botschaft) festgeschrieben |

---

_Bericht aktualisiert: 2026-09-13 | Commit: ed8d692 / 8828e50_
