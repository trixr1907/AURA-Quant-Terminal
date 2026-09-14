# OpenHands Task-Brief — AURA Runde 33 / v1.9.0

## Ziel

Implementiere das Evidenz-Programm A–E vollständig und minimal. Bewahre Handelslogik, Gates, Setup-Parameter, echte Ledger-Kette und Lockbox-Nutzung unverändert.

## Harte Grenzen

- Kein Ändern von WF-OOS-, DSR-, Trial-, Score-, MTF-, Regime-, Liquiditäts- oder Risiko-Schwellen.
- Keine echte `Hypothesis-PreReg` in `docs/research/trials_ledger_chain.jsonl`; `ledger_checkpoint.json` bleibt unverändert.
- Keine Lockbox-Auswertung/Nutzung.
- Keine Topic-Namen oder Secrets im Repo.
- Keine destruktiven Git-Befehle (`checkout`, `restore`, `reset`, `clean`) und kein Commit/Push/Tag.
- Code-Kommentare Englisch, Nutzerdoku Deutsch.
- TDD strikt: pro vertikalem Slice zuerst fokussierter RED-Test, RED ausführen, minimale Implementierung, GREEN ausführen.

## Slice A — Daten-Fundament

1. RED-Tests für CSV-Audit mit Kerzen gesamt/geschlossen, Zeitraum, Lücken, Duplikaten, Null-/Outlier-Kerzen, real/synthetisch/unknown und WF-Tauglichkeit.
2. `scripts/data_foundation_audit.py` mit zwei Quellen:
   - lokale CSV-Dateien/Verzeichnisse;
   - öffentlicher Bitget-Fetch über explizite CLI-Optionen.
3. Tabelle nach stdout, JSON über `--json-out` oder JSON-Modus. Standard-Smoke muss offline auf Golden-Fixtures Exit 0 liefern.
4. Provenance nie raten: nur explizite CSV-Spalte/Metadaten als real oder synthetisch klassifizieren; unbekannt separat.

## Slice B — PreReg und Check

1. RED-Tests für `Hypothesis-PreReg` Pflichtfelder:
   `setup_id`, `symbol`, `tf`, `regime_context`, `hypothesis`, `params_sha256`, `acceptance={n_min,edge_min,dsr_min}`, genau ein Horizon-Typ (`bars` oder `until_date`), `status=PREREGISTERED`, `frozen_at` ISO.
2. Erweitere `scripts/append_ledger.py` mit explizitem PreReg-Modus/Flag. Fehlende/falsche Felder Exit ungleich 0. Bestehende Einträge und echte Kette bleiben kompatibel.
3. `scripts/hypothesis_check.py`: Ergebnis gegen PreReg prüfen. Hash und Acceptance müssen exakt passen. Ohne Match: `UNREGISTERED`, Exit ungleich 0; registrierter Match liefert Evidenz-Kandidatenstatus, aber hebt kein Modellverdikt.
4. Nur Temp-Fixtures in Tests.

## Slice C — Shadow Collector

1. Neue gemeinsame Node-Funktion/Modul, serverseitig Pflicht. Standardpfad `${AURA_STATE_DIR:-/var/lib/aura}/shadow_log.jsonl` bzw. `/var/lib/aura/shadow_log.jsonl` im Produktionsdefault.
2. Konfiguration:
   - `AURA_SHADOW=0` deaktiviert;
   - Retention default 180 Tage;
   - Cap default 20 MB.
3. Pro betrachteten Funnel-Kandidaten genau eine Entscheidung mit:
   `ts,symbol,tf,dir,score,regime,adx,atrPct,decision,reject_reason,signal_price,params_sha256`.
4. Ablehnungsgrund muss aus tatsächlichem bestehenden Funnelpfad stammen. Accepted erst nach allen existierenden Gates. Keine Gate-/Entscheidungsänderung.
5. Outcome nach 24 abgeschlossenen Setup-TF-Kerzen: `hit_sl`, `hit_tp1`, `hit_tp2`, `time_stop`, plus Netto-R. Nutze Default-Kosten analog Runner (`makerFee=0.001`, `takerFee=0.001`, `slippage=0.001`) und dokumentiere sie. Bei SL+TP derselben Kerze konservativ SL zuerst.
6. Isolierte deterministische Outcome-Funktion. Retention/Cap älteste Zeilen zuerst; atomarer Rewrite.
7. `runScanCycle()` akzeptiert injizierbaren Collector für Tests. Collector-Fehler fail-soft und ohne Funnel-Einfluss.
8. Health-Datei oder Shadow-Statistik so anbinden, dass `/ready` liefert:
   `shadow:{enabled,entries,pending_outcomes,evaluated}`.
9. Digest ergänzt nur bei enabled:
   `Schatten: X Setups beobachtet, Y bewertet, Ø-R der Akzeptierten vs. Verworfenen`.
10. Tests: Anatomie, deterministisches Outcome, Retention/Cap, identischer Funnel mit/ohne Collector, `/ready`, Digest.

## Slice D — Lockbox Registrar

1. RED-Tests für No-op Default, bestätigte Registrierung, Ablehnung, bestehendes LOCKED nicht überschreiben.
2. `scripts/lockbox_register.py --register --days N [--provenance PATH]`.
3. Exakter Prompt: `Lockbox-Spanne ab heute für N Tage sperren? Das kann nicht rückgängig gemacht werden.`
4. Nur explizites `ja`/`yes` bestätigt. Schreibe atomar UTC-Cutoff, positive Integer-Tage, `LOCKED`, `forward_holdout`.
5. Guard erkennt registrierte Temp-Provenance als LOCKED; fehlende Registrierung bleibt im Release-Kontext `UNUSED`, nicht benutzt.

## Slice E — Dokumente und Release

1. `docs/research/DATA_FOUNDATION.md`: echte Skriptausgabe der Standard-Fixtures, harte Zahlen und je Symbol/TF WF n≥N ja/nein. N exakt deklarieren.
2. `docs/research/EVIDENCE_PROTOCOL.md`: S1–S6; Hebung nur Lockbox-Pass UND registrierte Forward-Kriterien; 90-Tage-Rollfenster; `Evidence-Decay`; Nicht-Evidenz; verständliches heutiges `NO_EVIDENCE`; Lockbox erst nach registrierten WF-Hypothesen, single-shot und Ledger-Doku jeder Nutzung.
3. `VERSION=1.9.0`; alle aktuellen Nutzflächen konsistent aktualisieren. Historische Release-Dokumente nicht umschreiben.
4. CHANGELOG und neue `docs/releases/RELEASE_v1.9.0.md`; Package-Manifest anpassen.
5. Dashboard möglichst strukturell unberührt außer Versionssync; keine neue `innerHTML`-Senke.

## Stop-/Abnahmekriterien

- Fokussierte neue Tests grün.
- `python3 scripts/data_foundation_audit.py` offline Exit 0; Reportzahlen daraus übernommen.
- `python3 scripts/verify_ledger.py` grün und weiterhin `EXP-032`, Entry-Count 7, Total 10 (aktuellen Output prüfen, nicht annehmen).
- Vollständiges `python3 -m pytest -q` grün.
- Jede Datei `tests/test_*.js` mit Node grün.
- `python3 scripts/release_check.py` Exit 0, Verdict `SOFTWARE_GO / MODEL_NO_EVIDENCE`.
- `python3 scripts/build_package.py` grün.
- `git diff -- docs/research/trials_ledger_chain.jsonl ledger_checkpoint.json` leer.
- Berichte exakte Counts aus echtem Output, keine vorgegebenen Sollzahlen kopieren.
