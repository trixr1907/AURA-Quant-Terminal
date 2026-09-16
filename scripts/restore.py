"""Sichere Wiederherstellung (Restore) der AURA v3 Datenbank (scripts/restore.py).

Fuehrt vor dem Ueberschreiben eine Pruefung der SHA-256 Pruefsumme
und einen SQLite Integrity-Check durch. Atomare Wiederherstellung.
Dokumentiert in docs/OPERATIONS_RUNBOOK.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("aura.restore")


def restore_database(backup_file: Path, target_db: Path, verify_hash: bool = True) -> bool:
    if not backup_file.exists():
        raise FileNotFoundError(f"Backup-Datei existiert nicht: {backup_file}")

    logger.info("Starte Wiederherstellung: %s -> %s", backup_file, target_db)

    # 1. Pruefe Hash falls Meta-JSON existiert
    meta_file = backup_file.with_suffix(".json")
    if verify_hash and meta_file.exists():
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        expected_hash = meta.get("sha256")
        if expected_hash:
            h = hashlib.sha256()
            with open(backup_file, "rb") as f:
                while chunk := f.read(65536):
                    h.update(chunk)
            actual_hash = h.hexdigest()
            if actual_hash != expected_hash:
                raise ValueError(f"SHA-256 Mismatch: Erwartet {expected_hash}, erhalten {actual_hash}")
            logger.info("SHA-256 Hash erfolgreich verifiziert.")

    # 2. Integritaetspruefung der Backup-Datei
    check_conn = sqlite3.connect(str(backup_file))
    try:
        row = check_conn.execute("PRAGMA integrity_check").fetchone()
        if row[0] != "ok":
            raise RuntimeError(f"Integrity Check fehlgeschlagen: {row[0]}")
    finally:
        check_conn.close()

    # 3. Atomare Wiederherstellung ueber temporaere Datei
    target_db.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target_db.with_suffix(".tmp_restore")
    shutil.copy2(backup_file, temp_target)

    # Falls alte WAL/SHM Dateien existieren, entfernen
    wal_file = target_db.with_name(f"{target_db.name}-wal")
    shm_file = target_db.with_name(f"{target_db.name}-shm")
    if wal_file.exists():
        wal_file.unlink()
    if shm_file.exists():
        shm_file.unlink()

    temp_target.replace(target_db)
    logger.info("Datenbank erfolgreich wiederhergestellt: %s", target_db)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA v3 Database Restore")
    parser.add_argument("--backup", type=Path, required=True, help="Pfad zur Backup-Datei (.db)")
    parser.add_argument("--target", type=Path, default=Path("aura_state.db"), help="Ziel-Datenbankpfad")
    parser.add_argument("--skip-hash", action="store_true", help="Hash-Pruefung ueberspringen")
    args = parser.parse_args()

    try:
        restore_database(args.backup, args.target, verify_hash=not args.skip_hash)
        return 0
    except Exception as ex:
        logger.error("Wiederherstellung fehlgeschlagen: %s", ex, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
