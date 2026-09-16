"""Unit- und Invarianten-Tests fuer aura.core.stats.

Prueft DSR (F26), PAVA (F27), Selektions-Objektiv (F31), Walk-Forward (F32)
und Accounting-Reconciliation (F34, F59) nach den Mandatsanforderungen.
"""

from __future__ import annotations

import math

import pytest

from aura.core import stats


class TestNormalDistribution:
    def test_norm_cdf_standard_values(self):
        assert math.isclose(stats.norm_cdf(0.0), 0.5, abs_tol=1e-7)
        assert math.isclose(stats.norm_cdf(1.95996), 0.975, abs_tol=1e-3)
        assert math.isclose(stats.norm_cdf(-1.95996), 0.025, abs_tol=1e-3)

    def test_norm_inv_roundtrip(self):
        for p in [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]:
            z = stats.norm_inv(p)
            recovered_p = stats.norm_cdf(z)
            assert math.isclose(p, recovered_p, abs_tol=1e-5)


class TestDsr:
    def test_dsr_fallback_on_insufficient_sample(self):
        assert stats.calc_dsr([]).dsr == 0.5
        assert stats.calc_dsr([1.0, 2.0]).dsr == 0.5

    def test_dsr_fallback_on_zero_variance(self):
        assert stats.calc_dsr([1.0, 1.0, 1.0, 1.0]).dsr == 0.5

    def test_dsr_trials_deflation_property(self):
        # Mehr Trials muessen den DSR-Score streng monoton senken
        returns = [0.1, -0.05, 0.15, 0.08, -0.02, 0.12, 0.05, 0.09, -0.01, 0.11] * 3
        dsr_1 = stats.calc_dsr(returns, num_trials=1).dsr
        dsr_10 = stats.calc_dsr(returns, num_trials=10).dsr
        dsr_100 = stats.calc_dsr(returns, num_trials=100).dsr
        assert dsr_1 > dsr_10 > dsr_100


class TestPavaCalibration:
    def test_pava_monotonicity_invariant(self):
        # Beliebige OOS-Trades erzeugen, Kalibrierung muss monoton sein
        trades = [
            {"score": 25.0, "dir": 1, "outcome": "loss"},
            {"score": 35.0, "dir": 1, "outcome": "loss"},
            {"score": 55.0, "dir": 1, "outcome": "win"},
            {"score": 75.0, "dir": 1, "outcome": "win"},
            {"score": 85.0, "dir": 1, "outcome": "win"},
        ]
        calib_fn = stats.calibrate_probabilities(trades)
        prev_p = 0.0
        for s in range(0, 101, 5):
            p = calib_fn(float(s))
            assert 0.05 <= p <= 0.95
            assert p >= prev_p - 1e-9  # Monotonie
            prev_p = p

    def test_pava_empty_sample_uses_bayesian_prior(self):
        calib_fn = stats.calibrate_probabilities([])
        assert math.isclose(calib_fn(50.0), 0.5, abs_tol=1e-2)


class TestAccountingAndEvaluation:
    def test_reconcile_accounting_closed_and_open_trades(self):
        trades = [
            {"outcome": "win", "grossPnl": 150.0, "fees": 5.0},
            {"outcome": "loss", "grossPnl": -100.0, "fees": 5.0},
            {"outcome": "open", "grossPnl": 30.0, "fees": 2.5},
        ]
        # Starting 10000 -> Realized = 50, Unrealized = 30, Fees = 12.5 -> Expected = 10067.5
        rec = stats.reconcile_accounting(10000.0, trades)
        assert rec.is_reconciled is True
        assert math.isclose(rec.realized_pnl, 50.0)
        assert math.isclose(rec.unrealized_pnl, 30.0)
        assert math.isclose(rec.fees, 12.5)
        assert math.isclose(rec.expected_equity, 10067.5)

    def test_evaluate_trades_hand_calculated(self):
        trades = [
            {"outcome": "win", "rNet": 2.0},
            {"outcome": "win", "rNet": 1.0},
            {"outcome": "loss", "rNet": -1.0},
        ]
        ev = stats.evaluate_trades(trades)
        assert ev.total == 3
        assert ev.wins == 2
        assert ev.losses == 1
        assert math.isclose(ev.win_rate, 2.0 / 3.0)
        assert math.isclose(ev.profit_factor, 3.0 / 1.0)
        assert math.isclose(ev.expectancy_r, 2.0 / 3.0)


class TestWalkForward:
    def test_walk_forward_folds_no_overlap(self):
        # 500 Bars, Warmup 235, 4 Folds
        folds = stats.walk_forward_folds(500, warmup=235, k=4)
        assert len(folds) == 4
        for f in folds:
            # trainEnd muss genau testStart - 2 sein
            assert f.train_range[1] == f.test_range[0] - 2
            assert f.train_bars > 0
            assert f.test_bars > 0

    def test_selection_objective(self):
        assert stats.selection_objective(0.5, 1, min_trades=2) == float("-inf")
        obj_5 = stats.selection_objective(0.5, 5, min_trades=2)
        obj_20 = stats.selection_objective(0.5, 20, min_trades=2)
        assert obj_20 > obj_5 > 0.0
