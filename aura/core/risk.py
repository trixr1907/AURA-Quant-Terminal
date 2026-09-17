"""Kanonisches Risikomanagement: Fractional Kelly, Positionsgroesse und Hebel.

Dokumentiert in docs/FORMULA_SPEC.md (F28, F29, F30).
Mandats-Garantien:
  * Hebel veraendert niemals den absoluten Stop-Verlust, sondern nur Margin.
  * ULP-Schutz gegen Rundungs-Overshoot ueber das Risikobudget.
  * Keine Heuristik als kalibrierte Wahrscheinlichkeit.
  * Kelly mit Shrinkage bei kleiner Stichprobe (N in [5, 15)).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP, ROUND_HALF_UP
from typing import Any


@dataclass(frozen=True)
class KellyResult:
    edge_pct: float
    f_star: float
    half_kelly: float
    final_frac: float
    risk_amt: float
    has_edge: bool
    b: float


def calc_kelly(
    prob_win: float,
    avg_win_r: float,
    avg_loss_r: float,
    risk_pct: float,
    equity: float,
    total_trades: int | None = None,
) -> KellyResult:
    """Fractional Kelly nach Thorpe / López de Prado (F28).

    f* = (p*(b+1) - 1)/b, Half-Kelly = 0.5*f*, gedeckelt auf min(0.25, risk_pct/100).
    Sample-Shrinkage dämpft bei N in [5, 15); bei N < 5 oder negativem Edge -> 0.
    """
    no_edge = KellyResult(
        edge_pct=0.0,
        f_star=0.0,
        half_kelly=0.0,
        final_frac=0.0,
        risk_amt=0.0,
        has_edge=False,
        b=0.0,
    )
    valid_stats = (
        math.isfinite(prob_win)
        and 0.0 <= prob_win <= 1.0
        and math.isfinite(avg_win_r)
        and avg_win_r > 0.0
        and math.isfinite(avg_loss_r)
        and avg_loss_r > 0.0
    )
    valid_account = math.isfinite(risk_pct) and risk_pct > 0.0 and math.isfinite(equity) and equity > 0.0
    valid_sample = total_trades is None or (
        isinstance(total_trades, int) and total_trades >= 0
    )
    if not (valid_stats and valid_account and valid_sample):
        return no_edge

    b = avg_win_r / avg_loss_r
    p = prob_win
    f_star = (p * (b + 1.0) - 1.0) / b
    edge = p * b - (1.0 - p)

    if not (math.isfinite(b) and math.isfinite(f_star) and math.isfinite(edge)):
        return no_edge
    if f_star <= 0.0 or edge <= 0.0:
        return KellyResult(
            edge_pct=max(0.0, edge * 100.0) if math.isfinite(edge) else 0.0,
            f_star=0.0,
            half_kelly=0.0,
            final_frac=0.0,
            risk_amt=0.0,
            has_edge=False,
            b=b,
        )

    half_kelly = 0.5 * f_star
    hard_cap = min(0.25, risk_pct / 100.0)
    if total_trades is None or total_trades >= 15:
        sample_multiplier = 1.0
    elif total_trades < 5:
        sample_multiplier = 0.0
    else:
        sample_multiplier = (total_trades - 5) / 10.0

    final_frac = min(half_kelly, hard_cap) * sample_multiplier
    risk_amt = equity * final_frac
    has_edge = final_frac > 0.0

    return KellyResult(
        edge_pct=edge * 100.0,
        f_star=f_star,
        half_kelly=half_kelly,
        final_frac=final_frac,
        risk_amt=risk_amt,
        has_edge=has_edge,
        b=b,
    )


@dataclass(frozen=True)
class PositionSize:
    qty: float
    contracts: int
    notional: float
    margin: float
    actual_risk_amt: float


def size_position(
    risk_amt: float | Decimal,
    entry: float | Decimal,
    stop_distance: float | Decimal,
    leverage: int = 1,
    spec: dict[str, Any] | None = None,
) -> PositionSize:
    """Calculate base-coin size with exact downward step rounding."""
    zero = PositionSize(qty=0.0, contracts=0, notional=0.0, margin=0.0, actual_risk_amt=0.0)
    try:
        risk_d = Decimal(str(risk_amt))
        entry_d = Decimal(str(entry))
        stop_d = Decimal(str(stop_distance))
        leverage_d = Decimal(leverage)
    except (InvalidOperation, ValueError):
        return zero
    if not all(value.is_finite() and value > 0 for value in (risk_d, entry_d, stop_d, leverage_d)):
        return zero

    raw_step = spec.get("qtyStep", spec.get("ctVal")) if spec else None
    raw_min_qty = spec.get("minQty", spec.get("minSize", 0)) if spec else None
    raw_min_notional = spec.get("minNotional", 0) if spec else None
    try:
        qty_step = Decimal(str(raw_step))
        min_qty = Decimal(str(raw_min_qty))
        min_notional = Decimal(str(raw_min_notional))
    except (InvalidOperation, ValueError):
        return zero
    if not qty_step.is_finite() or qty_step <= 0 or min_qty < 0 or min_notional < 0:
        return zero

    raw_qty = risk_d / stop_d
    steps = int((raw_qty / qty_step).to_integral_value(rounding=ROUND_DOWN))
    min_steps = max(1, int((min_qty / qty_step).to_integral_value(rounding=ROUND_UP)))
    if steps < min_steps:
        return zero

    qty = qty_step * steps
    actual_risk = qty * stop_d
    if actual_risk > risk_d:
        return zero
    notional = qty * entry_d
    if notional < min_notional:
        return zero
    margin = notional / leverage_d

    return PositionSize(
        qty=float(qty),
        contracts=steps,
        notional=float(notional.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)),
        margin=float(margin.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)),
        actual_risk_amt=float(actual_risk.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)),
    )


def round_price_to_tick(
    price: Decimal | float,
    tick: Decimal | float,
    rounding: str = ROUND_HALF_UP,
) -> Decimal:
    """Rounds price to the nearest valid exchange price_tick increment."""
    try:
        d_price = Decimal(str(price))
        d_tick = Decimal(str(tick))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(str(price))
    if not d_price.is_finite() or not d_tick.is_finite() or d_tick <= 0:
        return d_price
    steps = (d_price / d_tick).quantize(Decimal("1"), rounding=rounding)
    return steps * d_tick


@dataclass(frozen=True)
class LeverageRecommendation:
    leverage: int
    stop_pct: float
    liquidation_buffer_pct: float  # Schätzung
    margin: float
    margin_budget: float
    safe_max: int
    warning: str


def recommend_leverage(
    entry: float,
    sl: float,
    notional: float,
    equity: float,
    max_leverage: int = 50,
) -> LeverageRecommendation:
    """Empfiehlt den kleinsten Hebel, der Notional <=35% Margin haelt (F30).

    Mandats-Garantie: Der Hebel bestimmt die Margin, niemals den Stop.
    Liquidationspuffer ist als 100/L - 0.5% MMR-Naeherung dokumentiert (Q-06).
    """
    if not (entry > 0 and notional > 0 and equity > 0 and math.isfinite(sl)):
        return LeverageRecommendation(
            leverage=0,
            stop_pct=0.0,
            liquidation_buffer_pct=0.0,
            margin=0.0,
            margin_budget=0.0,
            safe_max=0,
            warning="Kein aktiver Trade",
        )

    stop_pct = abs(entry - sl) / entry * 100.0
    margin_budget = equity * 0.35
    needed = max(1, int(math.ceil(notional / max(1.0, margin_budget))))
    safe_max = max(1, int(math.floor(100.0 / max(1.0, stop_pct * 3.0 + 0.5))))
    exchange_max = max(1, int(max_leverage or 50))
    leverage = min(needed, safe_max, exchange_max)
    margin = notional / float(leverage)
    liq_buffer = max(0.0, 100.0 / float(leverage) - 0.5)

    warning = ""
    if needed > safe_max:
        warning = (
            "Positionsgröße benötigt zu viel Margin für einen konservativen Hebel "
            "— Risiko/Konto anpassen."
        )

    return LeverageRecommendation(
        leverage=leverage,
        stop_pct=stop_pct,
        liquidation_buffer_pct=liq_buffer,
        margin=margin,
        margin_budget=margin_budget,
        safe_max=safe_max,
        warning=warning,
    )
