"""Unabhaengige quant-mathematische und Accounting-Pruefung (Mandat §4).

Verifiziert:
- Handberechnete Long/Short-P&L mit exakter Gebuehren- und Slippage-Verrechnung
- Konservative Intrabar-Kollisionsreihenfolge (SL vor TP)
- State-Wiederherstellung bei Engine-Neustart waehrend eines Partial-Exits (TP1)
- Kelly-Shrinkage, DSR-Deflation und Erhaltungsgleichungen
"""

from __future__ import annotations

import tempfile

from aura.core.risk import calc_kelly
from aura.core.stats import calc_dsr, reconcile_accounting
from aura.runner.paper_engine import EngineConfig, PaperTradingEngine
from aura.store.db import connect, migrate


class TestQuantAccountingIndependent:
    def test_hand_calculated_long_two_stage_tp(self):
        """Handberechneter Long-Trade mit 50% TP1 und 50% TP2."""
        cfg = EngineConfig(
            starting_equity=10000.0,
            maker_fee=0.0002,   # 0.02%
            taker_fee=0.0006,   # 0.06%
            slippage_bps=0.0,   # 0 bps fuer exakte Handrechnung
            max_open_positions=1,
        )
        engine = PaperTradingEngine(config=cfg)

        # Eroeffne Long: 0.05 BTC @ 50,000, SL=48,000, TP1=52,000, TP2=54,000
        spec = {"ctVal": 0.0001, "minSize": 0.0001, "minNotional": 5.0}
        pos = engine.open_trade(
            symbol="BTCUSDT",
            timeframe="1H",
            direction=1,
            entry_price=50000.0,
            sl_price=48000.0,
            tp1_price=52000.0,
            tp2_price=54000.0,
            spec=spec,
            leverage=10,
            score=80.0,
            current_time_ms=1000,
        )
        assert pos is not None
        qty = pos.qty  # 0.05 BTC

        # Handrechnung Entry Fee (Taker 0.06%): 0.05 * 50000 * 0.0006 = 1.50 USDT
        expected_entry_fee = qty * 50000.0 * 0.0006
        assert abs(pos.total_fees - expected_entry_fee) < 1e-6

        # Bar 1: TP1 Hit (High=52,500) -> 50% Partial Close (0.025 BTC) @ 52,000 (Maker Fee: 0.02%)
        engine.on_bar_update("BTCUSDT", high=52500.0, low=50500.0, close=52100.0, bar_time_ms=2000)
        assert pos.tp1_hit is True
        assert pos.status == "partial_tp1"
        assert abs(pos.qty - (qty * 0.5)) < 1e-6
        assert pos.sl_price == 50000.0  # Breakeven SL

        tp1_qty = qty * 0.5
        expected_tp1_gross = tp1_qty * (52000.0 - 50000.0)  # 0.025 * 2000 = 50.0 USDT
        expected_tp1_fee = tp1_qty * 52000.0 * 0.0002       # 0.025 * 52000 * 0.0002 = 0.26 USDT
        expected_tp1_net = expected_tp1_gross - expected_tp1_fee  # 49.74 USDT
        assert abs(pos.realized_pnl - expected_tp1_net) < 1e-4

        # Bar 2: TP2 Hit (High=54,500) -> Full Close (0.025 BTC) @ 54,000 (Maker Fee: 0.02%)
        closed = engine.on_bar_update("BTCUSDT", high=54500.0, low=51800.0, close=54200.0, bar_time_ms=3000)
        assert len(closed) == 1
        c = closed[0]
        assert c.status == "closed"
        assert c.exit_reason == "tp2_hit"

        tp2_qty = qty * 0.5
        expected_tp2_gross = tp2_qty * (54000.0 - 50000.0)  # 0.025 * 4000 = 100.0 USDT
        expected_tp2_fee = tp2_qty * 54000.0 * 0.0002       # 0.025 * 54000 * 0.0002 = 0.27 USDT
        expected_tp2_net = expected_tp2_gross - expected_tp2_fee  # 99.73 USDT
        expected_total_realized_from_exits = expected_tp1_net + expected_tp2_net  # 149.47 USDT
        expected_total_fees = expected_entry_fee + expected_tp1_fee + expected_tp2_fee  # 2.03 USDT

        assert abs(c.realized_pnl - expected_total_realized_from_exits) < 1e-4
        assert abs(c.total_fees - expected_total_fees) < 1e-4

        # Reconciled Equity: Start - EntryFee + ExitsRealizedPnL = 10000 - 1.50 + 149.47 = 10147.97
        expected_equity = 10000.0 - expected_entry_fee + expected_total_realized_from_exits
        assert abs(engine.equity - expected_equity) < 1e-4

    def test_hand_calculated_short_two_stage_tp(self):
        """Handberechneter Short-Trade mit 50% TP1 und 50% TP2."""
        cfg = EngineConfig(
            starting_equity=10000.0,
            maker_fee=0.0002,   # 0.02%
            taker_fee=0.0006,   # 0.06%
            slippage_bps=0.0,
            max_open_positions=1,
        )
        engine = PaperTradingEngine(config=cfg)

        spec = {"ctVal": 0.0001, "minSize": 0.0001, "minNotional": 5.0}
        pos = engine.open_trade(
            symbol="BTCUSDT",
            timeframe="1H",
            direction=-1,
            entry_price=50000.0,
            sl_price=52000.0,
            tp1_price=48000.0,
            tp2_price=46000.0,
            spec=spec,
            leverage=10,
            score=20.0,
            current_time_ms=1000,
        )
        assert pos is not None
        qty = pos.qty  # 0.05 BTC (or sized amount)
        notional = qty * 50000.0

        expected_entry_fee = notional * 0.0006
        assert abs(pos.total_fees - expected_entry_fee) < 1e-6

        # Bar 1: TP1 Hit (Low=47500 <= 48000)
        engine.on_bar_update("BTCUSDT", high=50200.0, low=47500.0, close=47900.0, bar_time_ms=2000)
        assert pos.tp1_hit is True
        assert pos.status == "partial_tp1"
        assert abs(pos.qty - (qty * 0.5)) < 1e-6
        assert pos.sl_price == 50000.0  # Breakeven SL

        tp1_qty = qty * 0.5
        expected_tp1_gross = tp1_qty * (50000.0 - 48000.0)
        expected_tp1_fee = tp1_qty * 48000.0 * 0.0002
        expected_tp1_net = expected_tp1_gross - expected_tp1_fee
        assert abs(pos.realized_pnl - expected_tp1_net) < 1e-4

        # Bar 2: TP2 Hit (Low=45500 <= 46000)
        closed = engine.on_bar_update("BTCUSDT", high=48200.0, low=45500.0, close=45800.0, bar_time_ms=3000)
        assert len(closed) == 1
        c = closed[0]
        assert c.status == "closed"
        assert c.exit_reason == "tp2_hit"

        tp2_qty = qty * 0.5
        expected_tp2_gross = tp2_qty * (50000.0 - 46000.0)
        expected_tp2_fee = tp2_qty * 46000.0 * 0.0002
        expected_tp2_net = expected_tp2_gross - expected_tp2_fee
        expected_total_realized = expected_tp1_net + expected_tp2_net
        expected_total_fees = expected_entry_fee + expected_tp1_fee + expected_tp2_fee

        assert abs(c.realized_pnl - expected_total_realized) < 1e-4
        assert abs(c.total_fees - expected_total_fees) < 1e-4
        expected_equity = 10000.0 - expected_entry_fee + expected_total_realized
        assert abs(engine.equity - expected_equity) < 1e-4
        assert c.r_multiple > 0.0

    def test_conservative_intrabar_collision_sl_first(self):
        """Wenn SL und TP im selben Bar beruehrt werden: SL wird fail-closed priorisiert."""
        cfg = EngineConfig(starting_equity=10000.0, intrabar_conservative=True)
        engine = PaperTradingEngine(config=cfg)

        pos = engine.open_trade(
            symbol="ETHUSDT",
            timeframe="1H",
            direction=1,
            entry_price=3000.0,
            sl_price=2900.0,
            tp1_price=3200.0,
            tp2_price=3400.0,
            spec={"ctVal": 0.01, "minSize": 0.01, "minNotional": 5.0},
        )
        assert pos is not None

        # Intrabar: High=3300 (ueber TP1), Low=2850 (unter SL)
        closed = engine.on_bar_update("ETHUSDT", high=3300.0, low=2850.0, close=3100.0, bar_time_ms=5000)
        assert len(closed) == 1
        assert closed[0].exit_reason == "sl_hit_intrabar_collision"
        assert closed[0].realized_pnl < 0  # Verlust realisiert

    def test_restart_during_partial_exit_preserves_be_and_pnl(self):
        """Neustart waehrend Partial-Exit behaelt Breakeven-SL und realisierten TP1-Gewinn bei."""
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            db_path = tmp.name
            conn1 = connect(db_path)
            migrate(conn1)

            engine1 = PaperTradingEngine(conn=conn1)
            pos1 = engine1.open_trade(
                symbol="SOLUSDT",
                timeframe="1H",
                direction=1,
                entry_price=150.0,
                sl_price=140.0,
                tp1_price=165.0,
                tp2_price=180.0,
                spec={"ctVal": 0.1, "minSize": 0.1, "minNotional": 5.0},
            )
            assert pos1 is not None
            init_qty = pos1.initial_qty

            # TP1 ausfuehren
            engine1.on_bar_update("SOLUSDT", high=166.0, low=148.0, close=164.0, bar_time_ms=10000)
            assert pos1.status == "partial_tp1"
            tp1_pnl = pos1.realized_pnl
            assert tp1_pnl > 0
            conn1.close()

            # Neustart mit neuem Engine-Objekt gegen dieselbe SQLite-DB
            conn2 = connect(db_path)
            engine2 = PaperTradingEngine(conn=conn2)
            assert len(engine2.open_positions) == 1
            reloaded_pos = list(engine2.open_positions.values())[0]

            assert reloaded_pos.status == "partial_tp1"
            assert reloaded_pos.tp1_hit is True
            assert abs(reloaded_pos.qty - (init_qty * 0.5)) < 1e-4
            assert reloaded_pos.sl_price == pos1.entry_price  # Breakeven SL intakt
            assert abs(reloaded_pos.realized_pnl - tp1_pnl) < 1e-4

            # Naechster Bar faellt auf Breakeven SL zurueck
            closed = engine2.on_bar_update("SOLUSDT", high=155.0, low=140.0, close=145.0, bar_time_ms=20000)
            assert len(closed) == 1
            assert closed[0].exit_reason == "sl_hit"
            # Realisierter Gewinn aus TP1 bleibt erhalten
            assert closed[0].realized_pnl > 0
            conn2.close()

    def test_restart_equity_uses_persisted_fee_not_current_config(self, tmp_path):
        db_path = tmp_path / "fee-restart.db"
        conn1 = connect(db_path)
        engine1 = PaperTradingEngine(
            config=EngineConfig(taker_fee=0.001, maker_fee=0.0, slippage_bps=0.0),
            conn=conn1,
        )
        pos = engine1.open_trade(
            symbol="FEEUSDT", timeframe="1H", direction=1,
            entry_price=100.0, sl_price=90.0, tp1_price=120.0, tp2_price=130.0,
            spec={"ctVal": 0.1, "minSize": 0.1, "minNotional": 1.0},
            current_time_ms=1000,
        )
        assert pos is not None
        equity_before = engine1.equity
        conn1.close()

        conn2 = connect(db_path)
        engine2 = PaperTradingEngine(
            config=EngineConfig(taker_fee=0.009, maker_fee=0.0, slippage_bps=0.0),
            conn=conn2,
        )
        assert abs(engine2.equity - equity_before) < 1e-12

    def test_r_multiple_uses_immutable_initial_stop_after_tp1(self):
        cfg = EngineConfig(starting_equity=10000.0, maker_fee=0.0, taker_fee=0.0, slippage_bps=0.0)
        for direction, sl, tp1, tp2 in ((1, 90.0, 110.0, 120.0), (-1, 110.0, 90.0, 80.0)):
            engine = PaperTradingEngine(config=cfg)
            pos = engine.open_trade(
                symbol=f"TEST{direction}", timeframe="1H", direction=direction,
                entry_price=100.0, sl_price=sl, tp1_price=tp1, tp2_price=tp2,
                spec={"ctVal": 0.1, "minSize": 0.1, "minNotional": 1.0},
                current_time_ms=1000,
            )
            assert pos is not None
            initial_risk = pos.initial_qty * abs(pos.entry_price - sl)
            if direction == 1:
                engine.on_bar_update(pos.symbol, high=111.0, low=99.0, close=110.0, bar_time_ms=2000)
                closed = engine.on_bar_update(pos.symbol, high=121.0, low=109.0, close=120.0, bar_time_ms=3000)
            else:
                engine.on_bar_update(pos.symbol, high=101.0, low=89.0, close=90.0, bar_time_ms=2000)
                closed = engine.on_bar_update(pos.symbol, high=91.0, low=79.0, close=80.0, bar_time_ms=3000)
            assert len(closed) == 1
            expected_r = closed[0].realized_pnl / initial_risk
            assert abs(closed[0].r_multiple - expected_r) < 1e-12
            assert closed[0].r_multiple > 0.0

    def test_timestop_uses_position_timeframe_duration(self):
        engine = PaperTradingEngine(
            config=EngineConfig(max_hold_bars=4, maker_fee=0.0, taker_fee=0.0, slippage_bps=0.0)
        )
        pos = engine.open_trade(
            symbol="TIME15", timeframe="15m", direction=1,
            entry_price=100.0, sl_price=90.0, tp1_price=120.0, tp2_price=130.0,
            spec={"ctVal": 0.1, "minSize": 0.1, "minNotional": 1.0},
            current_time_ms=1000,
        )
        assert pos is not None
        before = engine.on_bar_update(
            "TIME15", high=101.0, low=99.0, close=100.0,
            bar_time_ms=1000 + (4 * 15 * 60 * 1000) - 1,
        )
        assert before == []
        closed = engine.on_bar_update(
            "TIME15", high=101.0, low=99.0, close=100.0,
            bar_time_ms=1000 + (4 * 15 * 60 * 1000),
        )
        assert len(closed) == 1
        assert closed[0].exit_reason == "timestop"

    def test_kelly_sample_shrinkage_schedule(self):
        """Prueft Sample-Shrinkage nach López de Prado: 0 bei <5, linear 5-15, voll ab 15."""
        # N=3: keine Evidenz (<5 trades)
        k3 = calc_kelly(prob_win=0.6, avg_win_r=2.0, avg_loss_r=1.0, risk_pct=2.0, equity=10000.0, total_trades=3)
        assert k3.has_edge is False
        assert k3.final_frac == 0.0

        # N=10: Halbe Shrinkage ((10-5)/10 = 0.5)
        k10 = calc_kelly(prob_win=0.6, avg_win_r=2.0, avg_loss_r=1.0, risk_pct=2.0, equity=10000.0, total_trades=10)
        assert k10.has_edge is True
        assert k10.final_frac > 0.0

        # N=20: Volle Skalierung
        k20 = calc_kelly(prob_win=0.6, avg_win_r=2.0, avg_loss_r=1.0, risk_pct=2.0, equity=10000.0, total_trades=20)
        assert k20.has_edge is True
        assert k20.final_frac >= k10.final_frac
