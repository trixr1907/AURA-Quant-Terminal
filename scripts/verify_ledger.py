#!/usr/bin/env python3
"""Verify AURA's append-only trials ledger and anchored checkpoint."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEGACY_LEDGER = ROOT / "docs" / "research" / "TRIALS_LEDGER_LEGACY_v1.2.8.md"
CHAIN_LEDGER = ROOT / "docs" / "research" / "trials_ledger_chain.jsonl"
LEDGER_CHECKPOINT = ROOT / "ledger_checkpoint.json"
LEGACY_SHA256 = "23f59ef8df9f348609280d8f57583e32c2d7afc1e9b428f9d50ae75051eeeb0c"
FIRST_ENTRY_ID = 26
BASELINE_TOTAL = 10
FIELD_ORDER = (
    "id", "date", "version", "type", "hypothesis", "change",
    "success_criterion", "result", "delta", "total_model_experiments",
    "status", "prereg_commit", "prev_hash",
)
RECORD_ORDER = (*FIELD_ORDER, "entry_hash")
ALL_FIELDS = set(RECORD_ORDER)
CHECKPOINT_ORDER = ("schema_version", "last_entry_id", "entry_count", "chain_head")
CHECKPOINT_FIELDS = set(CHECKPOINT_ORDER)
HASH_RE = re.compile(r"[0-9a-f]{64}")
ID_RE = re.compile(r"EXP-(\d{3,})")


class LedgerVerificationError(ValueError):
    """Raised when ledger evidence is missing or invalid."""


def _canonical_json(data: dict, fields: tuple[str, ...]) -> str:
    return json.dumps({field: data[field] for field in fields}, ensure_ascii=False, separators=(",", ":"))


def canonical_entry(entry: dict) -> bytes:
    return (_canonical_json(entry, FIELD_ORDER) + "\n").encode("utf-8")


def canonical_record(entry: dict) -> bytes:
    return (_canonical_json(entry, RECORD_ORDER) + "\n").encode("utf-8")


def canonical_checkpoint(checkpoint: dict) -> bytes:
    return (_canonical_json(checkpoint, CHECKPOINT_ORDER) + "\n").encode("utf-8")


def _read_legacy(path: Path, expected_sha256: str) -> str:
    if not path.is_file():
        raise LedgerVerificationError(f"legacy ledger missing: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise LedgerVerificationError("legacy ledger SHA-256 mismatch")
    return digest


def _read_chain(path: Path) -> list[str]:
    if not path.is_file():
        raise LedgerVerificationError(f"chain ledger missing: {path}")
    try:
        raw = path.read_bytes()
        if not raw:
            raise LedgerVerificationError("chain ledger has no entries")
        if not raw.endswith(b"\n"):
            raise LedgerVerificationError("chain ledger missing final LF")
        if b"\r" in raw:
            raise LedgerVerificationError("chain ledger contains non-canonical CR")
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise LedgerVerificationError(f"cannot read chain ledger: {exc}") from exc
    return text[:-1].split("\n")


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise LedgerVerificationError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise LedgerVerificationError(f"invalid JSON constant: {value}")


def _parse_json_object(raw: str, context: str) -> dict:
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise LedgerVerificationError(f"invalid {context} JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise LedgerVerificationError(f"{context} is not an object")
    return value


def _parse_entry(raw_line: str, line_number: int) -> dict:
    if not raw_line:
        raise LedgerVerificationError(f"blank entry at line {line_number}")
    entry = _parse_json_object(raw_line, "ledger")
    if set(entry) != ALL_FIELDS:
        raise LedgerVerificationError(f"invalid fields at line {line_number}")
    if raw_line != _canonical_json(entry, RECORD_ORDER):
        raise LedgerVerificationError(f"non-canonical JSON at line {line_number}")
    return entry


def _validate_numbers(entry: dict, expected_total: int, line_number: int) -> int:
    numeric = (entry["delta"], entry["total_model_experiments"])
    if any(isinstance(value, bool) for value in numeric):
        raise LedgerVerificationError(f"invalid numeric field at line {line_number}")
    if not isinstance(entry["delta"], int) or entry["delta"] not in (0, 1):
        raise LedgerVerificationError(f"invalid delta at line {line_number}")
    if not isinstance(entry["total_model_experiments"], int):
        raise LedgerVerificationError(f"invalid total at line {line_number}")
    total = expected_total + entry["delta"]
    if entry["total_model_experiments"] != total:
        raise LedgerVerificationError(f"total_model_experiments mismatch at line {line_number}")
    return total


def _validate_link(entry: dict, expected_id: int, expected_prev: str, line_number: int) -> str:
    id_match = ID_RE.fullmatch(entry["id"]) if isinstance(entry["id"], str) else None
    if not id_match or int(id_match.group(1)) != expected_id:
        raise LedgerVerificationError(f"non-sequential entry id at line {line_number}")
    if entry["prev_hash"] != expected_prev:
        raise LedgerVerificationError(f"prev_hash mismatch at line {line_number}")
    entry_hash = entry["entry_hash"]
    if not isinstance(entry_hash, str) or not HASH_RE.fullmatch(entry_hash):
        raise LedgerVerificationError(f"invalid entry_hash at line {line_number}")
    computed = hashlib.sha256(canonical_entry(entry)).hexdigest()
    if entry_hash != computed:
        raise LedgerVerificationError(f"entry_hash mismatch at line {line_number}")
    return computed


def _read_checkpoint(path: Path, first_entry_id: int) -> dict:
    if not path.is_file():
        raise LedgerVerificationError(f"checkpoint missing: {path}")
    try:
        raw = path.read_bytes()
        if not raw.endswith(b"\n"):
            raise LedgerVerificationError("checkpoint missing final LF")
        if raw.count(b"\n") != 1 or b"\r" in raw:
            raise LedgerVerificationError("checkpoint must be one canonical LF-terminated line")
        text = raw[:-1].decode("utf-8")
    except UnicodeError as exc:
        raise LedgerVerificationError(f"cannot read checkpoint: {exc}") from exc
    checkpoint = _parse_json_object(text, "checkpoint")
    if set(checkpoint) != CHECKPOINT_FIELDS:
        raise LedgerVerificationError("invalid checkpoint fields")
    if text != _canonical_json(checkpoint, CHECKPOINT_ORDER):
        raise LedgerVerificationError("non-canonical checkpoint JSON")
    count = checkpoint["entry_count"]
    if checkpoint["schema_version"] != 1:
        raise LedgerVerificationError("invalid checkpoint schema_version")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise LedgerVerificationError("invalid checkpoint entry_count")
    expected_last = f"EXP-{first_entry_id + count - 1:03d}"
    if checkpoint["last_entry_id"] != expected_last:
        raise LedgerVerificationError("checkpoint last_entry_id inconsistent with entry_count")
    if not isinstance(checkpoint["chain_head"], str) or not HASH_RE.fullmatch(checkpoint["chain_head"]):
        raise LedgerVerificationError("invalid checkpoint chain_head")
    return checkpoint


def verify_ledger(
    legacy_path: Path = LEGACY_LEDGER,
    chain_path: Path = CHAIN_LEDGER,
    *,
    checkpoint_path: Path = LEDGER_CHECKPOINT,
    expected_legacy_sha256: str = LEGACY_SHA256,
    first_entry_id: int = FIRST_ENTRY_ID,
    baseline_total: int = BASELINE_TOTAL,
) -> dict:
    """Return verified ledger metadata or raise fail-closed."""
    legacy_hash = _read_legacy(legacy_path, expected_legacy_sha256)
    raw_lines = _read_chain(chain_path)
    expected_prev, total = legacy_hash, baseline_total
    last_entry_id = None
    for offset, raw_line in enumerate(raw_lines):
        line_number = offset + 1
        entry = _parse_entry(raw_line, line_number)
        total = _validate_numbers(entry, total, line_number)
        expected_prev = _validate_link(entry, first_entry_id + offset, expected_prev, line_number)
        last_entry_id = entry["id"]

    checkpoint = _read_checkpoint(checkpoint_path, first_entry_id)
    actual = {
        "last_entry_id": last_entry_id,
        "entry_count": len(raw_lines),
        "chain_head": expected_prev,
    }
    for field in ("entry_count", "last_entry_id", "chain_head"):
        value = actual[field]
        if checkpoint[field] != value:
            raise LedgerVerificationError(
                f"checkpoint {field} mismatch: expected {checkpoint[field]!r}, reconstructed {value!r}"
            )
    return {
        "ok": True,
        **actual,
        "total_model_experiments": total,
        "legacy_sha256": legacy_hash,
    }


def main() -> int:
    try:
        print(json.dumps(verify_ledger(), ensure_ascii=False, separators=(",", ":")))
        return 0
    except (LedgerVerificationError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
