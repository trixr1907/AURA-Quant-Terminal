# AURA — Abschlussbericht Runde 15: Feed-Rotation-Bug, Bitget-Keepalive & Sticky-Socket (v1.3.1)

**Datum:** 2026-09-13  
**Auditor:** Hermes Agent (Senior Quant Systems Auditor & Coding Agent)  
**Ausgangsversion:** v1.3.0  
**Zielversion:** v1.3.1 (PATCH Release gem. SemVer-Policy)  
**Ledger-Status:** `EXP-031` (6 Einträge, Chain-Head `d9d270cdd62e247d045d7ed576e619800506f04f7f83335d348fec71cfb761d5`, 10 Modell-Experimente unverändert)  
**Verdict:** `SOFTWARE_GO / MODEL_NO_EVIDENCE` (real) · `synthetic-gate: PAPER_CANDIDATE` · `lockbox-eval: UNUSED`  

---

## 1. Übersicht & Wurzelursachen-Analyse

Der Eigentümer meldete folgendes Verhalten im Dashboard: Die Feed-Status-Pill zeigt beim Laden `LIVE · bitget-ws`, wechselt jedoch nach jeder Nutzer-Interaktion (wie Coin-/Symbol-Auswahl) auf `binance-fallback`.

Im Rahmen des forensischen Audits wurden zwei Wurzelursachen im Code verifiziert und behoben:
1. **Verlorener `wsTry`-Reset:** `wsTry` (der Feed-Index in `connectWS()`) wurde bei erfolgreichem `ws.onopen` nicht zurückgesetzt. Der v1.2.11-Feeds-Umbau hatte diesen Reset verloren. Dadurch rotierte jeder Neuaufbau (durch Symbolwechsel oder Reconnect) den Feed-Index weiter (`bitget-ws` → `binance-fallback` → `binance-vision-fallback` → ...).
2. **Fehlender Client-Keepalive-Ping:** Gemäß Bitget v2 WebSocket-Dokumentation trennt der Bitget-Server Verbindungen serverseitig, wenn kein anwendungsbezogener Client-Ping (`ws.send('ping')`) gesendet wird. Die serverseitige Trennung löste kaskadierende Reconnects und damit weitere unerwünschte Feed-Wechsel aus.

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

## 3. GitHub-API-Belege (Verifikationsnachweis)

### 3.1 Produkt Pull Request & Merge Commit
- **PR:** [#17 (fix(dashboard): fix feed rotation, add bitget keepalive, sticky socket, fallback pill, and feed-independent CVD (v1.3.1))](https://github.com/trixr1907/AURA-Quant-Terminal/pull/17)
- **Merge-Methode:** Normaler Merge-Commit (`--merge`, kein Squash — exakt 2 Parents)
- **Produkt-Merge-Commit SHA:** `9aa3b98820580f5449f17001876e30ed35cc01fb`
- **Merge-Parents (2 Parents nachgewiesen):**
  - Parent 1 (`main` vor PR #17): `b70c4465aca32e863fd4f1e90ecbad0b3a0738b2`
  - Parent 2 (`fix/round15-feed-rotation-bug` HEAD): `88d90a58ff8cc419d3cf95f4b726bafb43a4f4d6`

### 3.2 Annotierter Release-Tag
- **Tag:** `v1.3.1`
- **Tag-Objekt SHA:** `7d4142459522bf0782d995ceed8a597b3e77da5e`
- **Tag-Peel SHA (`v1.3.1^{commit}`):** `9aa3b98820580f5449f17001876e30ed35cc01fb`
- **Tag-Message:** `AURA v1.3.1 — Confluence Terminal (read-only research)`

### 3.3 GitHub Actions Check-Run Conclusions auf Merge Commit `9aa3b98`
- `SonarCloud Code Analysis`: status=`completed`, conclusion=`neutral`
- `Socket Security: Project Report`: status=`completed`, conclusion=`success`
- `publish`: status=`completed`, conclusion=`success`
- `Test Suite & Quality Gates`: status=`completed`, conclusion=`success`

### 3.4 GitHub Release Asset (`symbiose.zip`)
Das Asset wurde nach dem Upload via GitHub API heruntergeladen und unabhängig gehasht:
- **Download-URL:** `https://github.com/trixr1907/AURA-Quant-Terminal/releases/download/v1.3.1/symbiose.zip`
- **Asset-Dateigröße:** `229.118 Bytes`
- **SHA-256 (nach Upload heruntergeladen):**  
  `2ed29ace5859abab759739491281bc07582fca979e8a566e629c637540aba5f6`
- **Dateianzahl im ZIP-Archiv:** `26 Dateien`
- **VERSION im ZIP-Archiv:** `1.3.1`
- **Enthaltene Pflichtdateien:** `LICENSE`, `RELEASE_v1.3.1.md`, `README.md`, `VERSION`, `Dockerfile`, `Symbiose_Dashboard.html`, `bitget_relay.py`.

---

## 4. SonarCloud Audit-Klärung

Auf dem PR-Run (#17) meldete SonarCloud folgende Failures/Warnings:
1. **Regel `javascript:S5247` ("Make sure that this dynamic injection or execution of code is safe"):**
   - Betroffene Stellen: `tests/test_feed_status_fallback_pill.js:47`, `tests/test_bitget_keepalive.js:86`, `tests/test_cvd_feed_independence.js:26`.
   - **Bewertung & Begründung:** Die Tests laden isolierte Funktionsblöcke aus `Symbiose_Dashboard.html` über Node.js `vm.runInNewContext()` in eine geschlossene Sandbox, um reines Single-File-Client-HTML ohne Build-Schritt modular testen zu können. Dies ist der etablierte, hermetische Test-Pattern des Projekts und wird bewusst akzeptiert.
2. **Regel `javascript:S3776` ("Cognitive Complexity"):**
   - Betroffene Stellen: `Symbiose_Dashboard.html:5862` (Funktion `connectWS`, Score 25 vs. Threshold 15) und `Symbiose_Dashboard.html:5954` (`onmessage`, Score 23 vs. Threshold 15).
   - **Bewertung & Begründung:** Durch das Hinzufügen des Bitget-Keepalive-Pings, der Fallback-Kaskade und des Sticky-Socket-Umsubscriptions stieg die Verzweigungskomplexität der Verbindungssteuerung. Diese Logik ist intentional zentralisiert, um Race-Conditions zwischen asynchronen Sockets zu verhindern.
3. **Merge-Commit Status:**
   - Auf dem `main`-Branch-Merge-Commit läuft SonarCloud wie in allen vorherigen Runden neutral/non-blocking durch.

---

## 5. Bestätigung der Prüf- und Hygiene-Kriterien

1. **Reproduzierbare Test-Zählbefehle & Suiten-Anzahl:**
   - **Node.js Unit-Test-Dateien (`tests/test_*.js`):**
     ```bash
     for f in tests/test_*.js; do node "$f" >/dev/null && echo "$f: PASS"; done | wc -l
     ```
     **Ergebnis:** Exakt **54** (54/54 Suiten PASS; Basis 51 + 3 neue Suiten).
   - **Pytest Test-Suite:**
     ```bash
     python3 -m pytest -q
     ```
     **Ergebnis:** **224 passed, 57 subtests passed** in 8.89s (Basis 224/57).

2. **DOM-Sicherheit / innerHTML-Budget:**
   ```bash
   grep -c "innerHTML" Symbiose_Dashboard.html
   ```
   **Ergebnis:** Exakt **51** (Budget strikt eingehalten).

3. **Trials Ledger Integrity (`EXP-031`):**
   ```bash
   python3 scripts/verify_ledger.py
   ```
   **Ergebnis:**
   `{"ok":true,"last_entry_id":"EXP-031","entry_count":6,"chain_head":"d9d270cdd62e247d045d7ed576e619800506f04f7f83335d348fec71cfb761d5","total_model_experiments":10,"legacy_sha256":"23f59ef8df9f348609280d8f57583e32c2d7afc1e9b428f9d50ae75051eeeb0c"}`

4. **Finale Release-Gate-Ausgabe (`scripts/release_check.py`):**
   - **EXIT=0**
   - **Verdict:** `SOFTWARE_GO / MODEL_NO_EVIDENCE` (real) · `synthetic-gate: PAPER_CANDIDATE` · `lockbox-eval: UNUSED`
