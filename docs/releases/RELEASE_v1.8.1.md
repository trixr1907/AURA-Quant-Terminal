# AURA v1.8.1 — Watchdog-Pause-Awareness & Dashboard-Event-Hygiene

**Release-Typ:** PATCH (`1.8.1`, Fehlerbehebung & Event-Hygiene)  
**Datum:** 14. September 2026  
**Status:** Lokale Software-Verifikation; kein Live-/VM-/ntfy-Deploy-Beleg

---

## Zusammenfassung (Runde 31)

AURA v1.8.1 behebt Fehlalarme und Fehl-Restarts des v1.8.0-Watchdogs während regulärer Runner-Pausen (aktiver Browser-Bot), garantiert die P3-Heilungsquittung nach erfolgreichen Neustarts, entkoppelt die physische Selbstheilung vom 3600-s-Alert-Cooldown, stoppt die Ntfy-Test-Push-Flut durch idempotentes UI-Binding sowie 10-s-Rate-Limiting, eliminiert TradingView-Doppelöffnungen durch Event-Delegation mit `stopPropagation` und aktiviert das 5-s-Live-Preis- und PnL-Tracking für Autobot-Positionen.

---

## Behoben & Verbessert

### 1. Watchdog-Pause-Awareness (`bitget_relay.py`, `headless_autobot.js`)
- **Problem:** Bei geöffnetem Dashboard pausiert der Server-Runner regulär jede Minute („Browser bot is active — server bot paused this cycle"). Da Pausenzyklen den `cycleCount` nicht erhöhten, stieg `last_cycle_age_sec` über die Stall-Schwelle (248 s) und führte zu einem Falsch-Restart eines gesunden Runners.
- **Fix:**
  - `headless_autobot.js` aktualisiert bei jedem Pausenzyklus den Heartbeat (`lastHeartbeatAt`) und setzt `paused: true`, `pausedBy: 'browser'`.
  - `bitget_relay.py` bewertet bei `paused: true` das Alter des Heartbeats (`last_heartbeat_age_sec`). Solange der Heartbeat frisch ist, wird kein Stall erkannt.
  - Echtes Festfahren (fehlender Heartbeat) wird nach wie vor als Stall erkannt und geheilt.
  - `/ready` exponiert im `runner`-Block: `paused` (`true`/`false`), `paused_by` (`"browser"`/`null`) und `last_heartbeat_age_sec`.

### 2. P3-Heilungsquittung (`bitget_relay.py`)
- **Problem:** Nach einem Watchdog-Restart blieb die Bestätigungsmeldung P3 („Selbstheilung erfolgreich — Runner wieder aktiv") aus.
- **Fix:** `RunnerManager.watchdog()` und `runner_watchdog_cycle()` erfassen den ersten erfolgreichen Folgezyklus bzw. Folge-Heartbeat des Ersatzprozesses und senden die P3-Meldung zuverlässig.

### 3. Physische Selbstheilung vom Alert-Cooldown entkoppelt (`bitget_relay.py`)
- **Problem:** Bei mehreren Stalls blockierte der 3600-s-Alert-Cooldown für P4-Meldungen auch die physische Heilung.
- **Fix:** `RunnerManager.restart()` wird bei jedem festgestellten Stall ausgeführt und inkrementiert `runner_restart_count`. Lediglich die P4-Push-Benachrichtigung bleibt auf max. 1 Push pro 3600 s gedrosselt.

### 4. Ntfy-Bind-Akkumulation & Test-Push-Flut (`Symbiose_Dashboard.html`)
- **Problem:** `SyncEngine.applyRemote` rief bei jedem State-Sync `NtfySignals.bindUI()` auf, wodurch sich `addEventListener`-Handler auf den Test-Buttons und Toggles akkumulierten (bis zu 22 Pushes pro Klick).
- **Fix:** `NtfySignals.bindUI()` ist nun durch Guard-Flags (`dataset.ntfyBound`) strikt idempotent. Zusätzlich drosselt ein 10-s-Rate-Limit (`NtfySignals._lastTestPushAt`) Mehrfachklicks ab.

### 5. TradingView-Doppelöffnung & Trade-ID-Adressierung (`Symbiose_Dashboard.html`)
- **Problem:** Doppelöffnung von TradingView-Tabs durch redundante `onclick`-Handler in `Autobot.render()` plus Event-Delegation ohne `stopPropagation`. Zudem führten Index-Verschiebungen nach Trade-Schließungen zu Fehlgriffen.
- **Fix:** Redundantes `onclick` entfernt; zentrale Container-Delegation mit `e.stopPropagation()` öffnet exakt ein Fenster mit einheitlicher TF-URL. Umstellung auf eindeutige Trade-IDs (`data-tv-ab-id`, `data-copy-ab-id`, `data-close-ab-id`, `findAutobotTrade`).

### 6. Autobot-Trade-Live-Tracking (`Symbiose_Dashboard.html`)
- **Problem:** `refreshTradePrices()` aktualisierte nur manuelle Trades; Autobot-Karten wirkten bis zum 60-s-Voll-Scan eingefroren.
- **Fix:** `refreshTradePrices()` bindet nun offene Autobot-Positionen (`Autobot.trades`) in den 5-s-Ticker-Refresh ein und aktualisiert Mark-Preise, PnL und R-Multiples flüssig ohne DOM-Neubau.

---

## SemVer und Research-Status

- **PATCH-Begründung:** Reine Fehlerbehebungen in Watchdog, Event-Handling, Live-Tracking und UI-Hygiene ohne Änderung von APIs oder Breaking Changes.
- Keine Änderung an Scoring-Gewichten, Machine Learning, OOS-Logik oder DSR.
- Trials-Ledger bleibt `EXP-032`.
- Verdict bleibt `SOFTWARE_GO / MODEL_NO_EVIDENCE`.

---

## Testergebnisse & Gate-Belege

- **Python-Suite (Host):** `318 passed, 69 subtests passed` (Delta: +7 Tests in `tests/test_runner_self_healing.py`).
- **JavaScript-Suite:** `84/84` Testdateien bestanden (inkl. neuer Suite `tests/test_v181_dashboard_event_hygiene.js`).
- **UI-Invariante:** `Symbiose_Dashboard.html` enthält genau `63` `innerHTML`-Vorkommen (Delta: -3 durch Entfernung redundanter Inline-Handler).
- **Release-Gate:** `scripts/release_check.py` schließt mit Exit `0` ab (`SOFTWARE_GO`, `MODEL_NO_EVIDENCE`).

---

## Verifikationsgrenze

Die dokumentierten Aussagen beziehen sich auf lokale automatisierte Tests und statische Gates. Es wurden für diese Release-Notes keine Live-, VM-, Container- oder ntfy-Zustände behauptet; diese gelten unverändert als nicht live geprüft / reine Erwartungswerte.
