"""Regressionstests fuer /ready (DB-autoritativer Zustand) und /status/worker (oeffentlich).

Anforderungen:
  W1  /status/worker ohne Auth abrufbar (200)
  W2  /status/worker liefert fsm_state, is_halted, entries_locked, stale
  W3  /status/worker HALTED in DB → is_halted=True, entries_locked=True
  W4  /status/worker fehlender Eintrag → stale=True, is_halted=False (kein Schein-Halt)
  W5  /status/worker veralteter Eintrag (>120s) → stale=True
  W6  /ready HALTED in DB → bot_enabled=False (ohne Auth, direkt aus DB)
  W7  /ready RUNNING in DB → bot_enabled=True
  W8  /ready fehlender runner_state → bot_enabled=False (fail-closed)
  W9  /ready STARTING in DB → bot_enabled=False (kein Schein-Bereit)
  W10 /ready veralteter Worker (>120s) → stale=True, bot_enabled=False
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aura.api.app import create_app
from aura.runner import RunnerStateMachine, SystemState, PaperTradingEngine
from aura.store.db import connect


def _make_client(tmp_path: Path, monkeypatch, *, initial_state: SystemState = SystemState.RUNNING) -> TestClient:
    monkeypatch.setenv("AURA_RELAY_TOKEN", "test_worker_status_token")
    from aura.api.auth import _FAILED_LOGINS, _ACTIVE_SESSIONS
    _FAILED_LOGINS.clear()
    _ACTIVE_SESSIONS.clear()
    db_file = tmp_path / "worker_status_test.db"
    conn = connect(db_file)
    sm = RunnerStateMachine(initial_state)
    pe = PaperTradingEngine(conn=conn)
    app = create_app(conn=conn, state_machine=sm, paper_engine=pe)
    return TestClient(app, raise_server_exceptions=False)


def _insert_runner_state(conn: sqlite3.Connection, *, fsm_state: str, reason: str = "", age_ms: int = 0) -> None:
    """Schreibt einen runner_state-Eintrag mit gesteuertem Alter."""
    now_ms = int(time.time() * 1000) - age_ms
    conn.execute(
        """INSERT INTO runner_state (id, fsm_state, reason, equity, cycle_count, updated_at_ms)
           VALUES (1, ?, ?, '10000', 0, ?)
           ON CONFLICT(id) DO UPDATE SET
             fsm_state=excluded.fsm_state,
             reason=excluded.reason,
             updated_at_ms=excluded.updated_at_ms""",
        (fsm_state, reason, now_ms),
    )
    conn.commit()


class TestWorkerStatusEndpoint:
    """W1-W5: /status/worker"""

    def test_w1_no_auth_required(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/status/worker")
        assert resp.status_code == 200, f"Oeffentlicher Endpunkt wurde verweigert: {resp.text}"

    def test_w2_response_schema(self, tmp_path, monkeypatch):
        conn = connect(tmp_path / "schema_test.db")
        _insert_runner_state(conn, fsm_state="RUNNING")
        monkeypatch.setenv("AURA_RELAY_TOKEN", "test_worker_status_token")
        from aura.api.auth import _FAILED_LOGINS, _ACTIVE_SESSIONS
        _FAILED_LOGINS.clear(); _ACTIVE_SESSIONS.clear()
        app = create_app(conn=conn, state_machine=RunnerStateMachine(SystemState.RUNNING),
                         paper_engine=PaperTradingEngine(conn=conn))
        client = TestClient(app)
        data = client.get("/status/worker").json()
        required = {"fsm_state", "is_halted", "entries_locked", "stale", "reason", "data_age_seconds"}
        missing = required - set(data.keys())
        assert not missing, f"Fehlende Felder: {missing}"

    def test_w3_halted_in_db_returns_is_halted_true(self, tmp_path, monkeypatch):
        conn = connect(tmp_path / "halted_test.db")
        _insert_runner_state(conn, fsm_state="HALTED", reason="Test-Halt")
        monkeypatch.setenv("AURA_RELAY_TOKEN", "test_worker_status_token")
        from aura.api.auth import _FAILED_LOGINS, _ACTIVE_SESSIONS
        _FAILED_LOGINS.clear(); _ACTIVE_SESSIONS.clear()
        # API-SM startet in RUNNING – /ready muss DB lesen, nicht SM
        app = create_app(conn=conn, state_machine=RunnerStateMachine(SystemState.RUNNING),
                         paper_engine=PaperTradingEngine(conn=conn))
        client = TestClient(app)
        data = client.get("/status/worker").json()
        assert data["fsm_state"] == "HALTED"
        assert data["is_halted"] is True
        assert data["entries_locked"] is True

    def test_w4_missing_runner_state_returns_stale_no_schein_halt(self, tmp_path, monkeypatch):
        """Kein Eintrag → stale=True, is_halted=False (kein Schein-Halt annehmen)."""
        client = _make_client(tmp_path, monkeypatch)
        # Kein _insert_runner_state Aufruf – Tabelle leer
        data = client.get("/status/worker").json()
        assert data["stale"] is True, "Fehlender Eintrag muss stale=True liefern"
        assert data["is_halted"] is False, "Kein Eintrag darf nicht als HALTED angenommen werden"
        assert data["entries_locked"] is True, "Ohne verifizierten Zustand muss entries_locked=True (fail-closed)"

    def test_w5_stale_worker_over_120s(self, tmp_path, monkeypatch):
        """Worker-Eintrag 130 Sekunden alt → stale=True."""
        conn = connect(tmp_path / "stale_test.db")
        _insert_runner_state(conn, fsm_state="RUNNING", age_ms=130_000)
        monkeypatch.setenv("AURA_RELAY_TOKEN", "test_worker_status_token")
        from aura.api.auth import _FAILED_LOGINS, _ACTIVE_SESSIONS
        _FAILED_LOGINS.clear(); _ACTIVE_SESSIONS.clear()
        app = create_app(conn=conn, state_machine=RunnerStateMachine(SystemState.RUNNING),
                         paper_engine=PaperTradingEngine(conn=conn))
        client = TestClient(app)
        data = client.get("/status/worker").json()
        assert data["stale"] is True
        assert data["entries_locked"] is True, "Veralteter Zustand → entries_locked=True (fail-closed)"
        assert data["data_age_seconds"] >= 120


class TestReadyEndpointDbAuthority:
    """W6-W10: /ready liest Zustand aus DB, kein Auth nötig"""

    def _client_with_db_state(self, tmp_path, monkeypatch, *, db_state: str | None,
                               age_ms: int = 0, api_sm_state: SystemState = SystemState.STARTING):
        monkeypatch.setenv("AURA_RELAY_TOKEN", "test_worker_status_token")
        from aura.api.auth import _FAILED_LOGINS, _ACTIVE_SESSIONS
        _FAILED_LOGINS.clear(); _ACTIVE_SESSIONS.clear()
        conn = connect(tmp_path / f"ready_{db_state or 'none'}.db")
        if db_state is not None:
            _insert_runner_state(conn, fsm_state=db_state, age_ms=age_ms)
        sm = RunnerStateMachine(api_sm_state)
        pe = PaperTradingEngine(conn=conn)
        app = create_app(conn=conn, state_machine=sm, paper_engine=pe)
        return TestClient(app, raise_server_exceptions=False)

    def test_w6_halted_in_db_bot_enabled_false(self, tmp_path, monkeypatch):
        client = self._client_with_db_state(tmp_path, monkeypatch, db_state="HALTED")
        data = client.get("/ready").json()
        assert data["ok"] is True
        assert data["is_halted"] is True
        assert data["bot_enabled"] is False, (
            f"HALTED in DB muss bot_enabled=False liefern, bekommen {data}"
        )

    def test_w7_running_in_db_bot_enabled_true(self, tmp_path, monkeypatch):
        client = self._client_with_db_state(tmp_path, monkeypatch, db_state="RUNNING")
        data = client.get("/ready").json()
        assert data["bot_enabled"] is True
        assert data["is_halted"] is False

    def test_w8_missing_runner_state_bot_enabled_false(self, tmp_path, monkeypatch):
        """Kein Eintrag → fail-closed: bot_enabled=False."""
        client = self._client_with_db_state(tmp_path, monkeypatch, db_state=None)
        data = client.get("/ready").json()
        assert data["bot_enabled"] is False, (
            "Fehlender runner_state muss fail-closed bot_enabled=False liefern"
        )
        assert data.get("worker_known") is False

    def test_w9_starting_in_db_bot_enabled_false(self, tmp_path, monkeypatch):
        """STARTING darf keine Entry-Freigabe suggerieren."""
        client = self._client_with_db_state(tmp_path, monkeypatch, db_state="STARTING")
        data = client.get("/ready").json()
        assert data["bot_enabled"] is False, (
            "STARTING muss bot_enabled=False liefern (kein Schein-Bereit)"
        )

    def test_w10_stale_worker_bot_enabled_false(self, tmp_path, monkeypatch):
        """Veralteter Worker (>120s) → fail-closed."""
        client = self._client_with_db_state(tmp_path, monkeypatch,
                                             db_state="RUNNING", age_ms=130_000)
        data = client.get("/ready").json()
        assert data["bot_enabled"] is False, (
            "Veralteter Worker-Zustand muss bot_enabled=False liefern"
        )
        assert data.get("stale") is True

    def test_w6_no_auth_required_for_ready(self, tmp_path, monkeypatch):
        client = self._client_with_db_state(tmp_path, monkeypatch, db_state="HALTED")
        resp = client.get("/ready")
        assert resp.status_code == 200
        assert "Authorization" not in str(resp.request.headers)
