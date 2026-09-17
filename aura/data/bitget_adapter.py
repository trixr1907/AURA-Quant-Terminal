"""Bitget USDT-Futures REST Adapter (aura.data.bitget_adapter).

Dokumentiert in docs/DATA_CONTRACTS.md.
Beachtet Bitget API v2 Spezifikation fuer USDT-FUTURES:
  * Kerzen: /api/v2/mix/market/candles
  * Funding-Rate: /api/v2/mix/market/current-fund-rate
  * Open Interest: /api/v2/mix/market/open-interest
  * Contract Specs: /api/v2/mix/market/contracts
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from decimal import Decimal, InvalidOperation
from typing import Any, Sequence
from urllib import error, parse, request

from aura.data.models import Candle, ContractSpec, DataProvenance, ValidationReport
from aura.data.validation import validate_candle_series, validate_single_candle

logger = logging.getLogger("aura.data.bitget_adapter")

BITGET_BASE_URL = "https://api.bitget.com"


class BitgetMarketAdapter:
    """Oeffentlicher Bitget USDT-Futures Marktdaten-Adapter."""

    def __init__(
        self,
        base_url: str = BITGET_BASE_URL,
        timeout: float = 10.0,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_request_time = 0.0

    def fetch_candles(
        self,
        symbol: str,
        granularity: str = "1H",
        limit: int = 100,
        end_time_ms: int | None = None,
    ) -> tuple[list[Candle], ValidationReport]:
        """Laedt historische Kerzen von Bitget und validiert sie schema-konform."""
        params: dict[str, Any] = {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
            "granularity": granularity,
            "limit": str(min(1000, limit)),
        }
        if end_time_ms:
            params["endTime"] = str(end_time_ms)

        url = f"{self.base_url}/api/v2/mix/market/candles?{parse.urlencode(params)}"
        raw_data = self._http_get_json(url)

        candles: list[Candle] = []
        if not raw_data or raw_data.get("code") != "00000":
            err_msg = raw_data.get("msg") if raw_data else "Keine Antwort von Bitget"
            report = ValidationReport(is_valid=False, total_checked=0, errors=[f"Bitget API Fehler: {err_msg}"])
            return [], report

        rows = raw_data.get("data", [])
        now_ms = int(time.time() * 1000)

        # Bitget liefert: [ts, open, high, low, close, volume, usdt_volume]
        # Typischerweise absteigend sortiert -> wir sortieren chronologisch aufsteigend
        parsed_rows = []
        for r in rows:
            try:
                t = int(r[0])
                o = float(r[1])
                h = float(r[2])
                l = float(r[3])
                c = float(r[4])
                v = float(r[5])
                qv = float(r[6]) if len(r) > 6 else 0.0
                parsed_rows.append((t, o, h, l, c, v, qv))
            except (ValueError, IndexError) as ex:
                logger.warning("Fehler beim Parsen der Bitget-Kerze %s: %s", r, ex)

        parsed_rows.sort(key=lambda x: x[0])

        for idx, (t, o, h, l, c, v, qv) in enumerate(parsed_rows):
            is_last = idx == len(parsed_rows) - 1
            prov = DataProvenance(
                data_source="bitget_rest",
                market="USDT-FUTURES",
                instrument=symbol,
                event_time_ms=t,
                received_time_ms=now_ms,
                timezone="UTC",
            )
            candle = Candle(
                time_ms=t,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=v,
                quote_volume=qv,
                is_closed=not is_last,  # Letzter Bar ist oft noch laufend
                provenance=prov,
            )
            candles.append(candle)

        report = validate_candle_series(candles, timeframe=granularity.lower())
        return candles, report

    def fetch_contract_specs(self) -> list[ContractSpec]:
        """Load and strictly normalize active USDT perpetual specifications."""
        url = f"{self.base_url}/api/v2/mix/market/contracts?productType=USDT-FUTURES"
        raw_data = self._http_get_json(url)
        if not raw_data:
            return []
        try:
            raw_sha = hashlib.sha256(json.dumps(raw_data, sort_keys=True).encode("utf-8")).hexdigest()
            return self.parse_contract_specs(raw_data, fetched_at_ms=int(time.time() * 1000), raw_sha256=raw_sha)
        except ValueError as ex:
            logger.error("Konnte Bitget-Kontrakte nicht validieren: %s", ex)
            return []

    @staticmethod
    def parse_contract_specs(
        raw_data: dict[str, Any], *, fetched_at_ms: int, raw_sha256: str = "sha256_uncalculated"
    ) -> list[ContractSpec]:
        if raw_data.get("code") != "00000" or not isinstance(raw_data.get("data"), list):
            raise ValueError("ungueltige Contract-Config-Antwort")

        def required_decimal(item: dict[str, Any], field: str, *, allow_zero: bool = False) -> Decimal:
            if field not in item or item[field] in (None, ""):
                raise ValueError(f"{field} fehlt")
            try:
                value = Decimal(str(item[field]))
            except (InvalidOperation, ValueError) as ex:
                raise ValueError(f"{field} ist keine Dezimalzahl") from ex
            if not value.is_finite() or value < 0 or (value == 0 and not allow_zero):
                raise ValueError(f"{field} ist nicht positiv")
            return value

        specs: list[ContractSpec] = []
        for item in raw_data["data"]:
            if not isinstance(item, dict):
                raise ValueError("Contract-Eintrag ist kein Objekt")
            status = str(item.get("symbolStatus") or "")
            symbol_type = str(item.get("symbolType") or "")
            quote = str(item.get("quoteCoin") or "")
            margin_coins = item.get("supportMarginCoins")
            if status != "normal" or symbol_type != "perpetual" or quote != "USDT" or not isinstance(margin_coins, list) or "USDT" not in margin_coins:
                continue
            symbol = str(item.get("symbol") or "")
            base = str(item.get("baseCoin") or "")
            if not symbol or not base:
                raise ValueError("symbol/baseCoin fehlt")
            price_place = int(required_decimal(item, "pricePlace", allow_zero=True))
            price_end_step = required_decimal(item, "priceEndStep")
            qty_step = required_decimal(item, "sizeMultiplier")
            min_qty = required_decimal(item, "minTradeNum")
            if min_qty % qty_step != 0:
                raise ValueError(f"minTradeNum ist kein Vielfaches von sizeMultiplier fuer {symbol}")
            specs.append(
                ContractSpec(
                    symbol=symbol,
                    base_coin=base,
                    quote_coin=quote,
                    settle_coin="USDT",
                    product_type="USDT-FUTURES",
                    symbol_type=symbol_type,
                    symbol_status=status,
                    price_tick=price_end_step * (Decimal(10) ** -price_place),
                    qty_step=qty_step,
                    min_qty=min_qty,
                    min_notional=required_decimal(item, "minTradeUSDT"),
                    maker_fee_rate=required_decimal(item, "makerFeeRate", allow_zero=True),
                    taker_fee_rate=required_decimal(item, "takerFeeRate", allow_zero=True),
                    max_leverage=int(required_decimal(item, "maxLever")),
                    event_time_ms=int(raw_data.get("requestTime") or 0),
                    fetched_at_ms=int(fetched_at_ms),
                    raw_snapshot_sha256=raw_sha256,
                )
            )
        return specs

    def fetch_all_tickers(self, product_type: str = "USDT-FUTURES") -> tuple[dict[str, Any] | None, int, str]:
        """Fetch all tickers with timing and raw SHA256."""
        now_ms = int(time.time() * 1000)
        url = f"{self.base_url}/api/v2/mix/market/tickers?productType={product_type}"
        raw = self._http_get_json(url)
        if not raw:
            return None, now_ms, ""
        raw_bytes = json.dumps(raw, sort_keys=True).encode("utf-8")
        raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        return raw, now_ms, raw_sha256

    def fetch_orderbook_depth(
        self, symbol: str, limit: int = 50, precision: str = "scale0"
    ) -> tuple[dict[str, Any] | None, int, str]:
        """Fetch orderbook depth with timing and raw SHA256."""
        now_ms = int(time.time() * 1000)
        params = {
            "symbol": symbol,
            "productType": "USDT-FUTURES",
            "precision": precision,
            "limit": str(limit),
        }
        url = f"{self.base_url}/api/v2/mix/market/merge-depth?{parse.urlencode(params)}"
        raw = self._http_get_json(url)
        if not raw:
            return None, now_ms, ""
        raw_bytes = json.dumps(raw, sort_keys=True).encode("utf-8")
        raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        return raw, now_ms, raw_sha256

    @staticmethod
    def parse_depth_metrics(
        raw_depth: dict[str, Any], max_depth_band_bps: Decimal = Decimal("25")
    ) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, bool]:
        """Extract spread and notional depth within ±max_depth_band_bps of mid, strictly validating all levels."""
        data = raw_depth.get("data") if isinstance(raw_depth, dict) and "data" in raw_depth else raw_depth
        if not isinstance(data, dict):
            return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), False
        raw_asks = data.get("asks")
        raw_bids = data.get("bids")
        if not isinstance(raw_asks, list) or not isinstance(raw_bids, list):
            return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), False
        if len(raw_asks) == 0 or len(raw_bids) == 0:
            return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), False

        parsed_bids: list[tuple[Decimal, Decimal]] = []
        parsed_asks: list[tuple[Decimal, Decimal]] = []

        try:
            # 1. Parse and strictly validate all bids (must be finite, >0, strictly descending)
            prev_bid_price: Decimal | None = None
            for item in raw_bids:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), False
                p = Decimal(str(item[0]))
                s = Decimal(str(item[1]))
                if not p.is_finite() or not s.is_finite() or p <= 0 or s <= 0:
                    return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), False
                if prev_bid_price is not None and p >= prev_bid_price:
                    # Violates strict descending sorting or has duplicate prices
                    return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), False
                prev_bid_price = p
                parsed_bids.append((p, s))

            # 2. Parse and strictly validate all asks (must be finite, >0, strictly ascending)
            prev_ask_price: Decimal | None = None
            for item in raw_asks:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), False
                p = Decimal(str(item[0]))
                s = Decimal(str(item[1]))
                if not p.is_finite() or not s.is_finite() or p <= 0 or s <= 0:
                    return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), False
                if prev_ask_price is not None and p <= prev_ask_price:
                    # Violates strict ascending sorting or has duplicate prices
                    return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), False
                prev_ask_price = p
                parsed_asks.append((p, s))

            best_bid = parsed_bids[0][0]
            best_ask = parsed_asks[0][0]

            # 3. No crossed or locked book
            if best_ask <= best_bid:
                return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), False

            mid = (best_bid + best_ask) / Decimal("2")
            spread_bps = ((best_ask - best_bid) / mid) * Decimal("10000")
            min_bid = mid * (Decimal("1") - max_depth_band_bps / Decimal("10000"))
            max_ask = mid * (Decimal("1") + max_depth_band_bps / Decimal("10000"))

            bid_depth = sum(
                (p * s for p, s in parsed_bids if p >= min_bid),
                Decimal("0"),
            )
            ask_depth = sum(
                (p * s for p, s in parsed_asks if p <= max_ask),
                Decimal("0"),
            )
            return spread_bps, bid_depth, ask_depth, best_bid, best_ask, True
        except (InvalidOperation, ValueError, TypeError, IndexError):
            return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), False

    def _http_get_json(self, url: str) -> dict[str, Any] | None:
        """Fuehrt HTTP-GET mit Rate-Limiting und Retries mit Backoff aus."""
        # Rate Limiting: min 50ms zwischen Anfragen (max 20 req/s)
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < 0.05:
            time.sleep(0.05 - elapsed)

        headers = {
            "User-Agent": "AURA-Quant-Terminal/3.0",
            "Accept": "application/json",
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                self._last_request_time = time.time()
                req = request.Request(url, headers=headers, method="GET")
                with request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status == 200:
                        content = resp.read().decode("utf-8")
                        return json.loads(content)
            except (error.HTTPError, error.URLError, json.JSONDecodeError, TimeoutError) as ex:
                logger.warning("HTTP GET Fehler (Versuch %d/%d) fuer %s: %s", attempt, self.max_retries, url, ex)
                if attempt < self.max_retries:
                    backoff = 0.5 * (2 ** (attempt - 1))
                    time.sleep(backoff)

        return None
