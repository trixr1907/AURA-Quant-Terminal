# AURA v1.10.0 — QoL-Suite (Statusseite, Doctor, Trade-Export, Reload-Banner, Funnel-Glasbox & PreReg-Assistent)

**Release-Typ:** MINOR (`1.10.0`, Endbenutzer-QoL-Suite A–F)  
**Datum:** 2026-09-15  
**Research-Verdict:** `SOFTWARE_GO / MODEL_NO_EVIDENCE`  
**Trials-Ledger:** unverändert `EXP-032` (Entry-Count 7, Total 10)  

---

## Überblick

AURA v1.10.0 liefert sechs Endbenutzer-QoL-Features, **alle strikt lesend und diagnostisch**. Sie ändern nichts am Handelsverhalten, an den Signal- oder Risikogates, am Trials-Ledger, an der Lockbox oder am Evidenz-Protokoll. Ziel dieser Minor-Version ist maximale Transparenz des Bot-Verhaltens für den Nutzer, reibungslose Ein-Befehl-Diagnose im Server-Betrieb und ein geführter Workflow zur Präregistrierung quantitativer Hypothesen.

---

## Wichtigste Neuerungen

### Auftrag A — Menschen-Statusseite `GET /status`
- Neue, eigenständige HTML-Statusseite in `bitget_relay.py` (Content-Type `text/html; charset=utf-8`, vollständig self-contained mit Inline-CSS).
- Großer Ampel-Statusbanner: `ALLES OK` (grün) oder `HANDLUNGSBEDARF` (rot) mit klartextlichen Verstoßmeldungen bei Schwellenwertverletzungen (überalterter Runner, Bot nicht konfiguriert, Festplattenspeicher <= 500 MB, Relay-Fehlercodes).
- Systemkarten: Software-Version, Bot-Modus (`mode`/`bot_enabled`/`state`), Runner-Metriken (`cycle_count`, `last_cycle_age_sec`, Pause-Status), Schatten-Kollektor (`entries`, `pending_outcomes`, `evaluated`), letzter Tages-Digest, Push-Status mit strikter Topic-Maskierung (`https://ntfy.sh/aura-l…`), State-Verzeichnis & freier Speicher, Uptime sowie synchronisierte Serverzeit in UTC und Europe/Berlin.
- Fußzeile mit Diagnosebefehl-Hinweis auf `scripts/ops/aura_doctor.sh` und kanonischem Verdict-String.

### Auftrag B — Ein-Befehl-Diagnose `scripts/ops/aura_doctor.sh`
- Umfassendes Diagnosewerkzeug für die Docker-VM (Aufruf per SSH, `qm guest exec` oder Konsole).
- Strukturierte Prüfungen mit `PASS`, `WARN` und `FAIL` für:
  - Container-Laufzeitstatus und Image-Tag-Konsistenz mit `/serving`.
  - `/ready`-Endpoint-Zustand, Bot-Aktivierung und Runner-Zyklenfrische.
  - Container-ENV-Variablen (`AURA_BOT_MODE=server`, maskierte `AURA_NTFY_URL`), `--env-file`-Herkunft und Security-Härtungsflags (`ReadonlyRootfs`, `CapDrop`, `no-new-privileges`, `restart`).
  - Dateirechte und Lesbarkeit von `/var/lib/aura/aura_bot.env`, Schatten-Log-Wachstum und freier Plattenplatz.
  - 24-Stunden Docker Error-Log-Analyse (WARN ab >0, FAIL ab >50).
  - Systemd Deploy-Receiver-Status und Drop-in-Konfiguration.
- Option `--push` für verifizierte Live-Test-Pushes mit ntfy-ID-Rückgabe; Option `--json` für maschinelle Auswertung; Exit-Code 0 bei nominalem Zustand.

### Auftrag C — Trade-Export CSV/JSON
- Neue Buttons `⬇ CSV` und `⬇ JSON` im Trade-Verlauf von `Symbiose_Dashboard.html`.
- Client-seitiger Blob-Download (`aura_trades_YYYYMMDD.{csv|json}`) aller manuellen und Autobot-Positionen sowie der gesamten Historie ohne Server-Roundtrip.
- Standardisiertes 19-Spalten-Schema: `id, coin, dir, leverage, entry, signalPrice, markPrice, initialSl, currentSl, tp1, tp2, tp3, openedAt, closedAt, result_reason, r_result, pnl, equity_at_close, source`.
- CSV im UTF-8-Format mit BOM (`\uFEFF`) für reibungslosen Excel-Import in allen Regionen sowie RFC-4180-konformes Escaping.

### Auftrag D — Reload-Banner
- Dismissible Top-Banner im Dashboard bei Verfügbarkeit neuerer Software-Versionen auf dem Server (`/serving`).
- Regelmäßiges Polling alle 60 Sekunden und beim Initial-Load; kein Auto-Reload zur Vermeidung von Unterbrechungen aktiver Chart-Zeichnungen; fail-silent bei Netzwerkunterbrechungen.

### Auftrag E — Funnel-Glasbox („Warum handelt der Bot (nicht)?")
- Server-Runner erfasst und aggregiert Filterstufen über ein rollierendes 24h-Zeitfenster: `scanned, radar_passed, wf_evaluated, selected, reject_reasons`.
- Exponierung im `/ready`-Endpoint (`funnel24h`) und tägliche Zusammenfassungszeile im Tages-Digest-Push.
- Dashboard-Panel `🧭 Bot-Funnel (24 h)` visualisiert Kandidatendurchsatz und Top-Absagen mit dem bindenden Leitspruch: *„Gates arbeiten korrekt — kein Trade ist kein Fehler."*.

### Auftrag F — PreReg-Assistent `scripts/prereg_new.py`
- Interaktiver Wizard und CLI-Werkzeug zur Generierung valider `Hypothesis-PreReg`-Einträge.
- Deterministische Berechnung von `setup_id` und SHA-256-Parameter-Hashing.
- Schema-Validierung über `hypothesis_check.validate_prereg`.
- Two-Step-Preregistration-Design: Das Tool generiert ausschließlich die Entry-Datei; das tatsächliche Anhängen an den Ledger bleibt ein bewusster, manueller zweiter Schritt via `append_ledger.py --prereg`.

---

## Scope und Governance-Garantien

- **Evidenz-Schutzklausel:** Alle Features sind rein deskriptiv und leiten keine automatischen Handlungsempfehlungen aus Schatten- oder Funnel-Daten ab.
- **Ledger & Verdict:** Ledger-Kette unverändert auf `EXP-032`; Lockbox bleibt `UNUSED`; Verdict bleibt `SOFTWARE_GO / MODEL_NO_EVIDENCE`.
- **UI-Sicherheit:** Strikt 0 unsichere `innerHTML`-Zuweisungen im Dashboard (`grep -o innerHTML Symbiose_Dashboard.html | wc -l = 63`).
