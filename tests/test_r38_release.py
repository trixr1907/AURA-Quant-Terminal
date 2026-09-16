"""Expose the R38 JavaScript behavioral guards to pytest discovery."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_node_test(name: str) -> None:
    result = subprocess.run(
        ["node", f"tests/{name}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_r38_quant_guards() -> None:
    run_node_test("test_r38_quant_guards.js")


def test_r38_dsr_default_trials() -> None:
    run_node_test("test_dsr_default_trials.js")


def test_r38_score_clamp_negative() -> None:
    run_node_test("test_score_clamp_negative.js")


def test_r38_dsr_display_matches_operative_gate() -> None:
    run_node_test("test_r38_dsr_display.js")
