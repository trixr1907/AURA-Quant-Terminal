"""SQLite-Verbindung (WAL) und Migrations-Runner.

ADR-0002: SQLite WAL, nummerierte SQL-Migrationen, fail-closed bei
unbekannter Schema-Version. Kein ORM — das Schema ist klein und die
SQL-Texte sind auditierbar.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

# Schema-Version, die dieser Code versteht. Hoehere Versionen in der DB
# (z.B. nach Downgrade) sind fail-closed.
SUPPORTED_SCHEMA_VERSION = 6


class SchemaError(RuntimeError):
    """Unbekannte oder inkonsistente Schema-Version (fail-closed)."""


class SafeConnection(sqlite3.Connection):
    """SQLite-Verbindung mit echter Transaktions-Atomizitaet und Savepoints fuer 'with conn:'."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tx_depth = 0
        self._tx_lock = threading.RLock()
        self._tx_owner: int | None = None

    def __enter__(self):
        tid = threading.get_ident()
        if not self._tx_lock.acquire(timeout=1.0):
            raise RuntimeError(
                f"cannot start a transaction within a transaction: connection is already held by thread {self._tx_owner}"
            )
        self._tx_owner = tid
        if self._tx_depth == 0:
            self.execute("BEGIN")
        else:
            self.execute(f"SAVEPOINT sp_{self._tx_depth}")
        self._tx_depth += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> Literal[False]:
        try:
            self._tx_depth -= 1
            if exc_type is not None:
                if self._tx_depth == 0:
                    if self.in_transaction:
                        self.execute("ROLLBACK")
                else:
                    try:
                        self.execute(f"ROLLBACK TO SAVEPOINT sp_{self._tx_depth}")
                    finally:
                        try:
                            self.execute(f"RELEASE SAVEPOINT sp_{self._tx_depth}")
                        except sqlite3.OperationalError:
                            pass
            else:
                if self._tx_depth == 0:
                    if self.in_transaction:
                        self.execute("COMMIT")
                else:
                    try:
                        self.execute(f"RELEASE SAVEPOINT sp_{self._tx_depth}")
                    except sqlite3.OperationalError:
                        pass
        finally:
            if self._tx_depth == 0:
                self._tx_owner = None
            self._tx_lock.release()
        return False

    def executescript(self, sql_script: str) -> sqlite3.Cursor:
        """Fuehrt SQL-Skripte atomar aus, ohne vorzeitige COMMITs der Standardbibliothek."""
        statements = []
        current = []
        for part in sql_script.split(";"):
            current.append(part)
            candidate = ";".join(current) + ";"
            if sqlite3.complete_statement(candidate):
                stmt = candidate.strip()
                if stmt and stmt != ";":
                    statements.append(stmt)
                current = []
        trailing = ";".join(current).strip()
        if trailing and trailing != ";":
            statements.append(trailing)

        cursor = self.cursor()
        for stmt in statements:
            cursor.execute(stmt)
        return cursor


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Oeffnet die DB mit produktionsfesten Pragmas und laeuft Migrationen."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(path),
        timeout=30.0,
        isolation_level=None,
        factory=SafeConnection,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    migrate(conn)
    return conn


def _migration_files() -> list[tuple[int, Path]]:
    files: list[tuple[int, Path]] = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(f.name.split("_", 1)[0])
        files.append((version, f))
    return files


def current_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
    except sqlite3.OperationalError:
        return 0  # schema_migrations existiert noch nicht
    return int(row["v"] or 0)


def migrate(conn: sqlite3.Connection) -> int:
    """Fuehrt ausstehende Migrationen transaktional aus. Gibt Zielversion zurueck.

    Fail-closed: DB-Version > SUPPORTED_SCHEMA_VERSION -> SchemaError.
    Jede Migration laeuft in einer eigenen Transaktion; ein Fehler laesst
    den bisherigen Stand unveraendert und bricht den Start ab.
    """
    have = current_version(conn)
    if have > SUPPORTED_SCHEMA_VERSION:
        raise SchemaError(
            f"DB-Schema v{have} ist neuer als unterstuetzt (v{SUPPORTED_SCHEMA_VERSION}); "
            "Downgrade ohne Migration verboten (fail-closed)."
        )
    for version, path in _migration_files():
        if version <= have:
            continue
        sql = path.read_text(encoding="utf-8")
        applied_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        try:
            with conn:  # eigene Transaktion je Migration
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (version, applied_at),
                )
        except sqlite3.Error as exc:
            raise SchemaError(f"Migration {path.name} fehlgeschlagen: {exc}") from exc
    return current_version(conn)


@dataclass(frozen=True)
class DbInfo:
    path: str
    schema_version: int
    journal_mode: str


def info(conn: sqlite3.Connection, db_path: str | Path) -> DbInfo:
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    return DbInfo(path=str(db_path), schema_version=current_version(conn), journal_mode=str(mode))
