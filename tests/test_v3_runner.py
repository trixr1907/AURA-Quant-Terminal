"""Unit-, Lifecycle- und Invarianten-Tests fuer aura.runner (P3).

Prueft State Machine, Not-Halt, Paper-Trading-Engine (TP1/TP2, SL, Timestop,
Intrabar-Kollision, Equity-Erhaltung) und Persistenz.
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import pytest

from aura.runner import (
    EngineConfig,
    PaperPosition,
    PaperTradingEngine,
    RunnerStateMachine,
    SystemState,
)
from aura.store.db import connect


@pytest.fixture
def test_db(tmp_path: Path) -> sqlite3.Connection:
    db_file = tmp_path / "test_aura_runner.db"
    return connect(db_file)


class TestRunnerStateMachine:
    def test_valid_transitions(self):
        sm = RunnerStateMachine(SystemState.STARTING)
        assert sm.transition_to(SystemState.WARMING_UP) is True
        assert sm.current_state == SystemState.WARMING_UP
        assert sm.can_open_new_trades() is False

        assert sm.transition_to(SystemState.RUNNING) is True
        assert sm.current_state == SystemState.RUNNING
        assert sm.can_open_new_trades() is True
        assert sm.can_manage_existing_trades() is True

        # Degraded
        sm.mark_degraded("Feed-Ausfall")
        assert sm.current_state == SystemState.DEGRADED
        assert sm.can_open_new_trades() is False
        assert sm.can_manage_existing_trades() is True

        sm.mark_healthy()
        assert sm.current_state == SystemState.RUNNING

    def test_emergency_halt_blocks_new_trades_preserves_management(self):
        sm = RunnerStateMachine(SystemState.RUNNING)
        sm.emergency_halt("Manuelle Abschaltung")
        assert sm.is_halted is True
        assert sm.current_state == SystemState.HALTED
        assert sm.can_open_new_trades() is False
        assert sm.can_manage_existing_trades() is True

        # Resume
        assert sm.resume_from_halt() is True
        assert sm.is_halted is False
        assert sm.current_state == SystemState.RECOVERING


class TestPaperEngineLifecycle:
    def test_open_trade_and_sl_hit(self):
        engine = PaperTradingEngine(EngineConfig(starting_equity=10000.0, risk_per_trade_pct=1.0))
        spec = {"ctVal": 0.01, "minSize": 0.01, "minNotional": 5.0}

        # Long Entry: 1000, SL: 950 (Dist=50) -> Risk 100 USDT -> 200 Kontrakte (2.0 BTC)
        pos = engine.open_trade(
            symbol="BTCUSDT",
            timeframe="1h",
            direction=1,
            entry_price=1000.0,
            sl_price=950.0,
            tp1_price=1100.0,
            tp2_price=1200.0,
            spec=spec,
            leverage=5,
        )
        assert pos is not None
        assert pos.symbol == "BTCUSDT"
        assert len(engine.open_positions) == 1

        # Bar updates without hitting SL
        closed = engine.on_bar_update("BTCUSDT", high=1020.0, low=980.0, close=1010.0, bar_time_ms=1000)
        assert len(closed) == 0
        assert len(engine.open_positions) == 1

        # Bar hits SL (Low=940 <= 950)
        closed = engine.on_bar_update("BTCUSDT", high=980.0, low=940.0, close=945.0, bar_time_ms=2000)
        assert len(closed) == 1
        assert len(engine.open_positions) == 0
        assert closed[0].exit_reason == "sl_hit"
        assert closed[0].realized_pnl < 0  # Verlust realisiert
        # Mandat Q-01: Equity ist gesunken
        assert engine.equity < 10000.0
        # Entry-Fee ist bereits in der Equity abgezogen; realized_pnl enthält nur
        # die Netto-Ergebnisse der Exit-Tranchen.
        entry_fee = closed[0].initial_qty * closed[0].entry_price * engine.config.taker_fee
        assert math.isclose(
            engine.equity,
            10000.0 - entry_fee + closed[0].realized_pnl,
            rel_tol=1e-6,
        )

    def test_tp1_partial_close_and_breakeven_move(self):
        engine = PaperTradingEngine(EngineConfig(starting_equity=10000.0, risk_per_trade_pct=1.0))
        spec = {"ctVal": 0.01, "minSize": 0.01, "minNotional": 5.0}

        pos = engine.open_trade(
            symbol="ETHUSDT",
            timeframe="1h",
            direction=1,
            entry_price=2000.0,
            sl_price=1900.0,
            tp1_price=2100.0,
            tp2_price=2200.0,
            spec=spec,
            leverage=5,
        )
        assert pos is not None
        init_qty = pos.qty

        # Bar erreicht TP1 (High=2120 >= 2100)
        closed = engine.on_bar_update("ETHUSDT", high=2120.0, low=2010.0, close=2090.0, bar_time_ms=1000)
        assert len(closed) == 0  # Position bleibt mit 50% Rest offen
        assert len(engine.open_positions) == 1

        active = engine.open_positions[pos.trade_id]
        assert active.tp1_hit is True
        assert math.isclose(active.qty, init_qty * 0.5)
        assert active.sl_price == active.entry_price  # Stop auf BE nachgezogen
        assert active.realized_pnl > 0  # Teilgewinn realisiert
        assert engine.equity > 10000.0  # Equity bereits um Teilgewinn erhoeht

        # Naechster Bar faellt auf Breakeven zurueck -> SL Hit ohne zusaetzlichen Verlust
        closed2 = engine.on_bar_update("ETHUSDT", high=2080.0, low=1990.0, close=2000.0, bar_time_ms=2000)
        assert len(closed2) == 1
        assert len(engine.open_positions) == 0
        # Gesamt-Trade schliesst positiv ab wegen des TP1-Teilgewinns
        assert closed2[0].realized_pnl > 0

    def test_intrabar_collision_conservative_policy(self):
        # Wenn im selben Bar sowohl Low <= SL als auch High >= TP1 getroffen werden
        engine = PaperTradingEngine(EngineConfig(intrabar_conservative=True))
        spec = {"ctVal": 1.0, "minSize": 1.0, "minNotional": 10.0}

        pos = engine.open_trade(
            symbol="SOLUSDT",
            timeframe="1h",
            direction=1,
            entry_price=100.0,
            sl_price=90.0,
            tp1_price=120.0,
            tp2_price=140.0,
            spec=spec,
        )
        assert pos is not None

        # Intrabar-Kollision: Low 85 <= 90 UND High 125 >= 120
        closed = engine.on_bar_update("SOLUSDT", high=125.0, low=85.0, close=100.0, bar_time_ms=1000)
        assert len(closed) == 1
        assert closed[0].exit_reason is not None
        assert "sl_hit" in closed[0].exit_reason
        assert closed[0].realized_pnl < 0

    def test_timestop_labeled_correctly(self):
        # Q-04: Timestop darf nicht als sl_close gelabelt werden
        engine = PaperTradingEngine(EngineConfig(max_hold_bars=10))
        spec = {"ctVal": 1.0, "minSize": 1.0, "minNotional": 10.0}

        pos = engine.open_trade(
            symbol="DOGEUSDT",
            timeframe="1h",
            direction=1,
            entry_price=0.20,
            sl_price=0.15,
            tp1_price=0.30,
            tp2_price=0.40,
            spec=spec,
            current_time_ms=1000,
        )
        assert pos is not None

        # 11 Stunden spaeter (kein SL/TP getriggert)
        future_ms = 1000 + 11 * 3600 * 1000
        closed = engine.on_bar_update("DOGEUSDT", high=0.22, low=0.18, close=0.21, bar_time_ms=future_ms)
        assert len(closed) == 1
        assert closed[0].exit_reason == "timestop"
        assert closed[0].exit_reason != "sl_close"


class TestRunnerPersistence:
    def test_trade_persisted_and_recovered_on_restart(self, test_db: sqlite3.Connection):
        engine1 = PaperTradingEngine(EngineConfig(), conn=test_db)
        spec = {"ctVal": 0.01, "minSize": 0.01, "minNotional": 5.0}

        pos = engine1.open_trade(
            symbol="BTCUSDT",
            timeframe="1h",
            direction=1,
            entry_price=50000.0,
            sl_price=48000.0,
            tp1_price=54000.0,
            tp2_price=58000.0,
            spec=spec,
        )
        assert pos is not None

        # DB direkt pruefen
        cur = test_db.cursor()
        cur.execute("SELECT symbol, status, dir FROM trades WHERE id = ?", (pos.trade_id,))
        row = cur.fetchone()
        assert row is not None
        assert row["symbol"] == "BTCUSDT"
        assert row["status"] == "open"
        assert row["dir"] == 1

        # Zweite Engine instanziieren (Simulierter Neustart des Workers)
        engine2 = PaperTradingEngine(EngineConfig(), conn=test_db)
        assert len(engine2.open_positions) == 1
        assert pos.trade_id in engine2.open_positions
        rec = engine2.open_positions[pos.trade_id]
        assert rec.symbol == "BTCUSDT"
        assert rec.direction == 1
        assert math.isclose(rec.sl_price, 48000.0)
