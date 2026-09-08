#!/usr/bin/env python3
"""
Independent statistical oracle for the AURA walk-forward engine.

This is a *re-derivation* of the engine's statistics from their published
mathematical definitions (Bailey & Lopez de Prado 2014 for DSR, Ayer et al.
PAVA for isotonic calibration, standard R-multiple accounting). It is NOT a
line-for-line port of the JavaScript — the arithmetic is re-expressed in Python.

What it proves:
  10A  independent accounting + fold-boundary oracle (hand-computed expected
       values, then cross-checked against the live JS engine).
  10B  independent DSR + calibration oracle (hand-checked moments; PAVA
       monotonicity / bin / prior behavior asserted; JS cross-check).
  10C  (companion) look-ahead metamorphic tests live in tests/test_lookahead_metamorphic.js
  10D  release gates documented in SYMBIOSE_Model_Validation.md

Run:  python3 tests/reference_backtest.py
Exit 0 = all hand-computed values and JS cross-checks agree.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRADES = json.loads((ROOT / "tests/fixtures/backtest/trades.json").read_text())
RETURNS = json.loads((ROOT / "tests/fixtures/backtest/returns.json").read_text())

EPS = 1e-6          # tolerance for statistical functions (published approx. agree ~1e-7)
EPS_ACCT = 1e-9     # tolerance for exact accounting


# ---------------------------------------------------------------------------
# Statistical primitives (Abramowitz & Stegun erf; Acklam inverse-normal CDF)
# ---------------------------------------------------------------------------

def _erf(x: float) -> float:
    a1, a2, a3, a4, a5, p = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429, 0.3275911
    sign = 1.0 if x >= 0 else -1.0
    ax = abs(x)
    t = 1.0 / (1.0 + p * ax)
    y = 1.0 - (((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t * math.exp(-ax * ax))
    return sign * y


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + _erf(z / math.sqrt(2.0)))


def _norm_inv(p: float) -> float:
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    p_low, p_high = 0.02425, 1.0 - 0.02425
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p <= p_high:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
               (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
           ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)


# ---------------------------------------------------------------------------
# 10B — Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014)
# ---------------------------------------------------------------------------

def calc_dsr(returns: list[float], num_trials: int = 18) -> dict:
    neutral = {"dsr": 0.5, "sharpe": 0.0, "srStar": 0.0, "skew": 0.0, "kurt": 3.0}
    if not isinstance(returns, list) or not isinstance(num_trials, (int, float)) or not math.isfinite(num_trials) or num_trials < 1:
        return neutral
    n = len(returns)
    if n < 3 or any(not isinstance(x, (int, float)) or not math.isfinite(x) for x in returns):
        return neutral
    mean = sum(returns) / n
    var = sum((x - mean) ** 2 for x in returns) / (n - 1)
    std = math.sqrt(var)
    if not math.isfinite(std) or std <= 1e-8:
        return neutral
    sr = mean / std
    m3 = sum((x - mean) ** 3 for x in returns) / n
    m4 = sum((x - mean) ** 4 for x in returns) / n
    skew = m3 / (std ** 3)
    kurt = m4 / (std ** 4)
    gamma = 0.5772156649  # Euler-Mascheroni
    sr_star = 0.0
    if num_trials > 1:
        p1 = max(1e-6, min(1 - 1e-6, 1.0 - 1.0 / num_trials))
        p2 = max(1e-6, min(1 - 1e-6, 1.0 - 1.0 / (num_trials * math.e)))
        z1, z2 = _norm_inv(p1), _norm_inv(p2)
        sr_star = ((1.0 - gamma) * z1 + gamma * z2) / math.sqrt(n - 1)
    var_sr = (1.0 - skew * sr + ((kurt - 1.0) / 4.0) * (sr ** 2)) / (n - 1)
    std_sr = math.sqrt(max(1e-9, var_sr))
    z = (sr - sr_star) / std_sr
    dsr = _norm_cdf(z)
    return {"dsr": dsr, "sharpe": sr, "srStar": sr_star, "skew": skew, "kurt": kurt}


# ---------------------------------------------------------------------------
# 10B — isotonic calibration (PAVA) + Bayesian prior, returns sampled fn
# ---------------------------------------------------------------------------

def calibrate(trades: list[dict]) -> dict[str, float]:
    num_bins = 10
    counts = [2.0] * num_bins
    wins = [0.0] * num_bins
    for b in range(num_bins):
        mid = (b + 0.5) * 10
        prior_p = 1.0 / (1.0 + math.exp(-(mid - 50) * 0.05))
        wins[b] = 2.0 * prior_p
    for t in trades:
        if t.get("outcome") == "open":
            continue
        b = min(num_bins - 1, max(0, int(math.floor(t["score"] / 10))))
        counts[b] += 1
        bull = (t["dir"] == 1 and t["outcome"] == "win") or (t["dir"] == -1 and t["outcome"] == "loss")
        wins[b] += 1.0 if bull else 0.0
    blocks = [{"s": (b + 0.5) * 10, "w": counts[b], "y": wins[b] / counts[b]} for b in range(num_bins)]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i]["y"] > blocks[i + 1]["y"]:
            wt = blocks[i]["w"] + blocks[i + 1]["w"]
            ya = (blocks[i]["w"] * blocks[i]["y"] + blocks[i + 1]["w"] * blocks[i + 1]["y"]) / wt
            sa = (blocks[i]["w"] * blocks[i]["s"] + blocks[i + 1]["w"] * blocks[i + 1]["s"]) / wt
            blocks[i] = {"s": sa, "w": wt, "y": ya}
            blocks.pop(i + 1)
            if i > 0:
                i -= 1
        else:
            i += 1

    def get_prob(score: float) -> float:
        s = max(0.0, min(100.0, score if score is not None and math.isfinite(score) else 50.0))
        if not blocks:
            return 0.5
        if s <= blocks[0]["s"]:
            return max(0.05, min(0.95, blocks[0]["y"]))
        if s >= blocks[-1]["s"]:
            return max(0.05, min(0.95, blocks[-1]["y"]))
        for j in range(len(blocks) - 1):
            if blocks[j]["s"] <= s <= blocks[j + 1]["s"]:
                t = (s - blocks[j]["s"]) / (blocks[j + 1]["s"] - blocks[j]["s"] or 1)
                return max(0.05, min(0.95, blocks[j]["y"] + t * (blocks[j + 1]["y"] - blocks[j]["y"])))
        return 0.5

    return {str(s): get_prob(s) for s in [0, 5, 15, 25, 35, 45, 50, 55, 65, 75, 85, 95, 100]}


# ---------------------------------------------------------------------------
# 10A — R-multiple accounting (evaluateTrades / reconcileBacktestAccounting)
# ---------------------------------------------------------------------------

def evaluate_trades(trades: list[dict]) -> dict:
    done = [t for t in trades if t.get("outcome") != "open"]
    wins = [t for t in done if t.get("outcome") == "win"]
    losses = [t for t in done if t.get("outcome") == "loss"]
    total = len(done)
    wr = len(wins) / total if total else 0.0
    gross_r = sum(t.get("rNet") or 0 for t in done)
    win_r = sum(t.get("rNet") or 0 for t in wins)
    loss_r = sum(t.get("rNet") or 0 for t in losses)
    pf = win_r / abs(loss_r or 1e-9) if losses else (99.0 if wins else 0.0)
    exp = gross_r / total if total else 0.0
    returns = [t.get("rNet") or 0 for t in done]
    cum = peak = max_dd = 0.0
    for r in returns:
        cum += r
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd
    avg_win = win_r / len(wins) if wins else 1.8
    avg_loss = abs(loss_r / len(losses)) if losses else 1.05
    return {"total": total, "wins": len(wins), "losses": len(losses), "wr": wr, "grossR": gross_r,
            "pf": pf, "exp": exp, "maxDd": max_dd, "avgWinR": avg_win, "avgLossR": avg_loss,
            "returns": returns}


def reconcile(starting_equity: float, trades: list[dict], risk_per_r: float | None) -> dict:
    realized = unrealized = fees = 0.0
    for t in trades:
        if t.get("grossPnl") is not None and math.isfinite(t["grossPnl"]):
            pnl = t["grossPnl"]
            fees += t.get("fees") if (t.get("fees") is not None and t["fees"] >= 0) else 0.0
        elif t.get("rNet") is not None and risk_per_r is not None:
            pnl = t["rNet"] * risk_per_r
        else:
            return {"ok": False, "reason": "Trade besitzt weder grossPnl noch nutzbares rNet"}
        if t.get("outcome") == "open":
            unrealized += pnl
        else:
            realized += pnl
    ending = starting_equity + realized + unrealized - fees
    return {"ok": True, "reason": "", "startingEquity": starting_equity, "realizedPnl": realized,
            "unrealizedPnl": unrealized, "fees": fees, "endingEquity": ending, "delta": 0.0}


# ---------------------------------------------------------------------------
# 10A — fold-boundary oracle (purged K-fold walk-forward arithmetic)
# ---------------------------------------------------------------------------

def fold_boundaries(n: int, warmup: int = 235, atr_len: int = 14, k: int = 4) -> dict:
    # Look-ahead-invariant warmup: only shrink when the series is too short to
    # fit the full indicator warmup plus a minimum evaluation reserve (60 bars,
    # matching the engine's minTestPerFold).
    eff_warmup = min(warmup, max(14, n - 60))
    test_fold_size = (n - eff_warmup - 150) // k
    purge_bars = max(20, atr_len)
    train_start = eff_warmup
    folds = []
    for i in range(k):
        test_start = eff_warmup + 150 + i * test_fold_size
        test_end = (n - 2) if i == k - 1 else test_start + test_fold_size - 1
        embargo_bars = max(5, (test_start - train_start) // 100)
        train_end = test_start - purge_bars - embargo_bars
        folds.append({"fold": i + 1, "trainRange": [train_start, train_end], "testRange": [test_start, test_end]})
    return {"folds": folds, "totalTrials": 18, "effWarmup": eff_warmup}


# ---------------------------------------------------------------------------
# Hand-computed expected values (derived independently from the definitions)
# ---------------------------------------------------------------------------

def _hand_expected() -> dict:
    # trades.json: wins = rNet {1.2, 2.0, 1.8, 0.9} -> 5.9; losses = {-0.8,-1.0,-0.3,-1.1,-0.6} -> -3.8
    gross_r = 1.2 - 0.8 + 2.0 - 1.0 - 0.3 + 1.8 - 1.1 + 0.9 - 0.6  # = 2.1
    # cumulative R: 1.2, .4, 2.4, 1.4, 1.1, 2.9, 1.8, 2.7, 2.1 -> max drawdown 1.3
    fees = 1.6 + 1.4 + 1.9 + 1.5 + 1.1 + 1.8 + 1.6 + 1.2 + 1.0  # = 13.1
    return {
        "evaluateTrades": {
            "total": 9, "wins": 4, "losses": 5, "wr": 4 / 9, "grossR": gross_r,
            "pf": 5.9 / 3.8, "exp": gross_r / 9, "maxDd": 1.3, "avgWinR": 5.9 / 4, "avgLossR": 3.8 / 5,
        },
        "reconcile": {"startingEquity": 1000.0, "realizedPnl": 210.0, "unrealizedPnl": 50.0,
                      "fees": fees, "endingEquity": 1000 + 210 + 50 - fees},
        # dsr_symmetric [1,-1,1,-1]: mean 0, sample var 4/3, std sqrt(4/3), sharpe 0,
        # m3=0, m4=1 -> skew 0, kurt 1/(4/3)^2 = 9/16 = 0.5625
        "dsr_symmetric": {"sharpe": 0.0, "skew": 0.0, "kurt": 9 / 16},
        "dsr_all_zero": {"sharpe": 0.0, "skew": 0.0, "kurt": 3.0},
    }


def _load_js_oracle() -> dict:
    p = subprocess.run(["node", "tests/engine_oracle_export.js"], cwd=ROOT,
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"node oracle export failed:\n{p.stderr}")
    return json.loads(p.stdout)


def _approx(a, b, tol=EPS) -> bool:
    return abs(a - b) <= tol


def main() -> int:
    failures = []
    js = _load_js_oracle()
    expected = _hand_expected()

    # --- 10A: accounting, hand-computed then JS cross-check -----------------
    py = evaluate_trades(TRADES)
    for k, want in expected["evaluateTrades"].items():
        if not _approx(py[k], want, EPS_ACCT):
            failures.append(f"evaluateTrades[{k}] hand: {py[k]} != {want}")
        if k in js["evaluateTrades"] and not _approx(py[k], js["evaluateTrades"][k], EPS_ACCT):
            failures.append(f"evaluateTrades[{k}] JS: {py[k]} != {js['evaluateTrades'][k]}")

    rc = reconcile(1000.0, TRADES, 100.0)
    for k, want in expected["reconcile"].items():
        if not _approx(rc[k], want, EPS_ACCT):
            failures.append(f"reconcile[{k}] hand: {rc[k]} != {want}")
    for k in ("realizedPnl", "unrealizedPnl", "fees", "endingEquity"):
        if not _approx(rc[k], js["reconcile"][k], EPS_ACCT):
            failures.append(f"reconcile[{k}] JS: {rc[k]} != {js['reconcile'][k]}")

    # --- 10A: fold boundaries ----------------------------------------------
    py_folds = fold_boundaries(1000)
    js_folds = js["folds"]
    if len(py_folds["folds"]) != len(js_folds):
        failures.append("fold count mismatch")
    for pf, jf in zip(py_folds["folds"], js_folds):
        if pf != jf:
            failures.append(f"fold {pf['fold']}: py {pf} != js {jf}")
    if py_folds["totalTrials"] != js["totalTrials"]:
        failures.append("totalTrials mismatch")

    # --- 10B: DSR, hand-checked moments then JS cross-check ------------------
    for name in RETURNS:
        py_dsr = calc_dsr(RETURNS[name], 18)
        js_dsr = js["dsr"][name]
        for k in ("sharpe", "skew", "kurt", "srStar", "dsr"):
            if not _approx(py_dsr[k], js_dsr[k], EPS):
                failures.append(f"dsr[{name}][{k}] JS: {py_dsr[k]} != {js_dsr[k]}")
    for k, want in expected["dsr_symmetric"].items():
        if not _approx(calc_dsr(RETURNS["dsr_symmetric"], 18)[k], want, EPS):
            failures.append(f"dsr_symmetric[{k}] hand mismatch")
    for k, want in expected["dsr_all_zero"].items():
        if not _approx(calc_dsr(RETURNS["dsr_all_zero"], 18)[k], want, EPS):
            failures.append(f"dsr_all_zero[{k}] hand mismatch")

    # DSR structural invariants (must hold for ANY input)
    for name in RETURNS:
        d = calc_dsr(RETURNS[name], 18)
        if not (0.0 <= d["dsr"] <= 1.0 + EPS):
            failures.append(f"dsr[{name}] out of [0,1]: {d['dsr']}")

    # --- 10B: calibration, monotonicity + bounds + JS cross-check -------------
    py_cal = calibrate(TRADES)
    js_cal = js["calibration"]
    for s, v in py_cal.items():
        if not (0.05 - EPS <= v <= 0.95 + EPS):
            failures.append(f"calibration[{s}] out of [0.05,0.95]: {v}")
        if not _approx(v, js_cal[s], EPS):
            failures.append(f"calibration[{s}] JS: {v} != {js_cal[s]}")
    scores = sorted((int(s), v) for s, v in py_cal.items())
    for (s1, v1), (s2, v2) in zip(scores, scores[1:]):
        if v2 < v1 - EPS:
            failures.append(f"calibration not monotonic at {s1}->{s2}: {v1} -> {v2}")

    # --- report -------------------------------------------------------------
    if failures:
        print("REFERENCE BACKTEST: FAIL")
        for f in failures:
            print("  -", f)
        return 1
    print("REFERENCE BACKTEST: ALL ASSERTIONS PASSED")
    print(f"  accounting: evaluateTrades total={py['total']} wr={py['wr']:.4f} pf={py['pf']:.4f} exp={py['exp']:.4f} maxDd={py['maxDd']:.4f}")
    print(f"  reconcile:   endingEquity={rc['endingEquity']:.2f} (realized {rc['realizedPnl']:.2f}, unrealized {rc['unrealizedPnl']:.2f}, fees {rc['fees']:.2f})")
    print(f"  folds:       {py_folds['folds']}")
    print(f"  DSR:         symmetric sharpe={calc_dsr(RETURNS['dsr_symmetric'], 18)['sharpe']:.4f} kurt={calc_dsr(RETURNS['dsr_symmetric'], 18)['kurt']:.4f}")
    print(f"  calibration: monotonic, P(Long=50)={py_cal['50']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
