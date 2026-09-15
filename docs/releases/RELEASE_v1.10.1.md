# AURA v1.10.1 — Hotfix: Packaging-Closure-Gate & Crash-Fast-Detector

**Release-Typ:** PATCH (`1.10.1`, Hotfix)  
**Datum:** 2026-09-15  
**Research-Verdict:** `SOFTWARE_GO / MODEL_NO_EVIDENCE`  
**Trials-Ledger:** unverändert `EXP-032` (Entry-Count 7, Total 10)  

---

## Überblick

AURA v1.10.1 behebt eine Ursache für einen Runner-Crash-Loop im Headless-Server-Modus und etabliert ein zwingendes, automatisiertes Release-Gate sowie einen schnellen Crash-Detector.

### Produktionsbefund & Ursache
Im Release v1.10.0 fehlte das Modul `shadow_collector.js` im Release-Paket-Manifest (`scripts/build_package.py`) und im `Dockerfile`-COPY-Block. Da `headless_autobot.js` dieses Modul via `require('./shadow_collector.js')` lädt, stürzte der Node-Runner im Container unmittelbar nach dem Start ab.

---

## Wichtigste Neuerungen & Fixes

### Auftrag 1 — Paket- und Container-Vollständigkeit
- `shadow_collector.js` wurde in `MANIFEST` von `scripts/build_package.py` aufgenommen.
- `COPY --chown=aura:aura shadow_collector.js .` wurde im `Dockerfile` ergänzt.

### Auftrag 2 — Das Gate: Runtime-Packaging-Closure (`scripts/release_check.py`)
- Neues fail-closed Release-Gate `runtime packaging closure (zip & dockerfile)`.
- Parst automatisiert alle relativen `require('./...')`- und `import`-Referenzen in allen Laufzeitdateien (`headless_autobot.js`, `shadow_collector.js`, `bitget_relay.py`, etc.).
- Verifiziert für jede referenzierte Datei:
  1. Vorhandensein auf dem Dateisystem.
  2. Einschluss im `symbiose.zip` Release-Manifest.
  3. Einschluss im `Dockerfile` COPY-Block (für Container-Laufzeitdateien).
- Ein einziges fehlendes Modul führt sofort zum Release-Check-Abbruch (Exit ≠ 0).

### Auftrag 3 — Crash-Fast-Detector (`bitget_relay.py`)
- Wenn der Headless-Runner-Kindprozess weniger als 10 s nach Start stirbt:
  - Sofortiger Neustart (ohne bis zu 180s Stall-Schwelle abzuwarten).
  - WARN-Log `RUNNER_CRASH_FAST` mit Exit-Code und Laufzeit.
  - Zähler `runner_crash_count` und Erkennung `crash_loop_detected: true` bei ≥3 schnellen Abstürzen in Folge.
  - Transparente Anzeige in `/ready` und Verstoß-Meldung auf der `/status`-Seite.

### Auftrag 4 — Klärung der Sekundärbeobachtung (`MARKET_DATA_STALE`)
- Wenn der Runner im Crash-Loop stirbt und kein Browser-Tab geöffnet ist, werden keine Marktdaten über das Relay abgefragt. Nach 180 s ohne Abfragen meldet `/ready` daher erwartungsgemäß `MARKET_DATA_STALE`. Sobald der Runner läuft und periodisch scannt, bleibt `MARKET_DATA_READY` dauerhaft aktiv.

---

## Verifikations-Zusammenfassung

- **Pytest:** Alle Tests bestanden.
- **JS Testsuite:** Alle 90+ Tests bestanden.
- **Dashboard innerHTML:** Exakt **63** (Kanon unverändert).
- **Ledger & Lockbox:** Ledger unverändert bei `EXP-032`, Lockbox `UNUSED`.
- **Verdict:** `SOFTWARE_GO / MODEL_NO_EVIDENCE`.
