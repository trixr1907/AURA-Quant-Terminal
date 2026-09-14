# Runde 33 — Pre-Implementation-Audit

Datum: 2026-09-15
Branch: `feat/v1.9.0-evidence-program`
Baseline: `238e6c2b648381618a0a6501f015be43b22768bf`
Version vor Änderung: `1.8.2`

## Scope und unveränderliche Grenzen

- Features: Daten-Fundament-Audit, Hypothesen-Präregistrierung, beobachtender Schatten-Collector, Lockbox-Registrierung, Evidenz-Protokoll.
- Keine Gate-, Schwellen-, Signal-, Setup- oder Parameteränderung.
- Keine echte Hypothese und kein echter Ledger-Eintrag in dieser Runde.
- Keine Lockbox-Nutzung; Registrierung nur nach expliziter interaktiver Owner-Bestätigung.
- Modellverdikt bleibt `MODEL_NO_EVIDENCE`.
- Releaseversion: `1.9.0` (MINOR).

## Bestehende Integrationspunkte

| Bereich | Ist-Zustand | Geplanter Anschluss |
|---|---|---|
| Historische Daten | Fünf Golden-CSV-Fixtures in `tests/fixtures/golden`; CSV-Parsing in `scripts/cvd_reference.py` | Audit unterstützt CSV-Verzeichnis und Bitget-Fetch, erzeugt Tabelle plus JSON |
| Ledger | Verkettete kanonische JSONL-Einträge, Checkpoint, atomarer Append in `scripts/append_ledger.py` | PreReg-Payload wird als strikt validierte, kanonisch serialisierte Zusatzstruktur in einem kompatiblen Ledger-Eintrag geführt; Tests arbeiten nur mit Temp-Fixtures |
| Lockbox | `scripts/lockbox_guard.py` prüft `cutoff_time`, `locked_span_days`, `status=LOCKED`, `mode=forward_holdout` | Interaktiver Registrar schreibt dieselben Felder atomar; Default-Aufruf bleibt No-op |
| Server-Scan | `runScanCycle()` in `headless_autobot.js`; Gate-Reihenfolge ist bereits fail-closed | Gemeinsamer Collector erhält Entscheidungen nach dem bestehenden Funnel, ohne Rückwirkung auf dessen Ergebnis |
| Paper-Kosten | Runner-Konfiguration: Maker/Taker jeweils `0.001`, Slippage `0.001` | Outcome-Funktion dokumentiert und nutzt dieselben Default-Annahmen |
| Readiness | `/ready` kombiniert Marktdatenstatus und Runner-Health | Zusätzlicher `shadow`-Block aus Collector-Statistikdatei |
| Digest | `daily_digest_transition()` aggregiert Paperzustand | Optionale Schatten-Zeile nur bei aktiviertem Collector |
| Release-Gate | Dynamische JS-Erkennung, volles pytest, Ledger/Lockbox/Version | Neue Skripte in Compile/Smoke; unveränderte fail-close Verdict-Semantik |

## Hauptrisiken und Gegenmaßnahmen

1. Ledger-Kompatibilität: Bestehende Kette darf bytegenau unverändert bleiben. Darum keine Schema-Migration vorhandener Records und kein echter Append. PreReg wird über neue Validierung und Temp-Ledger-Tests bewiesen.
2. Funnel-Einfluss: Telemetriefehler dürfen Handelspfad nicht blockieren oder Entscheidungen ändern. Collector-Aufrufe sind beobachtend und Fehler werden getrennt behandelt; Regressionstest vergleicht Collector an/aus.
3. Outcome-Kausalität: Nur nach 24 abgeschlossenen Bars des Setup-TF auswerten. Keine laufende Kerze und kein späteres Wissen vor Horizontende.
4. Intrabar-Ambiguität: Wenn SL und TP in derselben Kerze berührt werden, gilt konservativ SL zuerst.
5. Retention/Cap: JSONL wird unter Lock/atomarem Replace beschnitten; älteste Einträge zuerst.
6. Datenklassifikation: `synthetic` stammt nur aus expliziter Provenance/Spalte, nie aus Vermutung. Unbekannt zählt nicht als real.
7. Lockbox-Irreversibilität: Ohne `--register` keine Mutation; exakter Prompt und bestätigte Eingabe nötig; bestehende LOCKED-Registrierung wird nicht überschrieben.

## Verifikation

- Jede neue Verhaltensscheibe folgt RED → GREEN.
- Zieltests: Daten-Audit, Ledger-PreReg/Hypothesencheck, Shadow-Anatomie/Outcome/Retention/Funnel-Parität/Ready/Digest, Lockbox-Registrar.
- Danach: vollständiges `pytest`, alle dynamisch entdeckten JS-Tests, `verify_ledger.py`, `release_check.py`, Paket-Smoke.
- Vor Commit: unabhängiger read-only Diff-Review.
- Veröffentlichung nur mit PR, grüner CI, 2-Parent-Merge, kanonischem annotierten Tag und verifiziertem Release-Asset.
- Deploy- und Push-Aussagen nur mit echten IDs/Ausgaben; Topic bleibt außerhalb des Repos.
