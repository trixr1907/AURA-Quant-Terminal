# AURA — Release Checklist & Prozess-Guardrails

Dieses Dokument enthält die verbindlichen, fail-closed Regeln und die vollständige Release-Checkliste für AURA Quant Terminal. Jede Regel basiert auf konkreten Lektionen und Vorfällen der Entwicklungshistorie (v1.0.7 → v1.1.1).

---

## 1. Verbindliche Prozess-Regeln (Fail-Closed)

Jede künftige Session und jeder Release-Vorgang muss die folgenden 8 Regeln ausnahmslos einhalten:

- [ ] **1. Kein Gate-Bypass (Fail-Closed CI & Packaging):**
  - **Regel:** Der Workflow zur Freigabe bleibt strikt `python3 scripts/release_check.py && python3 scripts/build_package.py` — ohne jegliche Bypass-Flags (`|| true`, `--force`, `--allow-current-version`).
  - **Exit-Semantik:** Exit `0` = Software-GO (auch bei `MODEL_NO_EVIDENCE` zulässig für Software-Ships); Exit `2` = Software-FAIL (blockiert alles). Läuft ein Gate rot, wird der Release-Versuch sofort abgebrochen und der Befund behoben — NIEMALS umgangen.
  - **Historische Begründung:** In Commit `513fe68` wurde `|| true` in die CI-Pipeline eingefügt, wodurch fehlerhafte Suites unbemerkt durchgelaufen wären. In Commit `baa23c1` (v1.1.1) wurde das strikte Fail-Closed-Verhalten wiederhergestellt.

- [ ] **2. Berichts-Hashes exakt & maschinell belegt:**
  - **Regel:** Jede Commit-SHA, Git-Tag-, Dateipfad- oder Hash-Angabe in Release-Notes, Berichten und Dokumenten MUSS direkt via `git rev-parse HEAD`, `git tag -v` oder `sha256sum <datei>` verifiziert werden — niemals aus dem Gedächtnis oder Vorab-Schätzungen.
  - **Historische Begründung:** Diskrepanzen in frühen Berichten (z. B. referenzierter Commit `a71ea5f` vs. tatsächlicher HEAD `60bb193` oder Hash-Drift `8a05272a` vs. `0dea7c77`) zerstören die Nachvollziehbarkeit.

- [ ] **3. Keine Behauptung ohne Repo-Deckung:**
  - **Regel:** Der Status „verifiziert: JA" oder „abgeschlossen" darf NUR vergeben werden, wenn der entsprechende Code committet UND im Remote gepusht ist. Andernfalls gilt zwingend die Kennzeichnung „lokal implementiert, nicht committet / nicht gepusht".
  - **Historische Begründung:** Vorab-Reports deklarierten Schritte als abgeschlossen, bevor der Git-Tree synchronisiert war.

- [ ] **4. Zeitstempel-Konvention: Strikt Millisekunden:**
  - **Regel:** Alle Daten-Pipelines, CSV-Importer, Test-Harnesse und Indikator-Engines nutzen die kanonische Zeitstempel-Normalisierung (`normalizeTimestamp`: Werte $< 10^{10}$ werden als Unix-Sekunden erkannt und mit $1000$ multipliziert). Jeder neue Harness MUSS diese Konvention erzwingen.
  - **Historische Begründung:** In `tests/model_evidence_real.js` führte die Auswertung von 4h-Fixtures in Unix-Sekunden zu fehlerhafter Tages-Aggregation im VWAP, da `Math.floor(s / 86400000) === 0` ergab (behoben in Commit `9f48397`).

- [ ] **5. Ein Parser, ein Ergebnis (Single Source of Truth):**
  - **Regel:** Niemals isolierte, leicht abweichende Ad-hoc-CSV-Parser in Test-Skripten neu schreiben. Bestehende, gehärtete Hilfsfunktionen (`compare_pine_js_golden.js` bzw. `model_evidence_real.js`) müssen wiederverwendet oder importiert werden.
  - **Historische Begründung:** Divergierende Header-Trim- und Floater-Parse-Logik erzeugte scheinbare Paritätsfehler, die reine Harness-Artefakte waren.

- [ ] **6. Vollständige Pre-Push-Verifikation:**
  - **Regel:** Vor jedem Push zum Remote müssen ausgeführt werden:
    1. `python3 scripts/release_check.py` (alle 16 Gates grün, Exit 0)
    2. `git diff --check` (keine Whitespace- oder Konflikt-Reste)
    3. `git ls-files | grep -c "^\.hermes/"` == 0 (keine Agent-internen Verzeichnisse im Git-Index)
  - **Historische Begründung:** Verhindert versehentliche Commits von internen Session-Dateien und unvollständigen Arbeitsständen.

- [ ] **7. Maschinenlesbares, ungeschöntes Berichts-Format:**
  - **Regel:** Jeder Audit-Befund wird nach folgendem Schema dokumentiert:
    `[ID] [WAHR|FALSCH|NICHT BELEGBAR] [KRITISCH|HOCH|MITTEL|NIEDRIG|INFO] — Quelle Datei:Zeile — Beleg / Messung — Empfehlung`
    Keinerlei beschönigender Werbesprech oder Ausflüchte bei schwachen Metriken.
  - **Historische Begründung:** Verhindert subjektive Verwässerung von statistischen und architektonischen Schwachstellen.

- [ ] **8. Verbraucherschutz & Ehrlichkeit des Edges:**
  - **Regel:** Kein Text, UI-Element oder Tooltip darf Profitabilität oder Edge suggerieren, solange die reale Out-of-Sample-Messung `MODEL_NO_EVIDENCE` meldet. Synthetische Tests MÜSSEN explizit als solche ausgewiesen werden (`synthetic-gate: fixture integrity, not model evidence`). Autobot-Logs zeigen ehrlichen DSR-Status.
  - **Historische Begründung:** Trennung von Software-Funktionsfähigkeit und echter statistischer Evidenz ist das Kernprinzip von AURA.

---

## 2. Automatisierte Release-Gates (`release_check.py`)

Ein einziger Befehl führt alle automatisierten Qualitäts-Gates fail-closed aus:

```bash
python3 scripts/release_check.py
```

### Übersicht der 16 Release-Gates:

| Gate | Prüfpfad | Pass-Kriterium |
|---|---|---|
| 1. Engine Unit Suite | `node tests/test_engine_full.js` | 100% Pass, keine Fehler |
| 2. Radar Progressive | `node tests/test_radar_progressive.js` | Batch-Updates & Early-Skip bestanden |
| 3. Live Trade Tracker | `node tests/test_live_trade_tracker.js` | Tracker-Logik, Transitions, Invarianten |
| 4. SMC Sessions (UTC) | `node tests/test_smc_sessions.js` | Killzones, Shading, Tooltips |
| 5. Statistik / Metamorphik | Python-Orakel, Metamorphik, Sensitivität | Deterministisch; Verdict korrekt klassifiziert |
| 6. Public Relay | `python3 -m unittest tests/test_relay_full.py` | Serving, CORS, Fail-closed Proxy |
| 7. Release & Sync Suite | `python3 -m unittest tests/test_release_sync.py` | Versionen, Golden-Authentizität, Sync |
| 8. Launcher Lifecycle | `python3 -m unittest tests/test_launcher.py` | GUI-/CLI-Fallback & Lifecycle |
| 9. Research Cleanup | `python3 -m unittest tests/test_research_cleanup.py` | Keine Execution-Artefakte im Produktpfad |
| 10. JavaScript-Syntax | extrahierter `<script>`-Block via `node --check` | Exit 0 |
| 11. Pine-Script-Statik | `python3 tests/pine_static_check.py` | Syntax, Regeln, 5 GM-Pflichtplots |
| 12. Golden Authenticity | `verify_golden_authenticity` | Echte TradingView-Exporte mit Provenance (fail-closed) |
| 13. Golden Parität | `compare_pine_js_golden.js` auf 5 Fixtures | Pine ↔ JS Parität $\ge 99.9\%$ |
| 14. Browser E2E | `python3 tests/browser_research_harness.py` | TOD-Layout, Invarianten, Rendering |
| 15. Versionskonsistenz | Relay, README, Dashboard | Alle Versionen identisch |
| 16. Secret Scan | Source- und Dokumentationsbaum | Keine Credentials oder API-Keys |

---

## 3. Paketierung & Release-Build

Nach einem erfolgreichen `release_check.py` (Exit 0):

```bash
python3 scripts/build_package.py
```

- Der Builder verwendet eine strikte Datei-Allowlist (`manifest`).
- Erzeugt ein reproduzierbares Archiv `symbiose.zip`.
- Führt automatische Smoke-Tests in einem sauberen temporären Verzeichnis durch.
- Überprüft das Archiv auf Ausschluss von `.venv`, `.git`, `__pycache__` und `.hermes/`.
