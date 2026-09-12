import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import verify_ledger  # noqa: E402


ENTRY_FIELDS = {
    "date": "2026-09-12",
    "version": "v1.2.10",
    "type": "Diagnose",
    "hypothesis": "test hypothesis",
    "change": "scripts/test.py",
    "success_criterion": "test criterion",
    "result": "test result",
    "delta": 0,
    "status": "PREREGISTERED",
    "prereg_commit": "abcdef0",
}


def canonical_entry(payload: dict) -> bytes:
    ordered = {field: payload[field] for field in verify_ledger.FIELD_ORDER}
    return (json.dumps(ordered, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def make_entry(prev_hash: str, entry_id: str = "EXP-026", total: int = 10) -> dict:
    payload = {
        "id": entry_id,
        **ENTRY_FIELDS,
        "total_model_experiments": total,
        "prev_hash": prev_hash,
    }
    return {**payload, "entry_hash": hashlib.sha256(canonical_entry(payload)).hexdigest()}


def canonical_record(entry: dict) -> str:
    order = (*verify_ledger.FIELD_ORDER, "entry_hash")
    return json.dumps({field: entry[field] for field in order}, ensure_ascii=False, separators=(",", ":")) + "\n"


def checkpoint_for(entries: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "last_entry_id": entries[-1]["id"],
        "entry_count": len(entries),
        "chain_head": entries[-1]["entry_hash"],
    }


def write_checkpoint(path: Path, checkpoint: dict) -> None:
    path.write_text(json.dumps(checkpoint, separators=(",", ":")) + "\n", encoding="utf-8", newline="")


def write_fixture(tmp_path: Path, entries: list[dict], *, with_checkpoint: bool = True) -> tuple[Path, Path, Path]:
    legacy = tmp_path / "TRIALS_LEDGER.md"
    chain = tmp_path / "chain.jsonl"
    checkpoint = tmp_path / "ledger_checkpoint.json"
    legacy.write_bytes(b"legacy\n")
    chain.write_text("".join(canonical_record(entry) for entry in entries), encoding="utf-8", newline="")
    if with_checkpoint:
        write_checkpoint(checkpoint, checkpoint_for(entries))
    return legacy, chain, checkpoint


def verify_fixture(legacy: Path, chain: Path, checkpoint: Path) -> dict:
    seed = hashlib.sha256(legacy.read_bytes()).hexdigest()
    return verify_ledger.verify_ledger(
        legacy,
        chain,
        checkpoint_path=checkpoint,
        expected_legacy_sha256=seed,
        first_entry_id=26,
        baseline_total=10,
    )


def test_valid_chain_and_checkpoint_pass(tmp_path):
    seed = hashlib.sha256(b"legacy\n").hexdigest()
    first = make_entry(seed)
    legacy, chain, checkpoint = write_fixture(tmp_path, [first])

    result = verify_fixture(legacy, chain, checkpoint)

    assert result["last_entry_id"] == "EXP-026"
    assert result["entry_count"] == 1
    assert result["chain_head"] == first["entry_hash"]


def test_manipulated_entry_fails(tmp_path):
    seed = hashlib.sha256(b"legacy\n").hexdigest()
    entry = make_entry(seed)
    legacy, chain, checkpoint = write_fixture(tmp_path, [entry])
    entry["result"] = "tampered"
    chain.write_text(canonical_record(entry), encoding="utf-8", newline="")

    with pytest.raises(verify_ledger.LedgerVerificationError, match="entry_hash"):
        verify_fixture(legacy, chain, checkpoint)


def test_tail_truncation_fails_against_checkpoint(tmp_path):
    seed = hashlib.sha256(b"legacy\n").hexdigest()
    first = make_entry(seed)
    second = make_entry(first["entry_hash"], entry_id="EXP-027")
    legacy, chain, checkpoint = write_fixture(tmp_path, [first, second])
    chain.write_text(canonical_record(first), encoding="utf-8", newline="")

    with pytest.raises(verify_ledger.LedgerVerificationError, match="checkpoint entry_count mismatch"):
        verify_fixture(legacy, chain, checkpoint)


def test_append_script_writes_verifiable_entry_and_checkpoint(tmp_path):
    seed = hashlib.sha256(b"legacy\n").hexdigest()
    first = make_entry(seed)
    legacy, chain, checkpoint = write_fixture(tmp_path, [first])
    entry_input = tmp_path / "entry.json"
    entry_input.write_text(json.dumps(ENTRY_FIELDS, ensure_ascii=False), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "append_ledger.py"),
            "--entry-file", str(entry_input),
            "--legacy", str(legacy),
            "--chain", str(chain),
            "--checkpoint", str(checkpoint),
            "--expected-legacy-sha256", seed,
            "--first-entry-id", "26",
            "--baseline-total", "10",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    result = verify_fixture(legacy, chain, checkpoint)
    assert result["last_entry_id"] == "EXP-027"
    assert result["entry_count"] == 2


def test_direct_valid_append_without_checkpoint_update_fails(tmp_path):
    seed = hashlib.sha256(b"legacy\n").hexdigest()
    first = make_entry(seed)
    legacy, chain, checkpoint = write_fixture(tmp_path, [first])
    second = make_entry(first["entry_hash"], entry_id="EXP-027")
    with chain.open("a", encoding="utf-8", newline="") as stream:
        stream.write(canonical_record(second))

    with pytest.raises(verify_ledger.LedgerVerificationError, match="checkpoint entry_count mismatch"):
        verify_fixture(legacy, chain, checkpoint)


@pytest.mark.parametrize("field,bad_value", [
    ("last_entry_id", "EXP-999"),
    ("entry_count", 99),
    ("chain_head", "0" * 64),
])
def test_manipulated_checkpoint_fails(tmp_path, field, bad_value):
    seed = hashlib.sha256(b"legacy\n").hexdigest()
    first = make_entry(seed)
    legacy, chain, checkpoint = write_fixture(tmp_path, [first])
    data = checkpoint_for([first])
    data[field] = bad_value
    write_checkpoint(checkpoint, data)

    with pytest.raises(verify_ledger.LedgerVerificationError, match="checkpoint"):
        verify_fixture(legacy, chain, checkpoint)


def test_missing_checkpoint_fails_closed(tmp_path):
    seed = hashlib.sha256(b"legacy\n").hexdigest()
    first = make_entry(seed)
    legacy, chain, checkpoint = write_fixture(tmp_path, [first], with_checkpoint=False)

    with pytest.raises(verify_ledger.LedgerVerificationError, match="checkpoint missing"):
        verify_fixture(legacy, chain, checkpoint)


def test_invalid_checkpoint_json_fails_closed(tmp_path):
    seed = hashlib.sha256(b"legacy\n").hexdigest()
    first = make_entry(seed)
    legacy, chain, checkpoint = write_fixture(tmp_path, [first])
    checkpoint.write_text("not json\n", encoding="utf-8")

    with pytest.raises(verify_ledger.LedgerVerificationError, match="invalid checkpoint JSON"):
        verify_fixture(legacy, chain, checkpoint)


def test_noncanonical_checkpoint_fails_closed(tmp_path):
    seed = hashlib.sha256(b"legacy\n").hexdigest()
    first = make_entry(seed)
    legacy, chain, checkpoint = write_fixture(tmp_path, [first])
    data = checkpoint_for([first])
    checkpoint.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    with pytest.raises(verify_ledger.LedgerVerificationError, match="non-canonical checkpoint"):
        verify_fixture(legacy, chain, checkpoint)


def test_noncanonical_record_field_order_fails_closed(tmp_path):
    seed = hashlib.sha256(b"legacy\n").hexdigest()
    first = make_entry(seed)
    legacy, chain, checkpoint = write_fixture(tmp_path, [first])
    chain.write_text(json.dumps(first, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")

    with pytest.raises(verify_ledger.LedgerVerificationError, match="non-canonical JSON"):
        verify_fixture(legacy, chain, checkpoint)


def test_deleted_inner_entry_fails(tmp_path):
    seed = hashlib.sha256(b"legacy\n").hexdigest()
    first = make_entry(seed)
    second = make_entry(first["entry_hash"], entry_id="EXP-027")
    legacy, chain, checkpoint = write_fixture(tmp_path, [second])

    with pytest.raises(verify_ledger.LedgerVerificationError):
        verify_fixture(legacy, chain, checkpoint)


def test_reordered_entries_fail(tmp_path):
    seed = hashlib.sha256(b"legacy\n").hexdigest()
    first = make_entry(seed)
    second = make_entry(first["entry_hash"], entry_id="EXP-027")
    legacy, chain, checkpoint = write_fixture(tmp_path, [second, first])

    with pytest.raises(verify_ledger.LedgerVerificationError):
        verify_fixture(legacy, chain, checkpoint)


@pytest.mark.parametrize("invalid_content,error", [
    ("not json\n", "invalid ledger JSON"),
    ('{"id":"EXP-026","id":"EXP-026"}\n', "duplicate JSON field"),
])
def test_invalid_chain_format_fails_closed(tmp_path, invalid_content, error):
    seed = hashlib.sha256(b"legacy\n").hexdigest()
    first = make_entry(seed)
    legacy, chain, checkpoint = write_fixture(tmp_path, [first])
    chain.write_text(invalid_content, encoding="utf-8")

    with pytest.raises(verify_ledger.LedgerVerificationError, match=error):
        verify_fixture(legacy, chain, checkpoint)


def test_missing_final_lf_fails_closed(tmp_path):
    seed = hashlib.sha256(b"legacy\n").hexdigest()
    first = make_entry(seed)
    legacy, chain, checkpoint = write_fixture(tmp_path, [first])
    chain.write_bytes(chain.read_bytes().removesuffix(b"\n"))

    with pytest.raises(verify_ledger.LedgerVerificationError, match="final LF"):
        verify_fixture(legacy, chain, checkpoint)
