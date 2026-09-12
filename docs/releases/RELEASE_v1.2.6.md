# AURA v1.2.6 — Robust Quant Audit & Verified Execution Architecture

## Überblick

AURA v1.2.6 schließt das umfassende Gesamtaudit (2026-09-12) erfolgreich ab. Alle identifizierten Mängel in Testabdeckung, Signal-Parität, Exit-Pfaden und Repo-Hygiene wurden behoben und durch behavior-basierte Tests sowie eine 100%ige Mutationsabdeckung (15/15 getötete Mutanten) abgesichert.

---

## Highlights in v1.2.6

### 1. 🛡️ Behavior-basierte Exit-Pfad & Kelly-Absicherung (F-17 bis F-20)
* **Analytisches Kelly-Oracle (`test_kelly_oracle.js`):** Strikte Verifikation von $f^*$, Half-Kelly, Hard-Cap und Stichproben-Ramp gegen theoretische Wahrscheinlichkeitsformeln statt String-Slicing.
* **In-Trade Monitoring & Time-Stop (`test_autobot_timestop_behavior.js`):** Echte Laufzeitprüfungen von `Autobot.updateActiveTrades()` über Timeframes (15m, 1h, 4h, 1d), Deadlines, Gewinn-/Verlustzustände und Fallbacks.
* **100% Mutations-Resistenz:** 15 von 15 absichtlichen Code-Mutationen (inkl. Zeit-Skalierung, invertierter Verlustbedingung und 12-Bar-Fallback) werden von den neuen Tests sofort rot gefangen.

### 2. 🔬 Pine v6 ↔ JS Signal-Parität & Epsilon-Härtung (F-16)
* **Klassenzerlegung der 20 Golden-Mismatches:** Vollständige Aufklärung der Scores in Float-Gleichheit bei Tageswechsel (Klasse 1), ADX-Schwellen-Diskretisierung an 18/25 (Klasse 2) und RMA-Restkonvergenz (Klasse 3).
* **Epsilon-Gleichheitsschutz:** Absicherung des VWAP-Vergleichs gegen IEEE-754 Unterläufe bei `close == hlc3`.

### 3. 🧹 Repo-Hygiene, Security & Code Cleanup (F-09, F-10, F-14)
* **XSS- und DOM-Sicherheit:** Überprüfung aller `innerHTML`-Zuweisungen und strikte Absicherung externer Strings via `esc()` und `textContent`.
* **Kanonische Dokumentationsstruktur:** Auflösung redundanter Root-Duplikate zugunsten der strukturierten `docs/`-Hierarchie (`docs/research/`, `docs/deployment/`, `docs/releases/`).
* **Toter Code entfernt:** Beseitigung ungenutzter Legacy-Klines-Funktionen (`binanceKlines`, `bybitKlines`, etc.) im Dashboard.

---

## Verifikationsstatus
- `pytest` Suite: **193 Tests bestanden, 57 Subtests bestanden**.
- Standalone JS Suites: **42/42 Testsuiten bestanden**.
- Mutations-Test (`audit_rev2_mutations.py`): **15/15 KILLED (0 überlebend)**.
- `scripts/release_check.py`: **SOFTWARE_GO / MODEL_NO_EVIDENCE** (Exit 0).
