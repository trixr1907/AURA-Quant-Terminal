"""Unit- und Invarianten-Tests fuer aura.core.indicators.

Prueft alle mathematischen Definitionen aus docs/FORMULA_SPEC.md (F01-F14, F24).
Handberechnete Mini-Fixtures, Nullteiler-Guards, leere Reihen, Flatlines.
"""

from __future__ import annotations

import math

import pytest

from aura.core import indicators


class TestMovingAverages:
    def test_ema_series_hand_calculated(self):
        # src = [10, 20, 30], period = 2 -> k = 2/3
        # ema[0] = 10
        # ema[1] = 20 * 2/3 + 10 * 1/3 = 40/3 + 10/3 = 50/3 = 16.66666667
        # ema[2] = 30 * 2/3 + (50/3) * 1/3 = 20 + 50/9 = 230/9 = 25.55555556
        res = indicators.ema_series([10.0, 20.0, 30.0], 2)
        assert len(res) == 3
        assert res[0] == 10.0
        assert math.isclose(res[1], 50.0 / 3.0, rel_tol=1e-9)
        assert math.isclose(res[2], 230.0 / 9.0, rel_tol=1e-9)

    def test_ema_empty_and_single(self):
        assert indicators.ema_series([], 10) == []
        assert indicators.ema_series([42.0], 10) == [42.0]

    def test_sma_series_hand_calculated(self):
        res = indicators.sma_series([1.0, 2.0, 3.0, 4.0, 5.0], 3)
        assert res[0] == 0.0
        assert res[1] == 0.0
        assert math.isclose(res[2], 2.0)
        assert math.isclose(res[3], 3.0)
        assert math.isclose(res[4], 4.0)


class TestRsi:
    def test_rsi_constant_prices_returns_neutral(self):
        res = indicators.rsi_series([100.0] * 30, 14)
        for val in res[14:]:
            assert val == 50.0

    def test_rsi_strictly_increasing_returns_100(self):
        res = indicators.rsi_series(list(range(100, 150)), 14)
        for val in res[14:]:
            assert math.isclose(val, 100.0, abs_tol=1e-6)

    def test_rsi_strictly_decreasing_returns_0(self):
        res = indicators.rsi_series(list(range(150, 100, -1)), 14)
        for val in res[14:]:
            assert math.isclose(val, 0.0, abs_tol=1e-6)


class TestAtr:
    def test_atr_flatline_returns_zero(self):
        res = indicators.atr_series([100.0] * 30, [100.0] * 30, [100.0] * 30, 14)
        for val in res:
            assert val == 0.0

    def test_atr_hand_calculated(self):
        # 15 bars with constant High=110, Low=90, Close=100 -> TR = 20 for all
        h = [110.0] * 20
        l = [90.0] * 20
        c = [100.0] * 20
        res = indicators.atr_series(h, l, c, 14)
        assert math.isclose(res[14], 20.0, rel_tol=1e-9)
        assert math.isclose(res[19], 20.0, rel_tol=1e-9)


class TestAdx:
    def test_adx_flatline_handles_zero_division(self):
        res = indicators.adx_series([100.0] * 40, [100.0] * 40, [100.0] * 40, 14)
        assert len(res.adx) == 40
        assert all(math.isfinite(x) for x in res.adx)


class TestSuperTrend:
    def test_supertrend_invariant_direction(self):
        # Constant bull market
        h = [float(x + 2) for x in range(100, 150)]
        l = [float(x - 2) for x in range(100, 150)]
        c = [float(x) for x in range(100, 150)]
        res = indicators.supertrend_series(h, l, c, 10, 3.0)
        assert len(res.direction) == 50
        assert all(d in (1, -1) for d in res.direction)
        assert res.direction[-1] == 1


class TestObvAndVwap:
    def test_obv_hand_calculated(self):
        # c = [10, 12, 11, 11, 15], v = [100, 200, 50, 30, 300]
        # obv[0] = 0 (Q-08 sauberer Start)
        # c[1]>c[0] -> +200 -> 200
        # c[2]<c[1] -> -50  -> 150
        # c[3]==c[2]-> +0   -> 150
        # c[4]>c[3] -> +300 -> 450
        c = [10.0, 12.0, 11.0, 11.0, 15.0]
        v = [100.0, 200.0, 50.0, 30.0, 300.0]
        res = indicators.obv_series(c, v)
        assert res == [0.0, 200.0, 150.0, 150.0, 450.0]

    def test_vwap_utc_midnight_reset(self):
        # 2 bars day 1, 2 bars day 2
        day1_ms = 1735689600000  # 2025-01-01 00:00:00 UTC
        day2_ms = 1735776000000  # 2025-01-02 00:00:00 UTC
        ts = [day1_ms, day1_ms + 3600000, day2_ms, day2_ms + 3600000]
        h = [105.0, 110.0, 205.0, 210.0]
        l = [95.0, 100.0, 195.0, 200.0]
        c = [100.0, 105.0, 200.0, 205.0]
        v = [10.0, 10.0, 10.0, 10.0]
        res = indicators.vwap_series(ts, h, l, c, v)
        # Bar 0 (hlc3=100, v=10): vwap = 100.0
        # Bar 1 (hlc3=105, v=10): vwap = (100*10 + 105*10)/20 = 102.5
        # Bar 2 (hlc3=200, v=10, new day): reset -> vwap = 200.0
        # Bar 3 (hlc3=205, v=10): vwap = (200*10 + 205*10)/20 = 202.5
        assert math.isclose(res[0], 100.0)
        assert math.isclose(res[1], 102.5)
        assert math.isclose(res[2], 200.0)
        assert math.isclose(res[3], 202.5)

    def test_vwap_seconds_timestamp_normalization(self):
        # Q-09: Zeitstempel in Sekunden (<1e11) werden automatisch multipliziert
        day1_s = 1735689600
        day2_s = 1735776000
        ts = [day1_s, day2_s]
        h = [105.0, 205.0]
        l = [95.0, 195.0]
        c = [100.0, 200.0]
        v = [10.0, 10.0]
        res = indicators.vwap_series(ts, h, l, c, v)
        assert math.isclose(res[0], 100.0)
        assert math.isclose(res[1], 200.0)  # reset erfolgt


class TestCvd:
    def test_cvd_proxy_labeling_and_range_formula(self):
        # Bar with H=110, L=90, C=105 (Rng=20), V=100
        # Delta = 100 * (2*105 - 110 - 90) / 20 = 100 * 10 / 20 = 50.0
        res = indicators.cvd_series([100.0], [110.0], [90.0], [105.0])
        assert res.is_proxy is True
        assert res.delta[0] == 50.0
        assert res.cvd[0] == 50.0

    def test_cvd_flat_bar_returns_zero_delta(self):
        res = indicators.cvd_series([100.0], [100.0], [100.0], [100.0])
        assert res.delta[0] == 0.0
        assert res.cvd[0] == 0.0


class TestSqueeze:
    def test_squeeze_compression_calculation(self):
        closes = [100.0 + i * 0.1 for i in range(30)]
        atrs = [5.0] * 30
        sqz = indicators.squeeze_metrics_at(closes, atrs, idx=25)
        assert math.isfinite(sqz.compression)
        assert sqz.active is True  # kleine Varianz < Keltner ATR
