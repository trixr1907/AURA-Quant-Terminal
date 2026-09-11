# AURA Quant Terminal — System & Datenpfad-Architektur

**Version:** 1.1.7 (Release)
**Dokumenttyp:** Technische Architektur- & Datenpfadspezifikation  
**Status:** Aktiv  

---

## 1. Systemübersicht & Datenpfad-Diagramm

Das AURA Quant Terminal ist ein **Client-First High-Performance Quantitative Trading & Analytics Terminal**. Es kombiniert einen Single-File Frontend-Client (`Symbiose_Dashboard.html`) mit einem leichtgewichtigen Python-Relay (`bitget_relay.py`) für API-Proxying, Caching, Rate-Limiting und Cross-Device State-Synchronisation.

```mermaid
flowchart TD
    subgraph Browser Client [AURA Browser Client - Symbiose_Dashboard.html]
        UI[UI Panels: Hero, Status, Price, Signal, MTF, Liq, Backtest, Radar, Pulse]
        RC[RenderCache: State-Hash Dirty-Flag]
        Engine[Quant Engine: Purged Walk-Forward, Kelly, DSR, Regimes]
        WS_Client[Direct WebSocket Client]
        HTTP_Client[HTTP Fetch Layer]
    end

    subgraph Python Relay [Local / Docker Relay - bitget_relay.py]
        Proxy[RelayHandler: CORS & Security Proxy]
        TB[Token Bucket Rate Limiter: 10 req/s, Burst 20]
        Cache[In-Memory TTL Cache: Klines 60s, Tickers 5s, Other 10s]
        StateStore[Shared State Store: Optimistic Revision Concurrency]
    end

    subgraph External Exchanges & Data Providers
        Bitget_WS[Bitget / Binance WebSocket]
        Bitget_REST[Bitget REST API v2]
        Binance_REST[Binance Public API]
        CG_REST[CoinGecko / Alternative.me]
    end

    %% Data flows
    WS_Client <==>|Direct Ticks / AggTrades (4s Throttled Analysis)| Bitget_WS
    HTTP_Client -->|REST Proxy Request /api/public| Proxy
    HTTP_Client <-->|State Get/Post /api/state| StateStore

    Proxy --> Cache
    Cache -->|Cache Miss| TB
    TB -->|Tokens Available| Bitget_REST
    TB -.->|Capacity Exceeded| HTTP_Client

    Engine --> RC
    RC -->|Only Dirty Panels| UI

    HTTP_Client -.->|Public Fallback 1| Binance_REST
    HTTP_Client -.->|Public Fallback 2| CG_REST
```

---

## 2. Detaillierte Datenpfad-Zuständigkeiten

| Datenpfad | Quelle / Ziel | Transport | Protokoll / Format | Latenz / Cache-Policy | Zweck / Verantwortlichkeit |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **P1: Direct WebSocket** | Bitget / Binance &rarr; Client | WSS (`wss://...`) | JSON Stream | < 50 ms (4 s Signal-Throttle) | Live-Ticker, letzte Preise, Orderbuch-Ticks, Trade-Aggregates für Live-Regime. |
| **P2: REST via Relay (Public)** | Client &rarr; Relay &rarr; Bitget | HTTP POST `/api/public` | JSON RPC Passthrough | **Ticker: 5 s TTL**<br>**Klines: 60 s TTL**<br>**Other: 10 s TTL** | Historische Klines, Markt-Ticker, Funding-Rates, Open Interest ohne Auth-Keys. |
| **P3: Token-Bucket Uplink** | Relay &rarr; Bitget REST | HTTPS Uplink | JSON REST | **10 req/s (Burst 20)**<br>Overflow &rarr; `429 (Retry-After: 1)` | Schutz vor Exchange-IP-Bans bei simultanen 120-Märkte-Scans. |
| **P4: Cross-Device State Sync** | Client &rarr; Relay `/api/state` | HTTP GET / POST | JSON (Revisioned) | `no-store` (Echtzeit)<br>Optimistic Concurrency | Speichert Autobot-State, aktive Trades, UI-Konfiguration zwischen Desktop/Mobile. |
| **P5: Fallback-Kette** | Client &rarr; Ext. APIs | HTTPS GET | JSON REST | Bei Relay-Ausfall / API-Down | 1. Bitget REST &rarr; 2. Binance Public &rarr; 3. CoinGecko &rarr; 4. Prebuilt 120-Asset Static Universe. |
| **P6: Reactive UI Render** | Quant Engine &rarr; DOM | In-Memory (`RenderCache`) | Hash-Vergleich | < 1 ms | Berechnet State-Hashes je Panel; baut **nur geänderte DOM-Elemente** neu auf. |

---

## 3. In-Memory Caching & Token-Bucket Spezifikation

### 3.1 TTL-Cache-Hierarchie (`TTLCache`)
```
Request -> /api/public (GET)
   |
   +---> Cache-Key: (Method, BasePath, sorted(Query/Body Params))
   |
   +---> Key vorhanden & now < expire_at?
           |-- JA  -> Return Cached JSON (is_cached = True, 0 Uplink Tokens verbraucht)
           \-- NEIN -> Weiter zu Token Bucket
```

- **Klines / Kerzen:** 60 Sekunden TTL (`/api/v2/mix/market/candles`, `history-candles`).
- **Tickers:** 5 Sekunden TTL (`/api/v2/mix/market/tickers`).
- **Funding & Open Interest:** 10 Sekunden TTL (`funding`, `open-interest`, `contracts`).
- **Fehlerantworten:** Werden **niemals** gecacht (sofortige Retry-Fähigkeit).

### 3.2 Token-Bucket Rate Limiter (`TokenBucketRateLimiter`)
- **Füllrate:** 10 Tokens / Sekunde.
- **Kapazität (Burst):** 20 Tokens.
- **Verhalten bei Erschöpfung:** Sofortige Rückgabe von HTTP `429 Too Many Requests` mit Header `Retry-After: 1` und Payload `{"code": "429", "msg": "Relay rate limit exceeded..."}`.
- **Bitget-Schutz:** Der externe Uplink-Call wird **nicht** ausgeführt; Exchange-IP-Reputation bleibt geschützt.

---

## 4. Reactive UI Rendering (`RenderCache`)

Um DOM-Thrashing bei hochfrequenten WebSocket-Ticks zu verhindern, nutzt das Dashboard einen State-Hash-Cache:

```
renderAll(force = false)
   |
   +---> Invalidate() wenn force == true
   +---> computeLive() (Aktualisiert Signale & Regimes)
   |
   +---> Für jedes Panel (Hero, Status, Price, Signal, MTF, Liq, Backtest, Chart, Radar, Pulse):
           |
           +-> StateKey = [relevante Input-Felder für dieses Panel]
           +-> RenderCache.isDirty(PanelName, StateKey)?
                 |-- NEIN -> Panel-DOM bleibt unangetastet (0 Mutationen)
                 \-- JA   -> Panel rendert & speichert neuen Hash
```

---

## 5. Ausblick: Modul-Split-Plan (Architektur-Vorschlag)

*Hinweis: Das Single-File-Format (`Symbiose_Dashboard.html`) bleibt als finales Release-Artefakt verbindlich erhalten.*

Für künftige Versionen kann der Quellcode in logische TypeScript/ES6-Module zerlegt werden, die vor dem Release deterministisch zu einer einzelnen Datei assembliert werden:

```
src/
├── core/
│   ├── engine.js          # Purged Walk-Forward Backtest, Regimes, DSR
│   ├── indicators.js      # EMA, ATR, SuperTrend, RSI, ADX, VWAP
│   └── kelly.js           # Kelly-Kriterium & Positionsgrößen
├── data/
│   ├── bitget_client.js   # REST & WebSocket Adapter
│   ├── universe.js        # Statisches & dynamisches Universum
│   └── state_sync.js      # /api/state Client mit Revision Locking
├── ui/
│   ├── render_cache.js    # Dirty-Flag Cache
│   ├── chart_canvas.js    # Canvas-2D Candlestick & Overlays Renderer
│   └── panels/            # Hero, Radar, Signal, MTF, Backtest Panels
└── build/
    └── assemble.py        # Inline-Bundler -> dist/Symbiose_Dashboard.html
```

Vorteile:
- 100%ige Abwärtskompatibilität (Distribution bleibt ein einziges autarkes HTML-File).
- Vollständige Modularisierung und isolierte Unit-Tests für jedes Submodul.

---

## 6. Zeitstempel-Konvention (Millisekunden-Standard)

- **Verbindlicher Standard:** Sämtliche Zeitstempel im gesamten System (`candles[i].t`, Engine-Indikatoren, Session-Filter, VWAP-Tagesgruppierung) werden ausnahmslos in **Millisekunden (ms)** geführt.
- **Produktions-APIs:** WebSocket- und REST-Streams (Bitget `openTime`, Binance `openTime`) liefern Zeitstempel nativ in ms (z. B. `1735689600000`).
- **CSV- & Fixture-Import:** Externe CSV-Exporte mit Zeitstempeln in Sekunden (`< 10_000_000_000`) werden ausnahmslos über `normalizeTimestamp(value)` automatisch in Millisekunden ($s \times 1000$) skaliert:
  $$\text{timestamp}_{\text{ms}} = (n < 10^{10}) \;?\; n \times 1000 : n$$
- **Harness-Pflicht:** Jeder Test-Harness, Parser oder Reader (JavaScript oder Python), der Fixtures oder historische Daten einliest, MUSS diese Normalisierung anwenden. Dies stellt sicher, dass datumsbasierte Gruppierungen wie `Math.floor(ms / 86400000)` über alle Test- und Produktivumgebungen exakt identische Tagesgrenzen berechnen.
