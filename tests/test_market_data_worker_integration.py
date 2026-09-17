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
    assert worker._liquidity_is_verified("BTCUSDT", 1_000_000, planned_notional="10000", direction=1) is True
    assert worker._liquidity_is_verified("BTCUSDT", 1_000_000, planned_notional="10000.01", direction=1) is False


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
