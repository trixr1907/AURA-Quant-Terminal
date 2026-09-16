# AURA v2.5.0 — Datenfluss-, Zuständigkeits- und Funktionsinventar-Audit

**Audit-Datum:** 17. September 2026  
**Zielsystem:** `/home/ivo/projects/AURA_v2` (Commit `de25830`, v2.5.0)  
**Dokumenttyp:** Forensische Datenfluss- & Architektur-Analyse für Server-seitige Neuentwicklung (Modularer Monolith / PostgreSQL / Proxmox & Docker)  
**Auditor:** Data-Engineering- & Quant-Architektur-Audit (Runde 40)

---

## 1. Text-Datenflussdiagramm: Quelle → Normalisierung → Berechnung → Speicherung → Anzeige

```text
+----------------------------------------------------------------------------------------------------+
|                                     EXTERNE MARKTDATEN-QUELLEN                                     |
|  - Bitget Futures WebSocket (wss://ws.bitget.com/v2/ws/public)                                     |
|  - Bitget REST API v2 (https://api.bitget.com/api/v2/mix/market/...)                               |
|  - Binance Futures REST/WS (fapi.binance.com - Funding, OI, Premium, Fallback WS)                  |
|  - Alternative.me REST (api.alternative.me/fng - Fear & Greed)                                     |
|  - Coinlore REST (api.coinlore.net - Global Cap & Rank)                                            |
+----------------------------------------------------------------------------------------------------+
                                |                                              |
        (Browser Direct)        |                                              | (Server-Side Uplink)
  [WebSocket: Live Ticks]       |                                              |
  [REST: Crypto-Features, F&G]  |                                              |
                                v                                              v
+--------------------------------------------------+  +-----------------------------------------------+
|             BROWSER CLIENT (VIEWER)              |  |         PYTHON RELAY (bitget_relay.py)        |
|            (Symbiose_Dashboard.html)             |  | - Token Bucket (10 req/s, Burst 20)           |
|                                                  |  | - In-Memory TTL-Cache & SingleFlight          |
| 1. QUELLEN-EMPFANG:                              |  | - Upstream 429 Retry-Backoff                  |
|    - WS: candle1H / ticker (direct to Bitget)    |  +-----------------------------------------------+
|    - REST: /api/public via Relay bgGet()         |                          |
|    - REST: Binance/Coinlore/F&G via jfetch()     |                          | REST Proxy (/api/public)
|                                                  |                          v
| 2. NORMALISIERUNG:                               |  +-----------------------------------------------+
|    - normalizeTimestamp(ts) -> ms                |  |        HEADLESS RUNNER (Docker/Server)        |
|    - Geschlossene Kerzen: ts + dur <= now        |  |             (headless_autobot.js)             |
|    - CVD Range Approximation (tbv: null)         |  |                                               |
|                                                  |  | 1. QUELLEN-EMPFANG & NORMALISIERUNG:          |
| 3. BERECHNUNG (In-Browser Research):             |  |    - REST Polling via Relay /api/public       |
|    - analyze() -> Confluence Score (0-100)       |  |    - Filter: confirm === '1' (geschlossen)   |
|    - regimeOf() / squeezeAt() -> BTC & Alt Reg   |  |    - Normalisierung: sort by ts asc           |
|    - Purged Walk-Forward Backtest & DSR          |  |                                               |
|    - Action Radar Universe Scan                  |  | 2. BERECHNUNG (Engine via VM-Sandbox):        |
|                                                  |  |    - loadEngine() aus Dashboard-HTML          |
| 4. SPEICHERUNG / CONTROL-PLANE:                  |  |    - analyze(), MTF-Filter, BTC-Regime-Gate   |
|    - Config Save -> POST /api/bot-config         |  |    - Walk-Forward DSR & Kelly-Sizing          |
|    - SyncEngine -> /api/state (Revision-Queue)   |  |    - Time-Stop Optimierung                    |
|    - localStorage (Viewer Cache & UI State)      |  |                                               |
|                                                  |  | 3. PAPER-TRADE EXECUTION & IN-TRADE:          |
| 5. ANZEIGE (Reactive DOM Rendering):             |  |    - Eröffnung 1 Trade/Zyklus bei Gate-Pass   |
|    - RenderCache.isDirty() State-Hash Prüfung    |  |    - In-Trade TP1-3, SL, Auto-BE, Time-Stop   |
|    - Live Candlestick Canvas & Status Badges     |  |    - Shadow Collector Record (accepted/rej)   |
+--------------------------------------------------+  +-----------------------------------------------+
                         ^                                                     |
                         | (State Sync: GET /api/state)                        | (Mutations: POST /api/state)
                         +-----------------------------------------------------+
                                                   |
                                                   v
+----------------------------------------------------------------------------------------------------+
|                                    PERSISTENZ-EBENE (DATEIBASIERT)                                 |
|  - data/aura_shared_state.json        (Schema v2: Active Trades, History, Bot-Config, Claims, Rev) |
|  - data/aura_signal_center_state.json  (Schema v2: BTC-Regime-Alerts, Cooldowns, Daily-Digest)      |
|  - data/runner_health.json            (Runner Heartbeat, Cycle-Count, 24h-Funnel)                  |
|  - data/shadow_log.jsonl              (Append-Only JSONL aller Entscheidungen & Rejects)           |
|  - data/shadow_stats.json             (Aggregierte Schatten-Statistiken)                           |
|  - docs/research/trials_ledger_chain.jsonl & ledger_checkpoint.json (Immutabler Research-Ledger)   |
+----------------------------------------------------------------------------------------------------+
                                                   |
                                                   v
+----------------------------------------------------------------------------------------------------+
|                                     NOTIFIKATIONEN & MONITORING                                    |
|  - bitget_relay.py: _ntfy_notify() -> ntfy.sh Topic                                                |
|  - Events: Trade-Open, TP1-3, SL-Close, Auto-BE, Time-Stop, BTC-Regime-Wechsel, Daily Digest       |
|  - Dedup: Atomare Claims via _signal_claims in aura_shared_state.json                               |
+----------------------------------------------------------------------------------------------------+
```

---

## 2. Detaillierte Code-Befunde (Punkte 1 bis 8)

### (1) Wer bezieht tatsächlich Marktdaten? — Pfad-Verifikation P1–P6 aus `docs/architecture.md`

| Pfad | Dokumentierte Beschreibung | Tatsächliche Code-Implementierung & Datenfluss | Verifikation / Abweichung |
| :--- | :--- | :--- | :--- |
| **P1** | **Direct WebSocket** (Bitget/Binance &rarr; Client, `<50ms`) | `Symbiose_Dashboard.html:6240-6355` (`connectWS()`): Öffnet direkte Browser-WebSocket-Verbindung zu `wss://ws.bitget.com/v2/ws/public`. Subscribiert `candle1H`/`candle15m` und `ticker` für das ausgewählte Symbol. Fallback-URLs: `stream.binance.com:9443` und `data-stream.binance.vision`. Enthält 25s Keepalive-Ping (`Symbiose_Dashboard.html:6348-6354`). **Wichtig:** Der Server-Runner (`headless_autobot.js`) und das Relay (`bitget_relay.py`) nutzen **kein** WebSocket! | **Verifiziert.** Läuft rein im Browser. |
| **P2** | **REST via Relay (Public)** (Client &rarr; Relay &rarr; Bitget, Ticker 5s, Klines 60s, Other 10s TTL) | Client ruft `bgGet()` (`Symbiose_Dashboard.html:2357-2360`) auf, das bei aktiver Relay-Origin `relayCall('/api/public', ...)` nutzt. Der Headless Runner (`headless_autobot.js:233, 252`) ruft ebenfalls `POST /api/public` auf. Das Relay (`bitget_relay.py:2419-2441`) leitet an `_public_request_cached()` weiter. Caching via `PUBLIC_CACHE` (`bitget_relay.py:1270-1300`): Klines 60s, Ticker 5s, Funding/OI/Contracts 10s. | **Verifiziert.** Relay schützt Bitget-IP vor Überlastung. |
| **P3** | **Token-Bucket Uplink** (Relay &rarr; Bitget REST, 10 req/s, Burst 20) | `bitget_relay.py:1242-1267` (`TokenBucketRateLimiter`) & `bitget_relay.py:2035, 2059`. Bei Token-Mangel liefert Relay HTTP 429 (`code: RELAY_BUSY`) mit `Retry-After: 1`. Upstream 429 von Bitget wird in `_upstream_request_with_backoff()` (`bitget_relay.py:2013-2028`) mit exponentiellem Backoff bis 3-mal wiederholt. | **Verifiziert.** Verhindert IP-Bans durch Exchange. |
| **P4** | **Server-Only State & Config** (Dashboard &harr; Relay &harr; Runner, `/api/state`, `/api/bot-config`) | Dashboard schreibt Config via `POST /api/bot-config` (`Symbiose_Dashboard.html:10108`), Relay speichert in `aura_shared_state.json` unter `aura-server-bot-config-v1` (`bitget_relay.py:1357, 2326`). Runner liest Config bei jedem Scan-Zyklus (`headless_autobot.js:457-478`) und schreibt Trades/History atomar mit `source: "server"` via `POST /api/state` (`headless_autobot.js:1028-1043`). | **Verifiziert.** Vollständig Server-geführt. |
| **P5** | **Fallback-Kette** (Bitget REST &rarr; Binance &rarr; CoinGecko/Coinlore &rarr; Static Universe) | In `Symbiose_Dashboard.html:5087-5126`: Wenn Bitget REST fehlschlägt, lädt Dashboard `data/bitget_usdt_futures_universe.json` (Fallback 1) oder `STATIC_TOP_UNIVERSE` (Fallback 2, 36 Assets, Zeile 5085). Für Krypto-Features (`Symbiose_Dashboard.html:2454-2525`) ruft der Browser direkt Binance Futures REST an (`fapi.binance.com`), dann Binance Vision, dann Bybit, dann Bitget. F&G via `api.alternative.me`, Coinlore via `api.coinlore.net`. | **Verifiziert mit Code-Detail:** Browser ruft Third-Party REST direkt ab (nicht über Relay). |
| **P6** | **Reactive UI Render** (Quant Engine &rarr; DOM via `RenderCache`, `<1ms`) | `Symbiose_Dashboard.html:2750-2820, 5139`: `RenderCache.isDirty(panel, stateKey)` prüft State-Hashes je Panel vor dem Rendern und verhindert unnötige DOM-Mutationen. | **Verifiziert.** Verhindert Layout-Thrashing. |

---

### (2) Wer berechnet Signale und Scores? Doppelte Produktionsimplementierungen

#### Ausführungsorte der Berechnungen:
1. **Browser-Engine (`Symbiose_Dashboard.html:1065-2272`):**
   Berechnet Indikatoren (EMA, ATR, ADX, SuperTrend, RSI, Stoch, MACD, BB, KC, CVD, VWAP, SMC), Confluence-Score (0–100), MTF-Ausrichtung, Regimes (`regimeOf()`), Walk-Forward DSR (`runWalkForwardBacktest()`, `calcDSR()`) und Kelly-Größen (`calcKelly()`) für interaktives Research und Chart-Visualisierung.
2. **Headless Runner (`headless_autobot.js:54-150`):**
   Implementiert die Berechnungsformeln **nicht** ein zweites Mal als getrennten Quelltext, sondern extrahiert den Code-Block zwischen `// ==ENGINE_BEGIN==` und `// ==ENGINE_END==` aus `Symbiose_Dashboard.html` zur Laufzeit via Node `fs.readFileSync` und führt ihn in einer isolierten Node `vm`-Sandbox aus.
3. **Python Relay (`bitget_relay.py:588-681`):**
   Enthält eine **redundante Python-Produktionsimplementierung** von EMA, ATR, ADX, Bollinger Bands, Keltner Channel und BTC-Regime-Klassifikation für den Hintergrund-Signal-Center-Loop (`_signal_center_loop`, alle 5 Minuten).
4. **Pine Script (`Symbiose_Signal_System_v1.pine:1-855`):**
   Vollständige Paritäts-Implementierung aller Indikatoren, Scoring-Regeln und Exits in Pine Script v6 für TradingView.
5. **Shadow Collector (`shadow_collector.js:58-185`):**
   Eigenständige Re-Implementierung der SL/TP1/TP2/BE/TimeStop-Ergebnissimulation (`evaluateDeterministicOutcome()`).

#### Detaillierte Liste doppelter Formel-Implementierungen:

| Berechnete Formel / Logik | Implementierung 1 (Kanonisch) | Implementierung 2 (Duplikat) | Implementierung 3 (Duplikat) | Drift- / Divergenz-Risiko |
| :--- | :--- | :--- | :--- | :--- |
| **EMA (Exponential Moving Average)** | `Symbiose_Dashboard.html:1120-1127` (`calcEMA`, $\alpha = \frac{2}{p+1}$) | `bitget_relay.py:588-595` (`_ema_series`) | `Symbiose_Signal_System_v1.pine:198-202` (`ta.ema`) | **Mittel:** Python initialisiert mit `values[0]`, JS mit Seed. Bei kurzen Serien Warmup-Drift möglich. |
| **ATR (Average True Range / RMA Wilder)** | `Symbiose_Dashboard.html:1129-1142` (`calcATR`, Wilder Smoothing) | `bitget_relay.py:598-610` (`_atr_series`) | `Symbiose_Signal_System_v1.pine:204` (`ta.atr`) | **Mittel:** RMA-Akkumulation driftet bei unterschiedlichen Fensterlängen leicht. |
| **ADX (Average Directional Index)** | `Symbiose_Dashboard.html:1169-1200` (`calcADX`, 14 Perioden) | `bitget_relay.py:613-643` (`_adx_series`) | `Symbiose_Signal_System_v1.pine:218-235` (Wilder DMI/ADX) | **Hoch:** Unterschiedliche Glättungsinitialisierung für $+DI/-DI$ kann Schwellenübertritte ($ADX \ge 20$) verzögern. |
| **BTC Regime & Squeeze Klassifikation** | `Symbiose_Dashboard.html:1683-1724` (`regimeOf`, `squeezeAt`, `squeezeMetricsAt`) | `bitget_relay.py:645-681` (`classify_btc_regime`) | `Symbiose_Signal_System_v1.pine:350-380` | **Hoch:** Python nutzt BB vs KC auf 20 Kerzen; JS nutzt Epsilon-Vergleiche gegen EMA200. Signal-Center im Relay und Dashboard können bei Grenzwerten asynchron sein. |
| **Trade Outcome Simulation (SL, TP, BE, TimeStop)** | `Symbiose_Dashboard.html:1780-1860` (`simulateRange`) | `shadow_collector.js:58-185` (`evaluateDeterministicOutcome`) | `headless_autobot.js:323-357` (`checkTpSlHits`, `applyAutoBreakeven`, `checkTimeStop`) | **Hoch:** Unterschiedliche Berechnungsreihenfolge von Bar-High/Low-Berührungen führt zu abweichenden Net-R-Ergebnissen. |
| **CVD (Cumulative Volume Delta) & Approximation** | `Symbiose_Dashboard.html:1225-1250` (`calcCVD`) | `scripts/cvd_reference.py:40-80` (`calculate_cvd`) | `Symbiose_Signal_System_v1.pine:209-215` | **Niedrig:** Durch Golden-Master-Paritätstest in CI auf $2,54 \times 10^{-11}$ Toleranz abgesichert. |

---

### (3) Wer schreibt Paper-Trades und wo landen sie?

1. **Ausführende Instanz (Trade Opener & Manager):**
   - **Ausschließlich `headless_autobot.js`** (wenn `AURA_BOT_MODE=server` gesetzt ist, `headless_autobot.js:1114`).
   - Eröffnet Trades in `runScanCycle()` (`headless_autobot.js:980-999`).
   - Verwaltet aktive Trades (Trailing-SL, TP1-3, Breakeven bei $+1R$, Time-Stop) in `headless_autobot.js:615-648`.
   - Der Browser (`Symbiose_Dashboard.html:10406-10409`) führt **keine** Trades mehr aus (`if (App.serverBotActive) return null;`).
2. **Speicherorte & Zieldateien:**
   - **Primärer State-Store:** `data/aura_shared_state.json` (bzw. `/var/lib/aura/aura_shared_state.json` im Container).
     - Aktive Trades: Key `aura-quant-terminal-active-trades-v2` (`headless_autobot.js:1038`, `record_schema: 2`, `source: "server"`).
     - Geschlossene Trades: Key `aura-quant-terminal-history-trades-v2` (`headless_autobot.js:1042`).
     - Bot-Metadaten & Equity: Key `aura-server-bot-state-v1` (`headless_autobot.js:1024`).
   - **Schatten- & Audit-Log:** `data/shadow_log.jsonl` (geschrieben von `shadow_collector.js:230-260` für jeden Scan-Kandidaten, sowohl `ACCEPTED` als auch `REJECTED`).
   - **Runner-Health-Datei:** `data/runner_health.json` (geschrieben von `headless_autobot.js:1087-1108` für Heartbeats, Cycle-Count und 24h-Funnel).
   - **Browser-Speicher (`localStorage`):**
     - Dashboard zieht State via `SyncEngine.pull()` (`Symbiose_Dashboard.html:9427`) von `/api/state` und spiegelt ihn in `localStorage` unter `aura-quant-terminal-active-trades-v2` / `*-history-trades-v2`. Dient rein als Offline-Cache und Anzeige-Puffer.

---

### (4) Persistenz, Schemas, Migrationen & Datenverlust bei Container-Neustart

#### Dateiinventar im State-Verzeichnis (`AURA_STATE_DIR` / `/var/lib/aura`):
1. `aura_shared_state.json` (Schema Version 2):
   - **Schema-Felder:** `schema_version` (2), `rev` / `_rev` (int), `_updated_at` (unix ts), `trades` / `history` (Arrays mit `record_schema: 2`), `aura-server-bot-config-v1` (Dict), `aura-server-bot-state-v1` (Dict), `_signal_claims` (Dict für Dedup), `cooldowns` (Dict).
2. `aura_signal_center_state.json` (Schema Version 2):
   - **Schema-Felder:** `schema_version` (2), `btc` (Regime-State & Last Notified), `digest` (Last Digest Date), `runner_health_alert`, `feed_error_alert`.
3. `runner_health.json` (JSON Snapshot):
   - `running`, `lastCycleAt`, `lastHeartbeatAt`, `cycleCount`, `tradeCount`, `equity`, `funnel24h`, `updatedAt`.
4. `shadow_log.jsonl` (Append-Only Text):
   - JSONL-Zeilen mit `{ ts, symbol, tf, dir, score, decision, reject_reason, config_sha256, outcome }`.
5. `shadow_stats.json` (JSON Snapshot):
   - Zähler für `accepted_count`, `rejected_count`, `reject_reasons`.
6. `aura_*.v1-backup-<timestamp>`:
   - Byte-getreue Backups vor Migrationen.

#### Migrations-Architektur (`scripts/state_migration.py` & `scripts/ops/aura_state_migrate.py`):
- Wird beim Relay-Start (`bitget_relay.py:2759`) automatisch aufgerufen (`migrate_state_directory(STATE_DIR)`).
- Wandelt Legacy-Keys (`*-v1`) in Schema v2 (`*-v2`) um, stempelt `record_schema = 2` auf Trade-Objekte.
- Erzeugt ein Backup `.v1-backup-<UTC-Timestamp>` vor dem ersten Schreibvorgang.
- Schreibt atomar über temporäre Dateien (`.tmp`) und `os.replace`.
- **Fail-Closed:** Wenn `schema_version > 2`, wirft das System `StatePersistenceError` und bricht den Start ab (`bitget_relay.py:288-294`).
- CLI-Unterstützung: `--dry-run`, `--rollback`, `--yes` (`scripts/ops/aura_state_migrate.py`).

#### Was geht bei Container-Neustart OHNE Volume verloren?
- Das Dockerfile definiert `AURA_STATE_DIR=/var/lib/aura` (`Dockerfile:17`).
- Im `docker-compose.yml:38` ist das Volume `aura-state:/var/lib/aura` deklariert.
- **Wird der Container ohne Volume betrieben (`docker run` ohne `-v`):**
  - **100% Datenverlust bei Container-Löschung/Recreation:**
    - Alle offenen Paper-Trades (`aura-quant-terminal-active-trades-v2`) werden gelöscht.
    - Die gesamte Trade-Historie geht verloren.
    - Das Paper-Eigenkapital wird auf den Startwert (`AURA_BOT_EQUITY=10000`) zurückgesetzt.
    - `runner_health.json` und `shadow_log.jsonl` werden gelöscht (Verlust empirischer Schatten-Validierungsdaten).
    - Signal-Dedup-Claims (`_signal_claims`) werden gelöscht &rarr; Re-Alerting alter Signale möglich.
    - Signal-Center-Cooldowns werden zurückgesetzt &rarr; sofortige Regime-Pushes möglich.

---

### (5) Konfigurationsfluss: `/api/bot-config`, Revisionen & Konfliktauflösung

1. **Konfigurationsänderung im UI:**
   - Benutzer ändert Einstellungen im Dashboard (z. B. Min Score, Risikoprozent, MTF Need, Profil).
   - UI ruft `Autobot.save()` (`Symbiose_Dashboard.html:10054`) und `Autobot.pushServerConfig()` (`Symbiose_Dashboard.html:10087`).
   - Dashboard sendet `POST /api/bot-config` mit JSON-Body an das Relay.
2. **Server-seitige Verarbeitung:**
   - Relay prüft Payload-Größe (`MAX_STATE_VALUE_BYTES = 1MB`, `bitget_relay.py:2331`).
   - Speichert Payload in `aura_shared_state.json` unter `aura-server-bot-config-v1` via `save_server_bot_config()` (`bitget_relay.py:1357`).
   - Inkrementiert die Server-Revision `_rev` atomar unter `STATE_LOCK` (`bitget_relay.py:450-455`).
3. **Runner-Übernahme:**
   - Im nächsten Scan-Zyklus (alle 15–60s) ruft `headless_autobot.js:595` `getState()` auf.
   - `readBotConfig(serverState)` (`headless_autobot.js:457-478`) extrahiert die Parameter und steuert damit sofort die Filter- und Positionsgrößen-Logik.
4. **Konfliktauflösung (PC vs. Smartphone / Multi-Client):**
   - **Optimistic Concurrency Control (OCC):**
     - Jede Mutation (`POST /api/state`) sendet `expected_rev` mit (`bitget_relay.py:2351, 380`).
     - Stimmt `expected_rev` nicht mit dem aktuellen `_rev` überein (z. B. Handy hat veralteten Stand), antwortet das Relay mit HTTP `409 Conflict` (`ERR_STATE_CONFLICT`) und liefert den aktuellen Server-State mit (`bitget_relay.py:2366-2371`).
     - `SyncEngine` im Client (`Symbiose_Dashboard.html:9634-9640`) fängt 409 ab, aktualisiert seine lokale Revision (`this.rev = conflict.rev`), wendet den Server-State an (`this.applyServerState(conflict.state, true)`), setzt UI-Status auf `"Konflikt — wiederhole"` und sendet die Mutation mit exponentiellem Backoff erneut.
     - Mutation-Batches arbeiten ID-basiert (`upsert`/`delete` einzelner Trade-IDs in `bitget_relay.py:334-364`), sodass parallele Änderungen verschiedener Trades konfliktfrei zusammengeführt werden.

---

### (6) Datenqualität: Gaps, Backfill, Dedup, Rate-Limits & Fallback-Kette

1. **Gap-Erkennung & Backfill:**
   - **Befund:** Es gibt **keine** automatisierte Gap-Erkennung oder historische Multi-Step-Backfill-Engine im System.
   - Bitget-Kerzen werden mit `limit=1000` als einmaliger Snapshot geladen (`headless_autobot.js:234`, `Symbiose_Dashboard.html:2365`).
   - Kerzen werden nach Timestamp aufsteigend sortiert (`candles.sort((a, b) => a.t - b.t)`). Fehlen Kerzen innerhalb der 1000 Balken, bleibt die Lücke unbemerkt.
2. **Deduplizierung:**
   - **Kerzen / Ticks:** WebSocket-Handler (`Symbiose_Dashboard.html:6370-6440`) prüft Timestamp der eingehenden Kerze: gleicher Timestamp aktualisiert den laufenden Balken; neuerer Timestamp wird angehängt (`c.t > last.t`).
   - **Signale & Notifications:** Atomare, persistente Claims in `aura_shared_state.json` unter `_signal_claims` (`bitget_relay.py:480-520`). Der Event-Key `${trade.id}:${event}` kann systemweit nur einmal geclaimed werden (`headless_autobot.js:286-290`).
3. **Rate-Limit-Handling:**
   - Relay: `TokenBucketRateLimiter` (10 req/s, Burst 20).
   - SingleFlight (`bitget_relay.py:2011, 2042-2068`): Bündelt identische gleichzeitige Anfragen auf denselben Cache-Key (verhindert Thundering Herd).
   - Exponentieller Upstream-Backoff bei Bitget-429 (`bitget_relay.py:2013-2028`).
   - Client-seitiger Retry-Backoff (`Symbiose_Dashboard.html:2340-2356`).
4. **Fallback-Kette & Signal-Blockade (Bitget &rarr; Binance &rarr; CoinGecko/Coinlore &rarr; Static):**
   - **Ist der Fallback für Signale blockiert oder still aktiv?**
   - **Befund: Fallback für Signale ist EINDEUTIG FAIL-CLOSED BLOCKIERT.**
   - **Code-Beleg:**
     - Wenn das Universe in den Offline-Fallback wechselt (`Symbiose_Dashboard.html:5087-5126`), werden die Assets mit `liquidityVerified: false` und `vol: null` markiert (`Symbiose_Dashboard.html:5101, 5124`).
     - Der Headless Runner (`headless_autobot.js:705-714`) und die Dashboard-Engine (`Symbiose_Dashboard.html:10460-10465`) verlangen zwingend:
       ```javascript
       if (!universeRow || universeRow.liquidityVerified !== true ||
           !Number.isFinite(+universeRow.vol) || +universeRow.vol < cfg.min24hVol) {
         addAutobotReject(funnel, 'LIQUIDITY');
         continue;
       }
       ```
     - Im Fallback-Modus wird jeder Kandidat mit `reject_reason: 'LIQUIDITY'` abgewiesen. Es werden **keine** Trades eröffnet.

---

### (7) Zeitverarbeitung: UTC-Konvention, laufende vs. geschlossene Kerzen, HTF-Vorschau

1. **UTC-Konvention (Millisekunden-Standard):**
   - Gemäß `docs/architecture.md` Abschnitt 7 werden alle Zeitstempel (`t`, `openedAt`, `lastCycleAt`) ausnahmslos in **Unix-Epochen-Millisekunden (ms)** geführt.
   - `normalizeTimestamp(val)` (`Symbiose_Dashboard.html:2325`): Werte unter $10^{10}$ (Sekunden) werden automatisch mit 1000 multipliziert.
   - UTC ISO-Formatierung in Python via `time.gmtime()` (`bitget_relay.py:683-685`, `_iso_utc()`).
   - VWAP-Tagesgruppierung: Exakt auf UTC-Mitternacht über `Math.floor(ts / 86400000) * 86400000` (`Symbiose_Dashboard.html:1255`).
   - Daily Digest: Auslösung zur konfigurierten UTC-Stunde (`AURA_NTFY_DIGEST_UTC=7`, `bitget_relay.py:806-830`).
2. **Laufende vs. geschlossene Kerzen:**
   - **Signal-Berechnung & Backtest:** Arbeiten **ausschließlich mit geschlossenen Kerzen**!
     - `headless_autobot.js:241-248`: Filtert Klines mit `c[8] === '1'` (Bitget Bestätigungs-Flag für abgeschlossene Kerzen).
     - `Symbiose_Dashboard.html:2367-2375`: Filtert `if (ts + dur > now) continue;`.
     - `bitget_relay.py:742-756` (`_parse_bitget_candles`): Schließt Kerzen aus, deren Schließzeitpunkt in der Zukunft liegt.
   - **Live-Chart & TP/SL-Monitoring:**
     - Live-Ticker-Ticks aktualisieren den laufenden Balken auf dem Canvas (`Symbiose_Dashboard.html:6370-6440`).
     - Autobot prüft TP/SL-Berührungen gegen den aktuellen Live-Marktpreis (`headless_autobot.js:323-337`).
3. **HTF-Vorschau (Higher Timeframe Preview):**
   - MTF-Scoring (15m, 1h, 4h, 1d) berechnet die Scores für jeden Timeframe separat auf dessen jeweiligen geschlossenen Kerzen.
   - Pine Script (`Symbiose_Signal_System_v1.pine:43-49`) nutzt `request.security(..., lookahead = barmerge.lookahead_off)` zur Vermeidung von Repaint/Lookahead-Lecks.

---

## 3. Funktionsinventar & Empfehlungen für serverseitige Zielarchitektur

| Funktion | Aktueller Implementierungsort | Kernlogik / Komponenten | Empfehlung für Zielarchitektur | Begründung & Migrationspfad |
| :--- | :--- | :--- | :--- | :--- |
| **1. Action Radar (Scanner)** | `Symbiose_Dashboard.html:4500-5050`<br>`headless_autobot.js:550-650` | Scannt 120+ Futures-Märkte über 4 Zeiteinheiten (15m, 1h, 4h, 1d); filtert Liquidität, MTF und Confluence. | **Ersetzen & Server-seitig kapseln** | Client-seitiges Scannen im Browser führt zu UI-Lags, Netzwerk-Spikes und bricht ab, wenn der Tab im Hintergrund schläft. Im Server-Monolithen: Asynchroner Python/Node-Worker mit kontinuierlichem Timeseries-Cache, der aggregierte Radar-Ergebnisse per WebSocket an das Frontend pusht. |
| **2. Confluence Engine** | `Symbiose_Dashboard.html:1065-2272`<br>`headless_autobot.js:54-150`<br>`bitget_relay.py:588-681` | Multi-Layer Scoring (Trend, Momentum, Volatilität, Volumen, SMC-Struktur) + Regime + MTF. | **Ersetzen / Konsolidieren in Python** | Bisher dreifache Code-Basis (JS-Engine, String-Extraction in Node VM, redundanter Python-Code im Relay). Konsolidierung als Single Source of Truth in Python (NumPy/Polars/Numba) für schnellere Berechnungen und zero-drift Backtests. |
| **3. Risk-Gates (DSR / Kelly / Regime)** | `Symbiose_Dashboard.html:1730-2200`<br>`headless_autobot.js:130-150`<br>`tests/test_kelly_oracle.js` | Deflated Sharpe Ratio ($DSR \ge 0.10 / 0.50$), Half-Kelly Sizing mit Sample-Ramp, BTC-Regime-Filter, Stagnation Time-Stop. | **Beibehalten & Server-seitig erzwingen** | Das mathematische Herzstück von AURA. Muss als unumgehbares Domain-Gate direkt vor jeder Trade-Ausführung im Order-Engine-Service liegen. |
| **4. Paper-Historie & State Management** | `bitget_relay.py:240-460`<br>`headless_autobot.js:393-452`<br>`Symbiose_Dashboard.html:9326-9690`<br>`scripts/state_migration.py` | JSON-basierte Speicherung (`aura_shared_state.json`) mit Optimistic Revision Concurrency (`_rev`) und localStorage Sync-Queue. | **Ersetzen durch relationale DB (PostgreSQL / SQLite)** | JSON-Flatfiles mit File-Locks sind anfällig für Concurrency-Probleme, erlauben keine performanten historischen Abfragen und sind migrationsintensiv. Ersetzen durch echtes relationales Schema mit WAL-Mode, foreign keys und sauberen Transaktionen. |
| **5. Notifikationen (ntfy)** | `bitget_relay.py:526-580`<br>`headless_autobot.js:285-318`<br>`bitget_relay.py:806-920` | Push-Nachrichten für Trade-Events, BTC-Regime, Daily Digest und Systemfehler via ntfy.sh Topic; zentrale Claim-Deduplizierung. | **Beibehalten & Modularisieren** | ntfy ist schlank, selbst-hostbar und betriebssicher. Als eigenständigen Notification-Service kapseln, der Event-getrieben arbeitet und optional Telegram/Webhooks unterstützt. |
| **6. TradingView-Bridge** | `bitget_relay.py:102-135, 2315-2324`<br>`Symbiose_Dashboard.html:3650-3750`<br>`scripts/ops/aura_webhook_receiver.reference.py` | Desktop-URL Protocol Integration (`tradingview://...`) und Webhook-Empfänger-Referenz. | **Beibehalten (als Utility-Route)** | Nützliches Workflow-Feature für manuelle Chart-Inspektion. Als schlanker API-Endpunkt beibehalten. |
| **7. Shadow Collector** | `shadow_collector.js`<br>`headless_autobot.js:493-515`<br>`data/shadow_log.jsonl` | Zeichnet alle Scan-Entscheidungen (Accepted + Rejects) append-only auf und simuliert deterministische Net-R-Ergebnisse. | **Beibehalten & in DB integrieren** | Kritisch für statistische Hygiene und Überwachung von Model Decay. Zukünftig direkt in eine strukturierte DB-Tabelle oder Parquet-Audit-Store schreiben. |
| **8. Tutorial** | `SYMBIOSE_Tutorial.html`<br>`bitget_relay.py:2231-2236` | Interaktives Benutzer-Handbuch für Indikatoren, Scoring-Modell, Kelly-Formel und Risikomanagement. | **Beibehalten / In Web-UI integrieren** | Als responsive Hilfeseite/Dokumentationskomponente in das neue Frontend übernehmen. |
| **9. Pine Script System** | `Symbiose_Signal_System_v1.pine`<br>`bitget_relay.py:2237-2242` | Pine Script v6 Indikator für TradingView-Charts mit identischer Confluence- und Exit-Logik. | **Beibehalten (als externes Research-Artefakt)** | Ermöglicht TradingView-Nutzern die visuelle Verifikation von Signalen. CI-Paritätstests (`test_compare_pine_js_golden.js`) beibehalten. |

---

## 4. Fazit & Architektur-Empfehlungen für den modularen Monolithen

1. **Entkopplung von Frontend und Quant-Berechnung:**
   - Der Browser darf keine schweren 120-Coin-MTF-Scans durchführen. Alle Berechnungen laufen auf dem Server in einem asynchronen Python-Worker.
   - Das Frontend wird ein rein reaktives Dashboard (z. B. modernisiertes HTML/JS oder leichtes SPA-Framework), das aggregierte Snapshots und Live-Events via WebSocket/SSE empfängt.
2. **Konsolidierung auf eine einzige Quant-Engine:**
   - Beseitigung der Node-VM-Code-Extraktion (`loadEngine()`) und der redundanten Relay-Formeln (`_ema_series`, `classify_btc_regime`).
   - Eine einheitliche, hochperformante Python-Engine (NumPy/Polars) bedient Scanner, Live-Runner und Backtest.
3. **Echte Persistenz & Container-Sicherheit:**
   - Migration von JSON-Flatfiles (`aura_shared_state.json`) auf eine relationale Datenbank (PostgreSQL oder eingebettetes SQLite im WAL-Modus mit Host-Volume-Mount).
   - Echte ACID-Garantien für Trade-Transaktionen, Funnel-Logs und Schatten-Historie.
4. **Ausfallsichere Marktdaten-Pipeline:**
   - Server-seitiger Marktdaten-Manager mit WebSocket-Verbindung zu Bitget, automatischem Reconnect, Lücken-Erkennung (Gap Detection) und periodischem Klines-Backfill.
   - Strenges Fail-Closed-Verhalten bei Datenfehlern bleibt oberste Priorität.
