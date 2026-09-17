# AURA R40 — Agent Progress (evidenzbasierte Neuentwicklung)

> Laufendes Arbeitsprotokoll über Sitzungen hinweg. Jede Phase: implementieren → gezielt testen → Integration prüfen → Befunde beheben → Regression prüfen → Evidenz sichern.

## Ausgangspunkt

- **Ausgangs-SHA:** `de25830de9884a4a6b9019d1ecf0bf2da6f147a9` (main, 2026-09-16, v2.5.0)
- **Arbeits-Branch:** `audit/r40-baseline` (spätere Feature-Branches je Phase)
- **Arbeits-Checkout:** `/home/ivo/projects/AURA_v2` (frischer Clone; Alt-Checkout mit Nutzer-WIP unverändert)
- **Baseline-Dokument:** `docs/research/BASELINE_R40_20260917.md` — pytest 508+69 grün, JS 98/98 grün, Gate `SOFTWARE_GO / MODEL_NO_EVIDENCE`, Ledger EXP-032 valide.

## Stakeholder-Entscheidungen (2026-09-17)

1. Ubuntu/Debian-VM auf Proxmox existiert, ausreichende Ressourcen.
2. Bestandsinstallation läuft; **State-Migration ist Pflicht**.
3. Zugriff: LAN + WireGuard/Tailscale, kein offener Port.
4. Backup-Ziel: keines vorhanden → Vorschlag erarbeiten.
5. ntfy bleibt Benachrichtigungskanal.
6. Annahme (konservativ, dokumentiert): Single-User.

## Phasenplan (Arbeitsstand)

| Phase | Inhalt | Status |
|---|---|---|
| 0 | Baseline einfrieren, Mandatsfragen | ✅ DONE (2026-09-17) |
| 1 | Subaudits (Quant / Integrity / Dataflow / UX), Befundliste, Funktionsinventar, Datenflusskarte | ✅ DONE (2026-09-17) → `docs/AUDIT.md` + `docs/research/audit_r40/` |
| 2 | Zielarchitektur + ADRs + Migrationsfolge + priorisierter Plan | ✅ DONE (2026-09-17) → `docs/ARCHITECTURE.md` + `docs/adr/ADR-0001..0005` |
| 3 | Vertikale Implementierung (serverseitiger Kern zuerst) | ⬜ |
| 4 | Formelregister + Golden-Fixtures + Parität | ⬜ |
| 5 | Web-UI (responsive) + Control Plane + Auth (Arbeitspaket 1) | ✅ DONE (2026-09-17) → `docs/V3_UI_INTEGRATION_ACCEPTANCE.md` (`UI_INTEGRATION: PASS`) |
| 6 | Docker/Compose-Härtung, Backup/Restore, Runbook | ⬜ |
| 7 | Evidenz: Acceptance-Matrix, Release-Evidence, Soak (oder NOT_RUN) | ⬜ |

## Entscheidungen (laufend)

- 2026-09-17: Arbeit erfolgt im frischen Clone `AURA_v2`; Alt-Checkout bleibt unangetastet (Nutzer-WIP `test_bot_config_security.py` → wird als Requirement übernommen: serverseitige Config-Validierung + Relay-Token).
- 2026-09-17: Subaudit-Kritikalitäten vom Lead verifiziert: Q-01 (Equity ohne PnL, `headless_autobot.js:644/981/1075`), Q-02 (kein TP-Exit, `:624-632`), Q-03 (Time-Stop als sl_close, `:642`) bestätigt; Q-04 (SL-Maske `:332`) bestätigt, aber HIGH→MEDIUM herabgestuft (aktuelle Auswirkung begrenzt, da `currentSl=entry<tp1`; bricht bei künftigem Trailing über TP1).
- 2026-09-17: Zielarchitektur festgelegt (ADRs): Python 3.12 + FastAPI, SQLite WAL, 2 Container (worker/app) aus einem Image, Session+CSRF+Bearer (Argon2id), SemVer-Images ohne `latest`. Bestands-State-Migration ist Pflichtbestandteil (M-0..M-4).
- 2026-09-17: Runner-Fixes Q-01..Q-04 werden NICHT im Alt-Code geflickt, sondern in `aura.runner` neu implementiert (Ledger-Klassifikation: Prozess-Fix, kein Modellexperiment — Ausführungskorrektheit, keine Signaländerung).

## Ausgeführte Kernbefehle (Phase 0)

```
git clone https://github.com/trixr1907/AURA-Quant-Terminal.git AURA_v2
git checkout -b audit/r40-baseline
python3 -m pytest -q                      # 508 passed, 69 subtests, exit 0
for f in tests/test_*.js; node $f         # 98/98 PASS
python3 scripts/release_check.py          # SOFTWARE_GO / MODEL_NO_EVIDENCE, exit 0 (Worktree /tmp/aura_gate)
python3 scripts/verify_ledger.py          # ok:true EXP-032, exit 0
python3 tests/reference_backtest.py       # ALL ASSERTIONS PASSED, exit 0
python3 tests/pine_static_check.py        # OK, exit 0
```

## Blocker / Offenes

- Lokales `docker compose`-Plugin fehlt → Compose-Smoke auf Ziel-VM (Deployment bleibt NOT_RUN bis dahin).
- Backup-Ziel: Vorschlag offen (in `docs/DEPLOYMENT_PROXMOX.md`, Phase P7).
- Alt-State der Produktiv-VM muss für M-0/M-1 gesichert werden (Zugriff auf VM nötig; bis dahin Entwicklung gegen synthetische Alt-State-Fixtures).

## Nächste Schritte

1. Accounting- und Restart-Failures red-first beheben; danach v3- und vollständige Python-Suite erneut ausführen.
2. Bestehende JS-Suiten dynamisch vollständig ausführen und Funktionsdrift inventarisieren.
3. Worker/Risk-Gates/Persistenz/API/UI als einen deterministischen Replay-Durchstich integrieren.
4. Browser-E2E, Container/Restore/Störungstests und anschließend Abnahmebericht durchführen.

## Verifikation 2026-09-17 — Abschluss Arbeitspaket 1 (UI- & Control-Plane-Integration)

- **Paketstatus:** `UI_INTEGRATION: PASS` (nachweisbar durch Playwright-E2E, Pytest- und JS-Regressionen).
- **Review-Befunde R1–R5 (Commit 373daa3) behoben & verifiziert:**
  - **R1 (Persistenter Halt & Konfig-Recovery):** `AuraWorkerService` stellt beim Start aus `config_revisions` und `runner_state`/`commands` den Not-Halt und die zuletzt wirksame Konfiguration wieder her (`tests/test_v3_review_r1_to_r5_regressions.py::TestR1PersistentHaltAndConfig`).
  - **R2 (Resume-Recovery & Health-Gating):** Resume schaltet das System in `RECOVERING`. Erst nach vollständiger und erfolgreicher Validierung der Marktdaten-Feeds aller konfigurierten Symbole erfolgt über `mark_healthy()` die Rückkehr nach `RUNNING` und die Freigabe neuer Einstiege (`TestR2ResumeRecoveryAndHealthGating`).
  - **R3 (Echte Transaktions-Atomizität):** `aura/store/db.py` verwendet `SafeConnection` mit echten `BEGIN`/`COMMIT`/`ROLLBACK`-Transaktionsgrenzen und Savepoints für `with conn:`. Abbruch mitten im Block hinterlässt keine Teilzustände (`TestR3DatabaseTransactionAtomicity`).
  - **R4 (Absturzsichere Bar-Verarbeitung):** Verwaiste `'processing'`-Claims aus vorangegangenen Abstürzen werden bei Neustart bereinigt; unfertige Kerzenverarbeitung geht nicht verloren und wird nach Recovery ausgeführt. Nach `_complete_closed_bar` wird Doppelverarbeitung dauerhaft verhindert (`TestR4CrashResilientBarProcessing`).
  - **R5 (Echter Worker-Prozess-Neustart):** Test mit echtem Subprozess (`python3 -m aura.runner.worker --db ...`), Heartbeat-Prüfung, `proc.terminate()`/`kill()` und Neustart auf derselben Datenbank ohne direkte SQL-Manipulation (`TestR5RealSubprocessWorkerRestart`).
- **Verbleibende Review-Befunde (dokumentiert offen):**
  - R6 (Dockerfile-Benutzerreihenfolge & Healthchecks im Compose-Stack für Deployment).
  - R7 (Closed-Bar-Prüflogik im Bitget-Adapter, 8h-Funding, TP3, DSR-Evidenz).
- **Test-Evidenz (Rohlogs unter `docs/evidence/v3_acceptance_20260917/`):**
  - `pytest tests/test_v3_review_r1_to_r5_regressions.py -v`: 7 passed (100% grün).
  - `pytest tests/test_v3_e2e_playwright.py -v`: 11 passed (100% grün, Desktop + Mobile).
  - `pytest tests/test_v3_*.py -ra`: 122 passed (100% grün).
  - `pytest -ra`: 630 passed (100% grün, 0 Fehler).
  - `node tests/test_*.js`: 98/98 passed (100% grün).


- `python3 -m pytest -ra` vor Fix: **593 passed, 2 failed, Exit 1**; Rohlog `docs/evidence/v3_acceptance_20260917/pytest_full.log`.
- Accounting/Restart red-first behoben; gezielte Suite **13/13 PASS** und vollständige Python-Suite danach **595/595 PASS, Exit 0** (`accounting_fix.log`, `pytest_full_after_accounting_fix.log`).
- Dynamische JS-Regression: **98/98 PASS, Exit 0**; Artefakte `docs/evidence/v3_acceptance_20260917/js_full.log` und `js_results.json`.
- Vertikale Integration nach Ergänzung von Closed-Bar-Persistenz, Same-Bar-Dedupe, fail-closed Liquiditätsgate und DB-Refresh der API: **7/7 PASS**; vollständige Python-Suite danach **600/600 PASS** (`vertical_integration.log`, `pytest_full_after_vertical_fix.log`).
- Der öffentliche Bitget-Test hat in dieser Runde real Daten empfangen und validiert; Nichterreichbarkeit wird nun als `NOT_RUN`/Skip statt als PASS ausgewiesen.
- Verbleibende Blocking-Befunde: Dashboard ist nicht an die mutierende v3-Control-Plane angebunden; Compose bleibt lokal NOT_RUN.
- Der zuvor nur prozesslokale Not-Halt wurde über die SQLite-Command-Tabelle an den separaten Worker gekoppelt; Cross-Process Halt+Resume ist mit getrennten DB-Verbindungen grün getestet.
- Unabhängige Read-only-Reviews bestätigten weitere Blocker: fehlendes Funding/TP3, falsches R-Multiple nach TP1, Backtest-Entry-Fee, fehlender Holdout-Gate, unsicherer Default-Token und unkoordinierter Restore; der ebenfalls gefundene Same-Bar-Dedupe-Fehler ist inzwischen red-first behoben.
- Daher derzeit ausdrücklich: **kein SOFTWARE GO, kein Deployment GO, MODEL_NO_EVIDENCE**.

## Verifikation 2026-09-17 — Folgeprüfung F1–F5 (nach Commit 473cbf4)

- **F1 (R4 — Atomare Bar-Verarbeitung & Replay-Resilienz):**
  - Bar-Verarbeitung (`_process_closed_bar`) inklusive Bar-Claim, Trades (`on_bar_update`), Signal-Scanning und Abschlussmarker (`completed`) in eine gemeinsame atomare Transaktion gefasst.
  - In-Memory-Snapshotting der Engine (`_snapshot_engine_state` / `_restore_engine_snapshot`): Bei Exceptions/Crashes vor Bar-Abschluss rollt SQLite die DB-Änderungen zurück und die In-Memory-Instanz wird synchron auf den Pre-Bar-Zustand restauriert.
  - Transaktionale Benachrichtigungs-Pufferung: Trade-Close-Alerts werden erst nach erfolgreichem COMMIT versendet; bei Abbruch werden sie verworfen.
  - Verhindert, dass dieselbe Kerze nach Wiederanlauf an einem fälschlich nachgezogenen Stop ausgestoppt wird. Der Trade bleibt nach Wiederanlauf im Status `open` (`partial_tp1`), der PnL wird exakt einmal verbucht.

- **F2 (R2 — Tatsächliche Datenfrische & Historie-Validierung):**
  - Echte Wall-Clock-Frischeprüfung (`_is_candle_feed_healthy`): Letzter geschlossener Bar darf maximal `max_stale_age_sec` (Default: 7200s / 2h) in der Vergangenheit liegen; Zukunfts-Zeitstempel (Clock-Skew > 60s) werden abgewiesen.
  - Mindesthistorie von 30 geschlossenen Kerzen wird zwingend gefordert; Unterschreitung setzt `all_feeds_valid = False`.
  - Globales All-Feed-Gate: Alle Feeds werden vor Trade-Entscheidungen validiert. Ist ein Feed fehlerhaft/veraltet und das System `RUNNING`, wechselt es unverzüglich in `DEGRADED`.

- **F3 (R2 — Selbstständige Warmup-Recovery):**
  - `RunnerStateMachine.mark_degraded()` erweitert, sodass auch der Übergang `WARMING_UP -> DEGRADED` bei fehlgeschlagenem Warmup zulässig ist.
  - Nach Rückkehr valider, aktueller Marktdaten erkennt die Worker-Schleife die Genesung (`all_feeds_valid == True`) und führt das System selbstständig von `DEGRADED` (oder `WARMING_UP`/`RECOVERING`) nach `RUNNING`.

- **F4 (R3 — Echte Transaktions-Atomizität für Migrationen):**
  - `SafeConnection.executescript()` überschrieben: Skripte werden über `sqlite3.complete_statement` in Einzelschritte zerlegt und innerhalb der bestehenden Transaktion ausgeführt, ohne implizite C-Level-`COMMIT`s der Python-Standardbibliothek auszulösen.
  - `threading.local` für Transaktionstiefe (`_tx_depth`), um nebenläufige Threads sauber zu isolieren.
  - `migrate()` führt jede Migrationsdatei und die zugehörige Registrierung in `schema_migrations` in einer echten atomaren Transaktion aus. Bricht ein Skript ab, rollt SQLite die Schemaänderungen vollständig zurück.

- **F5 (R5 — Echte Prozessneustart- und Heartbeat-Evidenz):**
  - Worker generiert eindeutige `instance_id` (`w_<pid>_<uuid>`) und schreibt sie in `runner_state.reason`.
  - Heartbeat-Zeitstempel (`updated_at_ms`) wird bei jedem Zyklus aktualisiert.
  - CLI unterstützt `--test-mode` und float-basierte `--interval` (z.B. 0.2s) für vollständig deterministische, offline-fähige Lifecycle-Tests ohne Bitget-Netzwerkabhängigkeit.
  - Test `test_real_worker_subprocess_lifecycle_and_restart` belegt: echter Subprozess 1 wird gekillt (`proc.terminate()`), Subprozess 2 startet auf gleicher DB, beweist neue `instance_id`, frischen Heartbeat (`updated_at_ms >= t_restart`), Beibehaltung von `HALTED`, Wiederherstellung der Konfiguration und Übergang nach `RUNNING` nach quittiertem `resume`-Befehl.

- **Test-Evidenz (Rohlogs unter `docs/evidence/v3_followup_f1_to_f5_20260917/`):**
  - `pytest tests/test_v3_review_r1_to_r5_regressions.py -v`: 10 passed (100% grün).
  - `pytest tests/test_v3_*.py -ra`: 125 passed (100% grün).
  - `pytest -ra`: 633 passed (100% grün, 0 Fehler).
  - `node tests/test_*.js`: 98 passed (100% grün).
  - `pytest /mnt/c/Users/Ivo/Downloads/aura_followup_probes.py`: 4 von 4 Defekt-Probes schlagen fehl (`open -> open`, `RECOVERING`, `RUNNING`, `0 rows`), Transaktions-Test `PASSED` (Befunde nachweisbar abgestellt).

## Verifikation 2026-09-17 — Folgeprüfung G1–G3 (nach Commit 44dfe8c)

- **G1: Sichere SQLite-Verbindungsnutzung bei parallelen API-Zugriffen:**
  - `get_db()` in `aura/api/routes.py` liefert pro HTTP-Request eine eigene Verbindung via Dependency-Generator (`yield connect(_db_path)` mit `finally: conn.close()`), anstelle einer global geteilten Verbindung.
  - `SafeConnection` in `aura/store/db.py` mit `threading.RLock()` gegen parallele Transaktionskollisionen auf Connection-Ebene gehärtet: Überlappende Transaktionsversuche auf derselben Verbindung werden geordnet serialisiert oder nach Timeout mit aussagekräftigem Fehler abgewiesen.
  - Echte parallele Requests und Rollback-Isolation verifiziert: 25 gleichzeitige mutierende API-Requests (`/halt`, `/resume`, `/config`) laufen kollisionsfrei ohne `cannot start a transaction within a transaction` durch. Rollbacks in parallelen Threads bleiben strikt isoliert.

- **G2: Strikte Verifikation der Entry- und Exit-Alerts (Commit-Sicherheit & Entkopplung):**
  - `_evaluate_and_enter` entkoppelt: Entry-Alerts (`TRADE_OPEN`) werden nicht mehr vorab direkt versendet, sondern transaktional in `pending_alerts` gepuffert.
  - Sämtliche Alerts (Entry und Exit) verlassen die Transaktion erst NACH erfolgreichem DB-Commit.
  - Bei Rollback / Exception während der Bar-Verarbeitung wird kein einziger Alert emittiert (0 Ghost-Alerts).
  - Der Alert-Versand nach dem Commit ist isoliert: Netzwerkfehler des Notifiers führen niemals zu einem Rollback bereits committeter Buchungen.

- **G3: Kausalitäts-Guard für Kerzenfeeds, Zeitgrenzen & Testfeed-Korrektur:**
  - `_is_candle_feed_healthy` in `aura/runner/worker.py` prüft Bar-Ende strikt gegen Wall-Clock: Als geschlossen markierte Kerzen, deren Intervall noch nicht vollendet ist (`bar_end_ms > now_ms + 5_000`), werden als ungesund abgewiesen (`is_valid = False`).
  - Zulässige Zeitabweichung explizit auf 5000ms Jitter/Clock-Skew begrenzt.
  - `DeterministicFreshFeed` im Worker korrigiert: Erzeugt nun die zuletzt vollendete Stunde (`(now_s - (now_s % 3600)) - 3600`) statt der noch laufenden Stunde.
  - Deterministische Tests und E2E-Playwright-Generatoren auf kausal geschlossene Zeitintervalle synchronisiert.

- **Test-Evidenz (Rohlogs unter `docs/evidence/v3_review_g1_to_g3_20260917/`):**
  - `pytest tests/test_v3_review_g1_to_g3_regressions.py -v`: 9 passed (100% grün).
  - `pytest tests/test_v3_review_r1_to_r5_regressions.py -v`: 10 passed (100% grün, F1–F5 intakt).
  - `pytest tests/test_v3_*.py -ra`: 134 passed (100% grün).
  - `pytest -ra`: 642 passed (100% grün, 0 Fehler).
  - `node tests/test_*.js`: 98 passed (100% grün).
  - `aura_review_44dfe8c_probes.py`: Bestätigt Abstellung der Defekte (Entry-Alerts nach Rollback = 0, unvollständige Kerzen als ungesund abgewiesen).

## Verifikation 2026-09-17 — Docker-Umgebung & Multi-Container Lifecycle (Audit db9f07a -> D1-D5 Härtung)

- **D1 — Geprüfter Lockstand im Dockerfile verankert:**
  - `Dockerfile` kopiert nun explizit `requirements.lock` und führt `pip install --no-cache-dir -r requirements.lock` aus.
  - Verifizierter Build mit `--no-cache` belegt, dass exakt die 28 gelockten Paketversionen (u. a. `fastapi==0.141.1`, `uvicorn==0.53.0`, `pydantic==2.13.5`) installiert werden.

- **D2 — Wiederherstellung aller Container-Schutzmaßnahmen und ntfy-Konfiguration:**
  - `docker-compose.yml` stellt alle Sicherheitsmaßnahmen für beide Services wieder her:
    `read_only: true`, `security_opt: [no-new-privileges:true]`, `cap_drop: [ALL]`, `tmpfs: [/tmp:rw,noexec,nosuid,size=64m]`, Ressourcenlimits (`cpus: '1.0'`, `memory: 512M`).
    Zusätzlich Weiterreichung von `AURA_NTFY_URL=${AURA_NTFY_URL:-}` an den Worker.
  - Verifikation im laufenden Container via `docker inspect` belegt aktive Schutzmaßnahmen.

- **D3 — Eindeutige Run-ID, sichere Testisolation und Sentinel-Schutz:**
  - `scripts/verify_docker_compose_lifecycle.py` generiert pro Testlauf eine dynamische Run-ID (`run_<ts>_<uuid>`), dedizierte Image-Tags (`aura-audit-test:<run_id>`), Container-, Volume- und Netzwerknamen sowie freie Ports via Port-Finder.
  - Kollisionsprüfung bricht sofort ab, falls Namenskollisionen im Docker-Namespace vorliegen.
  - Isolations-Negativtest: Fremde markierte Sentinel-Ressourcen (`aura_sentinel_vol_*`, `aura_sentinel_net_*`) werden vorab erstellt; nach dem Clean-Teardown via Compose wird verifiziert, dass diese fremden Sentinels unversehrt erhalten blieben.

- **D4 — Strikte Healthchecks bis zum verifizierten 'healthy'-Zustand:**
  - `starting` wird nicht mehr als PASS akzeptiert (NO-GO). Der Harness pollt `docker inspect --format '{{json .State.Health}}'` bis zum Status `healthy`.
  - Negativtest: Ein Container mit absichtlich defektem Healthcheck (`exit 1`) wird gestartet; der Harness weist ihn nachweislich mit Fehler ab (`unhealthy`).

- **D5 — Robuste Worker-Quittierung, Negativtest & Cookie-only Authentifizierung:**
  - Konfigurationsquittierung verifiziert: Status `applied`, Timestamp `applied_at_ms IS NOT NULL`, `active_config_rev == requested_rev` sowie Quittierung in der SQLite-Tabelle `commands`.
  - Negativtest: Bei gestopptem Worker (`docker compose stop aura-worker`) wird Revision 2 angefordert; der Harness belegt, dass `active_config_rev` unverändert bleibt und der Befehl in `commands` auf `pending` stehen bleibt. Nach Worker-Wiederanlauf wird die Quittierung nachgeholt.
  - Authentifizierungs-Trennung:
    1. Header-Token-Test (ohne Cookie): HTTP 200.
    2. Cookie-only Test: Nach Login via `/api/v3/auth/login` wird `/api/v3/state` strikt ohne `X-AURA-TOKEN` Header abgefragt (HTTP 200).
    3. Session-Invalidierung: Nach API-Container-Neustart liefert das alte In-Memory-Cookie wie erwartet HTTP 401; erst Neuanmeldung stellt den Zugriff wieder her.
  - Neustart-Nachweis: Echte Regex-Trennung der Instanz-IDs (`w_1_3c3aaa` -> `w_1_7afe49`) und frischer Heartbeat-Timestamp (`>= Restart-Startzeit`).

- **Abschlussstatus:**
  - `CONTAINER_ENGINE_LOCAL: PASS`
  - `CONTAINER_COMPOSE_LOCAL: PASS (D1-D5 vollständig verifiziert)`
  - Python-Tests: 642/642 passed in 52.14s (`pytest_full_642.log`)
  - JS-Tests: 98/98 Testdateien passed in 4.84s, 0 Fehler (`all_js_tests_98.log`)
  - 35 gezielte Review-Tests: 35 passed in 3.28s (G1-G3, R1-R5, runner, store)

- **Evidenz & Rohlogs (unter `docs/evidence/docker_compose_verification_20260917/`):**
  - `docker_compose_version.log`: `Docker Compose version v5.5.1`.
  - `docker_compose_lifecycle_verification.log`: Vollständiges Protokoll aller 10 Stufen inkl. D1-D5 Negativtests.
  - `requirements.lock`: Vollständig gelockte transitive Abhängigkeiten.
  - `all_js_tests_98.log`: Protokoll aller 98 JS-Testdateien mit Exit 0.
  - `pytest_full_642.log`: 642/642 Unit-/Integrations-/Regressionstests bestanden.
