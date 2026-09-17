"""K-Fold Anchored Walk-Forward Pipeline (aura.backtest.walk_forward).

Dokumentiert in docs/MODEL_VALIDATION.md.
Mandats-Garantien:
  * t1-safe: Kein Zukunftsbezug von Train in Test.
  * DSR-Korrektur mit effektiver Trial-Zaehlung (Bailey & López de Prado).
  * Holdout Lockbox Schutz.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence

from aura.backtest.engine import BacktestConfig, BacktestSimulator
from aura.core.stats import (
    DsrResult,
    FoldGeometry,
    TradeEvaluation,
    calc_dsr,
    calibrate_probabilities,
    evaluate_trades,
    walk_forward_folds,
)

logger = logging.getLogger("aura.backtest.walk_forward")


@dataclass
class FoldResult:
    geometry: FoldGeometry
    train_eval: TradeEvaluation
    test_eval: TradeEvaluation
    train_trades_count: int
    test_trades_count: int
    oos_trades: list[dict[str, Any]]


@dataclass
class WalkForwardReport:
    k_folds: int
    total_bars: int
    warmup_bars: int
    fold_results: list[FoldResult]
    combined_oos_eval: TradeEvaluation
    combined_oos_trades: list[dict[str, Any]]
    dsr_result: DsrResult
    model_status: str  # 'EVIDENCE_SUPPORTED' | 'MODEL_NO_EVIDENCE' | 'INVALID'


class WalkForwardOptimizer:
    """Walk-Forward Validierung ueber K Folds mit t1-Sicherheit."""

    def __init__(self, k_folds: int = 4, warmup_bars: int = 235, num_trials: int = 18):
        self.k_folds = k_folds
        self.warmup_bars = warmup_bars
        self.num_trials = num_trials

    def run(
        self,
        candles: Sequence[dict[str, Any]],
        symbol: str = "BTCUSDT",
        config: BacktestConfig | None = None,
        spec: dict[str, Any] | None = None,
    ) -> WalkForwardReport:
        n = len(candles)
        folds = walk_forward_folds(n, warmup=self.warmup_bars, k=self.k_folds)
        simulator = BacktestSimulator(config or BacktestConfig(warmup_bars=self.warmup_bars))

        fold_results: list[FoldResult] = []
        all_oos_trades: list[dict[str, Any]] = []

        for fold_geo in folds:
            # 1. Train Period
            train_candles = candles[: fold_geo.train_range[1] + 1]
            train_res = simulator.run(train_candles, symbol=symbol, spec=spec)

            # 2. Test Period (OOS)
            test_candles = candles[fold_geo.test_range[0] : fold_geo.test_range[1] + 1]
            # Fuer OOS simulieren wir mit Warmup-Bars aus dem vorherigen Bereich
            warmup_start = max(0, fold_geo.test_range[0] - self.warmup_bars)
            oos_full_slice = candles[warmup_start : fold_geo.test_range[1] + 1]
            test_res = simulator.run(oos_full_slice, symbol=symbol, spec=spec)

            # Nur Trades zaehlen, die innerhalb des Test-Bereichs geoeffnet wurden
            test_start_time = test_candles[0].get("time") or test_candles[0].get("time_ms") or 0
            oos_trades = [t for t in test_res.trades if t.get("entry_time", 0) >= test_start_time]

            all_oos_trades.extend(oos_trades)
            fold_results.append(
                FoldResult(
                    geometry=fold_geo,
                    train_eval=train_res.evaluation,
                    test_eval=evaluate_trades(oos_trades),
                    train_trades_count=len(train_res.trades),
                    test_trades_count=len(oos_trades),
                    oos_trades=oos_trades,
                )
            )

        combined_eval = evaluate_trades(all_oos_trades)
        returns = combined_eval.returns
        dsr = calc_dsr(returns, num_trials=self.num_trials)

        # This component performs OOS measurement only. It does not receive or
        # consume a sealed final holdout, so it must never promote model evidence.
        model_status = "MODEL_NO_EVIDENCE"

        return WalkForwardReport(
            k_folds=len(folds),
            total_bars=n,
            warmup_bars=self.warmup_bars,
            fold_results=fold_results,
            combined_oos_eval=combined_eval,
            combined_oos_trades=all_oos_trades,
            dsr_result=dsr,
            model_status=model_status,
        )
