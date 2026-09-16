# ADR-0004: Authentifizierung und Autorisierung

**Status:** Akzeptiert (2026-09-17) · **Kontext:** Befunde S-01..S-03 (keine Auth, kein Config-Validation, offener Push-Endpunkt); Zugriffsmodell LAN+VPN, Single-User (dokumentierte Annahme)

## Entscheidung

- **Single-User-Konto.** Beim ersten Start ohne Benutzer: Einmal-Setup über die Weboberfläche (Passwort setzen). Kein Default-Passwort, kein Passwort in `.env.example`.
- Passwort-Hash: **Argon2id** (Fallback bcrypt, falls native Abhängigkeit im Alpine-Image scheitert — Entscheidung im Build dokumentieren).
- **Session-Cookie:** HttpOnly, SameSite=Strict, `Secure` sobald TLS aktiv (hinter Tailscale/WireGuard ist TLS optional — dokumentiert; Cookie dann ohne Secure-Flag nur über VPN/LAN, Risiko akzeptiert und in `docs/SECURITY.md` begründet).
- **CSRF:** Synchronizer-Token für alle mutierenden Endpunkte bei Cookie-Sessions.
- **Bearer-Token** (`AURA_API_TOKEN`, env, nicht im Repo) für nicht-browserfähige Clients; konstant-zeitlicher Vergleich; fail-closed wenn gesetzt.
- **Login-Rate-Limit** (z. B. 5 Versuche/5 min/IP) + exponenzielles Backoff; Audit-Log-Einträge für Login, Config-Änderung, Not-Halt.
- Autorisierung: ein Rolle-Modell mit zwei Stufen (`viewer` read-only, `operator` darf Config/Not-Halt) — vorbereitet, aktiviert mit Single-User = operator.

## Begründung

- Ein VPN ersetzt keine Autorisierung in der Anwendung (Mandat §11). Die v2.5-Origin/Host-Prüfung ist gegen Nicht-Browser-Clients wirkungslos (S-01).
- Single-User: Kein OAuth/OIDC-Overhead; Session+CSRF ist der kleinste korrekte Mechanismus für Cookie-Browser; Bearer deckt Skripte ab.
- Serverseitige Validierung aller Config-Payloads (Allowlist-Schema, endliche Zahlen, Wertebereiche) — übernimmt exakt die Fälle aus dem Nutzer-WIP-Test `test_bot_config_security.py`.

## Konsequenzen

- Negative Tests sind Pflicht: unauthentifiziert, falscher Token, CSRF ohne Token, Rate-Limit, ungültige Config-Werte (400, nichts persistiert).
- Secrets nur via `.env` (gitignored) oder Docker-Secrets; niemals in Logs/URLs/Frontend. ntfy-Topic-URL wird in API-Antworten maskiert.
