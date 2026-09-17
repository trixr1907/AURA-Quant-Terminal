"""Kritischer vertikaler Integrationstest fuer AURA v3 (P3, Mandat §3).

Beweist den vollstaendigen vertikalen Ablauf:
Replay-Marktdaten -> Normalisierung -> Strategie-Analyse -> Risk-Gates ->
Paper-Entry -> TP1 (50% Partial Close & Breakeven) -> TP2 (Full Close) ->
Accounting-Reconciliation -> SQLite-Persistenz -> API-State -> Notification Dispatch.
"""

from __future__ import annotations

import sqlite3
import tempfile
import time
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from aura.api.app import create_app
from aura.core.risk import round_price_to_tick
from aura.core.scoring import analyze_candles
from aura.data.bitget_adapter import BitgetMarketAdapter
from aura.data.models import Candle
from aura.runner.paper_engine import EngineConfig, PaperTradingEngine
from aura.runner.state_machine import RunnerStateMachine, SystemState
from aura.runner.worker import AuraWorkerService
from aura.store.db import connect, migrate


def _seed_verified_market_data(worker: AuraWorkerService, symbol: str, now_ms: int) -> None:
    worker.persist_test_market_snapshot(
        symbol=symbol,
        now_ms=now_ms,
        price_tick="0.1",
        qty_step="0.0001",
        min_qty="0.0001",
        min_notional="5",
        spread_bps="5",
        bid_depth_notional="5000000",
        ask_depth_notional="5000000",
        quote_volume_24h="100000000",
    )

_TEST_TOKEN = "test-vertical-integration-token"


def _make_authenticated_client(app) -> TestClient:
    """Erstellt einen TestClient mit dem aktuell konfigurierten AURA_RELAY_TOKEN."""
    import os
    token = os.environ.get("AURA_RELAY_TOKEN", _TEST_TOKEN)
    client = TestClient(app)
    # Auth-Header auf Client-Ebene setzen (TestClient teilt keine Cookies zwischen Requests)
    client.headers.update({"X-AURA-TOKEN": token})
    return client


@pytest.fixture(autouse=True)
def _set_test_token_env(monkeypatch):
    """Setzt den Test-Token fuer alle Vertikal-Integration-Tests."""
    monkeypatch.setenv("AURA_RELAY_TOKEN", _TEST_TOKEN)


def generate_synthetic_bullish_trend(
    num_bars: int = 60, start_price: float = 60000.0, end_time_ms: int | None = None
) -> list[Candle]:
    """Generiert eine synthetische, deterministische bullische Kerzenfolge."""
    candles = []
    price = start_price
    if end_time_ms is None:
        end_time_ms = int(time.time() * 1000)
    start_time_ms = end_time_ms - num_bars * 3600000

    for i in range(num_bars):
        t = start_time_ms + i * 3600000
        step = 50.0 + (i * 5.0)
        open_p = price
        close_p = open_p + step
        high_p = close_p + 30.0
        low_p = open_p - 15.0
        vol = 100.0 + (i * 2.0)
        price = close_p

        candles.append(
            Candle(
                time_ms=t,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=vol,
            )
        )
    return candles


class TestVerticalIntegration:
    def test_full_vertical_trade_lifecycle_and_accounting(self):
        """Vollstaendiger Durchstich: Signal -> Entry -> TP1 (50%) -> TP2 -> Accounting -> SQLite -> API."""
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            db_path = tmp.name
            conn = connect(db_path)
            migrate(conn)

            now_sim = time.time()
            worker = AuraWorkerService(
                db_path=db_path,
                poll_interval_sec=1,
                symbols=["BTCUSDT"],
                time_provider=lambda: now_sim,
            )
            assert worker.sm.can_open_new_trades() is False

            # Initialisiere Worker auf RUNNING
            worker.sm.transition_to(SystemState.WARMING_UP, "Warmup")
            worker.sm.transition_to(SystemState.RUNNING, "Ready")
            assert worker.sm.can_open_new_trades() is True

            # Mocke Adapter mit bullischer Trend-Kerzenreihe
            initial_candles = generate_synthetic_bullish_trend(num_bars=50, start_price=50000.0)
            now_sim = initial_candles[-1].time_ms / 1000 + 3600
            worker.adapter.fetch_candles = MagicMock(return_value=(initial_candles, MagicMock(is_valid=True)))

            # Mocke Notifier
            worker.notifier.send_alert = MagicMock(return_value=True)
            _seed_verified_market_data(worker, "BTCUSDT", int(now_sim * 1000))

            # 1. Zyklus: Scanner erkennt bullisches Signal und eroeffnet Long-Position
            worker._run_cycle(1)

            assert len(worker.engine.open_positions) == 1
            pos = list(worker.engine.open_positions.values())[0]
            assert pos.symbol == "BTCUSDT"
            assert pos.direction == 1
            assert pos.status == "open"
            assert pos.tp1_hit is False
            expected_fill = float(round_price_to_tick(Decimal(str(initial_candles[-1].close * (1.0 + 1.5 / 10000.0))), Decimal("0.1")))
            assert abs(pos.entry_price - expected_fill) < 1e-4
            entry_price = pos.entry_price
            tp1_target = pos.tp1_price
            tp2_target = pos.tp2_price
            initial_qty = pos.initial_qty
            assert initial_qty > 0

            # Pruefe Benachrichtigung fuer Entry
            assert worker.notifier.send_alert.called
            entry_alert_call = worker.notifier.send_alert.call_args_list[0]
            assert "Neuer Trade" in entry_alert_call[1]["title"]
            assert entry_alert_call[1]["event_type"] == "TRADE_OPEN"

            # 2. Zyklus: Kerzen steigen ueber TP1 -> TP1-Hit -> 50% Partial Close & SL-Move auf Entry (Breakeven)
            tp1_bar = Candle(
                time_ms=initial_candles[-1].time_ms + 3600000,
                open=entry_price + 10.0,
                high=tp1_target + 50.0,  # Beruehrt TP1
                low=entry_price + 5.0,
                close=tp1_target + 20.0,
                volume=150.0,
            )
            now_sim = tp1_bar.time_ms / 1000 + 3600
            worker.adapter.fetch_candles = MagicMock(return_value=(initial_candles + [tp1_bar], MagicMock(is_valid=True)))
            worker._run_cycle(2)

            pos_tp1 = list(worker.engine.open_positions.values())[0]
            assert pos_tp1.tp1_hit is True
            assert pos_tp1.status == "partial_tp1"
            assert pos_tp1.qty == initial_qty * 0.5  # Exakt 50% verbleibend
            assert pos_tp1.sl_price == entry_price  # Breakeven SL nachgezogen
            assert pos_tp1.realized_pnl > 0  # Reconcilierter Teilgewinn verbucht

            # 3. Zyklus: Kerzen steigen weiter ueber TP2 -> Full Close
            tp2_bar = Candle(
                time_ms=tp1_bar.time_ms + 3600000,
                open=tp1_bar.close,
                high=tp2_target + 100.0,  # Beruehrt TP2
                low=tp1_bar.close - 10.0,
                close=tp2_target + 50.0,
                volume=200.0,
            )
            now_sim = tp2_bar.time_ms / 1000 + 3600
            worker.adapter.fetch_candles = MagicMock(return_value=(initial_candles + [tp1_bar, tp2_bar], MagicMock(is_valid=True)))
            worker._run_cycle(3)

            # Erste Position muss vollstaendig als TP2 geschlossen sein
            assert len(worker.engine.closed_positions) >= 1
            closed_pos = worker.engine.closed_positions[0]
            assert closed_pos.status == "closed"
            assert closed_pos.exit_reason == "tp2_hit"
            assert closed_pos.realized_pnl > 0
            assert closed_pos.total_fees > 0

            # 4. Pruefe Persistenz in SQLite
            cur = conn.cursor()
            cur.execute("SELECT id, symbol, dir, status, realized_pnl, fees FROM trades WHERE symbol='BTCUSDT'")
            row = cur.fetchone()
            assert row is not None
            assert row[1] == "BTCUSDT"
            assert row[2] == 1
            assert float(row[4]) > 0
            assert float(row[5]) > 0

            # 5. Pruefe REST Control Plane / API State
            app = create_app(db_path=db_path)
            client = _make_authenticated_client(app)
            resp = client.get("/api/v3/state")
            assert resp.status_code == 200
            data = resp.json()
            assert data["equity"] > 10000.0  # Start 10.000 + Nettogewinn
            assert len(data["closed_trades"]) >= 1
            assert data["closed_trades"][0]["exit_reason"] == "tp2_hit"


    def test_api_state_refreshes_after_separate_worker_writes(self, tmp_path):
        db_path = tmp_path / "refresh-state.db"
        api_conn = connect(db_path)
        app = create_app(
            conn=api_conn,
            state_machine=RunnerStateMachine(SystemState.RUNNING),
            paper_engine=PaperTradingEngine(conn=api_conn),
        )
        client = _make_authenticated_client(app)
        assert client.get("/api/v3/state").json()["open_positions"] == []

        worker = AuraWorkerService(db_path=str(db_path), symbols=["BTCUSDT"])
        worker.sm.transition_to(SystemState.WARMING_UP, "test")
        worker.sm.transition_to(SystemState.RUNNING, "test")
        candles = generate_synthetic_bullish_trend(num_bars=50, start_price=50000.0)
        worker.adapter.fetch_candles = MagicMock(return_value=(candles, MagicMock(is_valid=True)))
        worker.notifier.send_alert = MagicMock(return_value=True)
        _seed_verified_market_data(worker, "BTCUSDT", candles[-1].time_ms + 3600_000)
        worker._run_cycle(1)

        state = client.get("/api/v3/state").json()
        assert len(state["open_positions"]) == 1
        assert state["open_positions"][0]["symbol"] == "BTCUSDT"


class TestWorkerMarketPersistence:
    def test_closed_candles_are_persisted_and_same_bar_is_not_reprocessed(self, tmp_path):
        db_path = tmp_path / "worker-persistence.db"
        worker = AuraWorkerService(db_path=str(db_path), symbols=["BTCUSDT"])
        worker.sm.transition_to(SystemState.WARMING_UP, "test")
        worker.sm.transition_to(SystemState.RUNNING, "test")

        candles = generate_synthetic_bullish_trend(num_bars=50, start_price=50000.0)
        candles.append(
            Candle(
                time_ms=candles[-1].time_ms + 3600000,
                open=candles[-1].close,
                high=candles[-1].close + 20.0,
                low=candles[-1].close - 20.0,
                close=candles[-1].close + 5.0,
                volume=100.0,
                is_closed=False,
            )
        )
        worker.adapter.fetch_candles = MagicMock(return_value=(candles, MagicMock(is_valid=True)))
        worker.notifier.send_alert = MagicMock(return_value=True)
        _seed_verified_market_data(worker, "BTCUSDT", candles[-2].time_ms + 3600_000)

        worker._run_cycle(1)
        first_trade_ids = set(worker.engine.open_positions)
        persisted = worker.conn.execute(
            "SELECT COUNT(*) AS n FROM candles WHERE symbol = 'BTCUSDT' AND timeframe = '1h'"
        ).fetchone()["n"]
        processed = worker.conn.execute(
            "SELECT COUNT(*) AS n FROM processed_bars WHERE symbol = 'BTCUSDT' AND timeframe = '1h'"
        ).fetchone()["n"]

        assert persisted == len(candles)
        assert processed == 1
        assert first_trade_ids
        first_trade = next(iter(worker.engine.open_positions.values()))
        assert first_trade.entry_time_ms == candles[-2].time_ms

        worker._run_cycle(2)

        assert set(worker.engine.open_positions) == first_trade_ids
        assert worker.conn.execute("SELECT COUNT(*) AS n FROM processed_bars").fetchone()["n"] == 1


    def test_entry_is_blocked_without_liquidity_verification(self, tmp_path):
        db_path = tmp_path / "risk-gates.db"
        worker = AuraWorkerService(db_path=str(db_path), symbols=["BTCUSDT"])
        worker.sm.transition_to(SystemState.WARMING_UP, "test")
        worker.sm.transition_to(SystemState.RUNNING, "test")
        candles = generate_synthetic_bullish_trend(num_bars=50, start_price=50000.0)
        worker.adapter.fetch_candles = MagicMock(return_value=(candles, MagicMock(is_valid=True)))
        worker.notifier.send_alert = MagicMock(return_value=True)

        worker._run_cycle(1)
        assert worker.engine.open_positions == {}

        _seed_verified_market_data(worker, "BTCUSDT", candles[-1].time_ms + 3600_000)
        worker.conn.execute("DELETE FROM processed_bars")
        worker._run_cycle(2)

        assert len(worker.engine.open_positions) == 1


class TestCrossProcessControlPlane:
    def test_halt_command_reaches_separate_worker_connection(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AURA_RELAY_TOKEN", "cross-process-test-token")
        db_path = tmp_path / "control-plane.db"

        api_conn = connect(db_path)
        app = create_app(
            conn=api_conn,
            state_machine=RunnerStateMachine(SystemState.RUNNING),
            paper_engine=PaperTradingEngine(conn=api_conn),
        )
        client = _make_authenticated_client(app)

        worker = AuraWorkerService(db_path=str(db_path), symbols=["BTCUSDT"])
        worker.sm.transition_to(SystemState.WARMING_UP, "test")
        worker.sm.transition_to(SystemState.RUNNING, "test")

        response = client.post(
            "/api/v3/halt",
            json={"reason": "cross process halt"},
            headers={"X-AURA-TOKEN": "cross-process-test-token"},
        )
        assert response.status_code == 200
        assert worker.sm.can_open_new_trades() is True

        worker._apply_control_plane_commands()

        assert worker.sm.current_state == SystemState.HALTED
        assert worker.sm.can_open_new_trades() is False
        command = worker.conn.execute(
            "SELECT status, applied_at_ms FROM commands WHERE type = 'halt'"
        ).fetchone()
        assert command["status"] == "applied"
        assert command["applied_at_ms"] is not None

        resume = client.post(
            "/api/v3/resume",
            json={"reason": "cross process resume"},
            headers={"X-AURA-TOKEN": "cross-process-test-token"},
        )
        assert resume.status_code == 200
        worker._apply_control_plane_commands()
        assert worker.sm.current_state == SystemState.RECOVERING
        assert worker.sm.can_open_new_trades() is False
        resume_command = worker.conn.execute(
            "SELECT status FROM commands WHERE type = 'resume'"
        ).fetchone()
        assert resume_command["status"] == "applied"

    def test_config_revision_is_pending_until_worker_applies_it(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AURA_RELAY_TOKEN", "cross-process-test-token")
        db_path = tmp_path / "config-control-plane.db"
        api_conn = connect(db_path)
        app = create_app(
            conn=api_conn,
            state_machine=RunnerStateMachine(SystemState.RUNNING),
            paper_engine=PaperTradingEngine(conn=api_conn),
        )
        client = _make_authenticated_client(app)
        worker = AuraWorkerService(db_path=str(db_path), symbols=["BTCUSDT"])

        payload = {
            "risk_per_trade_pct": 2.0,
            "max_open_positions": 4,
            "max_leverage": 8,
            "long_threshold": 72.0,
            "short_threshold": 28.0,
            "macro_cap": 12.0,
            "dry_run": True,
            "ntfy_enabled": False,
        }
        response = client.post(
            "/api/v3/config",
            json=payload,
            headers={"X-AURA-TOKEN": "cross-process-test-token"},
        )
        assert response.status_code == 200
        requested_rev = response.json()["data"]["requested_rev"]

        before = client.get("/api/v3/state").json()
        assert before["requested_config_rev"] == requested_rev
        assert before["active_config_rev"] is None
        assert worker.engine.config.risk_per_trade_pct == 1.0

        worker._apply_control_plane_commands()

        after = client.get("/api/v3/state").json()
        assert after["requested_config_rev"] == requested_rev
        assert after["active_config_rev"] == requested_rev
        assert worker.engine.config.risk_per_trade_pct == 2.0
        assert worker.engine.config.max_open_positions == 4
        assert worker.long_threshold == 72.0
        assert worker.short_threshold == 28.0


class TestBitgetOnlineIntegration:
    def test_live_bitget_public_feed_and_validation(self):
        """Echter Online-Integrationstest gegen oeffentliche Bitget REST API."""
        adapter = BitgetMarketAdapter()
        candles, rep = adapter.fetch_candles(symbol="BTCUSDT", granularity="1H", limit=10)

        if not candles:
            reason = rep.errors[0] if rep.errors else "unbekannter Providerfehler"
            pytest.skip(f"NOT_RUN: Bitget nicht erreichbar: {reason}")

        assert rep.is_valid is True
        assert len(candles) > 0
        first = candles[0]
        assert first.high >= max(first.open, first.close)
        assert first.low <= min(first.open, first.close)
        assert first.volume >= 0.0
        assert first.time_ms > 0
