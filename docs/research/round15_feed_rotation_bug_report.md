# AURA — Abschlussbericht Runde 15: Feed-Rotation-Bug, Bitget-Keepalive & Sticky-Socket (v1.3.1)

**Datum:** 2026-09-13  
**Auditor:** Hermes Agent (Senior Quant Systems Auditor & Coding Agent)  
**Ausgangsversion:** v1.3.0  
**Zielversion:** v1.3.1 (PATCH Release gem. SemVer-Policy)  
**Ledger-Status:** `EXP-031` (6 Einträge, Chain-Head validiert, 10 Modell-Experimente unverändert)  
**Verdict:** `SOFTWARE_GO / MODEL_NO_EVIDENCE` (real) · `synthetic-gate: PAPER_CANDIDATE` · `lockbox-eval: UNUSED`  

---

## 1. Übersicht & Wurzelursachen-Analyse

Der Eigentümer meldete folgendes Verhalten im Dashboard: Die Feed-Status-Pill zeigt beim Laden `LIVE · bitget-ws`, wechselt jedoch nach jeder Interaktion (wie Coin-/Symbol-Auswahl) auf `binance-fallback`.

Im Rahmen des forensischen Audits wurden zwei Wurzelursachen im Code verifiziert und behoben:
1. **Verlorener `wsTry`-Reset:** `wsTry` (der Feed-Index in `connectWS()`) wurde bei erfolgreichem `ws.onopen` nicht zurückgesetzt. Der v1.2.11-Feeds-Umbau hatte diesen Reset verloren. Dadurch rotierte jeder Neuaufbau (durch Symbolwechsel oder Reconnect) den Feed-Index weiter (`bitget-ws` → `binance-fallback` → `binance-vision-fallback` → ...).
2. **Fehlender Client-Keepalive-Ping:** Gemäß Bitget v2 WebSocket-Dokumentation trennt der Bitget-Server Verbindungen serverseitig, wenn kein anwendungsbezogener Client-Ping (`ws.send('ping')`) gesendet wird. Die Trennung löste kaskadierende Reconnects und damit weitere unerwünschte Feed-Wechsel aus.

---

## 2. Umgesetzte Pflicht-Arbeitspakete

### PF-18 — Feed-Index zurücksetzen
- In `ws.onopen` wird `wsTry = 0` für jeden erfolgreich geöffneten Feed gesetzt.
- Bitget ist damit nach jedem kontrollierten Reconnect wieder die primäre Wahl; Fallbacks werden ausschließlich nach echten Bitget-Verbindungsfehlern angesteuert.

### PF-19 — Bitget-Keepalive
- Solange eine Bitget-WS-Verbindung offen ist, sendet ein Intervall-Timer alle 25 Sekunden ein anwendungsbezogenes `ws.send('ping')` (Bitget v2 WS-Protokoll).
- `onmessage` ignoriert `pong`-Antworten (`'pong'` bzw. `{"data":"pong"}`) geräuschlos ohne JSON-Parse-Fehler.
- Der Timer (`App.wsPingTimer`) wird in `onclose`, `onerror` und bei Reconnects sauber via `clearInterval()` bereinigt.
- Binance-Pfade benötigen keinen App-Ping (Protokoll-Ping übernimmt der Browser).

### PF-20 — Sticky-Socket: Symbolwechsel ohne Neuverbindung
- Bei Symbol- oder Timeframe-Wechsel (`switchToAsset`, `chartTF`-Änderung) bei einer bestehenden, lebenden Bitget-Verbindung wird kein destruktives `close()` + `connectWS()` mehr ausgeführt.
- Stattdessen wird auf demselben Socket gearbeitet: `unsubscribe` für die alte Subscription und `subscribe` für die neue Symbol/Kanal-Kombination.
- Null Verbindungs-Churn und sofortige Reaktionszeiten beim Durchklicken von Assets.

### PF-21 — Pill-Ehrlichkeit: Fallback-Zustand sichtbar
- `buildFeedStatus` und `renderFeedStatus` unterstützen nun 3 Zustände:
  1. `LIVE · bitget-ws · vor <N>s` (grüne Pill, `feed-status-pill live`)
  2. `FALLBACK · <quelle> · vor <N>s` (gelbe Pill, `feed-status-pill fallback`) wenn `ws === 'live'` aber Quelle ≠ `bitget-ws`.
  3. `WS offline seit <N>s` (rote Pill, `feed-status-pill offline`)
- Begründung: Binance-Kerzen besitzen abweichende Liquiditäts- und Volumeneigenschaften. Eine Fallback-Nutzung ist für den Nutzer sofort transparent sichtbar.

### PF-22 — CVD feed-unabhängig (Pine-Range-Approximation)
- `cvdSeries` wurde vereinheitlicht: Der undokumentierte `tbv`-Zweig (`2*tbv − v`) wurde entfernt zugunsten der 1:1 Pine-paritätsgeprüften Range-Approximation:
  $$\Delta = \text{rng} > 0 \; ? \; v \cdot \frac{2c - h - l}{\text{rng}} : 0$$
- **Golden-Master-CVD-Gate:** Alle 5 Golden-Master-Datensätze bleiben 100% unverändert grün (0 Flips, relative Drift $\le 10^{-10}$).
- **Node-Test:** `tests/test_cvd_feed_independence.js` verifiziert, dass Kerzen mit `tbv: null`, `tbv: 1234` oder ohne `tbv`-Feld mathematisch identische CVD-, Delta- und EMA-CVD-Serien erzeugen.
- **Ledger-Klassifikation:** `EXP-031` registriert als `Prozess-Fix` (Konsistenz-Richtung Pine, Beseitigung undokumentierter Dual-Semantik; $\Delta = 0$, Modell-Experimente unverändert bei 10).

### PF-23 — Vollständige Test-Abdeckung
1. `tests/test_bitget_websocket_reconnect.js`: Erweitert um Sticky-Socket-Umsubscription, Feed-Index-Reset auf Bitget und saubere Fallback-Kette.
2. `tests/test_bitget_keepalive.js`: Neuer Test für 25s Ping-Timer, Pong-Toleranz und Aufräumen bei Close/Error.
3. `tests/test_feed_status_fallback_pill.js`: Neuer Test für alle 3 Pill-Zustände (LIVE, FALLBACK, OFFLINE).
4. `tests/test_cvd_feed_independence.js`: Neuer Test für Feed-Invarianz der CVD-Berechnung.

---

## 3. Zählbefehle & Prüf-Kriterien (Baseline vs. Runde 15)

1. **Pytest Test-Suite:**
   ```bash
   python3 -m pytest -q
   ```
   **Ergebnis:** `224 passed, 57 subtests passed in 8.83s` (Basis: 224/57).

2. **Node.js Unit-Test-Dateien (`tests/test_*.js`):**
   ```bash
   for f in tests/test_*.js; do node "$f" >/dev/null && echo "$f: PASS"; done | wc -l
   ```
   **Ergebnis:** Exakt **54** (Basis: 51 Suiten + 3 neue Suiten, 54/54 PASS).

3. **DOM-Sicherheit / innerHTML-Budget:**
   ```bash
   grep -c "innerHTML" Symbiose_Dashboard.html
   ```
   **Ergebnis:** Exakt **51** (Budget strikt eingehalten).

4. **Trials Ledger Integrity:**
   ```bash
   python3 scripts/verify_ledger.py
   ```
   **Ergebnis:** `EXP-031: VALID (chain valid, entry_count=6, total_model_experiments=10)`.

5. **Release Gate:**
   ```bash
   python3 scripts/release_check.py
   ```
   **Ergebnis:** `EXIT=0`, `VERDICT: SOFTWARE_GO / MODEL_NO_EVIDENCE`.
