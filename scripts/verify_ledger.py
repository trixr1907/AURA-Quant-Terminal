#!/usr/bin/env python3
"""Verify AURA's append-only trials ledger hash chain."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEGACY_LEDGER = ROOT / "docs" / "research" / "TRIALS_LEDGER_LEGACY_v1.2.8.md"
CHAIN_LEDGER = ROOT / "docs" / "research" / "trials_ledger_chain.jsonl"
LEGACY_SHA256 = "23f59ef8df9f348609280d8f57583e32c2d7afc1e9b428f9d50ae75051eeeb0c"
FIRST_ENTRY_ID = 26
BASELINE_TOTAL = 10
FIELD_ORDER = (
    "id",
    "date",
    "version",
    "type",
    "hypothesis",
    "change",
    "success_criterion",
    "result",
    "delta",
    "total_model_experiments",
    "status",
    "prereg_commit",
    "prev_hash",
)
ALL_FIELDS = set(FIELD_ORDER) | {"entry_hash"}
HASH_RE = re.compile(r"[0-9a-f]{64}")
ID_RE = re.compile(r"EXP-(\d{3,})")


class LedgerVerificationError(ValueError):
    """Raised when ledger evidence is missing or invalid."""


def canonical_entry(entry: dict) -> bytes:
    payload = {field: entry[field] for field in FIELD_ORDER}
    return (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def verify_ledger(
    legacy_path: Path = LEGACY_LEDGER,
    chain_path: Path = CHAIN_LEDGER,
    *,
    expected_legacy_sha256: str = LEGACY_SHA256,
    first_entry_id: int = FIRST_ENTRY_ID,
    baseline_total: int = BASELINE_TOTAL,
) -> dict:
    """Return verified ledger metadata or raise fail-closed."""
    if not legacy_path.is_file():
        raise LedgerVerificationError(f"legacy ledger missing: {legacy_path}")
    if not chain_path.is_file():
        raise LedgerVerificationError(f"chain ledger missing: {chain_path}")

    legacy_hash = hashlib.sha256(legacy_path.read_bytes()).hexdigest()
    if legacy_hash != expected_legacy_sha256:
        raise LedgerVerificationError("legacy ledger SHA-256 mismatch")

    try:
        raw_lines = chain_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise LedgerVerificationError(f"cannot read chain ledger: {exc}") from exc
    if not raw_lines:
        raise LedgerVerificationError("chain ledger has no entries")

    expected_prev = legacy_hash
    expected_id = first_entry_id
    total = baseline_total
    head = legacy_hash
    for line_number, raw_line in enumerate(raw_lines, start=1):
        if not raw_line:
            raise LedgerVerificationError(f"blank entry at line {line_number}")
        try:
            entry = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise LedgerVerificationError(f"invalid JSON at line {line_number}: {exc.msg}") from exc
        if not isinstance(entry, dict):
            raise LedgerVerificationError(f"entry at line {line_number} is not an object")
        if set(entry) != ALL_FIELDS:
            raise LedgerVerificationError(f"invalid fields at line {line_number}")
        if any(isinstance(entry[field], bool) for field in ("delta", "total_model_experiments")):
            raise LedgerVerificationError(f"invalid numeric field at line {line_number}")
        if not isinstance(entry["delta"], int) or entry["delta"] not in (0, 1):
            raise LedgerVerificationError(f"invalid delta at line {line_number}")
        if not isinstance(entry["total_model_experiments"], int):
            raise LedgerVerificationError(f"invalid total at line {line_number}")
        id_match = ID_RE.fullmatch(entry["id"]) if isinstance(entry["id"], str) else None
        if not id_match or int(id_match.group(1)) != expected_id:
            raise LedgerVerificationError(f"non-sequential entry id at line {line_number}")
        if entry["prev_hash"] != expected_prev:
            raise LedgerVerificationError(f"prev_hash mismatch at line {line_number}")
        total += entry["delta"]
        if entry["total_model_experiments"] != total:
            raise LedgerVerificationError(f"total_model_experiments mismatch at line {line_number}")
        if not isinstance(entry["entry_hash"], str) or not HASH_RE.fullmatch(entry["entry_hash"]):
            raise LedgerVerificationError(f"invalid entry_hash at line {line_number}")
        computed = hashlib.sha256(canonical_entry(entry)).hexdigest()
        if entry["entry_hash"] != computed:
            raise LedgerVerificationError(f"entry_hash mismatch at line {line_number}")
        canonical_line = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
        if raw_line != canonical_line:
            raise LedgerVerificationError(f"non-canonical JSON at line {line_number}")
        expected_prev = computed
        head = computed
        expected_id += 1

    return {
        "ok": True,
        "entry_count": len(raw_lines),
        "total_model_experiments": total,
        "legacy_sha256": legacy_hash,
        "chain_head": head,
    }


def main() -> int:
    try:
        print(json.dumps(verify_ledger(), ensure_ascii=False, separators=(",", ":")))
        return 0
    except LedgerVerificationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
