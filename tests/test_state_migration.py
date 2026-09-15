import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.state_migration import (
    migrate_shared_state_dict,
    migrate_signal_state_dict,
    migrate_state_directory,
    rollback_state_directory,
)


class StateMigrationTests(unittest.TestCase):
    def test_golden_fixture_migrates_without_value_changes(self):
        source = json.loads(Path("data/aura_shared_state.json").read_text(encoding="utf-8"))
        migrated = migrate_shared_state_dict(source, now=1_700_000_000)
        self.assertEqual(migrated["schema_version"], 2)
        for key, value in source.items():
            self.assertEqual(migrated[key], value)
        for field in ("rev", "equity", "trades", "history", "funnel24h", "lastHeartbeatAt", "last_digest_date"):
            self.assertIn(field, migrated)

    def test_trade_ids_and_numeric_precision_are_preserved(self):
        source = {
            "schema_version": 1,
            "_rev": 7,
            "aura-quant-terminal-active-trades-v1": [{"id": "sb_fixed", "entry": 0.1234567890123456}],
            "aura-quant-terminal-history-trades-v1": [{"id": "h_fixed", "parentId": "sb_fixed", "realizedPnl": -1.23456789}],
        }
        migrated = migrate_shared_state_dict(source, now=100)
        self.assertEqual(migrated["trades"][0]["id"], "sb_fixed")
        self.assertEqual(migrated["trades"][0]["entry"], 0.1234567890123456)
        self.assertEqual(migrated["history"][0]["parentId"], "sb_fixed")
        self.assertEqual(migrated["history"][0]["realizedPnl"], -1.23456789)
        self.assertEqual(migrated["trades"][0]["record_schema"], 2)
        self.assertEqual(migrated["history"][0]["record_schema"], 2)

    def test_idempotence(self):
        source = {"schema_version": 1, "_rev": 2, "trades": [], "history": []}
        first = migrate_shared_state_dict(source, now=100)
        second = migrate_shared_state_dict(first, now=100)
        self.assertEqual(first, second)

    def test_future_schema_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "schema_version 3"):
            migrate_shared_state_dict({"schema_version": 3})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "aura_shared_state.json").write_text('{"schema_version":3}', encoding="utf-8")
            result = migrate_state_directory(path, now=100)
            self.assertFalse(result["ok"])
            self.assertEqual(result["actions"][0]["status"], "FAIL_FUTURE_VERSION")

    def test_backup_and_rollback_are_byte_identical(self):
        original = '{"schema_version":1,"_rev":9,"custom":1.2300}\n'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            state_file = path / "aura_shared_state.json"
            state_file.write_text(original, encoding="utf-8")
            original_hash = hashlib.sha256(original.encode()).hexdigest()
            result = migrate_state_directory(path, now=1_700_000_000)
            self.assertTrue(result["ok"])
            self.assertEqual(json.loads(state_file.read_text())["schema_version"], 2)
            backups = list(path.glob("aura_shared_state.json.v1-backup-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(hashlib.sha256(backups[0].read_bytes()).hexdigest(), original_hash)
            preview = rollback_state_directory(path)
            self.assertTrue(preview["dry_run"])
            rolled = rollback_state_directory(path, confirm_yes=True)
            self.assertTrue(rolled["ok"])
            self.assertEqual(hashlib.sha256(state_file.read_bytes()).hexdigest(), original_hash)

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            state_file = path / "aura_shared_state.json"
            state_file.write_text('{"schema_version":1}', encoding="utf-8")
            result = migrate_state_directory(path, dry_run=True, now=100)
            self.assertTrue(result["ok"])
            self.assertEqual(state_file.read_text(), '{"schema_version":1}')
            self.assertFalse(list(path.glob("*.v1-backup-*")))

    def test_signal_center_state_migrates_separately(self):
        source = {"btc": {"regime": "BULL"}, "custom": 9}
        migrated = migrate_signal_state_dict(source, now=100)
        self.assertEqual(migrated["schema_version"], 2)
        self.assertEqual(migrated["btc"], source["btc"])
        self.assertEqual(migrated["custom"], 9)
        self.assertIn("digest", migrated)
        self.assertIn("health", migrated)

    def test_empty_v1_state_has_no_fake_records(self):
        migrated = migrate_shared_state_dict({"schema_version": 1}, now=100)
        self.assertEqual(migrated["trades"], [])
        self.assertEqual(migrated["history"], [])
        self.assertEqual(migrated["rev"], 0)


if __name__ == "__main__":
    unittest.main()
