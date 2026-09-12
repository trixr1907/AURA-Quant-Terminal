# AURA v1.1.6 — Stabilisierung, Transparenz & Docker-Readiness

**Release-Version:** `v1.1.6`
**Datum:** 2026-09-10
**Typ:** Stability, Transparency & Production Hardening Patch Release
**Status:** Verifiziert & Bereit

---

## 1. Release-Zusammenfassung & Modell-Status

- **Modell-Status:** `MODEL_NO_EVIDENCE (real)` — Reale Golden-Master-Fixtures (BTC, ETH, SOL, XRP, DOGE) weisen DSR < 0.5 auf; die Software ist deterministisch abgesichert und blockiert unbewiesene Signale fail-closed.
- **Sprint 1 Stabilisierungs-Abschluss (Slice 1–5):**
  1. **Ehrliche Produktsemantik & Paper-CTA:** Konsistente Kennzeichnung als Paper Autobot / Paper-Simulation ohne Live-Orderausführung. Der Hero Paper-Trade Button ist fail-closed deaktiviert, wenn kein valides Live-Signal mit Kelly-Edge vorliegt.
  2. **Fail-Closed Liquidität:** Statische Fallback-Liquidität wird als unüberprüft (`liquidityVerified: false`) markiert; der Paper Autobot lehnt ungemessene Liquidität mit `LIQUIDITY` fail-closed ab.
  3. **Relay-Lastschutz & Singleflight:** Thread-safe Coalescing identischer Cache-Misses (Singleflight), begrenztes Upstream-429-Backoff mit `Retry-After`-Respektierung, Trennung von Relay-Busy und Bitget-Rate-Limits sowie dedizierter `/ready` Marktdaten-Readiness-Endpunkt neben `/serving`.
  4. **Radar-Transparenz:** Begrenzung gleichzeitiger Analysen via `RADAR_CONCURRENCY`, getrennte Fortschrittszähler für erfolgreiche, fehlerhafte und übersprungene Märkte sowie gemessene Restzeitschätzung.
  5. **Docker-Starter & LAN-Sicherheit:** Bounded Readiness-Polling in `docker_start.sh` und `DOCKER_START.bat` (`/serving`, `/ready`, `/api/public`, `/api/state`) vor Erfolgsmeldung und Browserstart; saubere Dokumentation der LAN-Host-Allowlist (`AURA_ALLOWED_HOSTS`).

---

## 2. Artefakte & Versionierung

- **Release-Version:** `v1.1.6`
- **Komponenten:** `bitget_relay.py`, `Symbiose_Dashboard.html`, `SYMBIOSE_Tutorial.html`, `Symbiose_Signal_System_v1.pine`, `Dockerfile`, `docker-compose.yml`, `docker_start.sh`, `DOCKER_START.bat`
