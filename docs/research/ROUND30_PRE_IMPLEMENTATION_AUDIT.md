# Runde 30 — Pre-Implementation-Audit

Datum: 2026-09-14
Branch: `feat/v1.8.0-runner-self-healing`
Baseline-Commit: `d3e44de58d924cf4bb12d8608de68244f5cbbbb6`
Baseline-Version: `1.7.1`

## Auftrag und unveränderte Grenzen

Runde 30 ist ein MINOR-Release für Runner-Selbstheilung, Netzwerk-Timeouts, Stall-Forensik und korrekte Digest-Equity. Schattenmodus, neue Signal-Typen, Charts, zweite Webhooks und Order-Bridges bleiben außerhalb des Scopes. Topic-Namen dürfen nicht ins Repository.

## Baseline-Belege

### Git und Version

Befehl:

    git status --short && git branch --show-current && git rev-parse HEAD && git show HEAD:VERSION

Ausgabe vor Branch-Erstellung:

    main
    d3e44de58d924cf4bb12d8608de68244f5cbbbb6
    1.7.1

`git status --short` war leer. Danach wurde der Audit-Branch erstellt:

    git checkout -b feat/v1.8.0-runner-self-healing

Ausgabe:

    Switched to a new branch 'feat/v1.8.0-runner-self-healing'

### Python-Baseline

Befehl:

    python3 -m pytest -q

Ausgabe:

    294 passed, 57 subtests passed in 9.90s

### JavaScript-Baseline

Befehl:

    for f in tests/test_*.js; do node "$f"; done

Aggregierte Ausgabe des fail-closed Loops:

    JS_FILES_PASSED=83
    JS_FILES_FAILED=0

### DOM-Sink-Baseline

Befehl:

    grep -o innerHTML Symbiose_Dashboard.html | wc -l

Ausgabe:

    66

### Netzwerk-Call-Baseline

Befehl:

    grep -n "urlopen(" bitget_relay.py headless_autobot.js

Ausgabe:

    bitget_relay.py:475:            with urllib.request.urlopen(req, timeout=10):
    bitget_relay.py:944:        with urllib.request.urlopen(req, timeout=15) as resp:

Befund: Alle Python-`urlopen`-Aufrufe besitzen bereits einen expliziten Timeout, aber der Bitget-REST-Pfad weicht mit 15 s von der neuen Vorgabe 10 s ab. `headless_autobot.js` nutzt kein `urlopen`, sondern `http.request`/`https.request`; dort fehlt aktuell ein Request-Timeout vollständig.

## Codepfad-Befunde

1. Runner-Lifecycle: `bitget_relay.py:_start_runner_if_enabled()` startet Node als Child-Prozess. Der Relay-Main-Pfad speichert nur die lokale Variable `runner_proc`; der Signal-Center-Thread kann den Prozess derzeit weder kontrolliert beenden noch durch exakt denselben Startpfad ersetzen.
2. Falsches Lebenssignal: `runner_dead_transition()` wertet `running` aus. Der Produktionsbefund beweist, dass dieses Feld beim Stall `true` bleibt. Selbstheilung muss ausschließlich auf Zyklus-Freshness beziehungsweise fehlendem Zyklus-Timestamp beruhen, unter Beibehaltung der Startup-Grace.
3. Starre Schwelle: `runner_dead_transition()` verwendet 300 s. Ziel ist `max(3 * AURA_BOT_SCAN_SEC, 180)` beziehungsweise `AURA_RUNNER_STALE_SEC` als Override.
4. Forensik: `faulthandler` ist nicht importiert. Beim ersten Erkennen eines konkreten Stall-Ereignisses müssen alle Python-Thread-Stacks nach stderr/stdout in Docker-Logs geschrieben werden. Da der blockierende Runner ein Node-Child ist, zeigt der Dump zusätzlich den Python-Manager-/Log-/HTTP-Zustand; der Node-Netzwerk-Call wird durch explizite 10-s-Timeouts verhindert und durch Runner-Logs benannt.
5. Heilungszustand: Es gibt weder einen persistenten/in-memory `runner_restart_count` noch eine Recovery-Erkennung nach dem ersten höheren `cycle_count` des Ersatzprozesses.
6. Digest-Bug: `daily_digest_transition()` liest Equity aus `aura-autobot-state-v2`, obwohl der kanonische Server-Runner-State unter `aura-server-bot-state-v1` liegt. Fallback muss `AURA_BOT_EQUITY` sein.
7. Timeout-Überleben: `runScanCycle()` fängt Fehler auf Zyklusebene und setzt `_scanInProgress` in `finally` zurück. Ein 10-s-Timeout im Relay-HTTP-Client muss als Promise-Rejection ankommen, damit der Zyklus sauber endet und der nächste Timer-Lauf möglich bleibt.
8. `/ready`: Runner-Daten kommen aus `runner_health.json`; `runner_restart_count` muss durch den Relay-Manager ergänzt werden, weil ein neu gestarteter Node-Prozess seinen lokalen Zustand neu lädt.
9. Dokumentation: Kanonischer Pfad ist `docs/deployment/SERVER_BOT_GUIDE.md`, nicht Root `SERVER_BOT_GUIDE.md`.
10. Release-Sync: VERSION, Relay/Runner, Dashboard, Tutorial, README, Startskripte, Docker-Metadaten, Pine-Metadaten, Claims-Generator, Docs-Index, Paketmanifest und neue Release-Notes müssen nach bestehendem Release-Gate konsistent auf 1.8.0 gebracht werden.

## Zielarchitektur

    aura-signal-center
          |
          | zyklisch: _runner_health() + stale threshold
          v
    RunnerManager --lock--> aktueller Node-Popen
          |                    |
          | Stall einmalig     +--> terminate -> wait -> kill fallback
          | faulthandler dump
          +--> exakt _start_runner_if_enabled()
          +--> restart_count + Recovery-Marker
          |
          +--> P4 "Selbstheilung ausgelöst"

    Ersatz-Runner schreibt ersten erfolgreichen cycleCount > Startwert
          |
          +--> einmalige P3 "Selbstheilung erfolgreich — Runner wieder aktiv"

Persistenter Trading-State und Equity bleiben im Relay-State; ein Ersatzprozess lädt denselben State beim normalen Boot-Pfad.

## Test-Slices (TDD)

1. Schwellenfunktion: Default 60 s -> 180 s; Scan 120 s -> 360 s; gültiger Override gewinnt; ungültiger Override fällt sicher zurück.
2. Stall-Erkennung ignoriert `running=true`, löst genau einen Stack-Dump/Restart je Ereignis aus und erhöht `runner_restart_count`.
3. Kontrollierter Restart beendet den alten Prozess, nutzt `_start_runner_if_enabled()` erneut und lässt persistente Trading-Daten unangetastet.
4. Erst ein erfolgreich geschriebener neuer Zyklus löst genau eine P3-Recovery-Info aus.
5. Node-Relay-Request bricht nach 10 s ab; Fehler wird gefangen; `_scanInProgress` wird freigegeben und ein Folgeturn kann laufen.
6. Digest nimmt `aura-server-bot-state-v1.equity=10000`, selbst wenn Browser/Autobot-State 1000 enthält; ENV-Fallback wird separat getestet.
7. `/ready`-Runner enthält `runner_restart_count`.
8. Digest enthält `X Selbstheilungen in 24 h`; Zeitfenster wird mit Restart-Timestamps geprüft.
9. Bestehende 294/57-Python- und 83-JS-Testdateien bleiben grün; neue Testklassen erhöhen nur Python-Zahlen, sofern kein neues JS-Testfile nötig ist.

## Release- und Abnahmegrenzen

- Release-Gate muss `SOFTWARE_GO / MODEL_NO_EVIDENCE` und Exit 0 liefern.
- Ledger bleibt `EXP-032`, weil keine Modell-, Signal-, Schwellen- oder Universumsänderung erfolgt.
- `innerHTML` bleibt 66; jede Abweichung wäre Scope-Drift.
- PR muss über Merge-Commit mit zwei Eltern landen; kein Squash/Rebase.
- Tag: `v1.8.0`, annotiert mit exakt `AURA v1.8.0 — Confluence Terminal (read-only research)`.
- Live-Deploy, ntfy-ID, Server-Zeitstempel und VM-Status werden nur bei realem Zugriff als Beleg berichtet; sonst ausdrücklich als Erwartung markiert.
