import hashlib
import json
from pathlib import Path

import pytest

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import verify_ledger  # noqa: E402


def canonical_entry(payload: dict) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def make_entry(prev_hash: str, entry_id: str = "EXP-026", total: int = 10) -> dict:
    payload = {
        "id": entry_id,
        "date": "2026-09-12",
        "version": "v1.2.9",
        "type": "Prozess-Fix",
        "hypothesis": "test hypothesis",
        "change": "scripts/test.py",
        "success_criterion": "test criterion",
        "result": "test result",
        "delta": 0,
        "total_model_experiments": total,
        "status": "PREREGISTERED",
        "prereg_commit": "abcdef0",
        "prev_hash": prev_hash,
    }
    return {**payload, "entry_hash": hashlib.sha256(canonical_entry(payload)).hexdigest()}


def write_fixture(tmp_path: Path, entries: list[dict]) -> tuple[Path, Path]:
    legacy = tmp_path / "TRIALS_LEDGER.md"
    chain = tmp_path / "chain.jsonl"
    legacy.write_bytes(b"legacy\n")
    chain.write_text("".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n" for e in entries), encoding="utf-8")
    return legacy, chain


def test_valid_chain_passes(tmp_path):
    seed = hashlib.sha256(b"legacy\n").hexdigest()
    first = make_entry(seed)
    legacy, chain = write_fixture(tmp_path, [first])
    result = verify_ledger.verify_ledger(legacy, chain, expected_legacy_sha256=seed, first_entry_id=26, baseline_total=10)
    assert result["total_model_experiments"] == 10
    assert result["chain_head"] == first["entry_hash"]


def test_manipulated_entry_fails(tmp_path):
    seed = hashlib.sha256(b"legacy\n").hexdigest()
    entry = make_entry(seed)
    entry["result"] = "tampered"
    legacy, chain = write_fixture(tmp_path, [entry])
    with pytest.raises(verify_ledger.LedgerVerificationError, match="entry_hash"):
        verify_ledger.verify_ledger(legacy, chain, expected_legacy_sha256=seed, first_entry_id=26, baseline_total=10)


def test_correct_append_passes(tmp_path):
    seed = hashlib.sha256(b"legacy\n").hexdigest()
    first = make_entry(seed)
    second = make_entry(first["entry_hash"], entry_id="EXP-027")
    legacy, chain = write_fixture(tmp_path, [first, second])
    result = verify_ledger.verify_ledger(legacy, chain, expected_legacy_sha256=seed, first_entry_id=26, baseline_total=10)
    assert result["entry_count"] == 2
    assert result["chain_head"] == second["entry_hash"]


def test_missing_ledger_fails_closed(tmp_path):
    with pytest.raises(verify_ledger.LedgerVerificationError, match="missing"):
        verify_ledger.verify_ledger(tmp_path / "missing.md", tmp_path / "missing.jsonl")


def test_deleted_entry_fails(tmp_path):
    seed = hashlib.sha256(b"legacy\n").hexdigest()
    first = make_entry(seed)
    second = make_entry(first["entry_hash"], entry_id="EXP-027")
    legacy, chain = write_fixture(tmp_path, [second])
    with pytest.raises(verify_ledger.LedgerVerificationError):
        verify_ledger.verify_ledger(legacy, chain, expected_legacy_sha256=seed, first_entry_id=26, baseline_total=10)


def test_reordered_entries_fail(tmp_path):
    seed = hashlib.sha256(b"legacy\n").hexdigest()
    first = make_entry(seed)
    second = make_entry(first["entry_hash"], entry_id="EXP-027")
    legacy, chain = write_fixture(tmp_path, [second, first])
    with pytest.raises(verify_ledger.LedgerVerificationError):
        verify_ledger.verify_ledger(legacy, chain, expected_legacy_sha256=seed, first_entry_id=26, baseline_total=10)


def test_invalid_format_fails_closed(tmp_path):
    legacy = tmp_path / "TRIALS_LEDGER.md"
    chain = tmp_path / "chain.jsonl"
    legacy.write_bytes(b"legacy\n")
    chain.write_text("not json\n", encoding="utf-8")
    with pytest.raises(verify_ledger.LedgerVerificationError, match="JSON"):
        verify_ledger._parse_entry(chain.read_text(encoding="utf-8").strip(), 1)
