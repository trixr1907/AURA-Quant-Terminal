"""Market data updater for Bitget USDT-FUTURES instruments and order books."""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from decimal import Decimal
from typing import Any, Callable, Sequence

from aura.data.bitget_adapter import BitgetMarketAdapter
from aura.data.liquidity import LiquidityPolicy, POLICY_VERSION
from aura.data.models import ContractSpec

logger = logging.getLogger("aura.data.market_updater")


class MarketDataUpdater:
    """Resource-bounded market data and liquidity updater."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        adapter: BitgetMarketAdapter | None = None,
        policy: LiquidityPolicy | None = None,
        symbols: Sequence[str] = ("BTCUSDT", "ETHUSDT"),
        min_interval_sec: float = 30.0,
        time_provider: Callable[[], float] | None = None,
    ):
        self.conn = conn
        self.adapter = adapter or BitgetMarketAdapter()
        self.policy = policy or LiquidityPolicy()
        self.symbols = list(symbols)
        self.min_interval_sec = min_interval_sec
        self.time_provider = time_provider or time.time
        self.last_update_ms: int = 0

    def update_cycle(self, *, force: bool = False, now_ms: int | None = None) -> dict[str, Any]:
        """Runs one update cycle if interval elapsed or forced."""
        current_ms = now_ms if now_ms is not None else int(self.time_provider() * 1000)
        if not force and (current_ms - self.last_update_ms) < int(self.min_interval_sec * 1000):
            return {"updated": False, "reason": "rate_limited_interval"}

        results: dict[str, Any] = {"updated": True, "symbols": {}}

        # 1. Fetch and persist contract specs
        try:
            specs = self.adapter.fetch_contract_specs()
            if specs:
                self.persist_contract_specs(specs)
                results["contracts_count"] = len(specs)
        except Exception as ex:
            logger.warning("Fehler beim Abruf von Kontraktspezifikationen: %s", ex)
            results["specs_error"] = str(ex)

        # 2. Fetch tickers for 24h quote volume
        tickers_by_symbol: dict[str, dict[str, Any]] = {}
        try:
            tickers_raw, _, _ = self.adapter.fetch_all_tickers()
            if tickers_raw and tickers_raw.get("code") == "00000" and isinstance(tickers_raw.get("data"), list):
                for t in tickers_raw["data"]:
                    sym = t.get("symbol")
                    if sym:
                        tickers_by_symbol[sym] = t
        except Exception as ex:
            logger.warning("Fehler beim Abruf von Tickers: %s", ex)

        # 3. For configured symbols, fetch orderbook depth and evaluate liquidity
        for symbol in self.symbols:
            try:
                depth_raw, fetched_ms, raw_sha = self.adapter.fetch_orderbook_depth(symbol, limit=50)
                if not depth_raw or depth_raw.get("code") != "00000":
                    err = depth_raw.get("msg") if depth_raw else "No depth response"
                    self.record_failure(symbol, current_ms, f"depth_fetch_failed: {err}")
                    results["symbols"][symbol] = {"status": "source_failed", "error": err}
                    continue

                spread_bps, bid_depth, ask_depth, best_bid, best_ask, ok = self.adapter.parse_depth_metrics(depth_raw)
                if not ok:
                    self.record_failure(symbol, current_ms, "unparseable_or_crossed_depth")
                    results["symbols"][symbol] = {"status": "insufficient", "error": "crossed_or_empty_depth"}
                    continue

                ticker = tickers_by_symbol.get(symbol, {})
                vol_str = str(ticker.get("usdtVolume") or ticker.get("quoteVolume") or "0")
                quote_vol = Decimal(vol_str) if vol_str else Decimal("0")

                event_ms = int(depth_raw.get("requestTime") or (depth_raw.get("data") or {}).get("ts") or current_ms)

                assessment = self.policy.evaluate_metrics(
                    active=True,
                    spread_bps=spread_bps,
                    bid_depth_notional=bid_depth,
                    ask_depth_notional=ask_depth,
                    quote_volume_24h=quote_vol,
                    event_time_ms=event_ms,
                    fetched_at_ms=fetched_ms,
                    decision_time_ms=current_ms,
                    book_complete=True,
                )

                self.persist_universe_snapshot(
                    symbol=symbol,
                    assessment=assessment,
                    spread_bps=spread_bps,
                    bid_depth=bid_depth,
                    ask_depth=ask_depth,
                    quote_vol=quote_vol,
                    event_ms=event_ms,
                    fetched_ms=fetched_ms,
                    raw_sha=raw_sha,
                )
                results["symbols"][symbol] = {
                    "status": assessment.status,
                    "verified": assessment.verified,
                    "spread_bps": str(spread_bps),
                }

            except Exception as ex:
                logger.warning("Fehler beim Aktualisieren von %s: %s", symbol, ex)
                self.record_failure(symbol, current_ms, str(ex))
                results["symbols"][symbol] = {"status": "source_failed", "error": str(ex)}

        self.last_update_ms = current_ms
        return results

    def persist_contract_specs(self, specs: list[ContractSpec]) -> None:
        with self.conn:
            for s in specs:
                self.conn.execute(
                    "INSERT INTO instrument_specs "
                    "(symbol, source, product_type, symbol_type, symbol_status, base_coin, quote_coin, settle_coin, "
                    "price_tick, qty_step, min_qty, min_notional, maker_fee_rate, taker_fee_rate, max_leverage, "
                    "event_time_ms, fetched_at_ms, raw_snapshot_sha256) "
                    "VALUES (?, 'bitget_rest_v2', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'bitget_contracts_v2') "
                    "ON CONFLICT(symbol) DO UPDATE SET "
                    "symbol_status=excluded.symbol_status, price_tick=excluded.price_tick, qty_step=excluded.qty_step, "
                    "min_qty=excluded.min_qty, min_notional=excluded.min_notional, maker_fee_rate=excluded.maker_fee_rate, "
                    "taker_fee_rate=excluded.taker_fee_rate, max_leverage=excluded.max_leverage, "
                    "event_time_ms=excluded.event_time_ms, fetched_at_ms=excluded.fetched_at_ms",
                    (
                        s.symbol, s.product_type, s.symbol_type, s.symbol_status, s.base_coin, s.quote_coin,
                        s.settle_coin, str(s.price_tick), str(s.qty_step), str(s.min_qty), str(s.min_notional),
                        str(s.maker_fee_rate), str(s.taker_fee_rate), s.max_leverage, s.event_time_ms, s.fetched_at_ms,
                    ),
                )

    def persist_universe_snapshot(
        self,
        *,
        symbol: str,
        assessment: Any,
        spread_bps: Decimal,
        bid_depth: Decimal,
        ask_depth: Decimal,
        quote_vol: Decimal,
        event_ms: int,
        fetched_ms: int,
        raw_sha: str,
    ) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO universe "
                "(symbol, active, liquidity_verified, vol_24h, updated_at_ms, source, status, policy_version, "
                "event_time_ms, fetched_at_ms, reasons_json, spread_bps, bid_depth_notional, ask_depth_notional, "
                "quote_volume_24h, raw_snapshot_sha256) "
                "VALUES (?, 1, ?, ?, ?, 'bitget_rest_v2', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(symbol) DO UPDATE SET active=excluded.active, liquidity_verified=excluded.liquidity_verified, "
                "vol_24h=excluded.vol_24h, updated_at_ms=excluded.updated_at_ms, source=excluded.source, "
                "status=excluded.status, policy_version=excluded.policy_version, event_time_ms=excluded.event_time_ms, "
                "fetched_at_ms=excluded.fetched_at_ms, reasons_json=excluded.reasons_json, spread_bps=excluded.spread_bps, "
                "bid_depth_notional=excluded.bid_depth_notional, ask_depth_notional=excluded.ask_depth_notional, "
                "quote_volume_24h=excluded.quote_volume_24h, raw_snapshot_sha256=excluded.raw_snapshot_sha256",
                (
                    symbol,
                    int(assessment.verified),
                    float(quote_vol),
                    fetched_ms,
                    assessment.status,
                    POLICY_VERSION,
                    event_ms,
                    fetched_ms,
                    json.dumps(list(assessment.reasons)),
                    str(spread_bps),
                    str(bid_depth),
                    str(ask_depth),
                    str(quote_vol),
                    raw_sha or "sha256_uncalculated",
                ),
            )

    def record_failure(self, symbol: str, now_ms: int, reason: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO universe "
                "(symbol, active, liquidity_verified, updated_at_ms, source, status, policy_version, "
                "fetched_at_ms, reasons_json) VALUES (?, 0, 0, ?, 'bitget_rest_v2', 'source_failed', ?, ?, ?) "
                "ON CONFLICT(symbol) DO UPDATE SET liquidity_verified=0, status='source_failed', "
                "updated_at_ms=excluded.updated_at_ms, fetched_at_ms=excluded.fetched_at_ms, reasons_json=excluded.reasons_json",
                (symbol, now_ms, POLICY_VERSION, now_ms, json.dumps([reason])),
            )
