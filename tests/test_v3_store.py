"""Tests fuer aura.store: Migrationen, Append-only-Evidenz, Legacy-Import (P1).

Die Legacy-Fixtures sind synthetisch, aber im exakten v2.5-Format
(Keys/Feldnamen aus headless_autobot.js und docs/architecture.md §8).
Sie sind keine Marktdaten und keine Performance-Evidenz.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from aura.store import db as store_db
from aura.store.legacy_import import import_legacy_state


def _legacy_state() -> dict:
    """Synthetischer v2.5-State (Format: aura_shared_state.json, schema v2)."""
    return {
        "schema_version": 2,
        "rev": 41,
        "aura-quant-terminal-active-trades-v2": [
            {
                "record_schema": 2,
                "id": "sb_abc123",
                "source": "server",
                "coin": "BTCUSDT",
                "dir": 1,
                "entry": 50000.0,
                "markPrice": 51200.0,
                "initialSl": 49000.0,
                "currentSl": 50000.0,
                "tp": 52000.0,
                "tp1": 52000.0,
                "tp2": 54000.0,
                "tp3": 56000.0,
                "tp1Hit": True,
                "beActive": True,
                "margin": 100.0,
                "initialMargin": 100.0,
                "leverage": 5,
                "notional": 500.0,
                "openedAt": 1758000000000,
                "maxHoldHours": 24,
            }
        ],
        "aura-quant-terminal-history-trades-v2": [
            {
                "record_schema": 2,
                "id": "sb_abc123_close_x1",
                "parentId": "sb_abc123",
                "source": "server",
                "coin": "ETHUSDT",
                "dir": -1,
                "entry": 3000.0,
                "initialSl": 3100.0,
                "currentSl": 3100.0,
                "margin": 50.0,
                "leverage": 4,
                "notional": 200.0,
                "openedAt": 1757000000000,
                "exit": 3050.0,
                "closedAt": 1757500000000,
                "realizedPnl": -3.33,
                "realizedR": -0.5,
                "closeReason": "sl_close",  # kann wegen Q-03 ein Time-Stop gewesen sein
            },
            {
                "record_schema": 2,
                "id": "sb_bad_dir",
                "source": "server",
                "coin": "SOLUSDT",
                "dir": 0,  # ungueltig -> wird uebersprungen
                "entry": 100.0,
                "initialSl": 90.0,
                "margin": 10.0,
                "leverage": 2,
                "notional": 20.0,
                "openedAt": 1757000000000,
                "exit": 95.0,
                "closedAt": 1757100000000,
                "realizedPnl": -1.0,
                "closeReason": "sl_close",
            },
        ],
        "aura-server-bot-config-v1": {
            "profile": "normal",
            "initialEquity": 10000,
            "riskPerTradePct": 0.75,
            "maxOpenTrades": 3,
            "minScore": 65,
        },
        "aura-server-bot-state-v1": {"equity": 10000.0, "cycleCount": 7},
    }


def _write_legacy_dir(tmp_path) -> None:
    (tmp_path / "aura_shared_state.json").write_text(
        json.dumps(_legacy_state()), encoding="utf-8"
    )
    (tmp_path / "shadow_log.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": 1757600000000,
                        "symbol": "BTCUSDT",
                        "tf": "1h",
                        "dir": 1,
                        "score": 72,
                        "decision": "ACCEPTED",
                        "reject_reason": None,
                        "config_sha256": "deadbeef",
                    }
                ),
                "{kein json",
                json.dumps(
                    {
                        "ts": 1757600100000,
                        "symbol": "XRPUSDT",
                        "tf": "4h",
                        "dir": -1,
                        "score": 40,
                        "decision": "REJECTED",
                        "reject_reason": "LIQUIDITY",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )


class TestMigrations:
    def test_fresh_db_migrates_to_v3_wal(self, tmp_path):
        conn = store_db.connect(tmp_path / "aura.db")
        info = store_db.info(conn, tmp_path / "aura.db")
        assert info.schema_version == 6
        assert info.journal_mode == "wal"
        conn.close()

    def test_migrate_is_idempotent(self, tmp_path):
        conn = store_db.connect(tmp_path / "aura.db")
        assert store_db.migrate(conn) == 6
        assert store_db.migrate(conn) == 6
        rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        assert [row["version"] for row in rows] == [1, 2, 3, 4, 5, 6]
        conn.close()

    def test_existing_v2_database_migrates_to_v3_without_trade_loss(self, tmp_path):
        db_path = tmp_path / "aura-v2.db"
        conn = sqlite3.connect(db_path)
        migration_v1 = (store_db.MIGRATIONS_DIR / "0001_init.sql").read_text(encoding="utf-8")
        migration_v2 = (store_db.MIGRATIONS_DIR / "0002_processed_bars.sql").read_text(encoding="utf-8")
        conn.executescript(migration_v1)
        conn.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (1, 'test')")
        conn.executescript(migration_v2)
        conn.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (2, 'test')")
        conn.execute(
            "INSERT INTO trades (id, source, symbol, dir, status, entry_price, current_sl, initial_sl, "
            "notional, margin, leverage, opened_at_ms, engine_version) "
            "VALUES ('legacy-v2', 'server', 'BTCUSDT', 1, 'open', '100', '90', '90', "
            "'1000', '100', 10, 1000, '3.0.0-dev')"
        )
        conn.commit()
        conn.close()

        migrated = store_db.connect(db_path)
        assert store_db.current_version(migrated) == 6
        row = migrated.execute(
            "SELECT id, symbol, timeframe, entry_fee, remaining_qty FROM trades WHERE id = 'legacy-v2'"
        ).fetchone()
        assert row["id"] == "legacy-v2"
        assert row["symbol"] == "BTCUSDT"
        assert row["timeframe"] == "1h"
        assert row["entry_fee"] is None
        assert row["remaining_qty"] is None
        migrated.close()

    def test_migration_0006_invalidates_legacy_v1_snapshots(self, tmp_path):
        db_path = tmp_path / "aura.db"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # Run migrations 0001 through 0005 manually
        for v in range(1, 6):
            p = store_db.MIGRATIONS_DIR / f"{v:04d}_*.sql"
            import glob
            files = glob.glob(str(p))
            assert len(files) == 1
            sql = open(files[0]).read()
            conn.executescript(sql)
            conn.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (?, 'test')", (v,))
        conn.commit()

        # Seed a positive universe snapshot under v1 policy
        conn.execute(
            "INSERT INTO universe (symbol, active, liquidity_verified, vol_24h, updated_at_ms, source, status, "
            "policy_version, event_time_ms, fetched_at_ms, book_event_time_ms, book_fetched_at_ms, "
            "ticker_event_time_ms, ticker_fetched_at_ms, reasons_json) "
            "VALUES ('BTCUSDT', 1, 1, 5000000.0, 1000, 'bitget_rest_v2', 'valid', 'aura-liquidity-v1', "
            "1000, 1000, 1000, 1000, 1000, 1000, '[]')"
        )
        conn.commit()
        conn.close()

        # Connect with store_db, which auto-applies migration 0006
        migrated = store_db.connect(db_path)
        assert store_db.current_version(migrated) == 6
        row = migrated.execute("SELECT active, liquidity_verified, status, reasons_json FROM universe WHERE symbol = 'BTCUSDT'").fetchone()
        assert row["liquidity_verified"] == 0
        assert row["status"] == "stale"
        assert "POLICY_UPGRADE_REVALIDATION_REQUIRED" in row["reasons_json"]
        migrated.close()

    def test_fail_closed_on_newer_schema(self, tmp_path):
        conn = store_db.connect(tmp_path / "aura.db")
        conn.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (99, 'x')")
        conn.close()
        with pytest.raises(store_db.SchemaError):
            store_db.connect(tmp_path / "aura.db")

    def test_append_only_triggers(self, tmp_path):
        conn = store_db.connect(tmp_path / "aura.db")
        conn.execute(
            "INSERT INTO shadow_log (ts_ms, symbol, timeframe, dir, decision, config_sha256)"
            " VALUES (1, 'BTCUSDT', '1h', 1, 'ACCEPTED', 'x')"
        )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("UPDATE shadow_log SET decision='REJECTED' WHERE id=1")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM shadow_log WHERE id=1")
        conn.execute("INSERT INTO audit_log (ts_ms, actor, action) VALUES (1, 'system', 't')")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM audit_log WHERE id=1")
        conn.close()


class TestLegacyImport:
    def test_dry_run_writes_nothing(self, tmp_path):
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        _write_legacy_dir(legacy)
        conn = store_db.connect(tmp_path / "aura.db")

        report = import_legacy_state(conn, legacy, dry_run=True)

        assert report.trades_open == 1
        assert report.trades_closed == 1  # dir=0-Record uebersprungen
        assert report.shadow_rows == 2  # kaputte Zeile uebersprungen
        assert report.config_revisions == 1
        assert conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM shadow_log").fetchone()[0] == 0
        assert any("Q-03" in w for w in report.warnings)
        assert any("ungueltige dir" in w for w in report.warnings)
        conn.close()

    def test_real_import_maps_fields(self, tmp_path):
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        _write_legacy_dir(legacy)
        conn = store_db.connect(tmp_path / "aura.db")

        report = import_legacy_state(conn, legacy, dry_run=False)
        assert report.duplicates_skipped == 0

        open_t = conn.execute("SELECT * FROM trades WHERE status='open'").fetchone()
        assert open_t["id"] == "sb_abc123"
        assert open_t["symbol"] == "BTCUSDT"
        assert open_t["source"] == "legacy-import"
        assert open_t["tp1_hit"] == 1 and open_t["be_active"] == 1
        assert open_t["engine_version"] == "v2.5.0-legacy"
        assert open_t["fees"] is None  # unbekannt, nicht 0

        closed_t = conn.execute("SELECT * FROM trades WHERE status='closed'").fetchone()
        assert closed_t["exit_reason"] == "sl_close"
        assert closed_t["realized_pnl"] == repr(-3.33)
        assert closed_t["fees"] is None

        assert conn.execute("SELECT COUNT(*) FROM shadow_log").fetchone()[0] == 2
        cfg = conn.execute("SELECT * FROM config_revisions").fetchone()
        assert json.loads(cfg["payload"])["minScore"] == 65
        rs = conn.execute("SELECT * FROM runner_state WHERE id=1").fetchone()
        assert rs["fsm_state"] == "HALTED"
        assert rs["equity"] == repr(10000.0)
        conn.close()

    def test_import_is_idempotent(self, tmp_path):
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        _write_legacy_dir(legacy)
        conn = store_db.connect(tmp_path / "aura.db")

        import_legacy_state(conn, legacy, dry_run=False)
        second = import_legacy_state(conn, legacy, dry_run=False)

        assert second.trades_open == 0 and second.trades_closed == 0 and second.shadow_rows == 0
        assert any("bereits ausgefuehrt" in w for w in second.warnings)
        assert conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM shadow_log").fetchone()[0] == 2
        conn.close()

    def test_missing_state_file_raises(self, tmp_path):
        conn = store_db.connect(tmp_path / "aura.db")
        with pytest.raises(FileNotFoundError):
            import_legacy_state(conn, tmp_path / "nichtda", dry_run=True)
        conn.close()
