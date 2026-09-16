# AURA v3 — Sicherheitsarchitektur & Bedrohungsmodell (SECURITY.md)

**Status:** Kanonisch v3.0 · **Datum:** 2026-09-17 · **Geltung:** Verbindlich fuer alle Netzwerk-, API-, Persistenz- und Deployment-Komponenten

---

## 1. Zugriffsmodell & Netzwerk-Isolation

- **Keine oeffentliche Portfreigabe:** Der Server wird **niemals** direkt ueber den Internet-Router ins WAN exponiert.
- **Primaerer Zugriff:** Privates LAN oder VPN (WireGuard / Tailscale).
- **Zonenteilung in Docker Compose:**
  - `aura-api`: Exponiert ausschliesslich Port 8000 intern auf dem Host.
  - `aura-worker`: Reiner interner Worker; keine exponierten Netzwerk-Ports.
  - `aura-db`: SQLite WAL Dateisystem auf sicherem Docker-Volume `aura_data` (kein Datenbank-Netzwerkport).

---

## 2. Authentifizierung & Autorisierung (ADR-0004)

- **Token-basierter Zugriff:** Alle zustandsveraendernden Endpunkte verlangen den HTTP-Header `X-AURA-TOKEN` oder `Authorization: Bearer <token>`.
- **Constant-Time Verification:** Der Abgleich erfolgt ausnahmslos ueber `secrets.compare_digest`, um Timing-Angriffe vollstaendig auszuschliessen.
- **Rollen und Privilegien:**
  - **Read-Only / Monitoring:** `GET /api/v3/health`, `GET /api/v3/status`, `GET /api/v3/state`.
  - **Privilegiert (Auth Pflicht):** `POST /api/v3/config`, `POST /api/v3/halt`, `POST /api/v3/resume`, `POST /api/v3/trades/close`.
- **Negative Auth Response Codes:**
  - Fehlender Token $\implies$ `401 Unauthorized`
  - Falscher Token $\implies$ `403 Forbidden`

---

## 3. Eingabe-Validierung & Schema-Schutz

- Alle eingehenden JSON-Payloads werden ueber strikte Pydantic-Schemas validiert (`BotConfigUpdate`, `HaltRequest`, `CloseTradeRequest`).
- Numerische Wertebereiche sind hart begrenzt (z.B. Risiko pro Trade $\le 5\%$, Hebel $\le 50$, Schwellwerte $[5..95]$).
- Ungueltige Payloads fuehren sofort zu `422 Unprocessable Entity` und verwerfen die Mutation ohne Seiteneffekte.

---

## 4. Security Headers & Content Security Policy (CSP)

Alle Antworten der API und des Web-Frontends fuehren verbindlich folgende HTTP-Header:

```http
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' wss: ws: https://api.bitget.com https://ntfy.sh;
```

---

## 5. Secret Hygiene

- **Keine Secrets in Git:** Private Keys, ntfy Tokens, API-Secrets gehoeren ausschliesslich in `.env` (ausserhalb von Git).
- **Logging Sanitization:** `aura.runner.notifier` und Logging-Handler maskieren alle sensiblen Header und Tokens in Ausgaben.
- **Keine privaten Boerse-Schluessel:** Im aktuellen Paper-Trading-Betrieb werden keine privaten Bitget-API-Keys benoetigt oder akzeptiert.
