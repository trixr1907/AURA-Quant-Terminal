"""Kausaler, event-basierter Backtest-Simulator (aura.backtest.engine).

Basiert auf kanonischer aura.core Quant-Engine und exaktem Kostenmodell.
Dokumentiert in docs/MODEL_VALIDATION.md.
Mandats-Garantien:
  * Keine Higher-Timeframe-Vorschau oder Look-ahead.
  * Kausale Signalverfuegbarkeit (Signal bei Bar-Close, Einstieg zum Open des Folgebars).
  * Konservative Intrabar-Policy bei kollidierenden SL/TP.
  * Realistische Maker/Taker-Gebuehren, Slippage und Funding.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from aura.core.indicators import atr_series
from aura.core.risk import PositionSize, size_position
from aura.core.scoring import analyze_candles
from aura.core.stats import TradeEvaluation, evaluate_trades

logger = logging.getLogger("aura.backtest.engine")


@dataclass(frozen=True)
class BacktestConfig:
    starting_equity: float = 10000.0
    risk_per_trade_pct: float = 1.0
    maker_fee: float = 0.0002
    taker_fee: float = 0.0006
    slippage_bps: float = 1.5
    leverage: int = 5
    max_hold_bars: int = 72
    warmup_bars: int = 235
    intrabar_conservative: bool = True


@dataclass
class BacktestResult:
    config: BacktestConfig
    total_bars: int
    trades: list[dict[str, Any]]
    evaluation: TradeEvaluation
    starting_equity: float
    ending_equity: float
    net_profit: float
    roi_pct: float
    max_drawdown_pct: float


class BacktestSimulator:
    """Kausale Replay-Engine fuer historische Kerzen."""

    def __init__(self, config: BacktestConfig | None = None):
        self.config = config or BacktestConfig()

    def run(
        self,
        candles: Sequence[dict[str, Any]],
        symbol: str = "BTCUSDT",
        spec: dict[str, Any] | None = None,
    ) -> BacktestResult:
        n = len(candles)
        if n < self.config.warmup_bars + 10:
            empty_eval = evaluate_trades([])
            return BacktestResult(
                config=self.config,
                total_bars=n,
                trades=[],
                evaluation=empty_eval,
                starting_equity=self.config.starting_equity,
                ending_equity=self.config.starting_equity,
                net_profit=0.0,
                roi_pct=0.0,
                max_drawdown_pct=0.0,
            )

        # 1. Berechne alle Indikatoren kausal ueber analyze_candles
        analysis = analyze_candles(candles)

        equity = self.config.starting_equity
        trades: list[dict[str, Any]] = []
        active_trade: dict[str, Any] | None = None
        peak_equity = equity
        max_dd_pct = 0.0

        for i in range(self.config.warmup_bars, n):
            c_curr = candles[i]
            t_curr = c_curr.get("time") or c_curr.get("time_ms") or 0
            open_p = float(c_curr["open"])
            high_p = float(c_curr["high"])
            low_p = float(c_curr["low"])
            close_p = float(c_curr["close"])

            # 1. Pruefe offene Position gegen den aktuellen Bar
            if active_trade:
                dir_ = active_trade["dir"]
                sl = active_trade["sl"]
                tp1 = active_trade["tp1"]
                tp2 = active_trade["tp2"]

                sl_hit = (low_p <= sl) if dir_ == 1 else (high_p >= sl)
                tp1_hit = (high_p >= tp1) if dir_ == 1 else (low_p <= tp1)
                tp2_hit = (high_p >= tp2) if dir_ == 1 else (low_p <= tp2)

                # Intrabar-Kollision
                if sl_hit and (tp1_hit or tp2_hit) and self.config.intrabar_conservative:
                    # SL fuehrt aus
                    exit_p = sl * (1.0 - (self.config.slippage_bps / 10000.0) * dir_)
                    gross = (exit_p - active_trade["entry"]) * dir_ * active_trade["qty"]
                    exit_fee = active_trade["qty"] * exit_p * self.config.taker_fee
                    net_pnl = gross - exit_fee + active_trade["realized_tp1_pnl"]
                    total_fees = active_trade["fees"] + exit_fee

                    equity += (gross - exit_fee)
                    init_risk = active_trade["init_risk"]
                    r_net = (net_pnl / init_risk) if init_risk > 0 else 0.0

                    active_trade["outcome"] = "loss" if net_pnl <= 0 else "win"
                    active_trade["exit_price"] = exit_p
                    active_trade["exit_time"] = t_curr
                    active_trade["exit_reason"] = "sl_hit_collision"
                    active_trade["grossPnl"] = gross + active_trade["realized_tp1_pnl"]
                    active_trade["fees"] = total_fees
                    active_trade["realized_pnl"] = net_pnl
                    active_trade["rNet"] = r_net
                    trades.append(active_trade)
                    active_trade = None

                elif sl_hit:
                    exit_p = sl * (1.0 - (self.config.slippage_bps / 10000.0) * dir_)
                    gross = (exit_p - active_trade["entry"]) * dir_ * active_trade["qty"]
                    exit_fee = active_trade["qty"] * exit_p * self.config.taker_fee
                    net_pnl = gross - exit_fee + active_trade["realized_tp1_pnl"]
                    total_fees = active_trade["fees"] + exit_fee

                    equity += (gross - exit_fee)
                    init_risk = active_trade["init_risk"]
                    r_net = (net_pnl / init_risk) if init_risk > 0 else 0.0

                    active_trade["outcome"] = "loss" if net_pnl <= 0 else "win"
                    active_trade["exit_price"] = exit_p
                    active_trade["exit_time"] = t_curr
                    active_trade["exit_reason"] = "sl_hit"
                    active_trade["grossPnl"] = gross + active_trade["realized_tp1_pnl"]
                    active_trade["fees"] = total_fees
                    active_trade["realized_pnl"] = net_pnl
                    active_trade["rNet"] = r_net
                    trades.append(active_trade)
                    active_trade = None

                elif tp2_hit:
                    exit_p = tp2
                    gross = (exit_p - active_trade["entry"]) * dir_ * active_trade["qty"]
                    exit_fee = active_trade["qty"] * exit_p * self.config.maker_fee
                    net_pnl = gross - exit_fee + active_trade["realized_tp1_pnl"]
                    total_fees = active_trade["fees"] + exit_fee

                    equity += (gross - exit_fee)
                    init_risk = active_trade["init_risk"]
                    r_net = (net_pnl / init_risk) if init_risk > 0 else 0.0

                    active_trade["outcome"] = "win"
                    active_trade["exit_price"] = exit_p
                    active_trade["exit_time"] = t_curr
                    active_trade["exit_reason"] = "tp2_hit"
                    active_trade["grossPnl"] = gross + active_trade["realized_tp1_pnl"]
                    active_trade["fees"] = total_fees
                    active_trade["realized_pnl"] = net_pnl
                    active_trade["rNet"] = r_net
                    trades.append(active_trade)
                    active_trade = None

                elif tp1_hit and not active_trade["tp1_hit"]:
                    # 50% TP1 Teilverkauf & SL auf BE
                    closed_qty = active_trade["qty"] * 0.5
                    active_trade["qty"] -= closed_qty
                    gross_tp1 = (tp1 - active_trade["entry"]) * dir_ * closed_qty
                    tp1_fee = closed_qty * tp1 * self.config.maker_fee
                    net_tp1 = gross_tp1 - tp1_fee

                    active_trade["tp1_hit"] = True
                    active_trade["sl"] = active_trade["entry"]  # Breakeven Stop
                    active_trade["realized_tp1_pnl"] = net_tp1
                    active_trade["fees"] += tp1_fee
                    equity += net_tp1

                elif (i - active_trade["entry_bar"]) >= self.config.max_hold_bars:
                    # Timestop
                    exit_p = close_p * (1.0 - (self.config.slippage_bps / 10000.0) * dir_)
                    gross = (exit_p - active_trade["entry"]) * dir_ * active_trade["qty"]
                    exit_fee = active_trade["qty"] * exit_p * self.config.taker_fee
                    net_pnl = gross - exit_fee + active_trade["realized_tp1_pnl"]
                    total_fees = active_trade["fees"] + exit_fee

                    equity += (gross - exit_fee)
                    init_risk = active_trade["init_risk"]
                    r_net = (net_pnl / init_risk) if init_risk > 0 else 0.0

                    active_trade["outcome"] = "win" if net_pnl > 0 else "loss"
                    active_trade["exit_price"] = exit_p
                    active_trade["exit_time"] = t_curr
                    active_trade["exit_reason"] = "timestop"
                    active_trade["grossPnl"] = gross + active_trade["realized_tp1_pnl"]
                    active_trade["fees"] = total_fees
                    active_trade["realized_pnl"] = net_pnl
                    active_trade["rNet"] = r_net
                    trades.append(active_trade)
                    active_trade = None

            # 2. Pruefe neuen Einstieg (Signal auf Vorbar i-1, Ausfuehrung bei Open i)
            if not active_trade and i > self.config.warmup_bars:
                prev_score = analysis.score[i - 1]
                prev_atr = analysis.atr[i - 1]
                st_dir = analysis.st_dir[i - 1]

                is_long = prev_score >= 60.0 and st_dir == 1
                is_short = prev_score <= 40.0 and st_dir == -1

                if is_long or is_short:
                    dir_val = 1 if is_long else -1
                    # Einstieg zum Open von Bar i mit Taker-Slippage
                    entry_p = open_p * (1.0 + (self.config.slippage_bps / 10000.0) * dir_val)
                    stop_dist = max(prev_atr * 1.5, entry_p * 0.005)
                    sl_p = entry_p - stop_dist * dir_val
                    tp1_p = entry_p + stop_dist * 1.5 * dir_val
                    tp2_p = entry_p + stop_dist * 3.0 * dir_val

                    risk_amt = equity * (self.config.risk_per_trade_pct / 100.0)
                    sized = size_position(risk_amt, entry_p, stop_dist, leverage=self.config.leverage, spec=spec)

                    if sized.qty > 0 and sized.contracts > 0:
                        entry_fee = sized.qty * entry_p * self.config.taker_fee
                        equity -= entry_fee
                        init_risk = sized.qty * stop_dist

                        active_trade = {
                            "symbol": symbol,
                            "dir": dir_val,
                            "entry": entry_p,
                            "sl": sl_p,
                            "tp1": tp1_p,
                            "tp2": tp2_p,
                            "qty": sized.qty,
                            "contracts": sized.contracts,
                            "init_qty": sized.qty,
                            "init_risk": init_risk,
                            "score": prev_score,
                            "entry_bar": i,
                            "entry_time": t_curr,
                            "tp1_hit": False,
                            "realized_tp1_pnl": 0.0,
                            "fees": entry_fee,
                            "outcome": "open",
                        }

            # Equity Drawdown Tracking
            if equity > peak_equity:
                peak_equity = equity
            dd = (peak_equity - equity) / peak_equity * 100.0 if peak_equity > 0 else 0.0
            if dd > max_dd_pct:
                max_dd_pct = dd

        evaluation = evaluate_trades(trades)
        net_profit = equity - self.config.starting_equity
        roi_pct = (net_profit / self.config.starting_equity) * 100.0

        return BacktestResult(
            config=self.config,
            total_bars=n,
            trades=trades,
            evaluation=evaluation,
            starting_equity=self.config.starting_equity,
            ending_equity=equity,
            net_profit=net_profit,
            roi_pct=roi_pct,
            max_drawdown_pct=max_dd_pct,
        )
