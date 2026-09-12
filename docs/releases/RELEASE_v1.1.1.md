# AURA v1.1.1 — Release-Dokumentation & Audit-Abschluss

**Release-Version:** `v1.1.1`  
**Datum:** 2026-09-10  
**Typ:** Post-Release-Fixes & Prozess-Patch-Release (kein Strategie-Update)  
**Status:** Verifiziert & Veröffentlicht  

---

## 1. Release-Zusammenfassung & Modell-Status

- **Modell-Status:** `MODEL_NO_EVIDENCE (real)` — Unverändert gegenüber v1.1.0.
  Auf den 5 realen Golden-Master-Fixtures (BTC, ETH, SOL, XRP, DOGE) liegt der DSR im Bereich 0.027–0.050 ($\ll 0.5$).
  Das Release v1.1.1 ist ein **Prozess- & Korrektheits-Release**. Es führt **keinerlei neue Strategie-, Indikator-, Order- oder Signalregeln** ein.
- **Release-Gates:** Das Release v1.1.1 lief vollständig ohne manuelle Bypass-Flags (kein `--allow-current-version`, kein `--force`, kein `|| true`).
  Das Release-Gatekeeper-Skript `scripts/release_check.py` liefert fail-closed `exit=0` bei `SOFTWARE_GO / MODEL_NO_EVIDENCE`.

---

## 2. Implementierte Fixes (B1–B3)

### B1: Fail-Closed CI-Release-Gate & Software-GO Packaging (Commit `baa23c1`)
- Wiederherstellung des strikten fail-closed Release-Gates: `exit_code_for_verdict` liefert Returncode 0 für `SOFTWARE_GO / MODEL_NO_EVIDENCE` und Returncode 2 für alle unvollständigen/fehlerhaften Zustände (`FAIL`, `NO-GO`, `CONDITIONAL`, `WARN`, `None`).
- Der CI-Workflow `.github/workflows/publish-release.yml` führt `python3 scripts/release_check.py && python3 scripts/build_package.py` ohne Flags aus.

### B2: Millisekunden-Zeitstempel-Normalisierung im Model Evidence Gate (Commit `9f48397`)
- Implementierung von `normalizeTimestamp` in `tests/model_evidence_real.js`.
- Deterministische Normalisierung von Unix-Sekunden ($< 10^{11}$) und Millisekunden auf einheitliche Millisekunden ($\text{ms} = s \times 1000$).
- Vollständige Konsistenz über alle 5 realen Golden-Master-Fixtures.

### B3: Architektur-Dokumentation & Provenienz-Update (Commit `e23b775`)
- Dokumentation der kanonischen Millisekunden-Zeitstempelkonvention in `docs/architecture.md`.
- Synchronisation der Provenienz-Deklarationen in `tests/fixtures/golden/provenance.json`.

---

## 3. Provenienz, Hashes & Artefakte

- **Release-Commit:** (Wird nach dem Version-Bump ermittelt und eingetragen)
- **Release-Tag:** `v1.1.1`
- **Release-URL:** `https://github.com/trixr1907/AURA-Quant-Terminal/releases/tag/v1.1.1`
- **Release-Status:** `Published` (Draft: `false`, Pre-Release: `false`)
- **Asset symbiose.zip SHA-256:** (Wird nach Workflow-Lauf ermittelt)
- **Asset .hermes/ Exclusion Check:** `unzip -l symbiose.zip | grep -c "\.hermes/"` = `0`
- **Dashboard SHA-256 (`Symbiose_Dashboard.html`):** `78e3b6ea294c35267572498227bfa9f2051d8186e75970141c4b007f60155462`
