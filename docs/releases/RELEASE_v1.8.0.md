# AURA v1.8.0 — Runner-Selbstheilung & Timeout-Härtung

**Release-Typ:** MINOR (`1.8.0`, neue Betriebsfunktion)  
**Datum:** 14. September 2026  
**Status:** Lokale Software-Verifikation; kein Live-/VM-/ntfy-Deploy-Beleg

---

## Zusammenfassung (Runde 30)

AURA v1.8.0 ergänzt den 24/7-Server-Bot um eine Relay-gesteuerte Selbstheilung. Der Watchdog bewertet ausschließlich die Freshness abgeschlossener Runner-Zyklen, wahrt die bestehende Startup-Gnadenfrist und startet einen festgefahrenen Node-Runner kontrolliert über denselben Boot-Pfad neu.

## Neu

- **Runner-Selbstheilung:** Die Stall-Schwelle ist `max(3 * AURA_BOT_SCAN_SEC, 180.0)`; ein positiver, endlicher Wert in `AURA_RUNNER_STALE_SEC` überschreibt sie.
- **Kontrollierter Lifecycle:** `terminate()`, begrenztes Warten, `kill()` als begrenzter Fallback und Neustart ausschließlich über `_start_runner_if_enabled()`.
- **Zustandsübergänge:** P4 enthält `Selbstheilung ausgelöst`; P3 `Selbstheilung erfolgreich — Runner wieder aktiv` folgt erst nach einem höheren erfolgreichen `cycle_count` des Ersatzprozesses.
- **Sichtbarkeit:** `/ready.runner.runner_restart_count` ist immer vorhanden; der Tages-Digest nennt Selbstheilungen der letzten 24 Stunden.

## Behoben

- **Netzwerk-Timeouts:** Alle Python-`urlopen`-Aufrufe und Node-`http.request`/`https.request`-Aufrufe sind explizit auf 10 Sekunden begrenzt. Timeout-Requests werden zerstört und Promise-Abschlüsse gegen Mehrfachauslösung geschützt.
- **Digest-Quelle:** Paper-Equity stammt aus `aura-server-bot-state-v1.equity`; bei ungültigem Wert greift `AURA_BOT_EQUITY`, danach 10000. Browser-Equity bestimmt den Server-Digest nicht mehr.
- **Stall-Forensik:** Pro Stall-Ereignis wird vor dem Stop genau ein klar markierter `faulthandler`-Dump aller Relay-Threads nach stderr ausgegeben.
- **Scheduler-Robustheit:** Unerwartete Signal-Center-Ausnahmen beenden den Loop nicht.

## SemVer und Research-Status

- **MINOR-Begründung:** Selbstheilung, Recovery-Meldung und Restart-Telemetrie sind neue, rückwärtskompatible Betriebsfunktionen des Server-Runners.
- Keine Änderung an Scoring, Sizing, Signalen, OOS/DSR oder Universe-Selektion.
- Trials-Ledger bleibt `EXP-032`.
- Verdict bleibt `SOFTWARE_GO / MODEL_NO_EVIDENCE`.

## Testergebnisse & Gate-Belege

- **Python-Suite (Host):** Baseline `294 passed, 57 subtests passed`; v1.8.0 `310 passed, 69 subtests passed` (Delta: +16 Tests, +12 Subtests; nach Review-Fix `311 passed, 69 subtests passed`, Delta +17/+12).
- **Neue Testklassen (`tests/test_runner_self_healing.py`):**
  - `TestRunnerStaleThreshold`
  - `TestRunnerManagerLifecycle`
  - `TestRunnerFreshnessTransition`
  - `TestRunnerWatchdogNotifications`
  - `TestRelayNetworkTimeout`
  - `TestDigestServerEquity`
  - `TestDigestRestartCount`
  - `TestRunnerReadyVisibility`
  - `TestWatchdogStartupGraceIntegration`
- **JavaScript-Suite:** `83/83` Testdateien bestanden; fokussierter PF70-Runner (`tests/test_pf66_headless_runner.js`) `35 passed, 0 failed`.
- **UI-Invariante:** `Symbiose_Dashboard.html` unverändert genau `66` `innerHTML`-Vorkommen.
- **Release-Gate:** Host-Lauf von `scripts/release_check.py` schließt mit Exit `0` ab; Software-Verdict `SOFTWARE_GO`, Modellverdict unverändert `MODEL_NO_EVIDENCE`.

## Verifikationsgrenze

Die dokumentierten Aussagen beziehen sich auf lokale automatisierte Tests und statische Gates. Es wurden für diese Release-Notes keine Live-, VM-, Container- oder ntfy-Zustände behauptet; diese gelten unverändert als nicht live geprüft / reine Erwartungswerte.
