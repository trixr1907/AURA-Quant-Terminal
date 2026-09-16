# ADR-0001: Sprache und Web-Stack

**Status:** Akzeptiert (2026-09-17) · **Kontext:** R40-Neuentwicklung, Basis v2.5.0

## Entscheidung

- **Sprache:** Python 3.12 für Engine, API, Worker, Migrationen.
- **Web-Framework:** FastAPI + Uvicorn (API v1, SSE). 
- **Frontend:** Server-geliefertes, schlankes HTML + Vanilla-ES-Module (kein SPA-Framework, kein Build-Step-Zwang). Design-Tokens aus `docs/brand_design.md`.
- **Node.js** bleibt nur im Test-/Tooling-Kontext (JS-Referenz-Engine, Paritäts-Golden-Generierung), nicht in der Produktionslaufzeit.

## Begründung

- Die Quant-Kernlogik braucht eine kanonische Implementierung; Python ist die Sprache des vorhandenen Orakels (`tests/reference_backtest.py`) und des Relays. NumPy-freie, deterministische Kernlogik bleibt mit Stdlib + Decimal möglich (Abhängigkeitsarmut = reproduzierbare Builds).
- FastAPI liefert serverseitige Validierung (Pydantic), OpenAPI-Doku und SSE/WebSocket-Support aus einem gepflegten Framework — ersetzt das handgerollte `http.server`-Relay (2786 Zeilen mit selbstgebautem Routing/Auth-Fehlern, vgl. S-01..S-03).
- Verzicht auf SPA-Framework: Single-User-Produkt, ruhige Oberfläche, WCAG-orientiert; Vanilla-Module sind ausreichend und halten das Frontend auditierbar (kein Bundle, in dem Secrets landen können).
- Alternativen verworfen: Weiterausbau von `http.server` (bewiesenermaßen fehleranfällig: S-01, S-02), Node/Express (zweite Produktionssprache wäre neuer Drift), React/Vue (Overhead ohne Bedarf).

## Konsequenzen

- `requirements.txt` wird zur versionierten Lock-Datei (konkrete Versionen, Hashes via `pip-compile` oder vergleichbar); Docker-Image pinnt Basis-Image per Digest.
- Pine Script bleibt externes Artefakt mit Paritätstests gegen `aura.core`.
