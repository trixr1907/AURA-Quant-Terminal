"""Tests fuer Backup- und Restore-Prozeduren (P8).

Prueft Online-Backup, SHA-256 Hashes, Integrity-Check und atomare Wiederherstellung.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aura.store.db import connect
from scripts.backup import backup_database
from scripts.restore import restore_database


def test_backup_and_restore_cycle(tmp_path: Path):
    src_db = tmp_path / "original_aura.db"
    backup_dir = tmp_path / "backups"
    restore_db = tmp_path / "restored_aura.db"

    # 1. DB initialisieren und Daten einfuegen
    conn = connect(src_db)
    with conn:
        conn.execute(
            "INSERT INTO trades (id, source, symbol, dir, status, entry_price, current_sl, initial_sl, notional, margin, leverage, opened_at_ms, engine_version) "
            "VALUES ('test_1', 'server', 'BTCUSDT', 1, 'open', '50000', '48000', '48000', '1000', '100', 10, 1000000, '3.0.0-dev')"
        )
    conn.close()

    # 2. Backup durchfuehren
    backup_file = backup_database(src_db, backup_dir)
    assert backup_file.exists()
    assert backup_file.with_suffix(".json").exists()

    # 3. Wiederherstellung in neue Zieldatei
    ok = restore_database(backup_file, restore_db)
    assert ok is True
    assert restore_db.exists()

    # 4. Daten in der wiederhergestellten DB pruefen
    restored_conn = connect(restore_db)
    cur = restored_conn.cursor()
    cur.execute("SELECT symbol, entry_price FROM trades WHERE id = 'test_1'")
    row = cur.fetchone()
    assert row is not None
    assert row["symbol"] == "BTCUSDT"
    assert row["entry_price"] == "50000"

    # Integrity Check
    check = restored_conn.execute("PRAGMA integrity_check").fetchone()
    assert check[0] == "ok"
    restored_conn.close()
