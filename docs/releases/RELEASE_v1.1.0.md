# AURA v1.1.0 — Release-Dokumentation & Audit-Abschluss

**Release-Version:** `v1.1.0`  
**Datum:** 2026-09-10  
**Typ:** Mess- & Infrastruktur-Minor-Release (kein Strategie-Update)  
**Status:** Verifiziert & Veröffentlicht  

---

## 1. Release-Zusammenfassung & Modell-Status

- **Modell-Status:** `MODEL_NO_EVIDENCE (real)` — Unverändert gegenüber v1.0.8/v1.0.9.
  Auf den 5 realen Golden-Master-Fixtures (BTC, ETH, SOL, XRP, DOGE) liegt der DSR im Bereich 0.029–0.050 ($\ll 0.5$).
  Das Release v1.1.0 führt **keinerlei neue Strategie-, Indikator- oder Signalregeln** ein. Es dient ausschließlich der mathematischen Ehrlichkeit der DSR-Messung, der Netzwerk-Stabilität und der UI-Rendering-Performance.
- **Strict Universe Gate:** `strictUniverseGate` ist standardmäßig **deaktiviert** (Option B / Default).
  Der Autobot bewertet das lokale Setup mit dem 18er-Grid ($T=18$) und weist den universumsweiten DSR ($T_{\text{eff}} = 18 \times \text{Universum} \times 4 = 8.640$) transparent im UI aus. Der Schalter `strictUniverseGate` kann vom Anwender bei Bedarf aktiviert werden.

---

## 2. Implementierte Neuerungen (Phasen 1–3)

### Phase 1: Dual-DSR Hypothesen-Funnel & Trials-Ledger
- Dynamische Universums-Hypothesenberechnung: $\text{Scanned} = \text{universeSymbols().length} \times 4$.
- Keine Doppelzählung: $T_{\text{eff}} = 18 \times \text{wfEvaluated}$ (kein Survivor-Bias).
- Strikt getrennte Summary-Ausgabe: `MODEL_NO_EVIDENCE (real)` vs. `synthetic-gate: PAPER_CANDIDATE`.
- Unveränderliches `TRIALS_LEDGER.md` zur Verhinderung schleichenden p-Hackings.

### Phase 2: Relay-Stabilität & Reactive UI-Rendering
- `bitget_relay.py`: In-Memory-TTL-Cache (`/api/public` Klines 60 s, Ticker 5 s, Key = Method+Path+Params) entlastet Bitget-Endpunkte.
- `bitget_relay.py`: Token-Bucket Rate Limiter (10 req/s, Burst 20). Überschuss antwortet sofort mit Relay-`429` (`Retry-After: 1`), ohne Bitget zu belasten. `/api/state` bleibt unberührt.
- `Symbiose_Dashboard.html`: `RenderCache` mit Hash-State pro Panel (Hero, Status, Price, Signal, MTF, Context, Liq, Backtest, Radar, MarketPulse). `renderAll()` überspringt unveränderte DOM-Panels.

### Phase 3: Lockbox-Evaluationsmechanik & System-Dokumentation
- `scripts/lockbox_guard.py`: Fail-closed Quarantäne für Bars $\ge \text{2026-09-10T00:00:00Z}$. Status `UNUSED` bei 0 gesperrten Fixture-Bars.
- `docs/architecture.md`: Vollständige ASCII- & Mermaid-Datenpfadspezifikation für WebSocket, REST-Proxy, State-Sync und Rendering.

---

## 3. Provenienz, Hashes & Artefakte

- **Release-Commit:** `513fe686c5c0d5b29184e2e9b304b37cd33669a8`
- **Release-Tag:** `v1.1.0` (Peeled Commit: `513fe686c5c0d5b29184e2e9b304b37cd33669a8`)
- **Release-URL:** `https://github.com/trixr1907/AURA-Quant-Terminal/releases/tag/v1.1.0`
- **Release-Status:** `Published` (Draft: `false`, Pre-Release: `false`)
- **Asset symbiose.zip SHA-256:** `4695656e10d070e767eb70c986f02340ac8ec5ff473ea7a03164cbbdf8ffa893`
- **Asset .hermes/ Exclusion Check:** `unzip -l symbiose.zip | grep -c "\.hermes/"` = `0`
- **Dashboard SHA-256 (`Symbiose_Dashboard.html`):** `fa5f1075436a385acfb0563216eabaf61aee227f736d3fd4be548763e825a1d4`
