# AURA v1.7.0 — Headless Paper-Autobot (Server-Modus)

**Release-Typ:** MINOR (`1.7.0`)  
**Datum:** September 2026  
**Status:** Canonical Release · Production Ready

---

## 🎯 Zusammenfassung (Runde 27)

AURA v1.7.0 bringt das Kernstück für 24/7 Signale im Homelab: Den **Headless Paper-Autobot (Server-Modus)**.  
Bisher lief die Autobot-Handelslogik ausschließlich im Browser-JavaScript — war der Browser geschlossen oder der PC aus, schlief auch der Bot.  

Mit v1.7.0 zieht die Handelslogik in den Docker-Container:
- Signale (Open, TP1–3, SL, Time-Stop) und BTC-Regime-Wechsel werden **rund um die Uhr ohne offenen Browser** emittiert.
- **Null Divergenz-Risiko:** Der Headless-Runner lädt die identische Engine und alle Autobot-Gate-Funktionen direkt aus `Symbiose_Dashboard.html` via VM-Extraktion (bewiesenes Muster aus den Node-Tests).
- **Doppel-Handel-Schutz:** Strenger Mode-Switch garantiert, dass immer genau ein Bot aktiv ist (Browser-Scan pausiert automatisch, wenn Server-Bot läuft).

---

## 📦 Umgesetzte Features & Fixes

### PF-66 — Headless-Runner im Container
- Eigenständiges Node.js-Programm `headless_autobot.js` im Container.
- Vollständiger Autobot-Zyklus: Universe laden, Radar-Scan mit serieller Pacing-Disziplin, `evaluateAutobotCandidate` → BTC-Gate → Fresh-Revalidierung → `runWalkForwardBacktest` → `evaluateAutobotEdge` → Sizing.
- Alle statistischen Schwellen und Gates identisch: Kein Trade ohne positive OOS-Evidenz.

### PF-67 — Server-State & Dashboard als Fernglas
- Server-State unter `/var/lib/aura` (Erweiterung des State-Sync-Speichers mit Monotonic Revision Counter).
- Modus-Schalter `AURA_BOT_MODE=server` (Opt-In) oder Panel-Steuerung.
- Dashboard zeigt Server-Bot-Trades mit Badge `🌐 SERVER-BOT` (PF-41-Karten).
- Dashboard-Panel schreibt Server-Konfiguration direkt in den Server-State.

### PF-68 — Signal-Emission & Zentrale Dedup
- Signal-Emission über den internen Relay-ntfy-Pfad `/api/signals`.
- Zentrale Cooldowns und Dedup via `_signal_claims` im Relay-State.
- Restart-persistent: Re-Push nach Container-Neustart ausgeschlossen.

### PF-69 — Robustheit & Ops
- Persistente Speicherung von Trades, Equity und Once-Flags über Container-Restarts hinweg.
- Runner-Health-Check in `/ready` (`runner.last_cycle_age_sec`).
- 429-Backoff und Fail-Close bei Datenfehlern.
- ENV-Matrix: `AURA_BOT_MODE`, `AURA_BOT_SCAN_SEC`, `AURA_BOT_EQUITY`.

### PF-70 — Tests & Verifikation
- 100% Funnel-Parität zwischen Browser-Engine und Headless-Runner (33 JS-Tests, 24 Python-Tests).
- Integrationstests für State-Synchronisation, Claim-Dedup, Runner-Health und Mode-Switch.

---

## 🧪 Test-Zahlen & Baseline
- **pytest:** 285 passed, 57 subtests passed (+32 Tests gegenüber v1.6.1 Baseline 253/57)
- **Node JS Suite:** 83/83 Testdateien bestanden (inklusive 33 Tests in `test_pf66_headless_runner.js`)
- **Regressions:** 0
- **Model Verdict / Trials-Ledger:** Intakt (EXP-032, SOFTWARE_GO / MODEL_NO_EVIDENCE real)
