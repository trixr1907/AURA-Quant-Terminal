#!/usr/bin/env python3
"""
Independent Python reference implementation for Cumulative Volume Delta (CVD).

Formelquelle: Symbiose_Signal_System_v1.pine:209-215, 479, 702-705
Serialisierungsformat: UTF-8, JSON mit Float64-Arrays und Drift-Metriken
Datum: 2026-09-12

Vergleicht die unabhängige Python-Berechnung mit dem realen JavaScript-
Dashboard-Analyzer auf den fünf Golden-Master-Fixtures (BTC/ETH/SOL 1h, XRP/DOGE 4h).
"""

from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = ROOT / "tests" / "fixtures" / "golden"
GOLDEN_FILES = [
    "BTCUSDT_1h.csv",
    "ETHUSDT_1h.csv",
    "SOLUSDT_1h.csv",
    "XRPUSDT_4h.csv",
    "DOGEUSDT_4h.csv",
]
MIN_BARS = 5000
MAX_RELATIVE_DRIFT_THRESHOLD = 1e-10


def parse_csv_ohlcv(path: Path) -> list[dict[str, float]]:
    with path.open("r", encoding="utf-8-sig") as stream:
        reader = csv.reader(stream)
        headers = [h.strip().lower() for h in next(reader)]
        try:
            h_idx = headers.index("high")
            l_idx = headers.index("low")
            c_idx = headers.index("close")
            v_idx = headers.index("volume")
        except ValueError as exc:
            raise ValueError(f"Missing required OHLCV column in {path}: {exc}") from exc

        rows = []
        for row in reader:
            if not row:
                continue
            rows.append({
                "high": float(row[h_idx]),
                "low": float(row[l_idx]),
                "close": float(row[c_idx]),
                "volume": float(row[v_idx]),
            })
    return rows


def compute_python_reference(path: Path) -> dict[str, list[float]]:
    """Compute CVD, EMA(20) and delta using math.fsum prefix summation."""
    rows = parse_csv_ohlcv(path)
    n = len(rows)
    if n == 0:
        return {"delta": [], "cvd": [], "ema_cvd": []}

    deltas: list[float] = []
    for r in rows:
        h, l, c, v = r["high"], r["low"], r["close"], r["volume"]
        rng = h - l
        delta = (v * (2.0 * c - h - l) / rng) if rng > 0.0 else 0.0
        deltas.append(delta)

    # Deliberate alternate summation using exact math.fsum on prefixes
    cvd = [math.fsum(deltas[: i + 1]) for i in range(n)]

    # EMA 20: alpha = 2 / 21
    alpha = 2.0 / 21.0
    ema_cvd = [0.0] * n
    e = cvd[0]
    ema_cvd[0] = e
    for i in range(1, n):
        e = cvd[i] * alpha + e * (1.0 - alpha)
        ema_cvd[i] = e

    return {"delta": deltas, "cvd": cvd, "ema_cvd": ema_cvd}


def extract_js_dashboard_output(path: Path) -> dict[str, list[float]]:
    script = ROOT / "scripts" / "cvd_dashboard_export.js"
    proc = subprocess.run(
        ["node", str(script), str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    return {
        "delta": [float(x) for x in data["delta"]],
        "cvd": [float(x) for x in data["cvd"]],
        "ema_cvd": [float(x) for x in data["ema_cvd"]],
    }


def compare_series(
    fixture_name: str,
    py_res: dict[str, list[float]],
    js_res: dict[str, list[float]],
    min_bars: int = MIN_BARS,
    drift_threshold: float = MAX_RELATIVE_DRIFT_THRESHOLD,
) -> dict:
    bars = len(py_res["cvd"])
    if bars != len(js_res["cvd"]):
        raise ValueError(f"Bar count mismatch for {fixture_name}: py={bars}, js={len(js_res['cvd'])}")

    max_abs_cvd = 0.0
    max_abs_ema = 0.0
    max_rel_drift = 0.0
    flip_count = 0

    for i in range(bars):
        py_c = py_res["cvd"][i]
        js_c = js_res["cvd"][i]
        py_e = py_res["ema_cvd"][i]
        js_e = js_res["ema_cvd"][i]

        d_cvd = abs(py_c - js_c)
        d_ema = abs(py_e - js_e)
        if d_cvd > max_abs_cvd:
            max_abs_cvd = d_cvd
        if d_ema > max_abs_ema:
            max_abs_ema = d_ema

        scale_c = max(1.0, abs(py_c), abs(js_c))
        scale_e = max(1.0, abs(py_e), abs(js_e))
        rel_c = d_cvd / scale_c
        rel_e = d_ema / scale_e
        if rel_c > max_rel_drift:
            max_rel_drift = rel_c
        if rel_e > max_rel_drift:
            max_rel_drift = rel_e

        py_above = py_c > py_e
        js_above = js_c > js_e
        if py_above != js_above:
            flip_count += 1

    end_abs_cvd = abs(py_res["cvd"][-1] - js_res["cvd"][-1]) if bars else 0.0
    end_abs_ema = abs(py_res["ema_cvd"][-1] - js_res["ema_cvd"][-1]) if bars else 0.0

    passed = (bars >= min_bars) and (flip_count == 0) and (max_rel_drift <= drift_threshold)

    return {
        "fixture": fixture_name,
        "bars": bars,
        "max_abs_cvd_drift": max_abs_cvd,
        "end_abs_cvd_drift": end_abs_cvd,
        "max_abs_ema_cvd_drift": max_abs_ema,
        "end_abs_ema_cvd_drift": end_abs_ema,
        "max_relative_drift": max_rel_drift,
        "flip_count": flip_count,
        "passed": passed,
    }


def run_full_parity_audit() -> dict:
    results = []
    all_passed = True
    for fname in GOLDEN_FILES:
        path = GOLDEN_DIR / fname
        py_res = compute_python_reference(path)
        js_res = extract_js_dashboard_output(path)
        comp = compare_series(fname, py_res, js_res)
        results.append(comp)
        if not comp["passed"]:
            all_passed = False

    return {
        "ok": all_passed,
        "thresholds": {
            "min_bars": MIN_BARS,
            "max_relative_drift": MAX_RELATIVE_DRIFT_THRESHOLD,
            "max_flip_count": 0,
        },
        "fixtures": results,
    }


def main() -> int:
    report = run_full_parity_audit()
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
