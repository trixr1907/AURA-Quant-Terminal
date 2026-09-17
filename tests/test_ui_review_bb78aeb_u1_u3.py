"""Regressionstests fuer AURA_UI_Review_bb78aeb.md, Befunde U1-U3.

Basis: bb78aeb385e62ad6c097e661d334a9ff4249110f.
Deckt ausschliesslich U1-U3 ab (keine erneute Pruefung von P1/Sizing).

U1  Entry-Status vs. State-Machine-Semantik
  U1a  WARMING_UP in DB -> entries_locked=True (kein Schein-Bereit)
  U1b  RECOVERING in DB -> entries_locked=True (kein Schein-Bereit)
  U1c  RUNNING+frisch in DB -> entries_locked=False (weiterhin erlaubt)
  U1d  DEGRADED in DB -> entries_locked=True, process_healthy=True (Trennung
       Prozessgesundheit / Entry-Faehigkeit)
  U1e  Unplausible Zukunftszeit (updated_at_ms weit in der Zukunft) -> stale=True,
       entries_locked=True (fail-closed statt "immer frisch")
  U1f  can_open_new_trades() bleibt unveraendert: nur RUNNING+nicht-halted (kein
       Trading-Gate wurde zur Anpassung an die Anzeige geaendert)

U2  Interner Halt-Freitext nicht anonym veroeffentlichen
  U2a  Vertraulicher synthetischer Marker als Halt-Grund in der DB wird von
       /status/worker NICHT zurueckgegeben
  U2b  /ready enthaelt ebenfalls keinen Freitext-Grund
  U2c  Bei HALTED liefert /status/worker nur den festen oeffentlichen Code

U3  Proxy-Allowlist exakt, keine stille Kuerzung, Cache begrenzt, kein
    Eventloop-Blocking
  U3a  Pfad mit nicht erlaubtem Suffix ("/candles_NOT_ALLOWED") -> 400
  U3b  Pfad mit Traversal-Versuch -> 400
  U3c  Pfad mit Sonderzeichen/Encoding-Trick -> 400
  U3d  Ueberlanger Parameterwert -> 400 (nicht mehr stillschweigend gekuerzt)
  U3e  Cache-Kapazitaet ist begrenzt (viele unterschiedliche Schluessel)
  U3f  Status-Endpunkte bleiben waehrend eines langsam antwortenden,
       gemockten Upstreams bedienbar (kein Eventloop-Blocking)
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from aura.api.app import create_app, PublicMarketCache
from aura.runner import PaperTradingEngine, RunnerStateMachine, SystemState
from aura.runner.state_machine import RunnerStateMachine as _RSM
from aura.store.db import connect

TEST_TOKEN = "u1_u3_test_token_secret"

# U2a: vertraulicher synthetischer Marker, der NIEMALS oeffentlich erscheinen darf.
_CONFIDENTIAL_MARKER = "CONFIDENTIAL_SECRET_MARKER_do_not_leak_/etc/shadow_sk-fake-12345"


def _clear_auth_state(monkeypatch):
    monkeypatch.setenv("AURA_RELAY_TOKEN", TEST_TOKEN)
    from aura.api.auth import _FAILED_LOGINS, _ACTIVE_SESSIONS
    _FAILED_LOGINS.clear()
    _ACTIVE_SESSIONS.clear()


def _insert_runner_state(conn: sqlite3.Connection, *, fsm_state: str, reason: str = "", age_ms: int = 0) -> None:
    """Schreibt runner_state mit gesteuertem Alter (age_ms>0: Vergangenheit; <0: Zukunft)."""
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


def _client_with_db_state(tmp_path: Path, monkeypatch, *, db_state: str, reason: str = "", age_ms: int = 0) -> TestClient:
    _clear_auth_state(monkeypatch)
    conn = connect(tmp_path / f"u1_u3_{db_state}_{age_ms}.db")
    _insert_runner_state(conn, fsm_state=db_state, reason=reason, age_ms=age_ms)
    app = create_app(
        conn=conn,
        state_machine=RunnerStateMachine(SystemState.STARTING),
        paper_engine=PaperTradingEngine(conn=conn),
    )
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# U1: Entry-Status vs. State-Machine-Semantik
# ---------------------------------------------------------------------------
class TestU1EntryStatusSemantics:
    def test_u1a_warming_up_entries_locked_true(self, tmp_path, monkeypatch):
        client = _client_with_db_state(tmp_path, monkeypatch, db_state="WARMING_UP")
        data = client.get("/status/worker").json()
        assert data["entries_locked"] is True, "WARMING_UP darf keine Entry-Freigabe melden (U1)"
        ready = client.get("/ready").json()
        assert ready["bot_enabled"] is False, "WARMING_UP darf /ready nicht bot_enabled=True liefern (U1)"

    def test_u1b_recovering_entries_locked_true(self, tmp_path, monkeypatch):
        client = _client_with_db_state(tmp_path, monkeypatch, db_state="RECOVERING")
        data = client.get("/status/worker").json()
        assert data["entries_locked"] is True, "RECOVERING darf keine Entry-Freigabe melden (U1)"
        ready = client.get("/ready").json()
        assert ready["bot_enabled"] is False, "RECOVERING darf /ready nicht bot_enabled=True liefern (U1)"

    def test_u1c_running_fresh_entries_locked_false(self, tmp_path, monkeypatch):
        client = _client_with_db_state(tmp_path, monkeypatch, db_state="RUNNING")
        data = client.get("/status/worker").json()
        assert data["entries_locked"] is False, "Frisches RUNNING muss weiterhin entries_locked=False liefern"
        ready = client.get("/ready").json()
        assert ready["bot_enabled"] is True

    def test_u1d_degraded_process_healthy_but_entries_locked(self, tmp_path, monkeypatch):
        """DEGRADED: Prozess laeuft (process_healthy), aber Entry-Gate bleibt gesperrt."""
        client = _client_with_db_state(tmp_path, monkeypatch, db_state="DEGRADED")
        data = client.get("/status/worker").json()
        assert data["entries_locked"] is True, "DEGRADED darf keine Entry-Freigabe melden (U1)"
        assert data["process_healthy"] is True, (
            "DEGRADED ist ein gesund laufender, aber gesperrter Prozess (U1: Trennung "
            "Prozessgesundheit von Entry-Faehigkeit)"
        )

    def test_u1d_halted_process_not_healthy(self, tmp_path, monkeypatch):
        """HALTED: weder Entry-Faehigkeit noch 'process_healthy' (per Definition Not-Halt)."""
        client = _client_with_db_state(tmp_path, monkeypatch, db_state="HALTED")
        data = client.get("/status/worker").json()
        assert data["entries_locked"] is True
        assert data["process_healthy"] is False

    def test_u1e_future_timestamp_treated_as_stale(self, tmp_path, monkeypatch):
        """Unplausible Zukunftszeit (updated_at_ms deutlich in der Zukunft) -> stale=True."""
        # age_ms negativ => updated_at_ms liegt in der Zukunft
        client = _client_with_db_state(tmp_path, monkeypatch, db_state="RUNNING", age_ms=-3_600_000)
        data = client.get("/status/worker").json()
        assert data["stale"] is True, "Unplausible Zukunftszeit muss als stale gelten (U1)"
        assert data["entries_locked"] is True, "Unplausible Zukunftszeit darf keine Entry-Freigabe erlauben (U1)"
        ready = client.get("/ready").json()
        assert ready["bot_enabled"] is False

    def test_u1e_small_clock_skew_tolerated(self, tmp_path, monkeypatch):
        """Geringer Uhren-Drift (< Toleranzschwelle) in der Zukunft ist kein stale."""
        client = _client_with_db_state(tmp_path, monkeypatch, db_state="RUNNING", age_ms=-1_000)
        data = client.get("/status/worker").json()
        assert data["stale"] is False, "Minimaler Clock-Skew darf nicht als stale gelten"

    def test_u1f_trading_gate_unchanged(self):
        """can_open_new_trades() bleibt exakt: nur RUNNING und nicht halted (kein Anzeige-Bypass)."""
        for state in (SystemState.STARTING, SystemState.WARMING_UP, SystemState.DEGRADED,
                      SystemState.HALTED, SystemState.RECOVERING):
            sm = _RSM(SystemState.STARTING)
            sm._state = state  # direkter Zustandssprung fuer isolierten Gate-Test
            assert sm.can_open_new_trades() is False, f"{state} darf can_open_new_trades()=True nicht liefern"
        sm_running = _RSM(SystemState.STARTING)
        sm_running._state = SystemState.RUNNING
        assert sm_running.can_open_new_trades() is True
        sm_running._halted = True
        assert sm_running.can_open_new_trades() is False, "Halted+RUNNING darf keine Trades erlauben"


# ---------------------------------------------------------------------------
# U2: Interner Halt-Freitext nicht anonym veroeffentlichen
# ---------------------------------------------------------------------------
class TestU2NoConfidentialReasonLeak:
    def test_u2a_confidential_marker_not_in_status_worker(self, tmp_path, monkeypatch):
        client = _client_with_db_state(
            tmp_path, monkeypatch, db_state="HALTED", reason=_CONFIDENTIAL_MARKER,
        )
        resp = client.get("/status/worker")
        assert resp.status_code == 200
        assert _CONFIDENTIAL_MARKER not in resp.text, (
            "Vertraulicher interner Halt-Freitext darf NIEMALS ueber /status/worker "
            "oeffentlich erscheinen (U2)"
        )

    def test_u2b_confidential_marker_not_in_ready(self, tmp_path, monkeypatch):
        client = _client_with_db_state(
            tmp_path, monkeypatch, db_state="HALTED", reason=_CONFIDENTIAL_MARKER,
        )
        resp = client.get("/ready")
        assert resp.status_code == 200
        assert _CONFIDENTIAL_MARKER not in resp.text, (
            "Vertraulicher interner Halt-Freitext darf NIEMALS ueber /ready "
            "oeffentlich erscheinen (U2)"
        )

    def test_u2c_halted_returns_fixed_public_code_only(self, tmp_path, monkeypatch):
        client = _client_with_db_state(
            tmp_path, monkeypatch, db_state="HALTED", reason=_CONFIDENTIAL_MARKER,
        )
        data = client.get("/status/worker").json()
        assert data["reason"] is not None
        # Fester Code, kein Freitext-Durchlass
        assert data["reason"] == "OPERATOR_OR_SYSTEM_HALT"
        assert data["reason"] != _CONFIDENTIAL_MARKER


# ---------------------------------------------------------------------------
# U3: Proxy-Allowlist, Parametervalidierung, Cache-Kapazitaet, Eventloop
# ---------------------------------------------------------------------------
@pytest.fixture
def halted_client(tmp_path: Path, monkeypatch) -> TestClient:
    _clear_auth_state(monkeypatch)
    conn = connect(tmp_path / "u3_proxy_test.db")
    sm = RunnerStateMachine(SystemState.HALTED)
    pe = PaperTradingEngine(conn=conn)
    app = create_app(conn=conn, state_machine=sm, paper_engine=pe)
    return TestClient(app, raise_server_exceptions=False)


class TestU3ExactAllowlist:
    def test_u3a_disallowed_suffix_rejected(self, halted_client: TestClient):
        """Reproduziert die im Review gezeigte Luecke: .../candles_NOT_ALLOWED muss abgewiesen werden."""
        resp = halted_client.post(
            "/api/public",
            json={"path": "/api/v2/mix/market/candles_NOT_ALLOWED"},
        )
        assert resp.status_code == 400, (
            f"Nicht freigegebener Suffixpfad wurde zugelassen (U3): {resp.status_code} {resp.text}"
        )

    def test_u3a_exact_allowed_path_still_works(self, halted_client: TestClient):
        with patch("aura.api.app._NO_REDIRECT_OPENER") as mock_opener:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=MagicMock(
                read=MagicMock(return_value=b'{"code":"00000","data":[]}')
            ))
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_opener.open.return_value = mock_ctx
            resp = halted_client.post(
                "/api/public",
                json={"path": "/api/v2/mix/market/candles",
                      "params": {"symbol": "BTCUSDT", "productType": "USDT-FUTURES", "granularity": "60"}},
            )
        assert resp.status_code == 200

    def test_u3b_path_traversal_rejected(self, halted_client: TestClient):
        resp = halted_client.post(
            "/api/public",
            json={"path": "/api/v2/mix/market/candles/../../../etc/passwd"},
        )
        assert resp.status_code == 400

    def test_u3c_encoded_special_chars_rejected(self, halted_client: TestClient):
        resp = halted_client.post(
            "/api/public",
            json={"path": "/api/v2/mix/market/candles%2F..%2Fsecret"},
        )
        assert resp.status_code == 400

    def test_u3c_backslash_rejected(self, halted_client: TestClient):
        resp = halted_client.post(
            "/api/public",
            json={"path": "/api/v2/mix/market/candles\\..\\secret"},
        )
        assert resp.status_code == 400

    def test_u3d_overlong_param_rejected_not_truncated(self, halted_client: TestClient):
        """Ueberlanger Parameterwert -> 400, kein stilles Abschneiden mehr (U3)."""
        long_val = "x" * 10_000
        resp = halted_client.post(
            "/api/public",
            json={
                "path": "/api/v2/mix/market/candles",
                "params": {"symbol": long_val, "productType": "USDT-FUTURES", "granularity": "60"},
            },
        )
        assert resp.status_code == 400, (
            f"Ueberlanger Parameterwert muss mit 400 abgelehnt werden, nicht gekuerzt (U3): {resp.status_code}"
        )

    def test_u3d_overlong_query_param_rejected(self, halted_client: TestClient):
        long_val = "y" * 500
        resp = halted_client.post(
            "/api/public",
            json={"path": f"/api/v2/mix/market/ticker?symbol={long_val}"},
        )
        assert resp.status_code == 400


class TestU3CacheCapacity:
    def test_u3e_cache_bounded_with_many_distinct_keys(self):
        """Viele unterschiedliche Cache-Schluessel duerfen die Kapazitaet nicht unbegrenzt wachsen lassen."""
        cache = PublicMarketCache()
        assert hasattr(cache, "_MAX_ENTRIES"), "Cache muss eine definierte Kapazitaetsgrenze haben (U3)"
        max_entries = cache._MAX_ENTRIES
        n_keys = max_entries * 4
        for i in range(n_keys):
            key = ("/api/v2/mix/market/candles", (("symbol", f"SYM{i}"),))
            cache.set(key, {"code": "00000", "data": [i]}, ttl=60.0)
        assert len(cache) <= max_entries, (
            f"Cache ist ueber die Kapazitaetsgrenze gewachsen: {len(cache)} Einträge "
            f"bei Limit {max_entries} (U3)"
        )
        assert len(cache) > 0


class TestU3NoEventloopBlocking:
    def test_u3f_status_endpoint_responsive_during_slow_upstream(self, tmp_path, monkeypatch):
        """Waehrend ein /api/public-Request auf einen langsamen (gemockten) Upstream
        wartet, muss /status/worker weiterhin sofort antworten (U3: kein Blocking
        der API-Eventloop durch synchrones Upstream-I/O).
        """
        _clear_auth_state(monkeypatch)
        conn = connect(tmp_path / "u3f_test.db")
        _insert_runner_state(conn, fsm_state="RUNNING")
        app = create_app(
            conn=conn,
            state_machine=RunnerStateMachine(SystemState.RUNNING),
            paper_engine=PaperTradingEngine(conn=conn),
        )

        SLOW_DELAY_S = 1.5

        def slow_open(req, timeout=8.0):
            time.sleep(SLOW_DELAY_S)
            mock_resp = MagicMock()
            mock_resp.read = MagicMock(return_value=b'{"code":"00000","data":[]}')
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_resp)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            return mock_ctx

        results: dict[str, float] = {}

        def do_slow_public_request():
            with TestClient(app, raise_server_exceptions=False) as c:
                with patch("aura.api.app._NO_REDIRECT_OPENER") as mock_opener:
                    mock_opener.open.side_effect = slow_open
                    t0 = time.monotonic()
                    # Eindeutiger Cache-Key (uuid-Symbol), damit dieser Test nicht
                    # versehentlich auf einem von anderen Tests bereits befuellten
                    # Eintrag des modul-globalen _PUBLIC_CACHE landet.
                    c.post("/api/public", json={"path": "/api/v2/mix/market/ticker",
                                                 "params": {"symbol": f"U3F{uuid.uuid4().hex[:12]}"}})
                    results["slow_call_duration"] = time.monotonic() - t0

        slow_thread = threading.Thread(target=do_slow_public_request)
        slow_thread.start()
        # Kurz warten, damit der langsame Request sicher gestartet/im Upstream-I/O ist.
        time.sleep(0.3)

        client = TestClient(app, raise_server_exceptions=False)
        t0 = time.monotonic()
        resp = client.get("/status/worker")
        status_duration = time.monotonic() - t0

        slow_thread.join(timeout=SLOW_DELAY_S + 5)

        assert resp.status_code == 200
        assert status_duration < 1.0, (
            f"/status/worker wurde durch langsamen Upstream-Call blockiert: "
            f"{status_duration:.2f}s (U3: I/O muss aus der Eventloop verlagert sein)"
        )
        assert results.get("slow_call_duration", 0) >= SLOW_DELAY_S - 0.1
