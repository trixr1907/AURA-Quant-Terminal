# AURA — Abschlussbericht Runde 11: Dashboard-Produkt-Fixes & Feed-Verlässlichkeit (v1.2.11)

**Datum:** 2026-09-12  
**Auditor:** Hermes Agent (Senior Quant Systems Auditor & Coding Agent)  
**Ausgangsversion:** `1.2.10`  
**Zielversion / Veröffentlichte Version:** `1.2.11`  
**Kanonischer Release-Tag:** `v1.2.11` (Tag-Objekt: `4dda742a4fe835240f981f81000cc7023bf310bf`, peeled: `a0bb774a3d0d521db59347b5ad84fa55f6695b8f`)  
**Release-Urteil:** `SOFTWARE_GO / MODEL_NO_EVIDENCE` (Exit 0)

---

## 1. Executive Summary

In Runde 11 wurden sieben konkrete Produkt- und UX-Qualitätsbefunde (PF-1 bis PF-7) für das AURA Quant Terminal umgesetzt, verifiziert und über den geregelten Release-Zyklus veröffentlicht. 

Die Änderungen betreffen ausschließlich Frontend-UX, Datenfluss-Resilienz und WebSocket-Stabilität. Die quantitativen Berechnungsformeln (Signal-Score, CVD-Parität, DSR-Gate) blieben unverändert.

### Release-Gates & Hygiene-Bestätigungen
- **DOM-Sicherheit / XSS-Hygiene:** `grep -c innerHTML Symbiose_Dashboard.html` = **51** (exakt 51 Vorkommen, neue UI-Elemente nutzen strikt `textContent` / `esc()`).
- **Python Test-Suite (pytest):** **216 passed, 57 subtests passed**.
- **Node Test-Suite:** **53/53 Tests passed** (inklusive aller neuen PF-1 bis PF-7 Test-Suiten).
- **Release-Gate (`scripts/release_check.py`):** **EXIT=0**, Urteil `SOFTWARE_GO / MODEL_NO_EVIDENCE`.

---

## 2. Detaillierte Implementierung der Produkt-Fixes (PF-1 bis PF-7)

### PF-1 — Bitget WebSocket als primärer Candle-Feed mit deterministischem Reconnect
- **Problem:** Binance WebSocket war primär konfiguriert; Bitget v2 WS fehlte als nativer Feed für Bitget Futures Candlesticks.
- **Lösung:** Bitget Public WebSocket v2 (`wss://ws.bitget.com/v2/ws/public`) ist jetzt die primäre Feed-Quelle (`candle15m`, `candle1H`, `candle4H`, `candle1D`). Binance (`stream.binance.com`, `data-stream.binance.vision`) dient als geordnete Fallback-Kette.
- **CVD-Semantik:** Bitget Klines liefern kein Taker-Buy-Volume (`tbv`). Bewusst bleibt `tbv` undefiniert, sodass die Pine-paritätsgeprüfte Bar-Range-Approximation `v*(2c-h-l)/(h-l)` greift (0 Flips über 64.859 Bars).
- **Test:** `tests/test_bitget_websocket_reconnect.js` (PASS).

### PF-2 — Datenalter-Pill & Tab-Rückkehr-Aufholjagd
- **Problem:** Keine sichtbare Anzeige der Datenfrische im Dashboard; Hintergrund-Tabs veralteten durch Browser-Throttling.
- **Lösung:** `#feed-status-pill` im Header zeigt Feed-Typ und Alter (`LIVE · bitget-ws · vor 3s`). `visibilitychange`- und `window.focus`-Handler rufen bei Datenalter > 60 s sofort `loadAll()` auf.
- **Test:** `tests/test_data_freshness_resume.js` (PASS).

### PF-3 — Radar-Volumenfilter mit Live-Zählern
- **Problem:** Action Radar war bei Hunderten Paaren unübersichtlich; Filtermöglichkeit nach 24h-Quote-Volumen fehlte.
- **Lösung:** `#radar-volume-filter` (`Alle`, `≥ 500k`, `≥ 1M`, `≥ 5M`) mit dynamischer Universum-Zählung (z. B. `Alle (787)`, `≥ 500k (188)`). Reiner Display-Filter (`filterRadarByVolume`), keine Beeinflussung der Signalberechnung, Speicherung in `localStorage`.
- **Test:** `tests/test_radar_volume_filter.js` (PASS).

### PF-4 — Tranchen-gewichtete Realized Win-Rate & PARTIAL_CLOSE Events
- **Problem:** Teilverkäufe (Scale-Outs) verzerrten die Trade-Historien-Statistik oder wurden wie Voll-Schließungen gezählt.
- **Lösung:** `PARTIAL_CLOSE` Events erfassen `fractionClosed: 0.5`. `calculateHistoryStats` berechnet `realizedWinRatePct` gewichtet nach geschlossenen Tranchen und weist Brutto- sowie Netto-PnL exakt aus.
- **Test:** `tests/test_partial_close_winrate_stats.js` (PASS).

### PF-5 — Aktueller Preis & Datenalter in Live-Trade-Karten
- **Problem:** Bei offenen Trades war der aktuelle Marktpreis nicht direkt neben dem Entry-Preis ersichtlich.
- **Lösung:** Live-Markpreis, farbkodierte prozentuale Entry-Abweichung (`+8.00%`) und Stale-Data-Warnung (roter Dot bei Alter > 30s) direkt in der Trade-Karte.
- **Test:** `tests/test_live_trade_current_price_render.js` (PASS).

### PF-6 — Autobot-Zyklusstatus, Funnel-Diagnostik & Decision-Log
- **Problem:** Der Autobot-Zustand war intransparent bezüglich des letzten Scan-Zeitpunkts und Ablehnungsgründen.
- **Lösung:** `#ab-funnel-summary` mit `Letzter Scan: vor 4s`, Funnel-Durchsatz (`12 Hypothesen → 1 qualifiziert`) und ausklappbares `#ab-live-log` mit detaillierten Ablehnungsgründen (`MODEL_NO_EVIDENCE`, `DSR_GATE`).
- **Test:** `tests/test_autobot_cycle_status_log.js` (PASS).

### PF-7 — TradingView URL-Standardisierung & Schneller Relay-Fallback
- **Problem:** Falsche Formatierung für Bitget Futures URLs und Hänger bei Relay-Anfragen in Docker-/Desktop-Umgebungen.
- **Lösung:** Standardformat `BITGET:<SYMBOL>.P`. 400ms `AbortController`-Timeout für Desktop-Relay-Anfragen mit sofortigem Fallback auf direkten Web-Browser-Aufruf.
- **Test:** `tests/test_tradingview_url_and_fast_fallback.js` (PASS).

---

## 3. GitHub Release- & Verifikations-Evidenz (API-Belege)

### 3.1 Produkt Pull Request & Merge Commit
- **Pull Request:** [#8 (fix(dashboard): resolve Round 11 product quality issues PF-1 to PF-7 (v1.2.11))](https://github.com/trixr1907/AURA-Quant-Terminal/pull/8)
- **Merge-Methode:** Normaler Merge-Commit (`--merge`, kein Squash)
- **Merge Commit SHA:** `a0bb774a3d0d521db59347b5ad84fa55f6695b8f`
- **Merge-Parents (2 Parents nachgewiesen):**
  - Parent 1 (`main` vor PR #8): `1753c963dbe02cd2d5000af62069b4939cf988ec`
  - Parent 2 (`fix/round11-dashboard-product-quality` HEAD): `8259e610a9c87be144010899bde465a74c69db89`

### 3.2 Annotierter Release-Tag
- **Tag:** `v1.2.11`
- **Tag-Objekt SHA:** `4dda742a4fe835240f981f81000cc7023bf310bf`
- **Tag-Peel SHA (`v1.2.11^{commit}`):** `a0bb774a3d0d521db59347b5ad84fa55f6695b8f`
- **Tag-Message:** `AURA v1.2.11 — Confluence Terminal (read-only research)`

### 3.3 GitHub Actions Check-Run Conclusions auf Merge Commit `a0bb774a`
- `SonarCloud Code Analysis`: status=`completed`, conclusion=`neutral`
- `Socket Security: Project Report`: status=`completed`, conclusion=`success`
- `Test Suite & Quality Gates`: status=`completed`, conclusion=`success`
- `publish`: status=`completed`, conclusion=`success`

### 3.4 GitHub Release Asset (`symbiose.zip`)
Das Asset wurde nach dem Upload via GitHub API heruntergeladen und unabhängig gehasht:
- **Download-URL:** `https://github.com/trixr1907/AURA-Quant-Terminal/releases/download/v1.2.11/symbiose.zip`
- **Asset-Dateigröße:** `226.020 Bytes`
- **SHA-256 (nach Download verifiziert):**  
  `e727872314240ce508f2fa01aac799f5a3234192a2bbb153f5f8b7e0662d022b`
- **Dateianzahl im ZIP-Archiv:** `26`
- **VERSION im ZIP-Archiv:** `1.2.11`
- **Enthaltene Pflichtdateien:** `LICENSE` (vorhanden), `RELEASE_v1.2.11.md` (vorhanden), `README.md` (vorhanden), `VERSION` (vorhanden).

---

## 4. Finale Bestätigung der Prüfkriterien

| Prüfkriterium | Soll-Vorgabe | Ist-Wert / Nachweis | Status |
|---|---|---|---|
| `innerHTML` Vorkommen | Exakt 51 | `grep -c 'innerHTML' Symbiose_Dashboard.html` = **51** | PASS |
| Pytest Testsuite | Alle Tests grün | **216 passed, 57 subtests passed in 2.68s** | PASS |
| Node Testsuite | Alle Tests grün | **53 passed, 0 failed** | PASS |
| Release-Gate (`release_check.py`) | EXIT = 0 | Urteil: `SOFTWARE_GO / MODEL_NO_EVIDENCE` (Exit 0) | PASS |
| Git Merge Struktur | 2 Parents (kein Squash) | `1753c96...` + `8259e61...` -> `a0bb774...` | PASS |
| Tag Peel Parität | Zeigt auf Merge-Commit | `v1.2.11^{commit}` == `a0bb774...` | PASS |
| Release Asset SHA-256 | Post-Upload Hash | `e727872314240ce508f2fa01aac799f5a3234192a2bbb153f5f8b7e0662d022b` | PASS |
