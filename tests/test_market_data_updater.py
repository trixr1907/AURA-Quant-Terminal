"""Unit and integration tests for MarketDataUpdater using offline fixtures."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

from aura.data.liquidity import POLICY_VERSION, LiquidityPolicy
from aura.data.market_updater import MarketDataUpdater
from aura.store.db import connect

FIXTURE_PATH = Path("tests/fixtures/bitget_public_v2_20260917.json")


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_market_data_updater_offline_fixture_sync(tmp_path):
    conn = connect(tmp_path / "market_updater.db")
    fixture = _load_fixture()

    mock_adapter = MagicMock()
    mock_adapter.fetch_contract_specs.return_value = [
        MagicMock(
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
