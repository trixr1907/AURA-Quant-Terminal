"""Unit- und Invarianten-Tests fuer aura.core.scoring.

Prueft Confluence-Scoring, Makro-Adjust, Funding/OI/Basis-Bias
und die Kerzenanalyse-Pipeline nach docs/FORMULA_SPEC.md.
"""

from __future__ import annotations

import math

import pytest

from aura.core import scoring


class TestConfluenceWeights:
    def test_weights_sum_to_100_percent(self):
        total = scoring.W_TREND + scoring.W_MOM + scoring.W_VOL + scoring.W_STR
        assert math.isclose(total, 1.0, rel_tol=1e-9)

    def test_aggregate_score_hand_calculated(self):
        # 0.30 * 80 + 0.25 * 60 + 0.25 * 40 + 0.20 * 50
        # = 24 + 15 + 10 + 10 = 59.0
        score = scoring.aggregate_confluence_score(80.0, 60.0, 40.0, 50.0)
        assert math.isclose(score, 59.0, rel_tol=1e-9)

    def test_aggregate_score_clamps_0_to_100(self):
        assert scoring.aggregate_confluence_score(-50.0, -10.0, 0.0, 0.0) == 0.0
        assert scoring.aggregate_confluence_score(150.0, 120.0, 100.0, 100.0) == 100.0


class TestBiasesAndMacro:
    def test_funding_bias_contrarian(self):
        # Starke positive Funding Rates mit starkem z-Score
        rates = [0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 0.0008]
        fb = scoring.calc_funding_bias(rates)
        assert fb.bias < 0.0
        assert "SHORT-BIAS" in fb.txt

    def test_oi_bias_accumulation(self):
        # Preis steigt und OI steigt -> Long Build-Up
        oi_hist = [
            {"sumOpenInterest": 1000.0},
            {"sumOpenInterest": 1100.0},
            {"sumOpenInterest": 1200.0},
            {"sumOpenInterest": 1300.0},
            {"sumOpenInterest": 1500.0},
            {"sumOpenInterest": 1600.0},
        ]
        oi_bias = scoring.calc_oi_bias(oi_hist, current_price=105.0, price_4h_ago=100.0)
        assert oi_bias.bias > 0.0
        assert "Long Build-Up" in oi_bias.quadrant

    def test_basis_bias_contango_backwardation(self):
        # Mark deutlich ueber Index -> Premium (Short-Bias)
        b_contango = scoring.calc_basis_bias(mark_price=10100.0, index_price=10000.0)
        assert b_contango.bias < 0.0
        assert "Premium" in b_contango.txt

        # Mark deutlich unter Index -> Discount (Long-Bias)
        b_back = scoring.calc_basis_bias(mark_price=9900.0, index_price=10000.0)
        assert b_back.bias > 0.0
        assert "Discount" in b_back.txt

    def test_macro_adjust_hard_cap_15(self):
        # Extremwerte duerfen niemals mehr als +/- 15 Punkte anpassen
        adj = scoring.macro_adjust(
            core=50.0,
            fg=100.0,
            fund_bias=100.0,
            funding_z=5.0,
            oi_bias=100.0,
            oi_spike=True,
            basis_bias=100.0,
            mtf_bonus=10.0,
        )
        assert abs(adj.macro_adj) <= scoring.MACRO_CAP
        assert adj.total <= 50.0 + scoring.MACRO_CAP + 4.0 + 3.0 + 10.0


class TestAnalyzeCandlesPipeline:
    def test_analyze_candles_synthetic_series(self):
        # 300 Kerzen generieren
        candles = []
        base = 100.0
        for i in range(300):
            p = base + math.sin(i / 10.0) * 10.0 + i * 0.1
            candles.append({
                "time": 1735689600000 + i * 3600000,
                "open": p - 0.2,
                "high": p + 1.0,
                "low": p - 1.0,
                "close": p,
                "volume": 1000.0 + (i % 5) * 200.0,
            })

        res = scoring.analyze_candles(candles)
        assert res.n == 300
        assert len(res.score) == 300
        assert len(res.rsi) == 300
        assert len(res.atr) == 300
        assert res.last is not None
        assert res.last.score >= 0.0
        assert res.last.atr > 0.0
