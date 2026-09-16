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
from decimal import Decimal
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
    risk_amt: float,
    entry: float,
    stop_distance: float,
    leverage: int = 1,
    spec: dict[str, Any] | None = None,
) -> PositionSize:
    """Berechnet Lots/Kontrakte mit Truncation und ULP-Schutz (F29).

    Rundet NIEMALS auf ein Boersen-Minimum auf, wenn das Budget ueberschritten wuerde.
    """
    zero = PositionSize(qty=0.0, contracts=0, notional=0.0, margin=0.0, actual_risk_amt=0.0)
    if not (
        math.isfinite(risk_amt)
        and risk_amt > 0
        and math.isfinite(entry)
        and entry > 0
        and math.isfinite(stop_distance)
        and stop_distance > 0
        and leverage > 0
    ):
        return zero

    ct_val = float(spec.get("ctVal", 0.0)) if spec else 0.0
    if ct_val <= 0:
        return zero

    raw_contracts = (risk_amt / stop_distance) / ct_val
    if not math.isfinite(raw_contracts) or raw_contracts < 1:
        return zero

    contracts = int(math.floor(raw_contracts))
    if contracts <= 0:
        return zero

    min_size = float(spec.get("minSize", 0.0)) if spec else 0.0
    min_contracts = max(1, int(math.ceil(min_size / ct_val))) if min_size > 0 else 1
    if contracts < min_contracts:
        return zero

    # Praezision aus ctVal ableiten
    ct_str = str(ct_val)
    if "e-" in ct_str:
        qty_precision = min(12, int(ct_str.split("e-")[1]))
    elif "." in ct_str:
        qty_precision = min(12, len(ct_str.split(".")[1]))
    else:
        qty_precision = 0

    qty = round(contracts * ct_val, qty_precision)
    actual_risk = qty * stop_distance

    # ULP-Schutz: falls Float-Multiplikation das Budget ueberschreitet
    if actual_risk > risk_amt:
        contracts -= 1
        if contracts < min_contracts:
            return zero
        qty = round(contracts * ct_val, qty_precision)
        actual_risk = qty * stop_distance

    raw_notional = qty * entry
    min_notional = float(spec.get("minNotional", 0.0)) if spec else 0.0
    if raw_notional < min_notional:
        return zero

    notional = math.floor(raw_notional * 1e8) / 1e8
    raw_margin = notional / float(leverage)
    margin = math.floor(raw_margin * 1e8) / 1e8
    actual_risk = math.floor(actual_risk * 1e8) / 1e8

    return PositionSize(
        qty=qty,
        contracts=contracts,
        notional=notional,
        margin=margin,
        actual_risk_amt=actual_risk,
    )


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
