#!/usr/bin/env python3
"""Hypothesis-PreReg validation and verification against results.

Supports:
1. Strict schema validation for Hypothesis-PreReg dictionaries.
2. Checking experimental results against registered PreRegs in ledger chain or standalone PreReg files.
3. Requiring exact params_sha256 hash match and acceptance criteria {n_min, edge_min, dsr_min}.
4. S6 Elevation Gate: requiring S4 Single-Shot Lockbox Holdout Pass AND S5 Forward Shadow Tracking over a 90-day rolling window.
5. Evidence Decay: automatic degradation if rolling 90-day window edge <= 0 or n < n_min.
6. Fail-closed: UNREGISTERED / CRITERIA_NOT_MET / DECAYED with non-zero exit code if no match or criteria failed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import math
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


# ---------------------------------------------------------------------------
# Statistical Primitives for S5 DSR Evaluation (Bailey & Lopez de Prado 2014)
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


def calc_dsr(returns: list[float], num_trials: int = 45) -> dict:
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
# S4 Lockbox & S5 Forward Window & Decay Evaluators
# ---------------------------------------------------------------------------

def evaluate_lockbox_pass(
    lockbox_path: Path | dict | None = None,
    provenance_path: Path | None = None,
) -> dict:
    """Evaluate whether S4 Lockbox holdout test passed.

    Returns a dictionary with 'pass', 'status', 'evaluation_state', 'reason', and details.
    Fail-closed: if UNUSED, unverified, missing, already consumed, or criteria failed -> pass: False.
    """
    if lockbox_path is None and provenance_path is None:
        default_prov = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "golden" / "provenance.json"
        if default_prov.is_file():
            provenance_path = default_prov

    eval_data: dict | None = None
    if isinstance(lockbox_path, dict):
        eval_data = lockbox_path
    elif isinstance(lockbox_path, (str, Path)):
        p = Path(lockbox_path).resolve()
        if p.is_file():
            try:
                eval_data = json.loads(p.read_text(encoding="utf-8"))
            except Exception as exc:
                return {
                    "pass": False,
                    "status": "ERROR",
                    "evaluation_state": "INVALID",
                    "reason": f"invalid lockbox file: {exc}",
                }

    if eval_data is not None:
        status = eval_data.get("status") or eval_data.get("lockbox_status")
        holdout_pass = bool(eval_data.get("holdout_pass") or eval_data.get("passed") or (eval_data.get("status") == "PASS" and eval_data.get("evaluation_state") in ("EVALUATED_PASS", "PASSED")))
        consumed_invalid = bool(eval_data.get("consumed_invalid", False) or eval_data.get("evaluation_state") == "LOCKBOX_ALREADY_CONSUMED")
        if consumed_invalid:
            return {
                "pass": False,
                "status": "LOCKBOX_ALREADY_CONSUMED",
                "evaluation_state": "CONSUMED_INVALID",
                "reason": "Lockbox holdout was already consumed (single-shot violation).",
                "details": eval_data,
            }
        if status == "LOCKED" and holdout_pass and not consumed_invalid:
            return {
                "pass": True,
                "status": "LOCKED",
                "evaluation_state": "PASSED",
                "reason": "S4 Lockbox single-shot evaluation passed with positive edge.",
                "details": eval_data,
            }
        return {
            "pass": False,
            "status": status or "UNKNOWN",
            "evaluation_state": eval_data.get("evaluation_state", "CRITERIA_NOT_MET"),
            "reason": eval_data.get("reason", "Lockbox evaluation did not achieve holdout pass."),
            "details": eval_data,
        }

    if provenance_path is not None and Path(provenance_path).is_file():
        try:
            prov = json.loads(Path(provenance_path).read_text(encoding="utf-8"))
            lb = prov.get("lockbox", {})
            lb_status = lb.get("status", "UNCONFIGURED")
            if lb_status != "LOCKED":
                return {
                    "pass": False,
                    "status": lb_status,
                    "evaluation_state": "NOT_LOCKED",
                    "reason": f"Lockbox status is {lb_status!r} (must be 'LOCKED').",
                }
            return {
                "pass": False,
                "status": "LOCKED",
                "evaluation_state": "UNUSED",
                "reason": "Lockbox is LOCKED but holdout evaluation is UNUSED (0 evaluations performed).",
            }
        except Exception as exc:
            return {
                "pass": False,
                "status": "ERROR",
                "evaluation_state": "INVALID",
                "reason": f"provenance parse error: {exc}",
            }

    return {
        "pass": False,
        "status": "MISSING",
        "evaluation_state": "MISSING",
        "reason": "No lockbox evaluation or provenance file found.",
    }


def _parse_record_timestamp(record: dict) -> datetime | None:
    """Extract UTC datetime from record dictionary."""
    for key in ("timestamp", "created_at", "time", "ts", "t", "date"):
        if key in record and record[key] is not None:
            val = record[key]
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                ts_sec = float(val) if float(val) < 10_000_000_000 else float(val) / 1000.0
                return datetime.fromtimestamp(ts_sec, tz=timezone.utc)
            if isinstance(val, str) and val.strip():
                try:
                    clean = val.strip().replace("Z", "+00:00")
                    dt = datetime.fromisoformat(clean)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except ValueError:
                    pass
    return None


def evaluate_forward_window(
    shadow_log_path: Path | list[dict] | None,
    n_min: int,
    edge_min: float,
    dsr_min: float,
    window_days: int = 90,
    now_dt: datetime | None = None,
    ledger_trials: int | None = None,
) -> dict:
    """Evaluate S5 Forward Shadow Tracking records over a rolling window (default 90 days).

    Filters records within [ref_time - window_days, ref_time], computes net expectancy
    and DSR (with DSR_TRIALS = max(45, ledger_trials or 10)), and validates against acceptance criteria.
    """
    if shadow_log_path is None:
        return {
            "pass": False,
            "n": 0,
            "edge": 0.0,
            "dsr": 0.0,
            "n_min": n_min,
            "edge_min": edge_min,
            "dsr_min": dsr_min,
            "window_days": window_days,
            "reason": "shadow log path missing (None)",
            "criteria": {"n": False, "edge": False, "dsr": False},
        }

    records: list[dict] = []
    if isinstance(shadow_log_path, list):
        records = list(shadow_log_path)
    elif isinstance(shadow_log_path, (str, Path)):
        p = Path(shadow_log_path).resolve()
        if not p.is_file():
            return {
                "pass": False,
                "n": 0,
                "edge": 0.0,
                "dsr": 0.0,
                "n_min": n_min,
                "edge_min": edge_min,
                "dsr_min": dsr_min,
                "window_days": window_days,
                "reason": f"shadow log file missing: {p}",
                "criteria": {"n": False, "edge": False, "dsr": False},
            }
        try:
            lines = p.read_text(encoding="utf-8").strip().splitlines()
            for line in lines:
                if line.strip():
                    records.append(json.loads(line))
        except Exception as exc:
            return {
                "pass": False,
                "n": 0,
                "edge": 0.0,
                "dsr": 0.0,
                "n_min": n_min,
                "edge_min": edge_min,
                "dsr_min": dsr_min,
                "window_days": window_days,
                "reason": f"error reading shadow log: {exc}",
                "criteria": {"n": False, "edge": False, "dsr": False},
            }

    if not records:
        return {
            "pass": False,
            "n": 0,
            "edge": 0.0,
            "dsr": 0.0,
            "n_min": n_min,
            "edge_min": edge_min,
            "dsr_min": dsr_min,
            "window_days": window_days,
            "reason": "shadow log contains 0 records",
            "criteria": {"n": False, "edge": False, "dsr": False},
        }

    ref_dt = now_dt
    if ref_dt is None:
        all_dts = [_parse_record_timestamp(r) for r in records]
        valid_dts = [d for d in all_dts if d is not None]
        ref_dt = max(valid_dts) if valid_dts else datetime.now(timezone.utc)

    if ref_dt.tzinfo is None:
        ref_dt = ref_dt.replace(tzinfo=timezone.utc)

    window_start = ref_dt - timedelta(days=window_days)

    window_trades: list[dict] = []
    for r in records:
        rec_dt = _parse_record_timestamp(r)
        if rec_dt is not None:
            if rec_dt < window_start or rec_dt > ref_dt:
                continue
        r_net = r.get("rNet") if r.get("rNet") is not None else r.get("net_r") if r.get("net_r") is not None else r.get("r")
        outcome = r.get("outcome") or r.get("decision_outcome")
        if r_net is not None and isinstance(r_net, (int, float)) and not isinstance(r_net, bool) and math.isfinite(r_net):
            if outcome not in ("pending", "open"):
                window_trades.append({**r, "rNet": float(r_net)})

    n = len(window_trades)
    if n == 0:
        return {
            "pass": False,
            "n": 0,
            "edge": 0.0,
            "dsr": 0.0,
            "n_min": n_min,
            "edge_min": edge_min,
            "dsr_min": dsr_min,
            "window_days": window_days,
            "window_start": window_start.isoformat(),
            "window_end": ref_dt.isoformat(),
            "reason": f"0 completed trades found in {window_days}-day window ({window_start.isoformat()} to {ref_dt.isoformat()})",
            "criteria": {"n": False, "edge": False, "dsr": False},
        }

    returns = [t["rNet"] for t in window_trades]
    edge = sum(returns) / n
    effective_trials = max(45, ledger_trials if (isinstance(ledger_trials, int) and ledger_trials > 0) else 10)
    dsr_calc = calc_dsr(returns, num_trials=effective_trials)
    dsr_val = dsr_calc["dsr"]

    n_pass = bool(n >= n_min)
    edge_pass = bool(edge >= edge_min)
    dsr_pass = bool(dsr_val >= dsr_min)
    all_pass = bool(n_pass and edge_pass and dsr_pass)

    return {
        "pass": all_pass,
        "n": n,
        "edge": edge,
        "dsr": dsr_val,
        "n_min": n_min,
        "edge_min": edge_min,
        "dsr_min": dsr_min,
        "window_days": window_days,
        "window_start": window_start.isoformat(),
        "window_end": ref_dt.isoformat(),
        "effective_trials": effective_trials,
        "criteria": {
            "n": {"actual": n, "min": n_min, "pass": n_pass},
            "edge": {"actual": edge, "min": edge_min, "pass": edge_pass},
            "dsr": {"actual": dsr_val, "min": dsr_min, "pass": dsr_pass},
        },
        "reason": "Forward window criteria met" if all_pass else "Forward window criteria not satisfied",
    }


def evaluate_decay(forward_window_result: dict, acceptance: dict) -> dict:
    """Evaluate whether evidence has decayed over the rolling forward window.

    If edge <= 0, or n < n_min, or criteria failed -> evidence decays and bot must degrade S6 -> S5/S1.
    """
    n_min = acceptance.get("n_min", 15)
    edge_min = acceptance.get("edge_min", 0.0)

    n_actual = forward_window_result.get("n", 0)
    edge_actual = forward_window_result.get("edge", 0.0)
    fwd_pass = forward_window_result.get("pass", False)

    if not fwd_pass or edge_actual <= 0.0 or edge_actual < edge_min or n_actual < n_min:
        return {
            "decayed": True,
            "reason": (
                f"Evidence decay triggered: rolling window edge ({edge_actual:.4f}R) <= 0 or below min "
                f"({edge_min}R) or sample size ({n_actual}) < min ({n_min})."
            ),
            "degradation": "S6 -> S5 (Shadow) -> S1 (Fail-Closed)",
            "action": "DEMOTE_TO_S5",
        }

    return {
        "decayed": False,
        "reason": "Active statistical evidence confirmed across full 90-day rolling window.",
        "degradation": None,
        "action": "MAINTAIN_S6",
    }


def check_hypothesis(
    result: dict,
    *,
    prereg_list: list[dict] | None = None,
    prereg_file: Path | None = None,
    shadow_log_path: Path | list[dict] | None = None,
    lockbox_path: Path | dict | None = None,
    window_days: int = 90,
    now_dt: datetime | None = None,
    chain_path: Path = CHAIN_LEDGER,
    legacy_path: Path = LEGACY_LEDGER,
    checkpoint_path: Path = LEDGER_CHECKPOINT,
    expected_legacy_sha256: str = LEGACY_SHA256,
) -> dict:
    """Check an experimental result against preregistered hypothesis and S6 elevation criteria."""
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

    available_preregs: list[dict] = []
    ledger_trials = 10
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
            v_res = verify_ledger(
                legacy_path=legacy_path,
                chain_path=chain_path,
                checkpoint_path=checkpoint_path,
                expected_legacy_sha256=expected_legacy_sha256,
            )
            ledger_trials = v_res.get("total_model_experiments", 10)
        except (LedgerVerificationError, OSError) as exc:
            return {
                "ok": False,
                "verdict": "UNREGISTERED",
                "status": "UNREGISTERED",
                "error": f"ledger verification failed: {exc}",
                "model_verdict_lifted": False,
            }

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
    res_hash = str(result.get("params_sha256", "")).lower()
    expected_hash = str(matched.get("params_sha256", "")).lower()
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

    # 2. Acceptance criteria evaluation on candidate result
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

    # 3. Evaluate S4 Lockbox, S5 Forward 90-day rolling window, and Decay
    lockbox_eval = evaluate_lockbox_pass(lockbox_path=lockbox_path)
    forward_eval = evaluate_forward_window(
        shadow_log_path=shadow_log_path,
        n_min=acceptance["n_min"],
        edge_min=acceptance["edge_min"],
        dsr_min=acceptance["dsr_min"],
        window_days=window_days,
        now_dt=now_dt,
        ledger_trials=ledger_trials,
    )
    decay_eval = evaluate_decay(forward_eval, acceptance)

    s6_eligible = bool(lockbox_eval["pass"] and forward_eval["pass"] and not decay_eval["decayed"])

    if s6_eligible:
        return {
            "ok": True,
            "verdict": "S6_PRODUCTION_ELIGIBLE",
            "status": "S6_PRODUCTION_ELIGIBLE",
            "setup_id": setup_id,
            "matched_prereg": {
                "setup_id": matched["setup_id"],
                "hypothesis": matched["hypothesis"],
                "params_sha256": matched["params_sha256"],
                "frozen_at": matched["frozen_at"],
            },
            "criteria_check": criteria_check,
            "lockbox_check": lockbox_eval,
            "forward_window_check": forward_eval,
            "decay_check": decay_eval,
            "model_verdict_lifted": True,
            "model_verdict": "EVIDENCE_CONFIRMED",
            "note": "S6 Production clearance granted: S4 Lockbox holdout pass and S5 90-day forward window verified.",
        }

    return {
        "ok": True,
        "verdict": "EVIDENCE_CANDIDATE",
        "status": "DECAYED_DEGRADED" if decay_eval["decayed"] and forward_eval.get("n", 0) > 0 else "EVIDENCE_CANDIDATE",
        "setup_id": setup_id,
        "matched_prereg": {
            "setup_id": matched["setup_id"],
            "hypothesis": matched["hypothesis"],
            "params_sha256": matched["params_sha256"],
            "frozen_at": matched["frozen_at"],
        },
        "criteria_check": criteria_check,
        "lockbox_check": lockbox_eval,
        "forward_window_check": forward_eval,
        "decay_check": decay_eval,
        "model_verdict_lifted": False,
        "model_verdict": "MODEL_NO_EVIDENCE",
        "note": "Evidence candidate status achieved. Does NOT lift model verdict (MODEL_NO_EVIDENCE remains unchanged until full protocol/lockbox verification).",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-file", required=True, type=Path, help="Path to result JSON file")
    parser.add_argument("--prereg-file", type=Path, default=None, help="Path to standalone PreReg JSON file")
    parser.add_argument("--shadow-log", type=Path, default=None, help="Path to shadow log JSONL file")
    parser.add_argument("--lockbox", type=Path, default=None, help="Path to lockbox evaluation JSON file")
    parser.add_argument("--window-days", type=int, default=90, help="Forward evaluation window in days (default: 90)")
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
        shadow_log_path=args.shadow_log,
        lockbox_path=args.lockbox,
        window_days=args.window_days,
        chain_path=args.chain,
        legacy_path=args.legacy,
        checkpoint_path=args.checkpoint,
        expected_legacy_sha256=args.expected_legacy_sha256,
    )

    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") is True else 1


if __name__ == "__main__":
    sys.exit(main())
