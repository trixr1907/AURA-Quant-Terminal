"""Unit and integration tests for MarketDataUpdater using offline fixtures."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

from aura.data.liquidity import POLICY_VERSION, LiquidityPolicy
from aura.data.market_updater import MarketDataUpdater
from aura.data.models import ContractSpec
from aura.store.db import connect

FIXTURE_PATH = Path("tests/fixtures/bitget_public_v2_20260917.json")


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_market_data_updater_offline_fixture_sync(tmp_path):
    conn = connect(tmp_path / "market_updater.db")
    fixture = _load_fixture()

    mock_adapter = MagicMock()
    mock_adapter.fetch_contract_specs.return_value = [
        ContractSpec(
            symbol="BTCUSDT",
            product_type="USDT-FUTURES",
            symbol_type="perpetual",
            symbol_status="normal",
            base_coin="BTC",
            quote_coin="USDT",
            settle_coin="USDT",
            price_tick=Decimal("0.1"),
            qty_step=Decimal("0.0001"),
            min_qty=Decimal("0.0001"),
            min_notional=Decimal("5"),
            maker_fee_rate=Decimal("0.0002"),
            taker_fee_rate=Decimal("0.0006"),
            max_leverage=125,
            event_time_ms=1789654627000,
            fetched_at_ms=1789654627000,
            raw_snapshot_sha256="sha_spec",
        )
    ]
    mock_adapter.fetch_all_tickers.return_value = (fixture["tickers"], 1789654627000, "sha_tickers")
    mock_adapter.fetch_orderbook_depth.return_value = (fixture["depths"]["BTCUSDT"], 1789654627000, "sha_depth")
    mock_adapter.parse_depth_metrics.return_value = (
        Decimal("0.013"),
        Decimal("958765.57"),
        Decimal("1432988.26"),
        Decimal("76755.4"),
        Decimal("76755.5"),
        True,
    )

    now_ms = 1789654627000
    updater = MarketDataUpdater(
        conn=conn,
        adapter=mock_adapter,
        policy=LiquidityPolicy(),
        symbols=["BTCUSDT"],
        min_interval_sec=30.0,
        time_provider=lambda: now_ms / 1000,
    )

    res = updater.update_cycle(force=True, now_ms=now_ms)
    assert res["updated"] is True
    assert res["symbols"]["BTCUSDT"]["status"] == "valid"
    assert res["symbols"]["BTCUSDT"]["verified"] is True

    # Check persistence
    row = conn.execute("SELECT * FROM universe WHERE symbol = 'BTCUSDT'").fetchone()
    assert row["active"] == 1
    assert row["liquidity_verified"] == 1
    assert row["status"] == "valid"
    assert row["policy_version"] == POLICY_VERSION
    assert row["source"] == "bitget_rest_v2"
    assert row["raw_snapshot_sha256"] == "sha_depth"
    assert Decimal(row["bid_depth_notional"]) == Decimal("958765.57")

    spec = conn.execute("SELECT * FROM instrument_specs WHERE symbol = 'BTCUSDT'").fetchone()
    assert spec["qty_step"] == "0.0001"
    assert spec["min_notional"] == "5"

    # Rate limiting on second immediate call
    second_res = updater.update_cycle(force=False, now_ms=now_ms + 1000)
    assert second_res["updated"] is False
    assert second_res["reason"] == "rate_limited_interval"


def test_market_data_updater_offline_network_failure_marks_source_failed(tmp_path):
    conn = connect(tmp_path / "failure.db")
    mock_adapter = MagicMock()
    mock_adapter.fetch_contract_specs.side_effect = ConnectionError("Network down")
    mock_adapter.fetch_all_tickers.return_value = (None, 1000, "")
    mock_adapter.fetch_orderbook_depth.return_value = (None, 1000, "")

    now_ms = 1_000_000
    updater = MarketDataUpdater(
        conn=conn,
        adapter=mock_adapter,
        symbols=["BTCUSDT"],
        time_provider=lambda: now_ms / 1000,
    )

    res = updater.update_cycle(force=True, now_ms=now_ms)
    assert res["updated"] is True
    assert res["symbols"]["BTCUSDT"]["status"] == "source_failed"

    row = conn.execute("SELECT status, liquidity_verified FROM universe WHERE symbol = 'BTCUSDT'").fetchone()
    assert row["status"] == "source_failed"
    assert row["liquidity_verified"] == 0


def test_market_data_updater_invalidates_removed_contract_specs(tmp_path):
    conn = connect(tmp_path / "delist.db")
    mock_adapter = MagicMock()
    now_ms = 1_000_000

    spec_btc = ContractSpec(
        symbol="BTCUSDT",
        product_type="USDT-FUTURES",
        symbol_type="perpetual",
        symbol_status="normal",
        base_coin="BTC",
        quote_coin="USDT",
        settle_coin="USDT",
        price_tick=Decimal("0.1"),
        qty_step=Decimal("0.0001"),
        min_qty=Decimal("0.0001"),
        min_notional=Decimal("5"),
        maker_fee_rate=Decimal("0.0002"),
        taker_fee_rate=Decimal("0.0006"),
        max_leverage=125,
        event_time_ms=now_ms,
        fetched_at_ms=now_ms,
        raw_snapshot_sha256="sha_spec",
    )
    spec_eth = ContractSpec(
        symbol="ETHUSDT",
        product_type="USDT-FUTURES",
        symbol_type="perpetual",
        symbol_status="normal",
        base_coin="ETH",
        quote_coin="USDT",
        settle_coin="USDT",
        price_tick=Decimal("0.01"),
        qty_step=Decimal("0.01"),
        min_qty=Decimal("0.01"),
        min_notional=Decimal("5"),
        maker_fee_rate=Decimal("0.0002"),
        taker_fee_rate=Decimal("0.0006"),
        max_leverage=100,
        event_time_ms=now_ms,
        fetched_at_ms=now_ms,
        raw_snapshot_sha256="sha_spec",
    )

    updater = MarketDataUpdater(
        conn=conn,
        adapter=mock_adapter,
        symbols=["BTCUSDT", "ETHUSDT"],
        time_provider=lambda: now_ms / 1000,
    )

    # Initial cycle persists both
    updater.persist_contract_specs([spec_btc, spec_eth])
    rows = conn.execute("SELECT symbol, symbol_status FROM instrument_specs ORDER BY symbol").fetchall()
    assert len(rows) == 2
    assert rows[0]["symbol_status"] == "normal"
    assert rows[1]["symbol_status"] == "normal"

    # Subsequent specs fetch returns only BTCUSDT (ETHUSDT delisted / missing)
    updater.persist_contract_specs([spec_btc])
    rows = conn.execute("SELECT symbol, symbol_status FROM instrument_specs ORDER BY symbol").fetchall()
    assert rows[0]["symbol"] == "BTCUSDT" and rows[0]["symbol_status"] == "normal"
    assert rows[1]["symbol"] == "ETHUSDT" and rows[1]["symbol_status"] == "delisted"

    eth_u = conn.execute("SELECT active, liquidity_verified, status FROM universe WHERE symbol = 'ETHUSDT'").fetchone()
    assert eth_u["active"] == 0
    assert eth_u["liquidity_verified"] == 0
    assert eth_u["status"] == "insufficient"


def test_updater_evaluates_fresh_clock_advancing_during_fetch(tmp_path):
    conn = connect(tmp_path / "advancing_clock.db")

    class AdvancingClock:
        def __init__(self, start_sec: float):
            self.current_sec = start_sec

        def time(self) -> float:
            return self.current_sec

        def advance(self, delta_sec: float):
            self.current_sec += delta_sec

    clock = AdvancingClock(1_000_000.0)
    spec_time_ms = int(clock.time() * 1000)

    spec = ContractSpec(
        symbol="BTCUSDT",
        product_type="USDT-FUTURES",
        symbol_type="perpetual",
        symbol_status="normal",
        base_coin="BTC",
        quote_coin="USDT",
        settle_coin="USDT",
        price_tick=Decimal("0.1"),
        qty_step=Decimal("0.0001"),
        min_qty=Decimal("0.0001"),
        min_notional=Decimal("5"),
        maker_fee_rate=Decimal("0.0002"),
        taker_fee_rate=Decimal("0.0006"),
        max_leverage=125,
        event_time_ms=spec_time_ms,
        fetched_at_ms=spec_time_ms,
        raw_snapshot_sha256="sha_spec",
    )

    mock_adapter = MagicMock()
    mock_adapter.fetch_contract_specs.return_value = [spec]

    def mock_fetch_tickers():
        t_ms = int(clock.time() * 1000)
        return (
            {
                "code": "00000",
                "data": [{"symbol": "BTCUSDT", "usdtVolume": "50000000", "ts": str(t_ms)}],
            },
            t_ms,
            "sha_tickers",
        )

    def mock_fetch_depth(symbol, limit=50):
        book_ts = int(clock.time() * 1000)
        clock.advance(130.0)
        fetch_finish_ms = int(clock.time() * 1000)
        return (
            {"code": "00000", "data": {"ts": str(book_ts)}},
            fetch_finish_ms,
            "sha_depth",
        )

    mock_adapter.fetch_all_tickers.side_effect = mock_fetch_tickers
    mock_adapter.fetch_orderbook_depth.side_effect = mock_fetch_depth
    mock_adapter.parse_depth_metrics.return_value = (
        Decimal("0.5"),
        Decimal("50000"),
        Decimal("50000"),
        Decimal("70000.0"),
        Decimal("70000.1"),
        True,
    )

    updater = MarketDataUpdater(
        conn=conn,
        adapter=mock_adapter,
        policy=LiquidityPolicy(),
        symbols=["BTCUSDT"],
        time_provider=clock.time,
    )

    res = updater.update_cycle(force=True)
    assert res["updated"] is True
    assert res["symbols"]["BTCUSDT"]["status"] == "stale"
    assert res["symbols"]["BTCUSDT"]["verified"] is False
    assert "STALE_BOOK_EVENT_TIME" in res["symbols"]["BTCUSDT"]["reasons"]

    row = conn.execute("SELECT active, liquidity_verified, status, reasons_json FROM universe WHERE symbol = 'BTCUSDT'").fetchone()
    assert row["liquidity_verified"] == 0
    assert row["status"] == "stale"
    assert "STALE_BOOK_EVENT_TIME" in row["reasons_json"]
