#!/usr/bin/env python3
"""Run the bounded Revision-2 mutation audit and restore source bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "Symbiose_Dashboard.html"

MUTATIONS = [
    {
        "id": "M01",
        "function": "Score-Berechnung",
        "mutation": "Trendbeitrag: Vorzeichen flippen",
        "expected": "Golden-Parität oder Score-Tests werden rot",
        "old": "SYM.wTrend * ts_ + SYM.wMom * msz",
        "new": "-SYM.wTrend * ts_ + SYM.wMom * msz",
    },
    {
        "id": "M02",
        "function": "Score-Berechnung",
        "mutation": "Volumen-Input um 1 verschieben",
        "expected": "Golden-Parität oder Score-Tests werden rot",
        "old": "SYM.wVol * vsc + SYM.wStr * ssc",
        "new": "SYM.wVol * (vsc + 1) + SYM.wStr * ssc",
    },
    {
        "id": "M03",
        "function": "Score-Berechnung",
        "mutation": "Momentum-Verknüpfung + durch - ersetzen",
        "expected": "Golden-Parität oder Score-Tests werden rot",
        "old": "SYM.wTrend * ts_ + SYM.wMom * msz + SYM.wVol",
        "new": "SYM.wTrend * ts_ - SYM.wMom * msz + SYM.wVol",
    },
    {
        "id": "M04",
        "function": "calcKelly",
        "mutation": "Kelly-Zähler -1 durch +1 ersetzen",
        "expected": "Kelly-Unit-Tests werden rot",
        "old": "const fStar = (p * (b + 1) - 1) / b;",
        "new": "const fStar = (p * (b + 1) + 1) / b;",
    },
    {
        "id": "M05",
        "function": "calcKelly",
        "mutation": "Half-Kelly-Faktor 0.5 auf -0.5 flippen",
        "expected": "Kelly-Unit-Tests werden rot",
        "old": "const halfKelly = 0.5 * fStar;",
        "new": "const halfKelly = -0.5 * fStar;",
    },
    {
        "id": "M06",
        "function": "calcKelly",
        "mutation": "hasEdge-Vergleich > 0 auf < 0 umdrehen",
        "expected": "Kelly-Unit-Tests werden rot",
        "old": "const hasEdge = finalFrac > 0;",
        "new": "const hasEdge = finalFrac < 0;",
    },
    {
        "id": "M07",
        "function": "Regime-Gate",
        "mutation": "Gate-Aktivierung if(regimeGate) invertieren",
        "expected": "Regime-/Backtest-Tests werden rot",
        "old": "    if (regimeGate) {\n      const reg = regimeOf(A, i);",
        "new": "    if (!regimeGate) {\n      const reg = regimeOf(A, i);",
    },
    {
        "id": "M08",
        "function": "Regime-Gate",
        "mutation": "Long-Regime != 1 auf == 1 umdrehen",
        "expected": "Regime-/Backtest-Tests werden rot",
        "old": "if (dir === 1 && reg.reg !== 1) continue;",
        "new": "if (dir === 1 && reg.reg === 1) continue;",
    },
    {
        "id": "M09",
        "function": "Regime-Gate",
        "mutation": "Squeeze-Veto if(reg.isSqz) invertieren",
        "expected": "Regime-/Backtest-Tests werden rot",
        "old": "if (reg.isSqz) continue;",
        "new": "if (!reg.isSqz) continue;",
    },
    {
        "id": "M10",
        "function": "Liquiditäts-Gate",
        "mutation": "liquidityVerified !== true auf === true umdrehen",
        "expected": "Autobot-Liquiditätstest wird rot",
        "old": "universeRow.liquidityVerified !== true ||",
        "new": "universeRow.liquidityVerified === true ||",
    },
    {
        "id": "M11",
        "function": "Liquiditäts-Gate",
        "mutation": "Volumenvergleich < min24hVol auf >= umdrehen",
        "expected": "Autobot-Liquiditätstest wird rot",
        "old": "+universeRow.vol < this.min24hVol) {",
        "new": "+universeRow.vol >= this.min24hVol) {",
    },
    {
        "id": "M12",
        "function": "Liquiditäts-Gate",
        "mutation": "Verknüpfung unverified || invalid-volume auf && ändern",
        "expected": "Fail-closed-Liquiditätstest wird rot",
        "old": "universeRow.liquidityVerified !== true ||\n          !Number.isFinite(+universeRow.vol)",
        "new": "universeRow.liquidityVerified !== true &&\n          !Number.isFinite(+universeRow.vol)",
    },
    {
        "id": "M13",
        "function": "Time-Stop-Skalierung",
        "mutation": "Millisekunden-Skalierung * 60000 auf / 60000 flippen",
        "expected": "Time-Stop-Live-Tracker-Test wird rot",
        "old": "(t.timeStopBars || 12) * tfMinutes * 60000",
        "new": "(t.timeStopBars || 12) * tfMinutes / 60000",
    },
    {
        "id": "M14",
        "function": "Time-Stop-Skalierung",
        "mutation": "Verlustvergleich curRoi < -3.0 auf > -3.0 umdrehen",
        "expected": "Asymmetrischer Time-Stop-Test wird rot",
        "old": "curRoi < -3.0) {",
        "new": "curRoi > -3.0) {",
    },
    {
        "id": "M15",
        "function": "Time-Stop-Skalierung",
        "mutation": "Fallback-Time-Stop 12 auf 13 Bars verschieben",
        "expected": "Time-Stop-Fallback-Test wird rot",
        "old": "(t.timeStopBars || 12) * tfMinutes * 60000",
        "new": "(t.timeStopBars || 13) * tfMinutes * 60000",
    },
]


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=300)


def last_nonempty_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else "(keine Ausgabe)"


def run_full_suite() -> dict[str, Any]:
    js_files = sorted((ROOT / "tests").glob("test_*.js"))
    js_failures = []
    for test_file in js_files:
        result = run(["node", str(test_file.relative_to(ROOT))])
        if result.returncode != 0:
            js_failures.append(
                {
                    "test": str(test_file.relative_to(ROOT)),
                    "exit": result.returncode,
                    "last_output": last_nonempty_line(result.stdout + "\n" + result.stderr),
                }
            )

    pytest_result = run([sys.executable, "-m", "pytest", "-q"])
    return {
        "js_test_count": len(js_files),
        "js_failures": js_failures,
        "pytest_exit": pytest_result.returncode,
        "pytest_last_output": last_nonempty_line(pytest_result.stdout + "\n" + pytest_result.stderr),
        "killed": bool(js_failures) or pytest_result.returncode != 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="/tmp/aura_rev2_mutation_results.json")
    args = parser.parse_args()

    original = DASHBOARD.read_bytes()
    original_text = original.decode("utf-8")
    original_sha256 = hashlib.sha256(original).hexdigest()
    results = []

    try:
        for mutation in MUTATIONS:
            occurrences = original_text.count(mutation["old"])
            if occurrences != 1:
                raise RuntimeError(
                    f"{mutation['id']}: expected exactly one target occurrence, found {occurrences}"
                )

            DASHBOARD.write_text(
                original_text.replace(mutation["old"], mutation["new"], 1), encoding="utf-8"
            )
            started = time.monotonic()
            suite = run_full_suite()
            duration = round(time.monotonic() - started, 3)
            result = {
                "id": mutation["id"],
                "function": mutation["function"],
                "mutation": mutation["mutation"],
                "expected": mutation["expected"],
                "status": "KILLED" if suite["killed"] else "SURVIVED",
                "duration_seconds": duration,
                **suite,
            }
            results.append(result)
            triggers = [failure["test"] for failure in suite["js_failures"]]
            if suite["pytest_exit"] != 0:
                triggers.append("python3 -m pytest -q")
            print(
                f"{mutation['id']} {mutation['function']}: {result['status']} | "
                f"JS={suite['js_test_count']} PytestExit={suite['pytest_exit']} | "
                f"Trigger={', '.join(triggers) if triggers else 'keiner'}",
                flush=True,
            )
    finally:
        DASHBOARD.write_bytes(original)

    restored = DASHBOARD.read_bytes()
    restore_sha256 = hashlib.sha256(restored).hexdigest()
    diff = run(["git", "diff", "--", str(DASHBOARD.relative_to(ROOT))])
    verification = {
        "source_sha256_before": original_sha256,
        "source_sha256_after": restore_sha256,
        "source_bytes_restored": restored == original,
        "git_diff_empty": diff.returncode == 0 and diff.stdout == "",
        "git_diff_exit": diff.returncode,
    }
    payload = {"mutations": results, "restore_verification": verification}
    pathlib.Path(args.output).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verification, sort_keys=True))
    print(
        f"SUMMARY killed={sum(item['status'] == 'KILLED' for item in results)} "
        f"survived={sum(item['status'] == 'SURVIVED' for item in results)} total={len(results)}"
    )
    return 0 if verification["source_bytes_restored"] and verification["git_diff_empty"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
