"""Sicheres Online-Backup der AURA v3 SQLite-Datenbank (scripts/backup.py).

Verwendet die native SQLite Backup API (unterstuetzt laufenden WAL-Betrieb
ohne Schreibblockaden). Berechnet SHA-256 Pruefsumme und fuehrt
automatisch einen PRAGMA integrity_check auf dem Backup aus.
Dokumentiert in docs/OPERATIONS_RUNBOOK.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sqlite3
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("aura.backup")


def backup_database(db_path: Path, dest_dir: Path) -> Path:
    if not db_path.exists():
        raise FileNotFoundError(f"Quelldatenbank existiert nicht: {db_path}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    backup_file = dest_dir / f"aura_backup_{timestamp}.db"

    logger.info("Starte konsistentes Online-Backup: %s -> %s", db_path, backup_file)
    src_conn = sqlite3.connect(str(db_path), timeout=30.0)
    dst_conn = sqlite3.connect(str(backup_file))

    try:
        # SQLite Online Backup API kopiert Seiten transaktionssicher
        src_conn.backup(dst_conn, pages=100)
    finally:
        dst_conn.close()
        src_conn.close()

    # 1. Integrity Check auf dem Backup
    check_conn = sqlite3.connect(str(backup_file))
    try:
        row = check_conn.execute("PRAGMA integrity_check").fetchone()
        if row[0] != "ok":
            raise RuntimeError(f"Integrity Check auf Backup fehlgeschlagen: {row[0]}")
        logger.info("Integrity Check erfolgreich: PRAGMA integrity_check = ok")
    finally:
        check_conn.close()

    # 2. SHA-256 Hash berechnen
    h = hashlib.sha256()
    with open(backup_file, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    sha256_hash = h.hexdigest()

    meta_file = dest_dir / f"aura_backup_{timestamp}.json"
    meta = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_path": str(db_path),
        "backup_file": backup_file.name,
        "size_bytes": backup_file.stat().st_size,
        "sha256": sha256_hash,
    }
    meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    logger.info("Backup erfolgreich abgeschlossen. Hash: %s", sha256_hash)

    return backup_file


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA v3 Online Database Backup")
    parser.add_argument("--db", type=Path, default=Path("aura_state.db"), help="Pfad zur Quelldatenbank")
    parser.add_argument("--dest", type=Path, default=Path("backups"), help="Zielverzeichnis")
    args = parser.parse_args()

    try:
        backup_database(args.db, args.dest)
        return 0
    except Exception as ex:
        logger.error("Backup fehlgeschlagen: %s", ex, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
