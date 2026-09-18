"""Unit- und Invarianten-Tests fuer aura.core.risk.

Prueft Fractional Kelly (F28), Positionsgroesse mit ULP-Schutz (F29)
und Hebelempfehlung (F30) nach den Mandatsanforderungen.
"""

from __future__ import annotations

import math

import pytest

from aura.core import risk


class TestKellyFormula:
    def test_kelly_positive_edge_hand_calculated(self):
        # p = 0.6, avg_win = 2.0, avg_loss = 1.0 -> b = 2.0
        # f* = (0.6 * 3 - 1) / 2 = 0.8 / 2 = 0.4
        # half_kelly = 0.2
        # risk_pct = 2.0 (0.02), equity = 10_000
        # hard_cap = min(0.25, 0.02) = 0.02
        # N = 20 (>=15 -> multiplier 1.0)
        # edge = 0.6 * 2.0 - (1 - 0.6) = 1.2 - 0.4 = 0.8 (80%)
        # final_frac = 0.02 -> risk_amt = 200.0
        res = risk.calc_kelly(0.6, 2.0, 1.0, 2.0, 10000.0, total_trades=20)
        assert res.has_edge is True
        assert math.isclose(res.f_star, 0.4, rel_tol=1e-9)
        assert math.isclose(res.half_kelly, 0.2, rel_tol=1e-9)
        assert math.isclose(res.final_frac, 0.02, rel_tol=1e-9)
        assert math.isclose(res.risk_amt, 200.0, rel_tol=1e-9)
        assert math.isclose(res.edge_pct, 80.0, rel_tol=1e-9)

    def test_kelly_negative_edge_returns_zero(self):
        # p = 0.3, b = 1.0 -> f* = -0.4
        res = risk.calc_kelly(0.3, 1.0, 1.0, 2.0, 10000.0, total_trades=50)
        assert res.has_edge is False
        assert res.f_star == 0.0
        assert res.final_frac == 0.0
        assert res.risk_amt == 0.0

    def test_kelly_sample_shrinkage(self):
        # N = 10: multiplier = (10-5)/10 = 0.5
        res10 = risk.calc_kelly(0.6, 2.0, 1.0, 2.0, 10000.0, total_trades=10)
        assert math.isclose(res10.final_frac, 0.01, rel_tol=1e-9)

        # N = 4: multiplier = 0.0
        res4 = risk.calc_kelly(0.6, 2.0, 1.0, 2.0, 10000.0, total_trades=4)
        assert res4.final_frac == 0.0

    def test_kelly_invalid_inputs_fail_closed(self):
        assert risk.calc_kelly(-0.1, 1.0, 1.0, 2.0, 10000.0).has_edge is False
        assert risk.calc_kelly(0.5, 0.0, 1.0, 2.0, 10000.0).has_edge is False
        assert risk.calc_kelly(0.5, 1.0, 1.0, -1.0, 10000.0).has_edge is False
        assert risk.calc_kelly(0.5, 1.0, 1.0, 2.0, float("nan")).has_edge is False


class TestPositionSizing:
    def test_size_position_hand_calculated(self):
        spec = {"ctVal": 0.001, "minSize": 0.001, "minNotional": 5.0}
        # Risk 100 USDT, Entry 1000, Stop 950 (Dist=50)
        # Raw contracts = (100 / 50) / 0.001 = 2000
        # Qty = 2.000, Notional = 2000.0, Margin (lev=10) = 200.0, Risk = 100.0
        res = risk.size_position(100.0, 1000.0, 50.0, leverage=10, spec=spec)
        assert res.contracts == 2000
        assert math.isclose(res.qty, 2.0)
        assert math.isclose(res.notional, 2000.0)
        assert math.isclose(res.margin, 200.0)
        assert math.isclose(res.actual_risk_amt, 100.0)

    def test_size_position_never_exceeds_risk_budget(self):
        # Truncation must round DOWN contracts, not up
        spec = {"ctVal": 1.0, "minSize": 1.0, "minNotional": 5.0}
        # Risk 95, Entry 100, Stop 90 (Dist=10)
        # Raw contracts = 9.5 -> floor = 9
        res = risk.size_position(95.0, 100.0, 10.0, leverage=1, spec=spec)
        assert res.contracts == 9
        assert res.qty == 9.0
        assert res.actual_risk_amt <= 95.0

    def test_size_position_below_minimum_returns_zero(self):
        spec = {"ctVal": 1.0, "minSize": 10.0, "minNotional": 100.0}
        # Risk 5, Dist 10 -> contracts = 0 < minSize
        res = risk.size_position(5.0, 100.0, 10.0, leverage=1, spec=spec)
        assert res.contracts == 0
        assert res.qty == 0.0


class TestLeverageRecommendation:
    def test_recommend_leverage_invariant(self):
        # Stop loss percentage = 2% (entry=100, sl=98)
        # safe_max = floor(100 / (2*3 + 0.5)) = floor(100 / 6.5) = 15
        # notional = 1000, equity = 10000 -> margin budget 3500
        # needed = ceil(1000 / 3500) = 1
        # leverage = min(1, 15, 50) = 1
        res = risk.recommend_leverage(100.0, 98.0, 1000.0, 10000.0, max_leverage=50)
        assert res.leverage == 1
        assert res.safe_max == 15
        assert res.warning == ""

    def test_leverage_does_not_change_stop_loss_distance(self):
        # Mandat §5: Hebel verändert Marginanforderungen, nicht den Stop
        r1 = risk.recommend_leverage(100.0, 95.0, 1000.0, 5000.0, max_leverage=10)
        r2 = risk.recommend_leverage(100.0, 95.0, 1000.0, 5000.0, max_leverage=20)
        assert r1.stop_pct == r2.stop_pct == 5.0
