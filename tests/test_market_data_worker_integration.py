"""Offline persistence, worker-gate, and API tests for market data."""
from __future__ import annotations

from fastapi.testclient import TestClient

from aura.api.app import create_app
from aura.data.liquidity import POLICY_VERSION
from aura.runner.worker import AuraWorkerService


def _seed(worker: AuraWorkerService, now_ms: int, *, verified: bool = True) -> None:
    worker.persist_test_market_snapshot(
        symbol="BTCUSDT",
        now_ms=now_ms,
        price_tick="0.1",
        qty_step="0.0001",
        min_qty="0.0001",
        min_notional="5",
        spread_bps="5" if verified else "11",
        bid_depth_notional="100000",
        ask_depth_notional="100000",
        quote_volume_24h="100000000",
    )


def test_empty_db_starts_fail_closed_and_source_failure_cannot_preserve_old_go(tmp_path):
    now_ms = 1_000_000
    worker = AuraWorkerService(db_path=str(tmp_path / "market.db"), symbols=["BTCUSDT"], time_provider=lambda: now_ms / 1000)
    assert worker._liquidity_is_verified("BTCUSDT", now_ms, planned_notional="100", direction=1) is False

    _seed(worker, now_ms)
    assert worker._liquidity_is_verified("BTCUSDT", now_ms, planned_notional="100", direction=1) is True

    worker.record_market_source_failure(["BTCUSDT"], now_ms + 1_000, "TIMEOUT")
    assert worker._liquidity_is_verified("BTCUSDT", now_ms + 1_000, planned_notional="100", direction=1) is False


def test_fresh_positive_expires_and_restart_rechecks_wall_clock(tmp_path):
    path = tmp_path / "restart.db"
    first = AuraWorkerService(db_path=str(path), symbols=["BTCUSDT"], time_provider=lambda: 1000)
    _seed(first, 1_000_000)

    restarted = AuraWorkerService(db_path=str(path), symbols=["BTCUSDT"], time_provider=lambda: 1121)
    assert restarted._liquidity_is_verified("BTCUSDT", 1_121_000, planned_notional="100", direction=-1) is False


def test_source_return_requires_actual_new_validation(tmp_path):
    worker = AuraWorkerService(db_path=str(tmp_path / "return.db"), symbols=["BTCUSDT"], time_provider=lambda: 1000)
    _seed(worker, 1_000_000)
    worker.record_market_source_failure(["BTCUSDT"], 1_001_000, "HTTP_429")
    assert worker._liquidity_is_verified("BTCUSDT", 1_002_000, planned_notional="100", direction=1) is False

    _seed(worker, 1_003_000)
    assert worker._liquidity_is_verified("BTCUSDT", 1_003_000, planned_notional="100", direction=1) is True


def test_execution_notional_is_bounded_by_relevant_side_depth(tmp_path):
    worker = AuraWorkerService(db_path=str(tmp_path / "depth.db"), symbols=["BTCUSDT"], time_provider=lambda: 1000)
    _seed(worker, 1_000_000)
    # ask_depth is 100,000 USDT -> 5% threshold is 5,000 USDT
    assert worker._liquidity_is_verified("BTCUSDT", 1_000_000, planned_notional="5000", direction=1) is True
    assert worker._liquidity_is_verified("BTCUSDT", 1_000_000, planned_notional="5000.01", direction=1) is False


def test_api_exposes_explainable_liquidity_status(tmp_path, monkeypatch):
    import time
    monkeypatch.setenv("AURA_RELAY_TOKEN", "test-token")
    path = tmp_path / "api.db"
    now_ms = int(time.time() * 1000)
    worker = AuraWorkerService(db_path=str(path), symbols=["BTCUSDT"], time_provider=lambda: now_ms / 1000)
    _seed(worker, now_ms)
    app = create_app(db_path=str(path))
    client = TestClient(app, headers={"X-AURA-TOKEN": "test-token"})

    payload = client.get("/api/v3/state").json()
    market = payload["market_data"]
    assert market["source"] == "bitget_rest_v2"
    assert market["policy_version"] == POLICY_VERSION
    assert market["status"] == "valid"
    assert market["symbols"][0]["criteria"]["spread_bps"] == "5"
    assert market["symbols"][0]["reasons"] == []


def test_spec_delisting_or_inactivity_blocks_worker(tmp_path):
    now_ms = 1_000_000
    worker = AuraWorkerService(db_path=str(tmp_path / "delist.db"), symbols=["BTCUSDT"], time_provider=lambda: now_ms / 1000)
    _seed(worker, now_ms)
    assert worker._liquidity_is_verified("BTCUSDT", now_ms, planned_notional="100", direction=1) is True

    # Mark spec delisted in db
    worker.conn.execute("UPDATE instrument_specs SET symbol_status = 'delisted' WHERE symbol = 'BTCUSDT'")
    assert worker._liquidity_is_verified("BTCUSDT", now_ms, planned_notional="100", direction=1) is False


def test_independent_stale_timestamps_block_worker_gate(tmp_path):
    now_ms = 1_000_000
    worker = AuraWorkerService(db_path=str(tmp_path / "ts.db"), symbols=["BTCUSDT"], time_provider=lambda: now_ms / 1000)

    # 1. Stale ticker
    worker.persist_test_market_snapshot(
        symbol="BTCUSDT",
        now_ms=now_ms,
        price_tick="0.1",
        qty_step="0.0001",
        min_qty="0.0001",
        min_notional="5",
        spread_bps="5",
        bid_depth_notional="100000",
        ask_depth_notional="100000",
        quote_volume_24h="100000000",
        book_event_time_ms=now_ms - 1000,
        book_fetched_at_ms=now_ms - 1000,
        ticker_event_time_ms=now_ms - 125_000,  # >120s stale
        ticker_fetched_at_ms=now_ms - 1000,
    )
    assert worker._liquidity_is_verified("BTCUSDT", now_ms, planned_notional="100", direction=1) is False

    # 2. Stale book
    worker.persist_test_market_snapshot(
        symbol="BTCUSDT",
        now_ms=now_ms,
        price_tick="0.1",
        qty_step="0.0001",
        min_qty="0.0001",
        min_notional="5",
        spread_bps="5",
        bid_depth_notional="100000",
        ask_depth_notional="100000",
        quote_volume_24h="100000000",
        book_event_time_ms=now_ms - 125_000,  # >120s stale
        book_fetched_at_ms=now_ms - 1000,
        ticker_event_time_ms=now_ms - 1000,
        ticker_fetched_at_ms=now_ms - 1000,
    )
    assert worker._liquidity_is_verified("BTCUSDT", now_ms, planned_notional="100", direction=1) is False

    # 3. Stale spec (>24h)
    worker.persist_test_market_snapshot(
        symbol="BTCUSDT",
        now_ms=now_ms,
        price_tick="0.1",
        qty_step="0.0001",
        min_qty="0.0001",
        min_notional="5",
        spread_bps="5",
        bid_depth_notional="100000",
        ask_depth_notional="100000",
        quote_volume_24h="100000000",
        book_event_time_ms=now_ms - 1000,
        book_fetched_at_ms=now_ms - 1000,
        ticker_event_time_ms=now_ms - 1000,
        ticker_fetched_at_ms=now_ms - 1000,
        spec_fetched_at_ms=now_ms - 86_405_000,  # >24h stale
    )
    assert worker._liquidity_is_verified("BTCUSDT", now_ms, planned_notional="100", direction=1) is False


def test_end_to_end_adapter_updater_worker_pipeline(tmp_path):
    from unittest.mock import MagicMock
    from decimal import Decimal
    from aura.data.market_updater import MarketDataUpdater
    from aura.data.models import ContractSpec, Candle
    from aura.data.liquidity import LiquidityPolicy

    db_file = tmp_path / "pipeline.db"
    now_ms = 1_000_000
    mock_adapter = MagicMock()

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
        event_time_ms=now_ms - 1000,
        fetched_at_ms=now_ms - 1000,
        raw_snapshot_sha256="sha_spec",
    )

    mock_adapter.fetch_contract_specs.return_value = [spec]
    mock_adapter.fetch_all_tickers.return_value = (
        {
            "code": "00000",
            "data": [{"symbol": "BTCUSDT", "usdtVolume": "50000000", "ts": str(now_ms - 1000)}],
        },
        now_ms - 1000,
        "sha_tickers",
    )
    mock_adapter.fetch_orderbook_depth.return_value = (
        {"code": "00000", "data": {"ts": str(now_ms - 1000)}},
        now_ms - 1000,
        "sha_depth",
    )
    mock_adapter.parse_depth_metrics.return_value = (
        Decimal("0.5"),  # 0.5 bps spread
        Decimal("50000"),  # 50k USDT bid depth (5% is 2.5k)
        Decimal("50000"),  # 50k USDT ask depth
        Decimal("70000.0"),
        Decimal("70000.1"),
        True,
    )

    worker = AuraWorkerService(
        db_path=str(db_file),
        symbols=["BTCUSDT"],
        time_provider=lambda: now_ms / 1000,
    )

    updater = MarketDataUpdater(
        conn=worker.conn,
        adapter=mock_adapter,
        policy=LiquidityPolicy(),
        symbols=["BTCUSDT"],
        time_provider=lambda: now_ms / 1000,
    )

    # Run updater cycle
    update_res = updater.update_cycle(force=True, now_ms=now_ms)
    assert update_res["updated"] is True
    assert update_res["symbols"]["BTCUSDT"]["status"] == "valid"

    # Worker gate check for sizing
    # Sizing of 2500 USDT (<= 5% of 50k) is allowed
    assert worker._liquidity_is_verified("BTCUSDT", now_ms, planned_notional="2500", direction=1) is True
    # Sizing of 2501 USDT (> 5% of 50k) is rejected
    assert worker._liquidity_is_verified("BTCUSDT", now_ms, planned_notional="2501", direction=1) is False

    # Simulate market source failure in subsequent cycle
    mock_adapter.fetch_orderbook_depth.return_value = ({"code": "40001", "msg": "API error"}, now_ms + 35_000, "")
    updater.update_cycle(force=True, now_ms=now_ms + 35_000)

    # Worker gate must immediately reject
    assert worker._liquidity_is_verified("BTCUSDT", now_ms + 35_000, planned_notional="2500", direction=1) is False


def test_legacy_policy_snapshot_without_separate_timestamps_is_rejected_at_worker_gate(tmp_path):
    now_ms = 1_000_000_000
    worker = AuraWorkerService(db_path=str(tmp_path / "legacy.db"), symbols=["BTCUSDT"], time_provider=lambda: now_ms / 1000)
    _seed(worker, now_ms)
    assert worker._liquidity_is_verified("BTCUSDT", now_ms, planned_notional="100", direction=1) is True

    # Invalidate separate timestamps and policy version (legacy v1 snapshot)
    worker.conn.execute(
        "UPDATE universe SET book_event_time_ms=NULL, book_fetched_at_ms=NULL, "
        "ticker_event_time_ms=NULL, ticker_fetched_at_ms=NULL, policy_version='aura-liquidity-v1'"
    )
    # Must be rejected fail-closed
    assert worker._liquidity_is_verified("BTCUSDT", now_ms, planned_notional="100", direction=1) is False


def test_real_worker_entry_path_enforces_price_tick_and_level_ordering(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import patch
    from decimal import Decimal
    from aura.data.models import Candle

    now_ms = 1_000_000_000
    w = AuraWorkerService(db_path=str(tmp_path / "tick.db"), symbols=["BTCUSDT"], time_provider=lambda: now_ms / 1000)
    _seed(w, now_ms)
    w.conn.execute("UPDATE instrument_specs SET price_tick='10' WHERE symbol='BTCUSDT'")

    c = Candle(time_ms=now_ms - 3600000, open=139.1, high=140.0, low=138.0, close=139.37, volume=100.0, is_closed=True)
    with patch("aura.runner.worker.analyze_candles", return_value=SimpleNamespace(score=[90], atr=[1.23])):
        p = w._evaluate_and_enter("BTCUSDT", [c], pending_alerts=[])

    assert p is not None
    # All levels must be exact multiples of price_tick=10
    assert Decimal(str(p.entry_price)) % Decimal("10") == 0
    assert Decimal(str(p.sl_price)) % Decimal("10") == 0
    assert Decimal(str(p.tp1_price)) % Decimal("10") == 0
    assert Decimal(str(p.tp2_price)) % Decimal("10") == 0

    # Strict ordering: sl < entry < tp1 <= tp2
    assert p.sl_price < p.entry_price < p.tp1_price <= p.tp2_price
    # Non-zero positive stop distance
    assert p.entry_price - p.sl_price > 0
    w.conn.close()


def test_coarse_price_tick_collapsing_levels_rejects_trade(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import patch
    from aura.data.models import Candle

    now_ms = 1_000_000_000
    w = AuraWorkerService(db_path=str(tmp_path / "coarse_tick.db"), symbols=["BTCUSDT"], time_provider=lambda: now_ms / 1000)
    _seed(w, now_ms)
    # Set price_tick = 50 (too coarse for asset price 139 with ATR 1.23, so SL/TP levels collapse)
    w.conn.execute("UPDATE instrument_specs SET price_tick='50' WHERE symbol='BTCUSDT'")

    c = Candle(time_ms=now_ms - 3600000, open=139.1, high=140.0, low=138.0, close=139.37, volume=100.0, is_closed=True)
    with patch("aura.runner.worker.analyze_candles", return_value=SimpleNamespace(score=[90], atr=[1.23])):
        p = w._evaluate_and_enter("BTCUSDT", [c], pending_alerts=[])

    # Must be safely rejected, not opening a collapsed setup
    assert p is None
    w.conn.close()
