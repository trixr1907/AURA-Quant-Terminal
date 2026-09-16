"""Kanonisches Confluence-Scoring, Regime, Makro-Adjust und Radar-Klassifikation.

Dokumentiert in docs/FORMULA_SPEC.md (F15-F25, F47, F60-F65).
Gewichte: Trend 30%, Momentum 25%, Volumen 25%, Struktur 20% (Summe 1.00).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from aura.core.indicators import (
    adx_series,
    atr_series,
    clamp,
    cvd_series,
    ema_series,
    macd_series,
    obv_series,
    rsi_series,
    sma_series,
    squeeze_metrics_at,
    stoch_rsi_series,
    supertrend_series,
    swing_pivots,
    vwap_series,
)

# Standard-Gewichte und Schwellenwerte
W_TREND = 0.30
W_MOM = 0.25
W_VOL = 0.25
W_STR = 0.20

W_FUNDING = 0.10
W_OI = 0.10
W_BASIS = 0.03
MACRO_CAP = 25.0

LONG_TH = 75.0
SHORT_TH = 25.0
MTF_NEED = 3
WARMUP_DEFAULT = 235


def aggregate_confluence_score(
    trend: float, momentum: float, volume: float, structure: float
) -> float:
    """Aggregiert Subscores zu Gesamtscore [0, 100]. Gewichte summieren zu 1.0."""
    return clamp(
        W_TREND * trend + W_MOM * momentum + W_VOL * volume + W_STR * structure,
        0.0,
        100.0,
    )


@dataclass
class FvgZone:
    dir: int  # 1 bull, -1 bear
    top: float
    bot: float
    age: int
    mitigated: bool
    start: int
    end: int | None
    ts_ms: int


@dataclass
class LastBarSummary:
    score: float
    trend: float
    mom: float
    vol: float
    str: float
    dir: int
    st_dir: int
    struct_trend: int
    last_ph: float
    last_pl: float
    atr: float
    adx: float
    rsi: float
    eqh_lvl: float
    eql_lvl: float
    fvg_act: bool
    fvg_dir: int
    fvg_top: float
    fvg_bot: float


@dataclass
class AnalysisResult:
    n: int
    ms: list[int]
    opens: list[float]
    highs: list[float]
    lows: list[float]
    closes: list[float]
    volumes: list[float]
    atr: list[float]
    adx: list[float]
    rsi: list[float]
    srk: list[float]
    e20: list[float]
    e50: list[float]
    e200: list[float]
    st_line: list[float]
    st_dir: list[int]
    vwap: list[float]
    obv: list[float]
    cvd: list[float]
    ema_cvd: list[float]
    cvd_delta: list[float]
    score: list[float]
    trend_s: list[float]
    mom_s: list[float]
    vol_s: list[float]
    str_s: list[float]
    dir_s: list[int]
    last_ph: list[float]
    last_pl: list[float]
    struct_a: list[int]
    eqh_lvl_a: list[float]
    eql_lvl_a: list[float]
    fvg_top_a: list[float]
    fvg_bot_a: list[float]
    fvg_dir_a: list[int]
    fvg_act_a: list[int]
    zones: list[FvgZone] = field(default_factory=list)
    last: LastBarSummary | None = None


def analyze_candles(
    candles: Sequence[dict[str, Any]],
    warmup: int = WARMUP_DEFAULT,
) -> AnalysisResult:
    """Vollstaendige technische Analyse einer Kerzenserie (geschlossene Kerzen)."""
    n = len(candles)
    ms = [int(c.get("t") or c.get("open_time_ms") or 0) for c in candles]
    o = [float(c["o"] if "o" in c else c.get("open", 0.0)) for c in candles]
    h = [float(c["h"] if "h" in c else c.get("high", 0.0)) for c in candles]
    l = [float(c["l"] if "l" in c else c.get("low", 0.0)) for c in candles]
    c = [float(c["c"] if "c" in c else c.get("close", 0.0)) for c in candles]
    v = [float(c["v"] if "v" in c else c.get("volume", 0.0)) for c in candles]

    if n == 0:
        return AnalysisResult(
            n=0,
            ms=[],
            opens=[],
            highs=[],
            lows=[],
            closes=[],
            volumes=[],
            atr=[],
            adx=[],
            rsi=[],
            srk=[],
            e20=[],
            e50=[],
            e200=[],
            st_line=[],
            st_dir=[],
            vwap=[],
            obv=[],
            cvd=[],
            ema_cvd=[],
            cvd_delta=[],
            score=[],
            trend_s=[],
            mom_s=[],
            vol_s=[],
            str_s=[],
            dir_s=[],
            last_ph=[],
            last_pl=[],
            struct_a=[],
            eqh_lvl_a=[],
            eql_lvl_a=[],
            fvg_top_a=[],
            fvg_bot_a=[],
            fvg_dir_a=[],
            fvg_act_a=[],
            zones=[],
            last=None,
        )

    e20 = ema_series(c, 20)
    e50 = ema_series(c, 50)
    e200 = ema_series(c, 200)
    rsi = rsi_series(c, 14)
    srk = stoch_rsi_series(c, 14, 3)
    macd = macd_series(c, 12, 26, 9)
    adx_res = adx_series(h, l, c, 14)
    adx = adx_res.adx
    atr = atr_series(h, l, c, 14)
    st = supertrend_series(h, l, c, 10, 3.0)
    obv = obv_series(c, v)
    eobv = ema_series(obv, 20)
    vwap = vwap_series(ms, h, l, c, v)
    smav = sma_series(v, 20)
    cvd_res = cvd_series(v, h, l, c)
    cvd = cvd_res.cvd
    cvd_delta = cvd_res.delta
    ecvd = ema_series(cvd, 20)
    piv = swing_pivots(h, l, 5, 5)

    score = [50.0] * n
    trend_s = [50.0] * n
    mom_s = [50.0] * n
    vol_s = [50.0] * n
    str_s = [50.0] * n
    dir_s = [0] * n
    last_ph_a = [float("nan")] * n
    last_pl_a = [float("nan")] * n
    eqh_lvl_a = [float("nan")] * n
    eql_lvl_a = [float("nan")] * n
    fvg_top_a = [float("nan")] * n
    fvg_bot_a = [float("nan")] * n
    fvg_dir_a = [0] * n
    fvg_act_a = [0] * n
    struct_a = [1] * n

    struct_trend = 1
    last_ph_v = float("nan")
    last_pl_v = float("nan")
    bos_bull = 99
    bos_bear = 99
    ch_bull = 99
    ch_bear = 99
    fvg_dir = 0
    fvg_top = float("nan")
    fvg_bot = float("nan")
    fvg_act = False
    fvg_age = 99
    ph_pool: list[float] = []
    pl_pool: list[float] = []
    zones: list[FvgZone] = []
    eqh_lvl = float("nan")
    eql_lvl = float("nan")
    pi = 0
    pj = 0

    for i in range(n):
        bos_bull = bos_bull + 1 if bos_bull < 99 else bos_bull
        bos_bear = bos_bear + 1 if bos_bear < 99 else bos_bear
        ch_bull = ch_bull + 1 if ch_bull < 99 else ch_bull
        ch_bear = ch_bear + 1 if ch_bear < 99 else ch_bear

        bull_brk = not math.isnan(last_ph_v) and c[i] > last_ph_v and (i == 0 or c[i - 1] <= last_ph_v)
        bear_brk = not math.isnan(last_pl_v) and c[i] < last_pl_v and (i == 0 or c[i - 1] >= last_pl_v)

        while pi < len(piv.ph) and piv.ph[pi].i == i:
            ev = piv.ph[pi]
            pi += 1
            prev = last_ph_v
            last_ph_v = ev.val
            ph_pool.append(ev.val)
            if len(ph_pool) > 8:
                ph_pool.pop(0)
            if struct_trend == 1 and not math.isnan(prev) and ev.val > prev:
                bos_bull = 0

        while pj < len(piv.pl) and piv.pl[pj].i == i:
            ev = piv.pl[pj]
            pj += 1
            prev = last_pl_v
            last_pl_v = ev.val
            pl_pool.append(ev.val)
            if len(pl_pool) > 8:
                pl_pool.pop(0)
            if struct_trend == -1 and not math.isnan(prev) and ev.val < prev:
                bos_bear = 0

        if bull_brk:
            if struct_trend == -1:
                struct_trend = 1
                ch_bull = 0
            else:
                bos_bull = 0

        if bear_brk:
            if struct_trend == 1:
                struct_trend = -1
                ch_bear = 0
            else:
                bos_bear = 0

        if i >= 2:
            fv_b = l[i] > h[i - 2]
            fv_s = h[i] < l[i - 2]
            if fv_b:
                fvg_dir = 1
                fvg_top = l[i]
                fvg_bot = h[i - 2]
                fvg_act = True
                fvg_age = 0
                zones.insert(
                    0,
                    FvgZone(
                        dir=1,
                        top=fvg_top,
                        bot=fvg_bot,
                        age=0,
                        mitigated=False,
                        start=i,
                        end=None,
                        ts_ms=ms[i],
                    ),
                )
            elif fv_s:
                fvg_dir = -1
                fvg_top = l[i - 2]
                fvg_bot = h[i]
                fvg_act = True
                fvg_age = 0
                zones.insert(
                    0,
                    FvgZone(
                        dir=-1,
                        top=fvg_top,
                        bot=fvg_bot,
                        age=0,
                        mitigated=False,
                        start=i,
                        end=None,
                        ts_ms=ms[i],
                    ),
                )
            elif fvg_act:
                fvg_age = fvg_age + 1 if fvg_age < 99 else fvg_age
                if fvg_dir == 1 and l[i] <= fvg_bot:
                    fvg_act = False
                if fvg_dir == -1 and h[i] >= fvg_top:
                    fvg_act = False

            completed = [z for z in zones if z.mitigated]
            if len(completed) > 8:
                removable = completed[: len(completed) - 8]
                for rz in removable:
                    if rz in zones:
                        zones.remove(rz)

            for z in zones:
                if z.mitigated or z.start >= i:
                    continue
                z.age += 1
                filled = (l[i] <= z.bot) if z.dir == 1 else (h[i] >= z.top)
                if filled:
                    z.mitigated = True
                    z.end = i

        eqh_lvl = float("nan")
        eql_lvl = float("nan")
        if atr[i] > 0 and len(ph_pool) >= 2:
            tol = 0.35 * atr[i]
            found = False
            for a in range(len(ph_pool) - 1):
                for b in range(a + 1, len(ph_pool)):
                    if abs(ph_pool[a] - ph_pool[b]) <= tol and ph_pool[a] > c[i] and ph_pool[b] > c[i]:
                        eqh_lvl = (ph_pool[a] + ph_pool[b]) / 2.0
                        found = True
                        break
                if found:
                    break

        if atr[i] > 0 and len(pl_pool) >= 2:
            tol = 0.35 * atr[i]
            found = False
            for a in range(len(pl_pool) - 1):
                for b in range(a + 1, len(pl_pool)):
                    if abs(pl_pool[a] - pl_pool[b]) <= tol and pl_pool[a] < c[i] and pl_pool[b] < c[i]:
                        eql_lvl = (pl_pool[a] + pl_pool[b]) / 2.0
                        found = True
                        break
                if found:
                    break

        eff_warmup = 30 if n < warmup else warmup
        if i >= eff_warmup:
            ai = (8.0 if e20[i] > e50[i] else -8.0) if adx[i] >= 25 else (-3.0 if adx[i] < 18 else 0.0)
            ts_ = clamp(
                50.0
                + (8.0 if c[i] > e20[i] else -8.0)
                + (8.0 if e20[i] > e50[i] else -8.0)
                + (7.0 if e50[i] > e200[i] else -7.0)
                + (12.0 if st.direction[i] == 1 else -12.0)
                + ai,
                0.0,
                100.0,
            )
            msz = clamp(
                50.0
                + clamp((rsi[i] - 50.0) * 1.5, -30.0, 30.0)
                + (12.0 if macd.macd[i] > macd.signal[i] else -12.0)
                + (8.0 if macd.hist[i] > 0 else -8.0)
                + clamp((srk[i] - 50.0) * 0.8, -20.0, 20.0),
                0.0,
                100.0,
            )
            vref = smav[i] if smav[i] > 0 else v[i]
            is_above_vwap = (c[i] - vwap[i]) > (1e-9 * max(1.0, abs(c[i])))
            vsc = clamp(
                50.0
                + (15.0 if obv[i] > eobv[i] else -15.0)
                + (10.0 if is_above_vwap else -10.0)
                + (clamp((v[i] / vref - 1.0) * 20.0, -10.0, 10.0) * (1.0 if c[i] > o[i] else -1.0))
                + (10.0 if cvd[i] > ecvd[i] else -10.0),
                0.0,
                100.0,
            )
            ssc = clamp(
                50.0
                + (15.0 if bos_bull <= 6 else (-15.0 if bos_bear <= 6 else 0.0))
                + (10.0 if ch_bull <= 6 else (-10.0 if ch_bear <= 6 else 0.0))
                + (
                    10.0
                    if (fvg_act and fvg_dir == 1 and c[i] > fvg_top)
                    else (-10.0 if (fvg_act and fvg_dir == -1 and c[i] < fvg_bot) else 0.0)
                )
                + (7.0 if not math.isnan(eqh_lvl) else (-7.0 if not math.isnan(eql_lvl) else 0.0))
                + (8.0 if struct_trend == 1 else -8.0),
                0.0,
                100.0,
            )
            trend_s[i] = ts_
            mom_s[i] = msz
            vol_s[i] = vsc
            str_s[i] = ssc
            score[i] = aggregate_confluence_score(ts_, msz, vsc, ssc)
            dir_s[i] = 1 if score[i] > 55.0 else (-1 if score[i] < 45.0 else 0)

        last_ph_a[i] = last_ph_v
        last_pl_a[i] = last_pl_v
        struct_a[i] = struct_trend
        eqh_lvl_a[i] = eqh_lvl
        eql_lvl_a[i] = eql_lvl
        fvg_top_a[i] = fvg_top
        fvg_bot_a[i] = fvg_bot
        fvg_dir_a[i] = fvg_dir
        fvg_act_a[i] = 1 if fvg_act else 0

    last_summary = LastBarSummary(
        score=score[n - 1],
        trend=trend_s[n - 1],
        mom=mom_s[n - 1],
        vol=vol_s[n - 1],
        str=str_s[n - 1],
        dir=dir_s[n - 1],
        st_dir=st.direction[n - 1],
        struct_trend=struct_a[n - 1],
        last_ph=last_ph_a[n - 1],
        last_pl=last_pl_a[n - 1],
        atr=atr[n - 1],
        adx=adx[n - 1],
        rsi=rsi[n - 1],
        eqh_lvl=eqh_lvl,
        eql_lvl=eql_lvl,
        fvg_act=fvg_act,
        fvg_dir=fvg_dir,
        fvg_top=fvg_top,
        fvg_bot=fvg_bot,
    )

    return AnalysisResult(
        n=n,
        ms=ms,
        opens=o,
        highs=h,
        lows=l,
        closes=c,
        volumes=v,
        atr=atr,
        adx=adx,
        rsi=rsi,
        srk=srk,
        e20=e20,
        e50=e50,
        e200=e200,
        st_line=st.line,
        st_dir=st.direction,
        vwap=vwap,
        obv=obv,
        cvd=cvd,
        ema_cvd=ecvd,
        cvd_delta=cvd_delta,
        score=score,
        trend_s=trend_s,
        mom_s=mom_s,
        vol_s=vol_s,
        str_s=str_s,
        dir_s=dir_s,
        last_ph=last_ph_a,
        last_pl=last_pl_a,
        struct_a=struct_a,
        eqh_lvl_a=eqh_lvl_a,
        eql_lvl_a=eql_lvl_a,
        fvg_top_a=fvg_top_a,
        fvg_bot_a=fvg_bot_a,
        fvg_dir_a=fvg_dir_a,
        fvg_act_a=fvg_act_a,
        zones=zones,
        last=last_summary,
    )


@dataclass(frozen=True)
class RegimeInfo:
    reg: int  # 1 bull, -1 bear, 0 sideways
    txt: str
    is_sqz: bool


def regime_of(analysis: AnalysisResult, idx: int | None = None) -> RegimeInfo:
    """Regime-Klassifikation am angegebenen oder letzten Bar (F47)."""
    n = analysis.n
    if n == 0:
        return RegimeInfo(reg=0, txt="SIDEWAYS", is_sqz=False)
    i = (n - 1) if idx is None else idx
    c = analysis.closes[i]
    e50 = analysis.e50[i]
    e200 = analysis.e200[i]
    adx_val = analysis.adx[i] if i < len(analysis.adx) else 20.0

    eps = max(1e-12, abs(e200) * 1e-12)
    bull = c > (e200 + eps) and e50 > (e200 + eps)
    bear = c < (e200 - eps) and e50 < (e200 - eps)

    sqz = squeeze_metrics_at(analysis.closes, analysis.atr, i)
    if sqz.active:
        return RegimeInfo(reg=0, txt="SIDEWAYS·SQZ", is_sqz=True)
    if bull and adx_val >= 20.0:
        return RegimeInfo(reg=1, txt="BULL", is_sqz=False)
    if bear and adx_val >= 20.0:
        return RegimeInfo(reg=-1, txt="BEAR", is_sqz=False)
    if bull:
        return RegimeInfo(reg=1, txt="BULL (schwach)", is_sqz=False)
    if bear:
        return RegimeInfo(reg=-1, txt="BEAR (schwach)", is_sqz=False)
    return RegimeInfo(reg=0, txt="SIDEWAYS", is_sqz=False)


@dataclass(frozen=True)
class DynamicTp1:
    price: float
    r_multiple: float
    source: str


def dynamic_tp1_at(
    analysis: AnalysisResult,
    idx: int,
    direction: int,
    entry: float,
    r: float,
) -> DynamicTp1:
    """Dynamischer TP1 auf EQH/EQL oder FVG in [1.0R, 2.0R), Fallback 2.0R (F25, F62)."""
    fixed = entry + direction * 2.0 * r
    if r <= 0:
        return DynamicTp1(price=fixed, r_multiple=2.0, source="2R")

    candidates: list[DynamicTp1] = []

    def _add(price: float, source: str) -> None:
        if math.isnan(price) or price <= 0:
            return
        rm = direction * (price - entry) / r
        if 1.0 <= rm < 2.0:
            candidates.append(DynamicTp1(price=price, r_multiple=rm, source=source))

    if direction == 1:
        if idx < len(analysis.eqh_lvl_a):
            _add(analysis.eqh_lvl_a[idx], "EQH")
        if (
            idx < len(analysis.fvg_act_a)
            and analysis.fvg_act_a[idx] == 1
            and analysis.fvg_dir_a[idx] == -1
        ):
            _add(analysis.fvg_bot_a[idx], "Opposing FVG")
    else:
        if idx < len(analysis.eql_lvl_a):
            _add(analysis.eql_lvl_a[idx], "EQL")
        if (
            idx < len(analysis.fvg_act_a)
            and analysis.fvg_act_a[idx] == 1
            and analysis.fvg_dir_a[idx] == 1
        ):
            _add(analysis.fvg_top_a[idx], "Opposing FVG")

    if not candidates:
        return DynamicTp1(price=fixed, r_multiple=2.0, source="2R")
    candidates.sort(key=lambda c: c.r_multiple)
    return candidates[0]


@dataclass(frozen=True)
class MacroAdjustment:
    total: float
    fg_adj: float
    fund_adj: float
    oi_adj: float
    basis_adj: float
    macro_adj: float
    funding_extreme: bool
    oi_spike: bool
    veto: bool


def macro_adjust(
    core: float,
    fg: float = 50.0,
    fund_bias: float = 0.0,
    funding_z: float = 0.0,
    oi_bias: float = 0.0,
    oi_spike: bool = False,
    basis_bias: float = 0.0,
    mtf_bonus: float = 0.0,
) -> MacroAdjustment:
    """Makro-Anpassung des Core-Scores (F23, F65)."""
    fg_adj = clamp((fg - 50.0) * 0.08, -4.0, 4.0)
    funding_extreme = abs(funding_z) > 2.5
    fund_adj = clamp(
        fund_bias * W_FUNDING,
        -25.0 if funding_extreme else -10.0,
        25.0 if funding_extreme else 10.0,
    )
    oi_adj = clamp(oi_bias * W_OI, -25.0 if oi_spike else -10.0, 25.0 if oi_spike else 10.0)
    basis_adj = clamp(basis_bias * W_BASIS, -3.0, 3.0)
    macro_adj_val = clamp(fund_adj + oi_adj, -MACRO_CAP, MACRO_CAP)
    total = clamp(
        core + (fg_adj if core >= 50.0 else -fg_adj) + macro_adj_val + basis_adj + mtf_bonus,
        0.0,
        100.0,
    )
    runner_score = 85.0
    weak_technical = (LONG_TH <= core < runner_score) or (SHORT_TH >= core > (100.0 - runner_score))
    veto = weak_technical and ((core >= 50.0 and total < LONG_TH) or (core < 50.0 and total > SHORT_TH))
    return MacroAdjustment(
        total=total,
        fg_adj=fg_adj,
        fund_adj=fund_adj,
        oi_adj=oi_adj,
        basis_adj=basis_adj,
        macro_adj=macro_adj_val,
        funding_extreme=funding_extreme,
        oi_spike=bool(oi_spike),
        veto=veto,
    )


@dataclass(frozen=True)
class FundingBias:
    rate: float
    z: float
    pos_streak: int
    neg_streak: int
    bias: float
    txt: str


def calc_funding_bias(raw_rates: Sequence[float | dict[str, Any]]) -> FundingBias:
    """Funding Rate Z-Score und Bias (F20)."""
    if len(raw_rates) < 5:
        return FundingBias(rate=0.0, z=0.0, pos_streak=0, neg_streak=0, bias=0.0, txt="—")
    rates = [
        float(r if isinstance(r, (int, float)) else r.get("fundingRate", 0.0)) for r in raw_rates
    ]
    n = len(rates)
    current_rate = rates[n - 1]
    mean = sum(rates) / float(n)
    variance = sum((r - mean) ** 2 for r in rates) / float(n)  # Populationsvarianz (Paritaet)
    std = math.sqrt(variance)
    funding_z = (current_rate - mean) / std if std > 1e-8 else 0.0

    pos_streak = 0
    neg_streak = 0
    for i in range(n - 1, -1, -1):
        if rates[i] > 0:
            if neg_streak == 0:
                pos_streak += 1
        elif rates[i] < 0:
            if pos_streak == 0:
                neg_streak += 1
        else:
            break

    bias = 0.0
    txt = "NEUTRAL"
    if funding_z > 1.5:
        bias = clamp(-(funding_z - 1.5) * 35.0 - 30.0 - (20.0 if pos_streak >= 6 else 0.0), -100.0, 0.0)
        txt = "SHORT-BIAS (Long-Crowding)"
    elif funding_z < -1.5:
        bias = clamp(-(funding_z + 1.5) * 35.0 + 30.0 + (20.0 if neg_streak >= 6 else 0.0), 0.0, 100.0)
        txt = "LONG-BIAS (Short-Squeeze-Gefahr)"
    elif pos_streak >= 6:
        bias = -25.0
        txt = "SHORT-BIAS (6x Positiv-Streak)"
    elif neg_streak >= 6:
        bias = 25.0
        txt = "LONG-BIAS (6x Negativ-Streak)"

    return FundingBias(
        rate=current_rate,
        z=funding_z,
        pos_streak=pos_streak,
        neg_streak=neg_streak,
        bias=bias,
        txt=txt,
    )


@dataclass(frozen=True)
class OpenInterestBias:
    latest: float
    chg_4h: float
    chg_24h: float
    quadrant: str
    bias: float


def calc_oi_bias(
    oi_hist: Sequence[dict[str, Any]],
    current_price: float | None,
    price_4h_ago: float | None,
) -> OpenInterestBias:
    """Open-Interest Quadrantenanalyse (F21)."""
    if len(oi_hist) < 5:
        return OpenInterestBias(
            latest=0.0, chg_4h=0.0, chg_24h=0.0, quadrant="Konsolidierung", bias=0.0
        )
    n = len(oi_hist)
    latest = float(oi_hist[n - 1].get("sumOpenInterest") or oi_hist[n - 1].get("openInterest") or 0.0)
    idx_4h = max(0, n - 1 - 4)
    idx_24h = max(0, n - 1 - 24)
    oi4 = float(oi_hist[idx_4h].get("sumOpenInterest") or oi_hist[idx_4h].get("openInterest") or latest)
    oi24 = float(
        oi_hist[idx_24h].get("sumOpenInterest") or oi_hist[idx_24h].get("openInterest") or latest
    )
    chg4h = ((latest - oi4) / oi4 * 100.0) if oi4 > 0 else 0.0
    chg24h = ((latest - oi24) / oi24 * 100.0) if oi24 > 0 else 0.0

    p_change_4h = (
        ((current_price - price_4h_ago) / price_4h_ago * 100.0)
        if (current_price and price_4h_ago and price_4h_ago > 0)
        else 0.0
    )

    quadrant = "Konsolidierung"
    bias = 0.0
    if chg4h > 5.0 and abs(p_change_4h) < 0.5:
        quadrant = "OI-Spike / Topping-Warnung"
        bias = -50.0
    elif p_change_4h >= 0.1 and chg4h >= 0.5:
        quadrant = "Long Build-Up (Bull-Trend)"
        bias = min(100.0, 50.0 + chg4h * 5.0)
    elif p_change_4h <= -0.1 and chg4h >= 0.5:
        quadrant = "Short Build-Up (Bear-Trend)"
        bias = max(-100.0, -50.0 - chg4h * 5.0)
    elif p_change_4h >= 0.1 and chg4h <= -0.5:
        quadrant = "Short Covering (Schwache Rally)"
        bias = 15.0
    elif p_change_4h <= -0.1 and chg4h <= -0.5:
        quadrant = "Long Unwinding (Schwacher Abverkauf)"
        bias = -15.0

    return OpenInterestBias(
        latest=latest, chg_4h=chg4h, chg_24h=chg24h, quadrant=quadrant, bias=bias
    )


@dataclass(frozen=True)
class BasisBias:
    val: float
    bias: float
    txt: str


def calc_basis_bias(
    mark_price: float, index_price: float, threshold: float = 0.0005
) -> BasisBias:
    """Spot-Perp-Basis (F22)."""
    if not (mark_price > 0 and index_price > 0):
        return BasisBias(val=0.0, bias=0.0, txt="Fair")
    val = (mark_price - index_price) / index_price
    txt = "Fair"
    bias = 0.0
    if val > threshold:
        txt = "Premium (Long-Crowding)"
        bias = clamp(-val / 0.001 * 50.0, -100.0, 0.0)
    elif val < -threshold:
        txt = "Discount (Short-Crowding)"
        bias = clamp(-val / 0.001 * 50.0, 0.0, 100.0)
    return BasisBias(val=val, bias=bias, txt=txt)
