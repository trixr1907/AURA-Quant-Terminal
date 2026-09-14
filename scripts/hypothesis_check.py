#!/usr/bin/env python3
"""Hypothesis-PreReg validation and verification against results.

Supports:
1. Strict schema validation for Hypothesis-PreReg dictionaries.
2. Checking experimental results against registered PreRegs in ledger chain or standalone PreReg files.
3. Requiring exact params_sha256 hash match and acceptance criteria {n_min, edge_min, dsr_min}.
4. Fail-closed: UNREGISTERED / CRITERIA_NOT_MET with non-zero exit code if no match or criteria failed.
5. EVIDENCE_CANDIDATE status on match, with explicit invariant: does NOT lift model verdict.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys

from verify_ledger import (
    CHAIN_LEDGER,
    FIRST_ENTRY_ID,
    HASH_RE,
    LEDGER_CHECKPOINT,
    LEGACY_LEDGER,
    LEGACY_SHA256,
    BASELINE_TOTAL,
    LedgerVerificationError,
    verify_ledger,
)

PREREG_MANDATORY_FIELDS = (
    "setup_id",
    "symbol",
    "tf",
    "regime_context",
    "hypothesis",
    "params_sha256",
    "acceptance",
    "status",
    "frozen_at",
)

ACCEPTANCE_FIELDS = ("n_min", "edge_min", "dsr_min")


class PreregValidationError(ValueError):
    """Raised when a Hypothesis-PreReg structure is invalid."""


def parse_iso_datetime(value: object, field_name: str = "date") -> datetime:
    """Parse an ISO-8601 string or raise PreregValidationError."""
    if not isinstance(value, str) or not value.strip():
        raise PreregValidationError(f"{field_name} must be a non-empty ISO-8601 string")
    clean = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(clean)
    except (ValueError, TypeError) as exc:
        raise PreregValidationError(f"invalid ISO-8601 timestamp in {field_name}: {value!r}") from exc


def validate_prereg(data: object) -> bool:
    """Validate all mandatory fields and invariants of a Hypothesis-PreReg dictionary."""
    if not isinstance(data, dict):
        raise PreregValidationError("prereg data must be a dictionary")

    # Check mandatory string/dict fields
    for field in PREREG_MANDATORY_FIELDS:
        if field not in data:
            raise PreregValidationError(f"missing mandatory field: {field}")

    # Validate string text fields
    for field in ("setup_id", "symbol", "tf", "regime_context", "hypothesis"):
        val = data[field]
        if not isinstance(val, str) or not val.strip():
            raise PreregValidationError(f"field {field!r} must be a non-empty string")

    # Validate params_sha256
    sha = data["params_sha256"]
    if not isinstance(sha, str) or not HASH_RE.fullmatch(sha.lower()):
        raise PreregValidationError(f"invalid params_sha256: {sha!r} (must be 64-character hex)")

    # Validate acceptance criteria
    acc = data["acceptance"]
    if not isinstance(acc, dict):
        raise PreregValidationError("acceptance must be a dictionary")
    for acc_field in ACCEPTANCE_FIELDS:
        if acc_field not in acc:
            raise PreregValidationError(f"acceptance missing mandatory field: {acc_field}")
        val = acc[acc_field]
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise PreregValidationError(f"acceptance.{acc_field} must be numeric")

    n_min = acc["n_min"]
    if isinstance(n_min, bool) or not isinstance(n_min, int) or n_min <= 0:
        raise PreregValidationError(f"acceptance.n_min must be positive integer, got {n_min!r}")

    # Validate horizon: exactly one of 'bars' or 'until_date'
    has_bars = "bars" in data and data["bars"] is not None
    has_until = "until_date" in data and data["until_date"] is not None

    if has_bars == has_until:
        raise PreregValidationError("prereg must specify exactly one horizon type: 'bars' or 'until_date'")

    if has_bars:
        bars = data["bars"]
        if isinstance(bars, bool) or not isinstance(bars, int) or bars <= 0:
            raise PreregValidationError(f"bars horizon must be positive integer, got {bars!r}")
    else:
        parse_iso_datetime(data["until_date"], field_name="until_date")

    # Validate status
    if data["status"] != "PREREGISTERED":
        raise PreregValidationError(f"prereg status must be 'PREREGISTERED', got {data['status']!r}")

    # Validate frozen_at
    parse_iso_datetime(data["frozen_at"], field_name="frozen_at")

    return True


def parse_prereg_from_entry(entry: dict) -> dict | None:
    """Extract a Hypothesis-PreReg payload from a ledger entry if present."""
    if entry.get("type") != "Hypothesis-PreReg" and entry.get("status") != "PREREGISTERED":
        return None

    # Check if change contains JSON-encoded prereg
    change_raw = entry.get("change", "")
    if isinstance(change_raw, str) and change_raw.strip().startswith("{"):
        try:
            payload = json.loads(change_raw)
            if isinstance(payload, dict) and "setup_id" in payload:
                # Merge top-level hypothesis/status if not in payload
                full = {
                    "hypothesis": entry.get("hypothesis", ""),
                    "status": entry.get("status", "PREREGISTERED"),
                    **payload,
                }
                if validate_prereg(full):
                    return full
        except (json.JSONDecodeError, PreregValidationError):
            pass

    return None


def load_preregistrations_from_chain(
    chain_path: Path = CHAIN_LEDGER,
    legacy_path: Path = LEGACY_LEDGER,
    checkpoint_path: Path = LEDGER_CHECKPOINT,
    expected_legacy_sha256: str = LEGACY_SHA256,
    first_entry_id: int = FIRST_ENTRY_ID,
    baseline_total: int = BASELINE_TOTAL,
) -> list[dict]:
    """Verify the ledger chain and load all validated Hypothesis-PreReg entries."""
    verify_ledger(
        legacy_path=legacy_path,
        chain_path=chain_path,
        checkpoint_path=checkpoint_path,
        expected_legacy_sha256=expected_legacy_sha256,
        first_entry_id=first_entry_id,
        baseline_total=baseline_total,
    )

    preregs: list[dict] = []
    lines = chain_path.resolve().read_text(encoding="utf-8").strip().splitlines()
    for line in lines:
        if not line:
            continue
        try:
            entry = json.loads(line)
            prereg = parse_prereg_from_entry(entry)
            if prereg:
                preregs.append(prereg)
        except json.JSONDecodeError:
            continue
    return preregs


def check_hypothesis(
    result: dict,
    *,
    prereg_list: list[dict] | None = None,
    prereg_file: Path | None = None,
    chain_path: Path = CHAIN_LEDGER,
    legacy_path: Path = LEGACY_LEDGER,
    checkpoint_path: Path = LEDGER_CHECKPOINT,
    expected_legacy_sha256: str = LEGACY_SHA256,
) -> dict:
    """Check an experimental result against preregistered hypothesis."""
    if not isinstance(result, dict):
        return {
            "ok": False,
            "verdict": "UNREGISTERED",
            "status": "UNREGISTERED",
            "error": "result must be a dictionary",
            "model_verdict_lifted": False,
        }

    setup_id = result.get("setup_id")
    if not setup_id or not isinstance(setup_id, str):
        return {
            "ok": False,
            "verdict": "UNREGISTERED",
            "status": "UNREGISTERED",
            "error": "result missing setup_id",
            "model_verdict_lifted": False,
        }

    # Load preregistrations
    available_preregs: list[dict] = []
    if prereg_file is not None:
        p_path = prereg_file.resolve()
        if not p_path.is_file():
            return {
                "ok": False,
                "verdict": "UNREGISTERED",
                "status": "UNREGISTERED",
                "error": f"prereg file missing: {p_path}",
                "model_verdict_lifted": False,
            }
        try:
            single = json.loads(p_path.read_text(encoding="utf-8"))
            validate_prereg(single)
            available_preregs.append(single)
        except Exception as exc:
            return {
                "ok": False,
                "verdict": "UNREGISTERED",
                "status": "UNREGISTERED",
                "error": f"invalid prereg file: {exc}",
                "model_verdict_lifted": False,
            }
    elif prereg_list is not None:
        available_preregs = list(prereg_list)
    else:
        try:
            available_preregs = load_preregistrations_from_chain(
                chain_path=chain_path,
                legacy_path=legacy_path,
                checkpoint_path=checkpoint_path,
                expected_legacy_sha256=expected_legacy_sha256,
            )
        except (LedgerVerificationError, OSError) as exc:
            return {
                "ok": False,
                "verdict": "UNREGISTERED",
                "status": "UNREGISTERED",
                "error": f"ledger verification failed: {exc}",
                "model_verdict_lifted": False,
            }

    # Find matching prereg by setup_id
    matched = next((p for p in available_preregs if p["setup_id"] == setup_id), None)
    if matched is None:
        return {
            "ok": False,
            "verdict": "UNREGISTERED",
            "status": "UNREGISTERED",
            "setup_id": setup_id,
            "error": f"no preregistration found for setup_id {setup_id!r}",
            "model_verdict_lifted": False,
        }

    # 1. Parameter hash matching (must match exact SHA-256)
    res_hash = result.get("params_sha256", "").lower()
    expected_hash = matched.get("params_sha256", "").lower()
    if not res_hash or res_hash != expected_hash:
        return {
            "ok": False,
            "verdict": "UNREGISTERED",
            "status": "UNREGISTERED",
            "setup_id": setup_id,
            "error": f"params_sha256 mismatch: expected {expected_hash}, got {res_hash}",
            "expected_hash": expected_hash,
            "actual_hash": res_hash,
            "model_verdict_lifted": False,
        }

    # 2. Acceptance criteria evaluation
    acceptance = matched["acceptance"]
    n_actual = result.get("n")
    edge_actual = result.get("edge")
    dsr_actual = result.get("dsr")

    n_pass = isinstance(n_actual, (int, float)) and not isinstance(n_actual, bool) and n_actual >= acceptance["n_min"]
    edge_pass = isinstance(edge_actual, (int, float)) and not isinstance(edge_actual, bool) and edge_actual >= acceptance["edge_min"]
    dsr_pass = isinstance(dsr_actual, (int, float)) and not isinstance(dsr_actual, bool) and dsr_actual >= acceptance["dsr_min"]

    criteria_check = {
        "n": {"actual": n_actual, "min": acceptance["n_min"], "pass": bool(n_pass)},
        "edge": {"actual": edge_actual, "min": acceptance["edge_min"], "pass": bool(edge_pass)},
        "dsr": {"actual": dsr_actual, "min": acceptance["dsr_min"], "pass": bool(dsr_pass)},
    }

    all_criteria_met = bool(n_pass and edge_pass and dsr_pass)

    if not all_criteria_met:
        return {
            "ok": False,
            "verdict": "CRITERIA_NOT_MET",
            "status": "REJECTED",
            "setup_id": setup_id,
            "criteria_check": criteria_check,
            "model_verdict_lifted": False,
            "note": "Acceptance criteria not satisfied.",
        }

    return {
        "ok": True,
        "verdict": "EVIDENCE_CANDIDATE",
        "status": "EVIDENCE_CANDIDATE",
        "setup_id": setup_id,
        "matched_prereg": {
            "setup_id": matched["setup_id"],
            "hypothesis": matched["hypothesis"],
            "params_sha256": matched["params_sha256"],
            "frozen_at": matched["frozen_at"],
        },
        "criteria_check": criteria_check,
        "model_verdict_lifted": False,
        "model_verdict": "MODEL_NO_EVIDENCE",
        "note": "Evidence candidate status achieved. Does NOT lift model verdict (MODEL_NO_EVIDENCE remains unchanged until full protocol/lockbox verification).",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-file", required=True, type=Path, help="Path to result JSON file")
    parser.add_argument("--prereg-file", type=Path, default=None, help="Path to standalone PreReg JSON file")
    parser.add_argument("--legacy", type=Path, default=LEGACY_LEDGER)
    parser.add_argument("--chain", type=Path, default=CHAIN_LEDGER)
    parser.add_argument("--checkpoint", type=Path, default=LEDGER_CHECKPOINT)
    parser.add_argument("--expected-legacy-sha256", default=LEGACY_SHA256)
    args = parser.parse_args()

    try:
        res_data = json.loads(args.result_file.resolve().read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({"ok": False, "verdict": "UNREGISTERED", "error": f"cannot read result file: {exc}"}), file=sys.stderr)
        return 2

    report = check_hypothesis(
        res_data,
        prereg_file=args.prereg_file,
        chain_path=args.chain,
        legacy_path=args.legacy,
        checkpoint_path=args.checkpoint,
        expected_legacy_sha256=args.expected_legacy_sha256,
    )

    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") is True else 1


if __name__ == "__main__":
    sys.exit(main())
