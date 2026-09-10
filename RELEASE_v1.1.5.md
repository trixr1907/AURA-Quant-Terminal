# AURA v1.1.5 — Institutional Audit Patches & UX-Härtung

**Release-Version:** `v1.1.5`  
**Datum:** 2026-09-10  
**Typ:** Institutional Quant, Performance & Accessibility Patch Release  
**Status:** Verifiziert & Veröffentlicht  

---

## 1. Release-Zusammenfassung & Modell-Status

- **Modell-Status:** `MODEL_NO_EVIDENCE (real)` — Reale Golden-Master-Fixtures (BTC, ETH, SOL, XRP, DOGE) weisen DSR < 0.5 auf; die Software ist deterministisch abgesichert und blockiert unbewiesene Signale fail-closed.
- **Audit-Abschluss:** Vollständige Behebung aller Befunde aus dem Institutional Quant Trading Terminal Audit:
  1. **Signal-Integrität:** Hero Direction Badge strikt an fokussiertes Asset gebunden; BTC-Trend-Veto ('wait') fest verankert; Radar State-Key berücksichtigt Sortierung und Timeframe.
  2. **Risk-Management:** Autobot-Positionsgrößenberechnung vollständig mit dynamischem Fractional Kelly (`calcKelly`) harmonisiert. Bei fehlendem statistischem Edge verweigert der Autobot die Ausführung fail-closed (`MODEL_NO_EVIDENCE`).
  3. **Stabilität & Kausalität:** Look-Ahead-invariantes Warmup für junge Tokens ($N < 295$) fixiert (Metamorphic-Tests verifiziert).
  4. **Netzwerk & Performance:** WebSocket-Tick-Drosselung via `requestAnimationFrame`, Stale-Data-Guard (`⚠️ STALE`), Relay Token-Bucket auf 15 req/s (30 Burst) optimiert und Radar-Batchgröße auf 4 reduziert.
  5. **UI/UX & Accessibility:** RenderCache-State-Keys repariert, CSS-Ausblendung für Mobile-Controls entfernt (Flex-Wrap) und Schriften/Kontraste auf WCAG AA gehärtet.

---

## 2. Artefakte & Hashes

- **Release-Commit:** `6a3b24b`
- **Release-Tag:** `v1.1.5`
- **Asset `symbiose.zip` SHA-256:** `5d73a2b34fc80f26101c4878d1e4b81ebe754865a2e98822a36ba7f4dec1254c`
