# AURA v2.5.0 — Integrity- & Security-Audit-Report
**Audit-Runde:** 40  
**Ziel-Repository:** `/home/ivo/projects/AURA_v2` (Commit `de25830`, Version `v2.5.0`)  
**Datum:** 2026-09-17  
**Auditor:** DevSecOps & Integrity Auditor  
**Status:** READ-ONLY Forensic & Integrity Audit  

---

## 1. Executive Summary & Audit-Scope

Dieser Bericht umfasst die forensische Integritäts- und Sicherheitsanalyse des AURA Quant Terminals v2.5.0. Der Schwerpunkt lag auf:
- Vollständiger Auditierung des Relay-Servers (`bitget_relay.py`, 2786 Zeilen) bzgl. Endpunkten, Authentifizierung, Autorisierung, CORS, State-Store-Concurrency, Token-Bucket-Rate-Limiting und ntfy-Push-Sicherheit.
- Prüfung des Headless Autobot Runners (`headless_autobot.js`, 1207 Zeilen) bzgl. Zustandsverwaltung, Kerzenverarbeitung, Race-Conditions und Not-Halt-Mechanismus.
- Container- und CI/CD-Integrität (`Dockerfile`, `docker-compose.yml`, `.github/workflows`).
- Forensischer Secrets-Scan im Repository.
- XSS/SSRF/Path-Traversal/WebSocket-Sicherheitsanalyse.

---

## 2. Vollständige HTTP-Endpunkt-Übersicht (`bitget_relay.py`)

| Methode | Pfad | Zweck | Auth / Privilegiert | CORS-Scope |
| :--- | :--- | :--- | :--- | :--- |
| **GET** | `/` | Bereitstellung von `Symbiose_Dashboard.html` | Keine | `*` |
| **GET** | `/tutorial` | Bereitstellung von `SYMBIOSE_Tutorial.html` | Keine | `*` |
| **GET** | `/pine`, `/Symbiose_Signal_System_v1.pine` | Bereitstellung des TradingView Pine-Scripts | Keine | `*` |
| **GET** | `/data/bitget_usdt_futures_universe.json`, `/api/universe` | Bereitstellung des USDT-Futures Universe | Keine | `*` |
| **GET** | `/serving` | Status- & Versionsinformationen (JSON) | Keine | `*` |
| **GET** | `/status` | Server- und Markt-Statusseite (HTML) | Keine | `*` |
| **GET** | `/ready` | Health- & Readiness-Probe für Docker/K8s | Keine | `*` |
| **GET** | `/api/state` | Abruf des synchronisierten Shared-State | Host/Origin-Check (Privilegiert) | Origin-gebunden |
| **POST** | `/api/open-tradingview` | OS-Dispatch von Chart-URLs an TradingView Desktop | Host/Origin-Check (Privilegiert) | Origin-gebunden |
| **POST** | `/api/bot-config` | Persistierung der Server-Bot-Konfiguration | Host/Origin-Check (Privilegiert) | Origin-gebunden |
| **POST** | `/api/state` | Mutation-Batches, Single-Key-Writes, Signal-Claims | Host/Origin-Check (Privilegiert) | Origin-gebunden |
| **POST** | `/api/signals` | Relay-seitiger Push-Trigger für ntfy-Benachrichtigungen | **KEINE (Öffentlich erreichbar!)** | `*` |
| **POST** | `/api/public` | Caching & Rate-Limited Bitget REST-Proxy | **KEINE (Öffentlich erreichbar!)** | `*` |
| **OPTIONS** | `*` | CORS-Preflight-Handling | Je nach Pfad | Dynamisch / `*` |

---

## 3. Top-Befunde (Strukturierte Findings)

### Finding 1: Fehlende Authentifizierung für privilegierte API-Endpunkte
* **Was:** Endpunkte `/api/bot-config`, `/api/state` und `/api/open-tradingview` verfügen über keinerlei Token- oder API-Key-Authentifizierung (`X-AURA-Token` bzw. `check_relay_token` ist in `bitget_relay.py` nicht implementiert).
* **Wo:** `bitget_relay.py:2095` (`_authorize_privileged`)
* **Warum kritisch:** Jeder Client im selben Netzwerk oder bei exponiertem Port kann ohne Berechtigungsnachweis Konfigurationen überschreiben, Trades manipulieren oder TradingView-Prozesse spawnen.
* **Fix:** `check_relay_token()` mit konstant-zeitlichem HMAC/Token-Vergleich implementieren und bei gesetztem `AURA_RELAY_TOKEN` zwingend vorschreiben.
* **Schweregrad:** **CRITICAL**

---

### Finding 2: Vollständige Umgehung des Origin-Schutzes bei fehlendem Origin-Header
* **Was:** `_authorize_privileged()` behandelt Anfragen ohne `Origin`-Header als uneingeschränkt vertrauenswürdig (`if origin_value is None: return True`).
* **Wo:** `bitget_relay.py:2110` (`_authorize_privileged`)
* **Warum kritisch:** Standard-HTTP-Clients (cURL, Python, Postman), Skripte im lokalen Netz oder Server-Side-Request-Forgery (SSRF) Angriffe senden regulär keinen `Origin`-Header und umgehen den Host/Origin-Schutz vollständig.
* **Fix:** Für Server-zu-Server- oder Non-Browser-Kommunikation einen expliziten Authorization-Header (`X-AURA-Token`) erzwingen, wenn kein valider `Origin` vorliegt.
* **Schweregrad:** **HIGH**

---

### Finding 3: Fehlende serverseitige Validierung der Bot-Konfiguration
* **Was:** Der Endpunkt `POST /api/bot-config` speichert eingehende Payloads ohne Validierung von Schema, Typen oder Wertegrenzen (`validate_bot_config` fehlt).
* **Wo:** `bitget_relay.py:2326` (`do_POST` `/api/bot-config`) & `bitget_relay.py:1357` (`save_server_bot_config`)
* **Warum kritisch:** Ungültige oder bösartige Werte (z.B. negatives Risiko, überhöhter Hebel, ungültige Timeframes, Script-Payloads) können persistiert werden und den Runner destabilisieren oder zu katastrophalem Fehlverhalten im Risikomanagement führen.
* **Fix:** Schema- und Wertebereichs-Validierungsfunktion `validate_bot_config(payload)` implementieren, die fehlerhafte Payloads mit `400 ERR_INVALID_BOT_CONFIG` ablehnt.
* **Schweregrad:** **HIGH**

---

### Finding 4: Ungeschützter ntfy-Push-Endpunkt `/api/signals`
* **Was:** `POST /api/signals` ist nicht in `_PRIVILEGED_PATHS` enthalten und durchläuft keinerlei Autorisierungsprüfung.
* **Wo:** `bitget_relay.py:2404` (`do_POST` `/api/signals`)
* **Warum kritisch:** Beliebige Akteure können Spam- oder manipulierte Push-Benachrichtigungen über den konfigurierten ntfy-Kanal versenden, Fehlalarme erzeugen oder den Benachrichtigungskanal überlasten.
* **Fix:** `/api/signals` zu `_PRIVILEGED_PATHS` hinzufügen und Autorisierung via Origin oder Token erzwingen.
* **Schweregrad:** **HIGH**

---

### Finding 5: Not-Halt- und Pause-Funktion im Headless Runner deaktiviert ("Server-Only Live")
* **Was:** Im Runner `headless_autobot.js` wird die `paused`-Eigenschaft in `ServerBotState.loadFromServerState` und zu Beginn jedes `runScanCycle` fest auf `false` überschrieben (`state.paused = false; state.pausedBy = null`).
* **Wo:** `headless_autobot.js:418-420`, `headless_autobot.js:531-532`
* **Warum kritisch:** Ein Betreiber kann den Server-Bot im Notfall (z.B. bei Marktturbulenzen oder Systemfehlern) über das Dashboard nicht pausieren oder notstoppen; der Bot ignoriert den Steuerbefehl auf dem Server.
* **Fix:** Die Persistenz des `paused`-Status im Shared State respektieren und bei gesetztem Pause-Flag den Scan-Zyklus fail-safe anhalten.
* **Schweregrad:** **HIGH**

---

### Finding 6: Docker Healthcheck Semantik — Kein automatischer Neustart bei "Unhealthy"
* **Was:** In `docker-compose.yml` ist `restart: unless-stopped` konfiguriert. Wenn der `/ready`-Healthcheck fehlschlägt (z.B. weil Marktdaten länger als 90s ausbleiben), markiert Docker den Container als `unhealthy`, startet ihn jedoch **nicht** neu.
* **Wo:** `docker-compose.yml:9`, `docker-compose.yml:37`
* **Warum kritisch:** Bei Hängern oder Verbindungsabbrüchen verbleibt der Container dauerhaft im Status `unhealthy`, ohne dass die Restart-Policy greift (Docker Restart Policies reagieren nur auf Prozess-Exits, nicht auf Healthcheck-Status).
* **Fix:** Einsatz eines Autoheal-Containers (z.B. `willfarrell/autoheal`) oder Watchdog-gesteuerter Selbstbeendigung bei anhaltendem Unhealthy-Zustand.
* **Schweregrad:** **HIGH**

---

### Finding 7: Fehlende Erkennung von Kerzen-Lücken (Candle Gaps) im Runner
* **Was:** `fetchKlinesViaRelay` filtert bestätigte Kerzen und sortiert nach Zeitstempel, prüft jedoch nicht auf Lücken (`t_n - t_{n-1} > duration`).
* **Wo:** `headless_autobot.js:229-249`
* **Warum kritisch:** Nach API-Ausfällen oder Verbindungslücken werden historische Lücken übersprungen. Dies verfälscht zeitabhängige Indikatoren (EMA, ATR, Volatilitätsbänder) und führt zu falschen Handelssignalen.
* **Fix:** Gap-Detection implementieren, die bei fehlenden Kerzen einen Datenfehler meldet oder die Serie als unvollständig verwirft.
* **Schweregrad:** **MEDIUM**

---

### Finding 8: Fehlende Ledger-Verifikation beim Relay-Start
* **Was:** `bitget_relay.py` führt beim Start (`__main__`) zwar die State-Migration durch, verifiziert jedoch nicht die kryptografische Checksumme des Research-Ledgers (`ledger_checkpoint.json` via `scripts/verify_ledger.py`).
* **Wo:** `bitget_relay.py:2758-2765`
* **Warum kritisch:** Manipulationen oder Regressionen am statistischen Research-Ledger werden zur Laufzeit nicht blockiert, sondern erst bei manuellen Prüfungen oder in der CI bemerkt.
* **Fix:** Integritätsprüfung des Ledgers in die Initialisierungsphase von `bitget_relay.py` vor dem Binden des Servers einbinden.
* **Schweregrad:** **MEDIUM**

---

### Finding 9: Fehlende Pfad-Whitelists für Bitget REST-Proxy (`/api/public`)
* **Was:** `/api/public` leitet jede Anfrage weiter, die mit `/api/` beginnt, ohne eine Allowlist der erlaubten Bitget-Marktdaten-Endpunkte zu erzwingen.
* **Wo:** `bitget_relay.py:2419-2442`
* **Warum kritisch:** Potenzielle missbräuchliche Nutzung des Proxys für nicht-vorgesehene Endpunkte oder Upstream-Fehlleitungen.
* **Fix:** Strikte Allowlist von erlaubten Pfaden (z.B. `/api/v2/mix/market/candles`, `/api/v2/mix/market/ticker`) definieren.
* **Schweregrad:** **MEDIUM**

---

### Finding 10: Verwendung des mutablen `latest`-Image-Tags in Docker-Compose
* **Was:** In `docker-compose.yml` wird `image: aura-quant-terminal:latest` referenziert anstelle eines versionierten oder Digest-gepinnten Images.
* **Wo:** `docker-compose.yml:9`
* **Warum kritisch:** Bei Updates oder Wiederanläufen kann es zu unvorhergesehenen Versionswechseln oder Schema-Inkompatibilitäten mit persistierten Volumes kommen.
* **Fix:** Explizite Versionierung `aura-quant-terminal:2.5.0` oder SHA256-Digest verwenden.
* **Schweregrad:** **LOW**

---

## 4. Detaillierte Teilsystem-Audits

### 4.1 State-Store-Concurrency & Datenpersistenz
- **Optimistic Locking:** Implementiert über `expected_rev` vs. `_rev`. Konflikte führen zu HTTP `409 ERR_STATE_CONFLICT`.
- **Atomare Schreibvorgänge:** Dateisystem-Schreibvorgänge nutzen temporäre `.tmp`-Dateien mit anschließendem atomarem `os.replace` (`tmp_path.replace(STATE_FILE)`).
- **In-Memory Thread-Sicherheit:** Mutex-Locks (`STATE_LOCK`, `SIGNAL_STATE_LOCK`) schützen Lese-/Schreibzugriffe innerhalb des Python-Prozesses.
- **Crash-Recovery:** Defekte JSON-Dateien werden erkannt und führen zu `StatePersistenceError`.
- **Schwäche:** Single-Key-Writes (`_save_shared_state`) besitzen keine tiefe Schema-Validierung gegenüber Mutationen.

### 4.2 Secrets-Handling & Repo-Hygiene
- **ntfy-Secrets:** Maskierung (`mask_ntfy_url`) verhindert die Klartextanzeige im Status-Dashboard. Das Secret verbleibt im Environment.
- **Forensischer Scan:** Keine echten API-Schlüssel oder privaten Zertifikate im Git-Verlauf oder Working-Tree gefunden.

### 4.3 Frontend XSS & WebSocket-Sicherheit
- **XSS / DOM Sinks:** Die 67 `innerHTML`-Stellen in `Symbiose_Dashboard.html` verwenden überwiegend statische Formatierungen oder die Sanitizer-Funktion `esc()` für Coin-Namen und Attribute.
- **WebSocket:** Der Relay-Server bietet keinen WebSocket-Endpunkt an (kein CSWSH-Risiko). Das Frontend verbindet sich als Client direkt mit öffentlichen Bitget-/Binance-Endpunkten.

### 4.4 Zustandsmaschine & Not-Halt-Architektur
- Der Runner besitzt **keine formale Finite State Machine (FSM)** mit expliziten Guard-Bedingungen, sondern arbeitet als prozedurale Schleife (`runScanCycle`).
- Not-Halt-Signale aus der Benutzeroberfläche werden durch die "Server-Only Live"-Logik überschrieben.

---

## 5. Fazit & Handlungsempfehlungen
Das System weist eine solide Basis bezüglich atomarer Dateioperationen, strikter CI-Action-Pinning und Non-Root-Container-Ausführung auf. Zur Erreichung vollständiger Produktionshärte müssen vorrangig die Authentifizierung privilegierter Endpunkte (`X-AURA-Token`), die serverseitige Config-Validierung, die Reaktivierung des Not-Halts und die Absicherung des `/api/signals`-Endpunkts implementiert werden.
