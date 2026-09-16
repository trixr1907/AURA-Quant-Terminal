# AURA v3 — Datenvertraege & Marktdaten-Spezifikation (DATA_CONTRACTS.md)

**Status:** Kanonisch v3.0 · **Datum:** 2026-09-17 · **Geltung:** Verbindlich fuer alle Datenadapter, Persistenz, Replay und UI

---

## 1. Datenquellen & Endpunkte

AURA v3 bezieht ausschliesslich echte, oeffentliche Marktdaten der Boerse **Bitget (USDT-FUTURES Perpetual)** ueber die offizielle REST API v2.

| Datentyp | Bitget REST Endpoint | Intervall / Frequenz | Cache / Vorhaltung |
|---|---|---|---|
| **Kerzen (OHLCV)** | `GET /api/v2/mix/market/candles` | 1m, 5m, 15m, 1h, 4h, 1d | SQLite WAL (`candles`) |
| **Funding Rate** | `GET /api/v2/mix/market/current-fund-rate` | 8h Taktung / minuetlich polled | In-Memory & SQLite |
| **Open Interest** | `GET /api/v2/mix/market/open-interest` | minuetlich polled | In-Memory History |
| **Ticker & Mark Price** | `GET /api/v2/mix/market/ticker` | 1s - 5s Polling / WebSocket | In-Memory Latest |
| **Kontrakte & Universum**| `GET /api/v2/mix/market/contracts` | 1x taeglich / bei Start | SQLite (`universe`) & Fallback JSON |

### Rate Limits & Schutz
- Bitget oeffentliches Limit: max. 20 Requests/Sekunde pro IP.
- Internes Token-Bucket / Throttling in `aura.data.bitget_adapter.BitgetMarketAdapter`: min. 50ms zwischen Anfragen.
- Retries: Max. 3 Versuche mit exponentiellem Backoff ($0.5s, 1.0s, 2.0s$) und Jitter.

---

## 2. Provenienz & Zeitstempel-Konventionen

Jedes in das System eingehende Datenobjekt traegt eine explizite Provenienz (`DataProvenance`):

```json
{
  "data_source": "bitget_rest",
  "market": "USDT-FUTURES",
  "instrument": "BTCUSDT",
  "event_time_ms": 1735689600000,
  "received_time_ms": 1735689601245,
  "timezone": "UTC",
  "processing_version": "3.0.0-dev",
  "is_proxy": false
}
```

### Mandats-Regeln:
1. **Interne Zeitbasis:** Immer UTC als 64-Bit-Ganzzahl (Unix-Millisekunden).
2. **Keine Spot-/Binance-Vermischung:** Kein stiller Austausch von Perpetual-Daten durch andere Boersen oder Spot-Preise.
3. **CVD als Proxy gekennzeichnet:** Solange CVD aus OHLCV-Kerzen berechnet wird (`is_proxy = True`), darf er nicht als exakter Orderflow-CVD dargestellt werden.
4. **Synthetische Fixtures:** Duerfen ausschliesslich in isolierten Softwaretests verwendet werden (`data_source = "synthetic_fixture"`) und werden niemals als Performance-Evidenz gewertet.

---

## 3. Kerzen-Schema & Physikalische Invarianten

Jede Kerze muss vor der Speicherung oder Verarbeitung folgende Invarianten erfuellen:

$$\text{time\_ms} > 0$$
$$\text{open} > 0, \quad \text{high} > 0, \quad \text{low} > 0, \quad \text{close} > 0$$
$$\text{high} \ge \max(\text{open}, \text{close})$$
$$\text{low} \le \min(\text{open}, \text{close})$$
$$\text{high} \ge \text{low}$$
$$\text{volume} \ge 0$$

Kerzen, die diese Invarianten verletzen, werden sofort abgelehnt und als `DATA_DEGRADED` geloggt.

---

## 4. Lueckenerkennung (Gap Detection) & Backfill

- Zeitreihen werden auf Luecken geprueft: Wenn $\Delta t > \text{Intervall}$, liegt eine Luecke vor.
- Die Engine plant automatisch fehlende Chunks (max. 100 Bars pro Request) und fuehrt einen geordneten Backfill durch.
- **Fail-Closed bei unvollstaendigen Daten:** Wenn erforderliche Warmup-Bars (z.B. 235 Bars fuer EMA200/ATR) fehlen, wird kein Signal generiert und kein neuer Trade eroeffnet.
