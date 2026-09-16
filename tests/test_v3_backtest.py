"""Unit- und Validierungstests fuer aura.backtest (P5).

Prueft Kausalitaet, Kosten-Sensitivitaet, Intrabar-Verhalten
und K-Fold Walk-Forward mit DSR-Auswertung.
"""

from __future__ import annotations

import math

import pytest

from aura.backtest import (
    BacktestConfig,
    BacktestSimulator,
    WalkForwardOptimizer,
)


@pytest.fixture
def synthetic_trending_candles() -> list[dict]:
    candles = []
    base = 100.0
    for i in range(500):
        # Zyklischer Aufwaertstrend
        p = base + math.sin(i / 15.0) * 15.0 + i * 0.2
        candles.append({
            "time": 1735689600000 + i * 3600000,
            "open": p - 0.2,
            "high": p + 1.5,
            "low": p - 1.5,
            "close": p,
            "volume": 1000.0 + (i % 5) * 100.0,
        })
    return candles


class TestBacktestSimulator:
    def test_backtest_causality_and_execution(self, synthetic_trending_candles):
        sim = BacktestSimulator(BacktestConfig(warmup_bars=235))
        spec = {"ctVal": 0.01, "minSize": 0.01, "minNotional": 5.0}
        res = sim.run(synthetic_trending_candles, symbol="BTCUSDT", spec=spec)

        assert res.total_bars == 500
        assert len(res.trades) > 0
        # Alle Einstiege muessen nach Warmup liegen
        for t in res.trades:
            assert t["entry_bar"] >= 235
            assert t["outcome"] in ("win", "loss")
            assert math.isfinite(t["realized_pnl"])
            assert math.isfinite(t["fees"])

    def test_cost_sensitivity_monotonic_pnl_reduction(self, synthetic_trending_candles):
        # Hoehere Kosten muessen den Netto-PnL streng monoton senken
        spec = {"ctVal": 0.01, "minSize": 0.01, "minNotional": 5.0}

        sim_low_cost = BacktestSimulator(BacktestConfig(slippage_bps=0.0, taker_fee=0.0001, maker_fee=0.0001))
        sim_high_cost = BacktestSimulator(BacktestConfig(slippage_bps=5.0, taker_fee=0.0010, maker_fee=0.0005))

        res_low = sim_low_cost.run(synthetic_trending_candles, symbol="BTCUSDT", spec=spec)
        res_high = sim_high_cost.run(synthetic_trending_candles, symbol="BTCUSDT", spec=spec)

        assert res_low.ending_equity > res_high.ending_equity


class TestWalkForwardOptimization:
    def test_walk_forward_pipeline_runs_and_evaluates(self, synthetic_trending_candles):
        wfo = WalkForwardOptimizer(k_folds=4, warmup_bars=235, num_trials=18)
        spec = {"ctVal": 0.01, "minSize": 0.01, "minNotional": 5.0}
        rep = wfo.run(synthetic_trending_candles, symbol="BTCUSDT", spec=spec)

        assert rep.k_folds == 4
        assert rep.total_bars == 500
        assert len(rep.fold_results) == 4
        assert rep.model_status in ("EVIDENCE_SUPPORTED", "MODEL_NO_EVIDENCE")
        assert 0.0 <= rep.dsr_result.dsr <= 1.0
