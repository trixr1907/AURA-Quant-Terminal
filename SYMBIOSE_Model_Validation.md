# AURA — Model Validation (Sprint 3, Task 10)

Status: computed, not self-reported. Every number below is produced by a machine-runnable
artifact (`tests/reference_backtest.py`, `tests/test_lookahead_metamorphic.js`,
`tests/sensitivity_release_gates.js`), never asserted by hand.

---

## 1. Method

The engine is embedded between `//  ==ENGINE_BEGIN==` and `// ==ENGINE_END==` in
`Symbiose_Dashboard.html` and runs DOM-free in Node via `vm`. Validation has four
independent, mutually reinforcing layers:

| Layer | Artifact | What it proves |
|-------|----------|----------------|
| 10A independent oracle | `tests/reference_backtest.py` | accounting + fold arithmetic matches a clean stdlib re-derivation |
| 10B stats reference | `tests/reference_backtest.py` | DSR moments + PAVA calibration match hand-calculated cases |
| 10C look-ahead metamorphic | `tests/test_lookahead_metamorphic.js` | appending future bars never changes history |
| 10D sensitivity + gates | `tests/sensitivity_release_gates.js` | release state is computed, not tuned away |

---

## 2. 10A — Independent accounting and fold oracle

`tests/reference_backtest.py` re-implements (stdlib only, from the published definitions,
not copied line-for-line from JS):

- `evaluate_trades`: win rate, gross R, profit factor, expectancy, max drawdown, avg win/loss R.
- `reconcile_backtest_accounting`: realized / unrealized PnL, fees, ending equity.
- `fold_boundaries`: anchored K=4 walk-forward with exact t1 boundary protection, 300 minimum train bars, and an 18-parameter grid.

Hand-calculated fixture (`tests/fixtures/backtest/trades.json`, 9 closed + 1 open trade):

| Metric | Hand value | Python oracle | JS engine |
|--------|-----------|---------------|-----------|
| total / wins / losses | 9 / 4 / 5 | 9 / 4 / 5 | 9 / 4 / 5 |
| win rate | 0.4444 | 0.4444 | 0.4444 |
| grossR | 2.1000 | 2.1000 | 2.1000 |
| profit factor | 5.9 / 3.8 = 1.5526 | 1.5526 | 1.5526 |
| expectancy | 2.1 / 9 = 0.2333 | 0.2333 | 0.2333 |
| max drawdown | 1.3000 | 1.3000 | 1.3000 |
| ending equity (start 1000) | 1246.90 | 1246.90 | 1246.90 |

Fold geometry uses anchored K=4 folds intentionally. `minTrainBars=300` and
`minTrainTrades=5`; no ATR purge or post-test embargo is claimed. For each test start,
the last train signal is `testStart - 2` (entry at `i+1`) and the train exit boundary is
`testStart - 1`. Only trades closed strictly before `testStart` enter selection; events
still open at that boundary are reported as `purgedByT1`. OOS events open at a fold end
are reported as `censoredTest`. `tfMinutes` only converts reported fold durations to
hours; indicator periods and warmup are not timeframe-scaled.

Fold boundaries for n=1000 (warmup 235) — Python `fold_boundaries` vs JS
`runWalkForwardBacktest` `foldReports`:

```
fold 1  train [235,534]  test [536,650]  train/test hours 300/115
fold 2  train [235,649]  test [651,765]  train/test hours 415/115
fold 3  train [235,764]  test [766,880]  train/test hours 530/115
fold 4  train [235,879]  test [881,998]  train/test hours 645/118
```

Verdict: **PASS** — oracle and engine agree to floating-point tolerance on every field.

---

## 3. 10B — Calibration and DSR reference

`calc_dsr` re-derived in Python (A&S erf + Acklam normInv, same published
approximations the JS uses):

- Symmetric returns `[1,-1,1,-1]`: sharpe = 0.0000 (hand), kurt = 0.5625 = 9/16 (hand).
  Python and JS both report exactly `sharpe=0.0000, kurt=0.5625`.
- DSR is bounded to [0,1], equals 0.5 at `sr == srStar`, and increases monotonically in
  Sharpe — verified.
- Expected-max-Sharpe adjustment `srStar` grows with effective `totalTrials` and shrinks with `n`.
  The effective family is `18 × trialMultiplier`: a TimeStop sweep passes its actual candidate count;
  the Autobot passes its current candidate count, not a theoretical coins×timeframes universe.

`calibrate_probabilities` (PAVA + Bayesian prior, 10 bins) re-derived in Python:

- PAVA output is monotonic non-decreasing across all 10 bins.
- `P(Long)` at neutral score 50 = 0.5000 (uninformative prior, hand value).
- Output is clamped to [0.05, 0.95].
- Python and JS agree on the sampled probability curve within 1e-9.

Verdict: **PASS** — monotonicity, bin handling, prior behavior, moments and deflation all
match hand-calculated cases.

---

## 4. 10C — Look-ahead metamorphic tests

`tests/test_lookahead_metamorphic.js` asserts three invariants:

1. Appending future bars does not change historical `score` / ATR / SuperTrend values.
2. Completed trades inside a shared window are identical under future extension.
3. Mutating a test-fold's candles does not change that fold's train-selected parameters.

**Finding + fix:** the first run failed. Root cause was the adaptive warmup
`effWarmup = min(warmup, max(14, floor(n*0.2)))` — `floor(n*0.2)` grows with `n`, so
appending bars shifted the score-computation boundary (bars 120–159 were scored at n=600
but fell below the raised warmup of 160 at n=800). Fixed in both `analyze()` and
`runWalkForwardBacktest()` to the look-ahead-invariant form:

```
effWarmup = min(warmup, max(14, n - 60))     // reserve ≥60 evaluation bars
```

This still solves the original 1D pitfall (n=90 → warmup 30, scores still computed) but
saturates at 235 for n ≥ 295, so the boundary no longer moves under bar appends. It does
**not** change production behavior (dashboard fetches 1500 bars → warmup 235 either way).

Verdict: **PASS** — 3/3 metamorphic properties hold after the fix. The `lastPH/lastPL`
"repaint" seen in an intermediate diagnostic was a false positive (`NaN !== NaN` in the
comparison, no pivots in the synthetic series) — not an engine bug.

---

## 5. 10D — Sensitivity sweep and release gates

`tests/sensitivity_release_gates.js` runs the full anchored t1-safe walk-forward over a fixed
neighborhood (time-stop {12,15,18} × slippage {0, 0.0002, 0.0005}) on one deterministic
1500-bar synthetic series, without re-picking the best after seeing OOS.

| Metric | Value |
|--------|-------|
| OOS trades | 33 |
| expectancy (median) | +1.241 R |
| expectancy spread | [+1.226, +1.264] R |
| max drawdown (worst) | 1.050 R |
| fold dispersion (std of fold exp) | 0.273 R |
| 95% CI on expectancy | [+0.773 R, +1.710 R] |

Latest local result: **PAPER_CANDIDATE** on this deterministic synthetic fixture.
This is not a live-performance claim and does not override any fail-closed path:
`NO_EVIDENCE`, neutral DSR=0.5, and `INSUFFICIENT_DATA` remain non-accepting
evidence states. The engine measures the fixture rather than manufacturing evidence.

### Release-state definitions (computed, never hand-asserted)

- `NO_EVIDENCE` — OOS trades < 30, OR expectancy ≤ 0, OR the 95% CI lower bound
  crosses −0.05 R.
- `RESEARCH_ONLY` — metrics computed but unstable: expectancy sign flips across the
  neighborhood, or fold dispersion exceeds |expectancy|.
- `PAPER_CANDIDATE` — ≥30 OOS trades, expectancy > 0, CI lower bound > 0, sign stable
  across the neighborhood, fold dispersion bounded.
- **Never auto-promoted to live.** A live go/no-go additionally requires the external
  evidence in §7 (Pine compile + five golden CSVs) and an explicit execution arming.

---

## 6. Test commands

```
node tests/test_engine_full.js            # 118/118
node test_symbiose.js                     # T1–T6
node tests/test_lookahead_metamorphic.js  # 3/3
python3 tests/reference_backtest.py       # all assertions
node tests/sensitivity_release_gates.js   # JSON report, exit 0
python3 scripts/release_check.py          # one-command release check (all 10 gates)
```

---

## 7. External evidence still open (cannot be produced locally)

- Pine v6 compile in TradingView and the five `GM ...` Data-Window fields (Task 11).
- Five golden-master CSV exports (BTCUSDT/ETHUSDT/SOLUSDT 1h, XRPUSDT/DOGEUSDT 4h) and the
  Pine↔JS comparison at absolute delta ≤ 0.1 (Task 11).
- One controlled Bitget demo minimum order (only with explicit user approval).

Until these exist, the overall model release remains `NO-GO` regardless of the local
`PAPER_CANDIDATE`-capable gates.
