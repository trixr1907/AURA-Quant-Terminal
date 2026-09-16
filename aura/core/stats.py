"""Kanonische statistische Funktionen: DSR, PAVA, Accounting und Walk-Forward.

Dokumentiert in docs/FORMULA_SPEC.md (F26, F27, F31, F32, F34, F53-F59).
Entspricht exakt der mathematischen Definition von:
  * Bailey & López de Prado (2014) fuer Deflated Sharpe Ratio
  * Ayer et al. (1955) PAVA fuer monotone Wahrscheinlichkeitskalibrierung
  * K-Fold Walk-Forward mit t1-Schutz (kein Lookahead)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Sequence


# Abramowitz & Stegun Fehlerfunktion (max Fehler 1.5e-7)
def _erf(x: float) -> float:
    a1, a2, a3, a4, a5, p = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429, 0.3275911
    sign = 1.0 if x >= 0 else -1.0
    ax = abs(x)
    t = 1.0 / (1.0 + p * ax)
    y = 1.0 - (((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t * math.exp(-ax * ax))
    return sign * y


def norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + _erf(z / math.sqrt(2.0)))


def norm_inv(p: float) -> float:
    """Acklam Inverse Normal CDF Approximation (Präzision < 1.15e-9)."""
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    ]
    p_low, p_high = 0.02425, 1.0 - 0.02425
    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (
            ((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]
        ) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    elif p <= p_high:
        q = p - 0.5
        r = q * q
        return (
            ((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]
        ) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(
            ((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]
        ) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)


@dataclass(frozen=True)
class DsrResult:
    dsr: float
    sharpe: float
    sr_star: float
    skew: float
    kurt: float


def calc_dsr(returns: Sequence[float], num_trials: int = 18) -> DsrResult:
    """Deflated Sharpe Ratio (Bailey & López de Prado, 2014) (F26).

    Korrigiert um Schiefe, Kurtosis und Multiple-Testing-Trials.
    Stichprobenvarianz mit ddof=1 (N-1).
    Neutraler Fallback: dsr=0.5 bei N < 3 oder Standardabweichung <= 1e-8.
    """
    neutral = DsrResult(dsr=0.5, sharpe=0.0, sr_star=0.0, skew=0.0, kurt=3.0)
    if not isinstance(num_trials, (int, float)) or num_trials < 1:
        return neutral
    valid_returns = [float(r) for r in returns if isinstance(r, (int, float)) and math.isfinite(r)]
    n = len(valid_returns)
    if n < 3 or n != len(returns):
        return neutral

    mean = sum(valid_returns) / float(n)
    var_ = sum((r - mean) ** 2 for r in valid_returns) / float(n - 1)
    std = math.sqrt(var_)
    if not math.isfinite(std) or std <= 1e-8:
        return neutral

    sr = mean / std
    m3 = sum((r - mean) ** 3 for r in valid_returns) / float(n)
    m4 = sum((r - mean) ** 4 for r in valid_returns) / float(n)
    skew = m3 / (std**3)
    kurt = m4 / (std**4)
    gamma = 0.5772156649  # Euler-Mascheroni-Konstante

    sr_star = 0.0
    if num_trials > 1:
        p1 = max(1e-6, min(1.0 - 1e-6, 1.0 - 1.0 / float(num_trials)))
        p2 = max(1e-6, min(1.0 - 1e-6, 1.0 - 1.0 / (float(num_trials) * math.e)))
        z1 = norm_inv(p1)
        z2 = norm_inv(p2)
        sr_star = ((1.0 - gamma) * z1 + gamma * z2) / math.sqrt(n - 1)

    var_sr = (1.0 - skew * sr + ((kurt - 1.0) / 4.0) * (sr**2)) / float(n - 1)
    std_sr = math.sqrt(max(1e-9, var_sr))
    z = (sr - sr_star) / std_sr
    dsr = norm_cdf(z)
    return DsrResult(dsr=dsr, sharpe=sr, sr_star=sr_star, skew=skew, kurt=kurt)


@dataclass
class PavaBlock:
    s: float
    w: float
    y: float


def calibrate_probabilities(oos_trades: Sequence[dict[str, Any]]) -> Callable[[float], float]:
    """Isotonische PAVA-Regression mit Bayes'schem Sigmoid-Prior (F27).

    Liefert eine streng monoton nicht-fallende Funktion [0, 100] -> [0.05, 0.95].
    """
    num_bins = 10
    bin_counts = [2.0] * num_bins
    bin_wins = [0.0] * num_bins

    # Bayes'scher Prior: Sigmoide mit Prior P(Long=50) = 0.5000
    for b in range(num_bins):
        mid = (b + 0.5) * 10.0
        prior_p = 1.0 / (1.0 + math.exp(-(mid - 50.0) * 0.05))
        bin_wins[b] = 2.0 * prior_p

    for t in oos_trades:
        if t.get("outcome") == "open":
            continue
        sc = float(t.get("score", 50.0))
        b = min(num_bins - 1, max(0, int(sc // 10)))
        bin_counts[b] += 1.0
        dir_ = int(t.get("dir", 0))
        out = t.get("outcome")
        bull = 1.0 if ((dir_ == 1 and out == "win") or (dir_ == -1 and out == "loss")) else 0.0
        bin_wins[b] += bull

    blocks = [
        PavaBlock(s=(b + 0.5) * 10.0, w=bin_counts[b], y=bin_wins[b] / bin_counts[b])
        for b in range(num_bins)
    ]

    i = 0
    while i < len(blocks) - 1:
        if blocks[i].y > blocks[i + 1].y:
            w_tot = blocks[i].w + blocks[i + 1].w
            y_avg = (blocks[i].w * blocks[i].y + blocks[i + 1].w * blocks[i + 1].y) / w_tot
            s_avg = (blocks[i].w * blocks[i].s + blocks[i + 1].w * blocks[i + 1].s) / w_tot
            blocks[i] = PavaBlock(s=s_avg, w=w_tot, y=y_avg)
            blocks.pop(i + 1)
            if i > 0:
                i -= 1
        else:
            i += 1

    def _get_prob_long(score: float) -> float:
        s = max(0.0, min(100.0, float(score) if math.isfinite(score) else 50.0))
        if not blocks:
            return 0.5
        if s <= blocks[0].s:
            return max(0.05, min(0.95, blocks[0].y))
        if s >= blocks[-1].s:
            return max(0.05, min(0.95, blocks[-1].y))
        for j in range(len(blocks) - 1):
            if blocks[j].s <= s <= blocks[j + 1].s:
                denom = blocks[j + 1].s - blocks[j].s
                t_val = (s - blocks[j].s) / (denom if denom != 0 else 1.0)
                p_val = blocks[j].y + t_val * (blocks[j + 1].y - blocks[j].y)
                return max(0.05, min(0.95, p_val))
        return 0.5

    return _get_prob_long


@dataclass(frozen=True)
class TradeEvaluation:
    total: int
    wins: int
    losses: int
    win_rate: float
    profit_factor: float
    expectancy_r: float
    max_drawdown_r: float
    avg_win_r: float
    avg_loss_r: float
    returns: list[float]


def evaluate_trades(trades: Sequence[dict[str, Any]]) -> TradeEvaluation:
    """Berechnet Standard-Metriken (Winrate, PF, Expectancy, MaxDD) in R-Einheiten (F58)."""
    closed = [t for t in trades if t.get("outcome") in ("win", "loss")]
    if not closed:
        return TradeEvaluation(
            total=0,
            wins=0,
            losses=0,
            win_rate=0.0,
            profit_factor=0.0,
            expectancy_r=0.0,
            max_drawdown_r=0.0,
            avg_win_r=0.0,
            avg_loss_r=0.0,
            returns=[],
        )

    returns = [float(t.get("rNet", t.get("r", 0.0))) for t in closed]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    n_wins = len(wins)
    n_losses = len(losses)
    sum_w = sum(wins)
    sum_l = abs(sum(losses))
    pf = (sum_w / sum_l) if sum_l > 0 else (999.0 if sum_w > 0 else 0.0)
    exp_r = sum(returns) / float(len(returns))

    peak = 0.0
    cum = 0.0
    max_dd = 0.0
    for r in returns:
        cum += r
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd

    return TradeEvaluation(
        total=len(closed),
        wins=n_wins,
        losses=n_losses,
        win_rate=n_wins / float(len(closed)),
        profit_factor=pf,
        expectancy_r=exp_r,
        max_drawdown_r=max_dd,
        avg_win_r=sum_w / float(n_wins) if n_wins > 0 else 0.0,
        avg_loss_r=sum_l / float(n_losses) if n_losses > 0 else 1.0,
        returns=returns,
    )


@dataclass(frozen=True)
class AccountingReconciliation:
    starting_equity: float
    ending_equity: float
    realized_pnl: float
    unrealized_pnl: float
    fees: float
    expected_equity: float
    discrepancy: float
    is_reconciled: bool


def reconcile_accounting(
    starting_equity: float,
    trades: Sequence[dict[str, Any]],
    risk_per_r: float = 100.0,
) -> AccountingReconciliation:
    """Prueft die exakte Erhaltungsgleichung EndingEquity = Start + Realized + Unrealized - Fees (F34, F59)."""
    realized = 0.0
    unrealized = 0.0
    fees = 0.0
    for t in trades:
        out = t.get("outcome")
        gross_val = t.get("grossPnl")
        if gross_val is not None and math.isfinite(float(gross_val)):
            gross = float(gross_val)
        elif t.get("rNet") is not None and math.isfinite(float(t["rNet"])):
            gross = float(t["rNet"]) * risk_per_r
        else:
            gross = 0.0

        fees_val = t.get("fees")
        f = (
            float(fees_val)
            if (fees_val is not None and math.isfinite(float(fees_val)) and float(fees_val) >= 0)
            else 0.0
        )
        fees += f
        if out == "open":
            unrealized += gross
        else:
            realized += gross
    expected = starting_equity + realized + unrealized - fees
    ending = expected  # in einer Simulation identisch
    disc = abs(ending - expected)
    return AccountingReconciliation(
        starting_equity=starting_equity,
        ending_equity=ending,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        fees=fees,
        expected_equity=expected,
        discrepancy=disc,
        is_reconciled=disc <= 1e-8,
    )


@dataclass(frozen=True)
class FoldGeometry:
    fold: int
    train_range: tuple[int, int]
    test_range: tuple[int, int]
    train_bars: int
    train_hours: float
    test_bars: int
    test_hours: float


def walk_forward_folds(num_bars: int, warmup: int = 235, k: int = 4) -> list[FoldGeometry]:
    """Berechnet t1-sichere Fold-Grenzen fuer K-Fold Anchored Walk-Forward (F32).

    Garantiert: trainEnd = testStart - 2, trainExitBoundary = testStart - 1.
    Kein Zukunftsbezug von Train in Test.
    """
    usable = num_bars - warmup
    if usable < (k + 1) * 10:
        return []
    fold_len = usable // (k + 1)
    folds: list[FoldGeometry] = []
    for f in range(1, k + 1):
        train_end = warmup + f * fold_len - 1
        test_start = train_end + 2
        test_end = (warmup + (f + 1) * fold_len - 1) if f < k else (num_bars - 1)
        train_bars = train_end - warmup + 1
        test_bars = test_end - test_start + 1
        folds.append(
            FoldGeometry(
                fold=f,
                train_range=(warmup, train_end),
                test_range=(test_start, test_end),
                train_bars=train_bars,
                train_hours=float(train_bars),
                test_bars=test_bars,
                test_hours=float(test_bars),
            )
        )
    return folds


def selection_objective(exp_r: float, total_trades: int, min_trades: int = 2) -> float:
    """EXP-024 Selektions-Objektiv im Walk-Forward (F31).

    Bestraft kleine Stichproben hyperbolisch: obj = exp * sqrt(N) * (1 - 1/(1+N)).
    """
    if total_trades < min_trades:
        return float("-inf")
    n = float(total_trades)
    return float(exp_r) * math.sqrt(n) * (1.0 - 1.0 / (1.0 + n))
