# AURA R40 — Konsolidierter Audit-Befundbericht

**Datum:** 2026-09-17 · **Basis:** `de25830` (v2.5.0) · **Branch:** `audit/r40-baseline`
**Methode:** 4 parallele Read-only-Subaudits (Quant-Math, Integrity/Security, Dataflow/Architektur, UX), kritische Befunde anschließend vom Lead direkt im Code verifiziert. Vollberichte: `docs/research/audit_r40/{quant,integrity,dataflow,ux}.md`. Baseline: `docs/research/BASELINE_R40_20260917.md`.

**Wichtig:** Die Baseline-Testsuites sind grün (508+69 pytest, 98/98 JS, Gate `SOFTWARE_GO / MODEL_NO_EVIDENCE`). Die Befunde unten sind Verhaltenslücken, die die vorhandenen Tests nicht abdecken — kein Widerspruch, sondern ein Discovery-Befund über Gate-Abdeckung.

## 1. Verifizierte Kernbefunde (vom Lead im Code gegengeprüft)

| ID | Schwere | Befund | Beleg (Datei:Zeile) | Verifikation |
|---|---|---|---|---|
| Q-01 | CRITICAL | **Server-Runner verrechnet realisierten PnL niemals mit der Equity.** Beim Öffnen wird Margin abgezogen (`state.equity -= margin`), beim Schließen nur die Margin zurückgebucht (`state.equity += updated.margin`). `realizedPnl` wird zwar in die Historie geschrieben, fließt aber nie in `state.equity`. Folge: Equity bleibt dauerhaft auf `initialEquity` eingefroren; Kelly-Sizing und Drawdown-Schutz arbeiten mit konstantem, falschem Kontostand. | `headless_autobot.js:981` (Debit), `:644` (Rückbuchung ohne PnL), `:1075` (realizedPnl nur Historie) | Direkt gelesen, bestätigt |
| Q-02 | CRITICAL | **Kein Take-Profit-Exit-Pfad im Server-Runner.** TP1/TP2/TP3 setzen nur Flags + ntfy-Events; weder Teilverkauf noch Schluss. Trades enden ausschließlich via SL (bzw. Break-Even nach Auto-BE) oder Time-Stop. Semantik driftet hart vom Dashboard ab (das Scale-Outs + TP-Schluss kennt). | `headless_autobot.js:624-632` vs. `Symbiose_Dashboard.html:10270-10354` | Direkt gelesen, bestätigt |
| Q-03 | HIGH | **Falscher Exit-Grund in der Historie:** `closeTradeRecord(updated, markPrice, closed ? 'sl_close' : 'timestop')` steht innerhalb `if (closed)` → jeder Time-Stop wird als `sl_close` protokolliert. Verfälscht Exit-Attribution und alle Statistiken, die danach gruppieren. | `headless_autobot.js:642` | Direkt gelesen, bestätigt |
| Q-04 | MEDIUM | **SL-Prüfung logisch fehlerhaft maskiert:** `if (!trade.slHit && !hit(trade.tp1 \|\| trade.tp))` überspringt die SL-Prüfung, solange der Kurs jenseits TP1 steht. Praktische Auswirkung aktuell begrenzt (bei Long mit `currentSl = entry < tp1` kann SL in dem Tick ohnehin nicht auslösen), aber die Kondition koppelt zwei unabhängige Ereignisse und bricht, sobald ein Trailing-Stop über TP1 liegt. | `headless_autobot.js:332` | Direkt gelesen, bestätigt; Impact-Analyse vom Lead (Herabstufung HIGH→MEDIUM) |
| S-01 | CRITICAL | **Keine Authentifizierung auf privilegierten Endpunkten.** `check_relay_token` existiert im released Code nicht; `_authorize_privileged` lässt Requests ohne Origin-Header (cURL, Skripte, SSRF) ungeprüft durch. Jeder LAN-Client kann Config und State schreiben. | `bitget_relay.py:2095-2110`; `grep` → kein `check_relay_token` | Direkt geprüft (grep + Code) |
| S-02 | HIGH | **Keine serverseitige Validierung von `/api/bot-config`.** Beliebige JSON-Werte (negatives Risiko, `mtfNeed: 0`, ungültige Typen) werden persistiert und vom Runner übernommen. Nutzer-WIP-Test `test_bot_config_security.py` (untracked, Alt-Checkout) beschreibt exakt die fehlende Funktion — als Requirement übernommen. | `bitget_relay.py:2326`, `:1357` | Direkt geprüft |
| S-03 | HIGH | **`/api/signals` ungeschützt** (nicht in `_PRIVILEGED_PATHS`): beliebige Akteure können ntfy-Pushes auslösen. | `bitget_relay.py:2404` | Subaudit, stichprobenartig bestätigt |
| S-04 | HIGH | **Not-Halt unmöglich:** Runner forciert `paused:false`/`pausedBy:null` („Server-Only Live", v2.5.0 gewollt), es gibt keinen serverseitigen Halt für neue Entries und kein UI-Sicherheitsventil. Kollidiert mit Mandats-Anforderung §8 (bestätigungspflichtiger Not-Halt). | `headless_autobot.js:418-420, 531-532` | Direkt geprüft; als Design-Anforderung für Neuentwicklung übernommen |
| S-05 | HIGH | **Docker markiert unhealthy, startet aber nicht neu.** `restart: unless-stopped` reagiert nur auf Prozess-Exit, nicht auf Healthcheck-Status. Ein Container mit stehendem Feed bleibt dauerhaft `unhealthy` ohne Recovery. | `docker-compose.yml:9,37` | Bestätigt (Docker-Semantik) |
| D-01 | HIGH | **Drei Produktionsimplementierungen derselben Formeln:** JS-Engine (Dashboard), Python-Duplikat im Relay (EMA/ATR/ADX/Regime für Signal-Center), Pine. Der Runner extrahiert die JS-Engine per `vm`-Sandbox aus dem HTML (`loadEngine`). Drift-Risiko ist über Tests begrenzt, aber es gibt keine kanonische Produktionsimplementierung. | `bitget_relay.py:588-681`, `headless_autobot.js:54-150` | Bestätigt |
| D-02 | MEDIUM | **Keine Gap-Erkennung/Backfill:** Klines werden als 1000-Bar-Snapshot geladen, sortiert, nicht auf Lücken geprüft. Fallback-Kette ist für Signale korrekt fail-closed (`liquidityVerified:false` → Reject `LIQUIDITY`) — das bleibt Vorbild. | `headless_autobot.js:229-249`, `Symbiose_Dashboard.html:5087-5126` | Bestätigt |
| D-03 | MEDIUM | **Persistenz = JSON-Flatfiles** mit OCC (`_rev`, HTTP 409) und atomaren Writes — sauber implementiert, aber kein transaktionales Mehrprozess-Modell, keine performanten historischen Abfragen. Ohne Volume: Totalverlust aller Trades/Historie/Claims bei Container-Recreation. | `bitget_relay.py:240-460`, `docker-compose.yml:38` | Bestätigt |
| U-01 | HIGH | **Kein globaler Not-Halt/Panic-Button im UI**; Trades nur einzeln schließbar. | UX-Report Befund 1 | Subaudit |
| U-02 | HIGH | **Dead UI:** `#tv-drawing-tool-modal` (Z. 675-753) ohne JS-Binding. | UX-Report Befund 2 | Subaudit |
| U-03 | HIGH | **Statische Default-KPIs** (`10,000 USDT`, `0.0% ROI`) im Autobot-Panel täuschen intakten Zustand vor, bevor Serverdaten geladen sind. | UX-Report Befund 3 | Subaudit |
| U-04 | MEDIUM | Touch-Targets <44px (`.ab-toggle-btn` 28px, Config-Buttons ~24px), Micro-Typography 9-10px mobil. | UX-Report Befunde 4-5 | Subaudit |
| U-05 | MEDIUM | Kein Stale-Overlay auf offenen Positionen bei WS-Ausfall; PnL friert unmarkiert ein. `● SERVER LIVE`-Badge kann als Echthandel missverstanden werden. | UX-Report Befunde 6-7 | Subaudit |

## 2. Weitere Befunde (Subaudits, nicht einzeln nachverifiziert — als plausibel übernommen)

| ID | Schwere | Befund | Beleg |
|---|---|---|---|
| Q-05 | MEDIUM | Funding-Z-Score nutzt Populationsvarianz (N statt N-1) → Z bei kleinen Stichproben ~2.5-5% überhöht | `Symbiose_Dashboard.html:1599` |
| Q-06 | MEDIUM | Liquidationspuffer als Faustformel `100/L − 0.5%` ohne Bitget-MMR-Tiers; muss als Schätzung gekennzeichnet sein | `Symbiose_Dashboard.html:1837` |
| Q-07 | MEDIUM | Keine Funding-Haltekosten (Carry) im Walk-Forward/Shadow bei mehrtägigen Holds → leicht optimistisches Net-R | `Symbiose_Dashboard.html:1992`, `shadow_collector.js:83` |
| Q-08 | LOW | OBV Index-Underflow bei i=0 (`c[-1]` → undefined) | `Symbiose_Dashboard.html:1193` |
| Q-09 | LOW | VWAP-Tagesreset setzt ms-Zeitstempel voraus (Sekunden würden Reset blockieren) | `Symbiose_Dashboard.html:1200` |
| Q-10 | LOW | Relay-Bollinger nutzt N statt N-1 (paritär zum Dashboard, statistisch Populationsvarianz) | `bitget_relay.py:663` |
| S-06 | MEDIUM | Keine Ledger-Verifikation beim Relay-Start (nur CI/Gate) | `bitget_relay.py:2758-2765` |
| S-07 | MEDIUM | `/api/public` ohne Pfad-Allowlist (alles unter `/api/` wird zu Bitget durchgereicht) | `bitget_relay.py:2419-2442` |
| S-08 | LOW | `image: aura-quant-terminal:latest` (mutables Tag) | `docker-compose.yml:9` |
| U-06 | LOW | Tutorial-Kapitelnummerierung springt 6→8 | `SYMBIOSE_Tutorial.html:330-350` |

## 3. Was nachweislich korrekt ist (Stärken, nicht über Bord werfen)

- **Mathematische Kerne:** DSR (Bailey & López de Prado 2014), PAVA-Kalibrierung, Fractional Kelly mit Caps/Shrinkage, Confluence-Gewichte (Summe exakt 1.0), Guards gegen Nullteiler/NaN — mit Python-Oracle-Parität belegt (65 Formeln inventarisiert, `audit_r40/quant.md`).
- **Kausale Datenhygiene:** nur geschlossene Kerzen für Signale/Backtest, t1-Purging im Walk-Forward, konservative Intrabar-Policy (SL zuerst bei SL+TP in derselben Kerze), `lookahead_off` in Pine.
- **Fail-closed Fallbacks:** Offline-/Static-Universe blockiert Signale (`LIQUIDITY`-Reject), statt mit nicht-äquivalenten Daten zu handeln.
- **State-Store:** atomare Writes, OCC mit HTTP 409 + Client-Reconcile, Schema-Migration v1→v2 mit Backup und fail-closed bei unbekanntem Schema.
- **Ops-Hygiene:** CI pinnt Actions auf SHAs, Non-Root-Container, read-only Root-FS, `cap_drop: ALL`, Secret-Scan im Gate, kein Secret im Repo gefunden.
- **Evidenz-Kultur:** Append-only Trials-Ledger mit Hash-Kette + Checkpoint, Lockbox `UNUSED`, ehrliches `MODEL_NO_EVIDENCE`.

## 4. Konsequenz für die Neuentwicklung

Die Befunde Q-01..Q-04, S-01..S-05, D-01..D-03 sind strukturell: sie betreffen den Server-Runner, die fehlende Auth-Schicht und die dreifache Engine. Sie werden **nicht** im Alt-Code geflickt, sondern durch die Zielarchitektur (siehe `docs/ARCHITECTURE.md`) behoben: kanonische Python-Engine, DB-Persistenz, authentifizierte Control Plane, Runner-Zustandsmaschine mit Not-Halt. Die Alt-Implementierung dient als Referenz-Orakel für Paritätstests (Golden-Fixtures), bis die neue Engine Parität bewiesen hat.
