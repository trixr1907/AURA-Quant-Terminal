# ADR-0003: Scheduler und Prozessmodell

**Status:** Akzeptiert (2026-09-17)

## Entscheidung

- **Zwei Container aus einem Image:** `worker` (Marktdaten, Scanner, Paper-Runner, Signal-Center, ntfy) und `app` (API + UI). 
- Scheduling **in-prozess** via `asyncio`-Tasks mit festen Intervallen und dokumentierten Zeitouts — kein Celery, kein Redis, kein System-Cron für Kernfunktionen.
- Runner-Zyklus: konfigurierbar (Default 15 s, wie bisher), Scan-Zyklus separat (Default 60 s).
- Jeder Task hat Heartbeat + strukturierte Fehlerzählung; die Runner-FSM (STARTING/WARMING_UP/RUNNING/DEGRADED/HALTED/RECOVERING) ist der einzige Ort, der Trade-Entscheidungen trifft.

## Begründung

- Die bisherige Architektur (Browser-Timer + Relay-Threads + Node-Runner) erzeugte drei Scheduler mit unklarer Hoheit. Ein Worker mit in-prozess asyncio ist für die Last (≈120 Symbole, REST-Polling mit Rate-Limit) ausreichend und deterministisch testbar.
- Externe Queue/Broker wären zusätzliche SPOFs ohne Bedarf (Single-User, keine Horizontal-Skalierung).
- Container-Trennung Worker/App: API-Neustarts (Deploy, Config) unterbrechen weder Datensammlung noch Positionsverwaltung.

## Konsequenzen

- Graceful Shutdown: SIGTERM → Runner beendet laufenden Zyklus, persistiert FSM-Zustand, dann Exit (Timeout dokumentiert).
- Recovery: Beim Start liest der Runner den persistierten FSM-Zustand und offene Positionen, geht über RECOVERING in RUNNING; Crash-Schleifen werden über Health-Datei + Autoheal begrenzt (Details `docs/DEPLOYMENT_PROXMOX.md`).
- 24/7 bedeutet: Dienste laufen dauerhaft; die FSM darf Entries blockieren (DEGRADED/HALTED), während Verwaltung weiterläuft.
