"""Bitget USDT-Futures REST Adapter (aura.data.bitget_adapter).

Dokumentiert in docs/DATA_CONTRACTS.md.
Beachtet Bitget API v2 Spezifikation fuer USDT-FUTURES:
  * Kerzen: /api/v2/mix/market/candles
  * Funding-Rate: /api/v2/mix/market/current-fund-rate
  * Open Interest: /api/v2/mix/market/open-interest
  * Contract Specs: /api/v2/mix/market/contracts
"""

from __future__ import annotations

import json
import logging
import math
import time
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
        """Laedt alle aktiven USDT-FUTURES Kontraktspezifikationen."""
        url = f"{self.base_url}/api/v2/mix/market/contracts?productType=USDT-FUTURES"
        raw_data = self._http_get_json(url)

        specs: list[ContractSpec] = []
        if not raw_data or raw_data.get("code") != "00000":
            logger.error("Konnte Kontrakte von Bitget nicht laden: %s", raw_data)
            return []

        for item in raw_data.get("data", []):
            if item.get("symbolStatus") != "normal":
                continue
            try:
                spec = ContractSpec(
                    symbol=item.get("symbol", ""),
                    base_coin=item.get("baseCoin", ""),
                    quote_coin=item.get("quoteCoin", "USDT"),
                    product_type=item.get("productType", "USDT-FUTURES"),
                    ct_val=float(item.get("sizeMultiplier") or 0.001),
                    maker_fee_rate=float(item.get("makerFeeRate") or 0.0002),
                    taker_fee_rate=float(item.get("takerFeeRate") or 0.0006),
                    min_size=float(item.get("minTradeNum") or 0.001),
                    min_notional=float(item.get("minTradeUSDT") or 5.0),
                    max_leverage=int(item.get("maxLever") or 50),
                    price_place=int(item.get("pricePlace") or 2),
                    volume_place=int(item.get("volumePlace") or 2),
                    price_end_step=float(item.get("priceEndStep") or 1.0),
                )
                specs.append(spec)
            except Exception as ex:
                logger.warning("Konnte Spezifikation fuer %s nicht parsen: %s", item.get("symbol"), ex)

        return specs

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
