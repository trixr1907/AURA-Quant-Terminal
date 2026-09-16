"""Kanonische technische Indikatoren (aura.core.indicators).

Deterministisch, reine Funktionen, float/int-basiert.
Absicherung gegen Nullteiler, leere Arrays, NaN/Inf.
Dokumentiert in docs/FORMULA_SPEC.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


def clamp(val: float, low: float, high: float) -> float:
    if math.isnan(val):
        return low
    return max(low, min(high, val))


def ema_series(src: Sequence[float], period: int) -> list[float]:
    """Exponential Moving Average. Warmup >= 3*period empfohlen."""
    n = len(src)
    if n == 0 or period <= 0:
        return [0.0] * n
    out = [0.0] * n
    k = 2.0 / (period + 1.0)
    e = float(src[0])
    out[0] = e
    for i in range(1, n):
        e = float(src[i]) * k + e * (1.0 - k)
        out[i] = e
    return out


def sma_series(src: Sequence[float], period: int) -> list[float]:
    """Simple Moving Average. Vor Index period-1 wird 0.0 geliefert."""
    n = len(src)
    out = [0.0] * n
    if n == 0 or period <= 0:
        return out
    s = 0.0
    for i in range(n):
        s += float(src[i])
        if i >= period:
            s -= float(src[i - period])
        if i >= period - 1:
            out[i] = s / float(period)
    return out


def rsi_series(closes: Sequence[float], period: int = 14) -> list[float]:
    """Relative Strength Index mit Wilder-Smoothing.

    Guards: Division durch 0 (Loss=0) -> 100 bzw. 50 bei Flatline.
    """
    n = len(closes)
    out = [50.0] * n
    if n < period + 1 or period <= 0:
        return out
    g = 0.0
    l = 0.0
    for i in range(1, period + 1):
        d = float(closes[i]) - float(closes[i - 1])
        if d > 0:
            g += d
        else:
            l -= d
    g /= float(period)
    l /= float(period)
    out[period] = 100.0 - 100.0 / (1.0 + g / l) if l > 0 else (100.0 if g > 0 else 50.0)

    for i in range(period + 1, n):
        d = float(closes[i]) - float(closes[i - 1])
        gain = d if d > 0 else 0.0
        loss = -d if d < 0 else 0.0
        g = (g * (period - 1) + gain) / float(period)
        l = (l * (period - 1) + loss) / float(period)
        out[i] = 100.0 - 100.0 / (1.0 + g / l) if l > 0 else (100.0 if g > 0 else 50.0)
    return out


def atr_series(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14
) -> list[float]:
    """Average True Range mit Wilder-Smoothing."""
    n = len(closes)
    out = [0.0] * n
    if n < period + 1 or period <= 0:
        return out
    tr = [0.0] * n
    tr[0] = float(highs[0]) - float(lows[0])
    for i in range(1, n):
        h_l = float(highs[i]) - float(lows[i])
        h_cp = abs(float(highs[i]) - float(closes[i - 1]))
        l_cp = abs(float(lows[i]) - float(closes[i - 1]))
        tr[i] = max(h_l, h_cp, l_cp)
    s = sum(tr[1 : period + 1])
    out[period] = s / float(period)
    for i in range(period + 1, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / float(period)
    return out


@dataclass(frozen=True)
class AdxResult:
    adx: list[float]
    di_plus: list[float]
    di_minus: list[float]


def adx_series(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14
) -> AdxResult:
    """Average Directional Index (Wilder DMI/ADX)."""
    n = len(closes)
    adx = [0.0] * n
    dp = [0.0] * n
    dm = [0.0] * n
    if n < 2 * period + 1 or period <= 0:
        return AdxResult(adx=adx, di_plus=dp, di_minus=dm)

    tr = [0.0] * n
    pdm = [0.0] * n
    ndm = [0.0] * n
    for i in range(1, n):
        up = float(highs[i]) - float(highs[i - 1])
        dn = float(lows[i - 1]) - float(lows[i])
        pdm[i] = up if (up > dn and up > 0) else 0.0
        ndm[i] = dn if (dn > up and dn > 0) else 0.0
        h_l = float(highs[i]) - float(lows[i])
        h_cp = abs(float(highs[i]) - float(closes[i - 1]))
        l_cp = abs(float(lows[i]) - float(closes[i - 1]))
        tr[i] = max(h_l, h_cp, l_cp)

    atr_val = sum(tr[1 : period + 1])
    pd = sum(pdm[1 : period + 1])
    nd = sum(ndm[1 : period + 1])

    dxs = [0.0] * n
    dp[period] = 100.0 * pd / atr_val if atr_val > 0 else 0.0
    dm[period] = 100.0 * nd / atr_val if atr_val > 0 else 0.0
    sum_di = dp[period] + dm[period]
    dxs[period] = 100.0 * abs(dp[period] - dm[period]) / sum_di if sum_di > 0 else 0.0

    for i in range(period + 1, n):
        atr_val = atr_val - atr_val / float(period) + tr[i]
        pd = pd - pd / float(period) + pdm[i]
        nd = nd - nd / float(period) + ndm[i]
        pv = 100.0 * pd / atr_val if atr_val > 0 else 0.0
        nv = 100.0 * nd / atr_val if atr_val > 0 else 0.0
        dp[i] = pv
        dm[i] = nv
        di_sum = pv + nv
        dxs[i] = 100.0 * abs(pv - nv) / di_sum if di_sum > 0 else 0.0

    sdx = sum(dxs[period : 2 * period])
    adx[2 * period - 1] = sdx / float(period)
    for i in range(2 * period, n):
        adx[i] = (adx[i - 1] * (period - 1) + dxs[i]) / float(period)

    return AdxResult(adx=adx, di_plus=dp, di_minus=dm)


@dataclass(frozen=True)
class MacdResult:
    macd: list[float]
    signal: list[float]
    hist: list[float]


def macd_series(
    closes: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> MacdResult:
    """MACD (12, 26, 9)."""
    n = len(closes)
    e_fast = ema_series(closes, fast)
    e_slow = ema_series(closes, slow)
    macd = [e_fast[i] - e_slow[i] for i in range(n)]
    sig = ema_series(macd, signal)
    hist = [macd[i] - sig[i] for i in range(n)]
    return MacdResult(macd=macd, signal=sig, hist=hist)


def stoch_rsi_series(closes: Sequence[float], period: int = 14, smooth: int = 3) -> list[float]:
    """Stochastic RSI (14, 3)."""
    n = len(closes)
    r = rsi_series(closes, period)
    st = [50.0] * n
    for i in range(n):
        if i < period:
            st[i] = 50.0
            continue
        window = r[i - period + 1 : i + 1]
        lo = min(window)
        hi = max(window)
        st[i] = ((r[i] - lo) / (hi - lo) * 100.0) if (hi - lo) > 0 else 50.0
    return sma_series(st, smooth)


@dataclass(frozen=True)
class SuperTrendResult:
    line: list[float]
    direction: list[int]  # 1 bull, -1 bear


def supertrend_series(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 10,
    multiplier: float = 3.0,
) -> SuperTrendResult:
    """SuperTrend (10, 3.0)."""
    n = len(closes)
    if n == 0:
        return SuperTrendResult(line=[], direction=[])
    at = atr_series(highs, lows, closes, period)
    line = [0.0] * n
    direction = [1] * n
    f_up = float("nan")
    f_dn = float("nan")
    st = float("nan")
    d = 1

    for i in range(n):
        mid = (float(highs[i]) + float(lows[i])) / 2.0
        up = mid + multiplier * at[i]
        dn = mid - multiplier * at[i]
        up_prev = f_up
        dn_prev = f_dn

        if math.isnan(f_up):
            f_up = up
        elif up < f_up or (i > 0 and float(closes[i - 1]) > f_up):
            f_up = up
        else:
            pass

        if math.isnan(f_dn):
            f_dn = dn
        elif dn > f_dn or (i > 0 and float(closes[i - 1]) < f_dn):
            f_dn = dn
        else:
            pass

        st_prev = st
        if math.isnan(st_prev):
            st = f_dn
        elif st_prev == up_prev:
            st = f_dn if float(closes[i]) > f_up else f_up
        else:
            st = f_up if float(closes[i]) < f_dn else f_dn

        if st_prev != st and not math.isnan(st):
            d = 1 if float(closes[i]) > st else -1

        line[i] = st
        direction[i] = d

    return SuperTrendResult(line=line, direction=direction)


def obv_series(closes: Sequence[float], volumes: Sequence[float]) -> list[float]:
    """On-Balance Volume (F09). Behebt Q-08 (sauberer Start bei i=0)."""
    n = len(closes)
    out = [0.0] * n
    if n == 0:
        return out
    o = 0.0
    out[0] = 0.0
    for i in range(1, n):
        c_curr = float(closes[i])
        c_prev = float(closes[i - 1])
        v = float(volumes[i])
        if c_curr > c_prev:
            o += v
        elif c_curr < c_prev:
            o -= v
        out[i] = o
    return out


def vwap_series(
    timestamps_ms: Sequence[int],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
) -> list[float]:
    """Volume Weighted Average Price mit UTC-Mitternachtsreset (F10).

    Behebt Q-09: automatische Normalisierung von Sekunden-Zeitstempeln (<1e11).
    """
    n = len(closes)
    out = [0.0] * n
    if n == 0:
        return out
    pv = 0.0
    vv = 0.0
    last_day = -1
    for i in range(n):
        ts = int(timestamps_ms[i])
        if ts < 100_000_000_000:
            ts *= 1000
        day = ts // 86_400_000
        if day != last_day:
            pv = 0.0
            vv = 0.0
            last_day = day
        hlc3 = (float(highs[i]) + float(lows[i]) + float(closes[i])) / 3.0
        v = float(volumes[i])
        pv += hlc3 * v
        vv += v
        out[i] = pv / vv if vv > 0 else hlc3
    return out


@dataclass(frozen=True)
class CvdResult:
    cvd: list[float]
    delta: list[float]
    is_proxy: bool = True  # Mandat §6: Range-Approximation explizit als Proxy markiert


def cvd_series(
    volumes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
) -> CvdResult:
    """Cumulative Volume Delta Range-Approximation (Proxy, F11)."""
    n = len(volumes)
    cvd = [0.0] * n
    delta = [0.0] * n
    cum = 0.0
    for i in range(n):
        rng = float(highs[i]) - float(lows[i])
        v = float(volumes[i])
        c = float(closes[i])
        h = float(highs[i])
        l = float(lows[i])
        bar_delta = v * (2.0 * c - h - l) / rng if rng > 0 else 0.0
        delta[i] = bar_delta
        cum += bar_delta
        cvd[i] = cum
    return CvdResult(cvd=cvd, delta=delta, is_proxy=True)


@dataclass(frozen=True)
class PivotPoint:
    i: int
    val: float


@dataclass(frozen=True)
class PivotResult:
    ph: list[PivotPoint]
    pl: list[PivotPoint]


def swing_pivots(
    highs: Sequence[float], lows: Sequence[float], left: int = 5, right: int = 5
) -> PivotResult:
    """Swing Pivots (F12). Bestaetigung erst nach right Bars (kein Lookahead)."""
    n = len(highs)
    ph: list[PivotPoint] = []
    pl: list[PivotPoint] = []
    for i in range(left, n - right):
        hv = float(highs[i])
        ok = True
        for j in range(i - left, i):
            if float(highs[j]) > hv:
                ok = False
                break
        if ok:
            for j in range(i + 1, i + right + 1):
                if float(highs[j]) >= hv:
                    ok = False
                    break
        if ok:
            ph.append(PivotPoint(i=i + right, val=hv))

        lv = float(lows[i])
        ok = True
        for j in range(i - left, i):
            if float(lows[j]) < lv:
                ok = False
                break
        if ok:
            for j in range(i + 1, i + right + 1):
                if float(lows[j]) <= lv:
                    ok = False
                    break
        if ok:
            pl.append(PivotPoint(i=i + right, val=lv))

    return PivotResult(ph=ph, pl=pl)


@dataclass(frozen=True)
class SqueezeMetrics:
    active: bool
    bb_upper: float
    bb_lower: float
    kc_upper: float
    kc_lower: float
    compression: float


def squeeze_metrics_at(
    closes: Sequence[float],
    atrs: Sequence[float],
    idx: int | None = None,
    period: int = 20,
) -> SqueezeMetrics:
    """Bollinger Bands vs Keltner Channel Squeeze-Kompression (F24)."""
    n = len(closes)
    i = (n - 1) if idx is None else idx
    nan_m = SqueezeMetrics(
        active=False,
        bb_upper=float("nan"),
        bb_lower=float("nan"),
        kc_upper=float("nan"),
        kc_lower=float("nan"),
        compression=float("nan"),
    )
    if i < period or i >= n:
        return nan_m

    window = [float(closes[k]) for k in range(i - period + 1, i + 1)]
    m = sum(window) / float(period)
    s2 = sum((x - m) ** 2 for x in window)
    sd = math.sqrt(s2 / float(period))  # Populationsvarianz (Paritaet zu JS/Pine)
    bb_w = (2.0 * sd) / (m if m != 0 else 1.0)

    at = float(atrs[i]) if i < len(atrs) else 0.0
    kc_w = (2.0 * 2.0 * at) / (m if m != 0 else 1.0)
    bb_upper = m + 2.0 * sd
    bb_lower = m - 2.0 * sd
    kc_upper = m + 2.0 * at
    kc_lower = m - 2.0 * at
    active = (bb_w < kc_w) and (at > 0)
    comp = (bb_w / kc_w) if kc_w > 0 else float("nan")

    return SqueezeMetrics(
        active=active,
        bb_upper=bb_upper,
        bb_lower=bb_lower,
        kc_upper=kc_upper,
        kc_lower=kc_lower,
        compression=comp,
    )
