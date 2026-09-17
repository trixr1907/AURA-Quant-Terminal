"""Market data updater for Bitget USDT-FUTURES instruments and order books."""
from __future__ import annotations

import hashlib
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
        self.last_specs_error: str | None = None

    def update_cycle(self, *, force: bool = False, now_ms: int | None = None) -> dict[str, Any]:
        """Runs one update cycle if interval elapsed or forced."""
        cycle_start_ms = now_ms if now_ms is not None else int(self.time_provider() * 1000)
        if not force and (cycle_start_ms - self.last_update_ms) < int(self.min_interval_sec * 1000):
            return {"updated": False, "reason": "rate_limited_interval"}

        results: dict[str, Any] = {"updated": True, "symbols": {}}
        self.last_specs_error = None

        # 1. Fetch and persist contract specs
        specs: list[ContractSpec] = []
        try:
            specs = self.adapter.fetch_contract_specs()
            if specs:
                raw_sha = getattr(specs[0], "raw_snapshot_sha256", "")
                self.persist_contract_specs(specs, raw_sha256=raw_sha)
                results["contracts_count"] = len(specs)
            else:
                self.last_specs_error = "empty_or_invalid_specs_response"
                results["specs_error"] = self.last_specs_error
        except Exception as ex:
            logger.warning("Fehler beim Abruf von Kontraktspezifikationen: %s", ex)
            self.last_specs_error = str(ex)
            results["specs_error"] = str(ex)

        # 2. Fetch tickers for 24h quote volume and ticker timestamps
        tickers_by_symbol: dict[str, dict[str, Any]] = {}
        tickers_fetched_ms = int(self.time_provider() * 1000)
        try:
            tickers_raw, fetched_ms, _ = self.adapter.fetch_all_tickers()
            tickers_fetched_ms = fetched_ms
            if tickers_raw is not None and isinstance(tickers_raw, dict) and tickers_raw.get("code") == "00000" and isinstance(tickers_raw.get("data"), list):
                for t in tickers_raw["data"]:
                    sym = t.get("symbol")
                    if sym:
                        tickers_by_symbol[sym] = t
            else:
                err_msg = tickers_raw.get("msg") if isinstance(tickers_raw, dict) else "no_ticker_response"
                results["tickers_error"] = err_msg
        except Exception as ex:
            logger.warning("Fehler beim Abruf von Tickers: %s", ex)
            results["tickers_error"] = str(ex)

        # 3. For configured symbols, fetch orderbook depth and evaluate liquidity
        for symbol in self.symbols:
            spec_check_ms = int(self.time_provider() * 1000)

            # Check instrument spec in database for this symbol
            spec_row = self.conn.execute(
                "SELECT symbol_status, symbol_type, quote_coin, settle_coin, fetched_at_ms "
                "FROM instrument_specs WHERE symbol = ?",
                (symbol,),
            ).fetchone()

            if spec_row is None:
                self.record_failure(symbol, spec_check_ms, "missing_instrument_spec")
                results["symbols"][symbol] = {"status": "source_failed", "error": "missing_instrument_spec"}
                continue

            spec_active = spec_row["symbol_status"] == "normal" and spec_row["symbol_type"] == "perpetual"
            spec_age = spec_check_ms - int(spec_row["fetched_at_ms"])
            spec_stale = spec_age > self.policy.spec_max_age_ms

            if not spec_active:
                self.record_failure(symbol, spec_check_ms, f"instrument_not_active:{spec_row['symbol_status']}")
                results["symbols"][symbol] = {"status": "insufficient", "error": "instrument_not_active"}
                continue

            if spec_stale:
                self.record_failure(symbol, spec_check_ms, f"instrument_spec_stale:{spec_age}ms")
                results["symbols"][symbol] = {"status": "stale", "error": f"instrument_spec_stale_{spec_age}ms"}
                continue

            try:
                depth_raw, depth_fetched_ms, raw_sha = self.adapter.fetch_orderbook_depth(symbol, limit=50)
                eval_time_ms = int(self.time_provider() * 1000)
                if not depth_raw or depth_raw.get("code") != "00000":
                    err = depth_raw.get("msg") if depth_raw else "no_depth_response"
                    self.record_failure(symbol, eval_time_ms, f"depth_fetch_failed:{err}")
                    results["symbols"][symbol] = {"status": "source_failed", "error": err}
                    continue

                spread_bps, bid_depth, ask_depth, best_bid, best_ask, ok = self.adapter.parse_depth_metrics(
                    depth_raw, max_depth_band_bps=self.policy.depth_band_bps
                )
                if not ok:
                    self.record_failure(symbol, eval_time_ms, "unparseable_or_crossed_depth")
                    results["symbols"][symbol] = {"status": "insufficient", "error": "crossed_or_empty_depth"}
                    continue

                # Extract and strictly validate order book event timestamp (must come from data.ts, not requestTime)
                depth_data = depth_raw.get("data") if isinstance(depth_raw.get("data"), dict) else {}
                book_ts_raw = depth_data.get("ts")
                if book_ts_raw is None or str(book_ts_raw).strip() == "":
                    self.record_failure(symbol, eval_time_ms, "book_timestamp_missing")
                    results["symbols"][symbol] = {"status": "source_failed", "error": "book_timestamp_missing"}
                    continue
                try:
                    book_event_ms = int(book_ts_raw)
                except (ValueError, TypeError):
                    self.record_failure(symbol, eval_time_ms, "book_timestamp_invalid")
                    results["symbols"][symbol] = {"status": "source_failed", "error": "book_timestamp_invalid"}
                    continue

                # Extract and strictly validate ticker volume and event timestamp
                ticker = tickers_by_symbol.get(symbol)
                if not ticker:
                    self.record_failure(symbol, eval_time_ms, "ticker_missing")
                    results["symbols"][symbol] = {"status": "source_failed", "error": "ticker_missing"}
                    continue

                ticker_ts_raw = ticker.get("ts")
                if ticker_ts_raw is None or str(ticker_ts_raw).strip() == "":
                    self.record_failure(symbol, eval_time_ms, "ticker_timestamp_missing")
                    results["symbols"][symbol] = {"status": "source_failed", "error": "ticker_timestamp_missing"}
                    continue
                try:
                    ticker_event_ms = int(ticker_ts_raw)
                except (ValueError, TypeError):
                    self.record_failure(symbol, eval_time_ms, "ticker_timestamp_invalid")
                    results["symbols"][symbol] = {"status": "source_failed", "error": "ticker_timestamp_invalid"}
                    continue

                vol_str = str(ticker.get("usdtVolume") or ticker.get("quoteVolume") or "0")
                quote_vol = Decimal(vol_str) if vol_str else Decimal("0")

                assessment = self.policy.evaluate_metrics(
                    active=True,
                    spread_bps=spread_bps,
                    bid_depth_notional=bid_depth,
                    ask_depth_notional=ask_depth,
                    quote_volume_24h=quote_vol,
                    book_event_time_ms=book_event_ms,
                    book_fetched_at_ms=depth_fetched_ms,
                    ticker_event_time_ms=ticker_event_ms,
                    ticker_fetched_at_ms=tickers_fetched_ms,
                    spec_fetched_at_ms=int(spec_row["fetched_at_ms"]),
                    decision_time_ms=eval_time_ms,
                    book_complete=True,
                )

                self.persist_universe_snapshot(
                    symbol=symbol,
                    assessment=assessment,
                    spread_bps=spread_bps,
                    bid_depth=bid_depth,
                    ask_depth=ask_depth,
                    quote_vol=quote_vol,
                    book_event_ms=book_event_ms,
                    book_fetched_ms=depth_fetched_ms,
                    ticker_event_ms=ticker_event_ms,
                    ticker_fetched_ms=tickers_fetched_ms,
                    raw_sha=raw_sha,
                )
                results["symbols"][symbol] = {
                    "status": assessment.status,
                    "verified": assessment.verified,
                    "spread_bps": str(spread_bps),
                    "reasons": list(assessment.reasons),
                }

            except Exception as ex:
                err_time_ms = int(self.time_provider() * 1000)
                logger.warning("Fehler beim Aktualisieren von %s: %s", symbol, ex)
                self.record_failure(symbol, err_time_ms, str(ex))
                results["symbols"][symbol] = {"status": "source_failed", "error": str(ex)}

        self.last_update_ms = cycle_start_ms
        return results

    def persist_contract_specs(self, specs: list[ContractSpec], raw_sha256: str = "") -> None:
        if not specs:
            return
        active_symbols = set()
        with self.conn:
            for s in specs:
                sha = raw_sha256 or s.raw_snapshot_sha256 or "sha256_uncalculated"
                if s.symbol_status == "normal":
                    active_symbols.add(s.symbol)
                self.conn.execute(
                    "INSERT INTO instrument_specs "
                    "(symbol, source, product_type, symbol_type, symbol_status, base_coin, quote_coin, settle_coin, "
                    "price_tick, qty_step, min_qty, min_notional, maker_fee_rate, taker_fee_rate, max_leverage, "
                    "event_time_ms, fetched_at_ms, raw_snapshot_sha256) "
                    "VALUES (?, 'bitget_rest_v2', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(symbol) DO UPDATE SET "
                    "symbol_status=excluded.symbol_status, price_tick=excluded.price_tick, qty_step=excluded.qty_step, "
                    "min_qty=excluded.min_qty, min_notional=excluded.min_notional, maker_fee_rate=excluded.maker_fee_rate, "
                    "taker_fee_rate=excluded.taker_fee_rate, max_leverage=excluded.max_leverage, "
                    "event_time_ms=excluded.event_time_ms, fetched_at_ms=excluded.fetched_at_ms, "
                    "raw_snapshot_sha256=excluded.raw_snapshot_sha256",
                    (
                        s.symbol, s.product_type, s.symbol_type, s.symbol_status, s.base_coin, s.quote_coin,
                        s.settle_coin, str(s.price_tick), str(s.qty_step), str(s.min_qty), str(s.min_notional),
                        str(s.maker_fee_rate), str(s.taker_fee_rate), s.max_leverage, s.event_time_ms, s.fetched_at_ms,
                        sha,
                    ),
                )

            # Mark removed or inactive contracts in existing instrument_specs
            rows = self.conn.execute("SELECT symbol FROM instrument_specs").fetchall()
            now_ms = int(self.time_provider() * 1000)
            for r in rows:
                sym = r["symbol"]
                if sym not in active_symbols:
                    self.conn.execute(
                        "UPDATE instrument_specs SET symbol_status = 'delisted' WHERE symbol = ?",
                        (sym,),
                    )
                    self.conn.execute(
                        "INSERT INTO universe (symbol, active, liquidity_verified, updated_at_ms, status, reasons_json) "
                        "VALUES (?, 0, 0, ?, 'insufficient', ?) "
                        "ON CONFLICT(symbol) DO UPDATE SET active = 0, liquidity_verified = 0, updated_at_ms = excluded.updated_at_ms, "
                        "status = 'insufficient', reasons_json = excluded.reasons_json",
                        (sym, now_ms, json.dumps(["INSTRUMENT_NOT_ACTIVE"])),
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
        book_event_ms: int,
        book_fetched_ms: int,
        ticker_event_ms: int,
        ticker_fetched_ms: int,
        raw_sha: str,
    ) -> None:
        overall_event_ms = min(book_event_ms, ticker_event_ms)
        overall_fetched_ms = min(book_fetched_ms, ticker_fetched_ms)
        with self.conn:
            self.conn.execute(
                "INSERT INTO universe "
                "(symbol, active, liquidity_verified, vol_24h, updated_at_ms, source, status, policy_version, "
                "event_time_ms, fetched_at_ms, book_event_time_ms, book_fetched_at_ms, ticker_event_time_ms, "
                "ticker_fetched_at_ms, reasons_json, spread_bps, bid_depth_notional, ask_depth_notional, "
                "quote_volume_24h, raw_snapshot_sha256) "
                "VALUES (?, 1, ?, ?, ?, 'bitget_rest_v2', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(symbol) DO UPDATE SET active=excluded.active, liquidity_verified=excluded.liquidity_verified, "
                "vol_24h=excluded.vol_24h, updated_at_ms=excluded.updated_at_ms, source=excluded.source, "
                "status=excluded.status, policy_version=excluded.policy_version, event_time_ms=excluded.event_time_ms, "
                "fetched_at_ms=excluded.fetched_at_ms, book_event_time_ms=excluded.book_event_time_ms, "
                "book_fetched_at_ms=excluded.book_fetched_at_ms, ticker_event_time_ms=excluded.ticker_event_time_ms, "
                "ticker_fetched_at_ms=excluded.ticker_fetched_at_ms, reasons_json=excluded.reasons_json, "
                "spread_bps=excluded.spread_bps, bid_depth_notional=excluded.bid_depth_notional, "
                "ask_depth_notional=excluded.ask_depth_notional, quote_volume_24h=excluded.quote_volume_24h, "
                "raw_snapshot_sha256=excluded.raw_snapshot_sha256",
                (
                    symbol,
                    int(assessment.verified),
                    float(quote_vol),
                    overall_fetched_ms,
                    assessment.status,
                    POLICY_VERSION,
                    overall_event_ms,
                    overall_fetched_ms,
                    book_event_ms,
                    book_fetched_ms,
                    ticker_event_ms,
                    ticker_fetched_ms,
                    json.dumps(list(assessment.reasons)),
                    str(spread_bps),
                    str(bid_depth),
                    str(ask_depth),
                    str(quote_vol),
                    raw_sha or "sha256_uncalculated",
                ),
            )

    def record_failure(self, symbol: str, now_ms: int, reason: str) -> None:
        status_val = "stale" if "stale" in reason.lower() else "source_failed"
        with self.conn:
            self.conn.execute(
                "INSERT INTO universe "
                "(symbol, active, liquidity_verified, updated_at_ms, source, status, policy_version, "
                "fetched_at_ms, reasons_json) VALUES (?, 0, 0, ?, 'bitget_rest_v2', ?, ?, ?, ?) "
                "ON CONFLICT(symbol) DO UPDATE SET liquidity_verified=0, status=excluded.status, "
                "updated_at_ms=excluded.updated_at_ms, fetched_at_ms=excluded.fetched_at_ms, "
                "reasons_json=excluded.reasons_json",
                (symbol, now_ms, status_val, POLICY_VERSION, now_ms, json.dumps([reason])),
            )
