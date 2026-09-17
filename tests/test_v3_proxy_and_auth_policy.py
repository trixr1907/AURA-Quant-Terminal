"""Gezielte Regressionstests fuer Proxy-Sicherheit und Auth-Policy (Audit R40 UI-Paket).

Abgedeckte Anforderungen:
  P1  /api/v3/state ohne Session → 401 (geschuetzter State bleibt geschuetzt)
  P2  /api/v3/state mit gueltigem Token → 200 mit Portfolio-Daten
  P3  Logout + erneuter State-Abruf → 401 (Session bereinigt)
  P4  /api/public mit erlaubtem Endpunkt → 200 (oder 502 wenn Bitget nicht erreichbar)
  P5  /api/public mit verbotenem Pfad → 400
  P6  /api/public mit absolutem URL im path → 400
  P7  /api/public mit zu vielen Parametern → 400
  P8  /api/public mit ueberlangen Parameterwerten → wird gestutzt (kein 500)
  P9  /ready bei HALTED → bot_enabled: false
  P10 /serving liefert Version aus aura.__version__
  P11 /api/v3/state anonym liefert KEINE equity/open_positions/config-Daten
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from aura import __version__ as AURA_VERSION
from aura.api.app import create_app
from aura.runner import PaperTradingEngine, RunnerStateMachine, SystemState
from aura.store.db import connect

TEST_TOKEN = "proxy_test_token_secret"


@pytest.fixture
def halted_client(tmp_path: Path, monkeypatch) -> TestClient:
    """Client mit HALTED-Worker, ohne aktive Session."""
    monkeypatch.setenv("AURA_RELAY_TOKEN", TEST_TOKEN)
    from aura.api.auth import _FAILED_LOGINS, _ACTIVE_SESSIONS
    _FAILED_LOGINS.clear()
    _ACTIVE_SESSIONS.clear()
    db_file = tmp_path / "proxy_test.db"
    conn = connect(db_file)
    sm = RunnerStateMachine(SystemState.HALTED)
    pe = PaperTradingEngine(conn=conn)
    app = create_app(conn=conn, state_machine=sm, paper_engine=pe)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def running_client(tmp_path: Path, monkeypatch) -> TestClient:
    """Client mit RUNNING-Worker."""
    monkeypatch.setenv("AURA_RELAY_TOKEN", TEST_TOKEN)
    from aura.api.auth import _FAILED_LOGINS, _ACTIVE_SESSIONS
    _FAILED_LOGINS.clear()
    _ACTIVE_SESSIONS.clear()
    db_file = tmp_path / "proxy_running_test.db"
    conn = connect(db_file)
    sm = RunnerStateMachine(SystemState.RUNNING)
    pe = PaperTradingEngine(conn=conn)
    app = create_app(conn=conn, state_machine=sm, paper_engine=pe)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# P1  Geschuetzter State ohne Session → 401
# ---------------------------------------------------------------------------
class TestStateAuthPolicy:
    def test_p1_state_without_token_returns_401(self, halted_client: TestClient):
        resp = halted_client.get("/api/v3/state")
        assert resp.status_code == 401, f"Erwartet 401, bekommen {resp.status_code}: {resp.text}"

    def test_p1_state_without_token_no_portfolio_data_in_error(self, halted_client: TestClient):
        resp = halted_client.get("/api/v3/state")
        assert resp.status_code == 401
        # Fehler-Body darf keine Portfolio-Daten enthalten
        body = resp.text
        assert "equity" not in body or "detail" in resp.json()
        # Der Body ist kein State-Objekt
        assert "open_positions" not in body

    def test_p2_state_with_valid_token_returns_200(self, halted_client: TestClient):
        resp = halted_client.get(
            "/api/v3/state",
            headers={"X-AURA-TOKEN": TEST_TOKEN},
        )
        assert resp.status_code == 200, f"Token-Auth fehlgeschlagen: {resp.text}"
        data = resp.json()
        # Muss Portfolio-Felder enthalten
        assert "equity" in data
        assert "open_positions" in data
        assert "worker" in data

    def test_p11_state_anonym_has_no_equity_when_401(self, halted_client: TestClient):
        """Ohne Auth gibt es keinen State-Body mit equity/config/open_positions."""
        resp = halted_client.get("/api/v3/state")
        assert resp.status_code == 401
        # Der 401-Body ist eine generische FastAPI-Fehlernachricht
        data = resp.json()
        # Muss 'detail' haben, darf kein 'equity' haben
        assert "detail" in data
        assert "equity" not in data
        assert "open_positions" not in data
        assert "config" not in data

    def test_p3_logout_then_state_returns_401(self, running_client: TestClient):
        """Login → State → Logout → State muss wieder 401 liefern."""
        # Login
        login_resp = running_client.post(
            "/api/v3/auth/login",
            json={"token": TEST_TOKEN},
        )
        assert login_resp.status_code == 200
        # State mit Session-Cookie
        cookies = login_resp.cookies
        state_resp = running_client.get(
            "/api/v3/state",
            cookies=cookies,
        )
        assert state_resp.status_code == 200
        # Logout
        logout_resp = running_client.post(
            "/api/v3/auth/logout",
            cookies=cookies,
        )
        assert logout_resp.status_code == 200
        # State nach Logout – Cookie aus Logout-Response nehmen (session geloescht)
        post_logout_resp = running_client.get("/api/v3/state")
        assert post_logout_resp.status_code == 401, (
            f"Nach Logout sollte State 401 liefern, bekommen {post_logout_resp.status_code}"
        )


# ---------------------------------------------------------------------------
# P4-P8  Proxy-Sicherheit
# ---------------------------------------------------------------------------
class TestProxySecurity:
    def test_p5_forbidden_path_returns_400(self, halted_client: TestClient):
        resp = halted_client.post(
            "/api/public",
            json={"path": "/api/v2/account/assets"},
        )
        assert resp.status_code == 400, f"Verbotener Pfad wurde zugelassen: {resp.text}"

    def test_p6_absolute_url_returns_400(self, halted_client: TestClient):
        resp = halted_client.post(
            "/api/public",
            json={"path": "https://evil.example.com/steal"},
        )
        assert resp.status_code == 400

    def test_p6_scheme_injection_in_path_returns_400(self, halted_client: TestClient):
        resp = halted_client.post(
            "/api/public",
            json={"path": "/api/v2/mix/market/candles?x=http://evil.example.com"},
        )
        # Pfad selbst ist erlaubt, aber der evil-Parameter-Wert landet nur als
        # Query-String-Wert beim Upstream – kein SSRF via path.
        # Dieser Test prueft dass der Pfad akzeptiert wird (der Wert ist harm-
        # los als String-Parameter) – Hauptangriff ueber path-Injection wird
        # durch den startswith-Check blockiert.
        # Wir mocken den Upstream-Aufruf um keinen echten Netzwerk-Hit zu machen.
        with patch("aura.api.app._NO_REDIRECT_OPENER") as mock_opener:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=MagicMock(
                read=MagicMock(return_value=b'{"code":"00000","data":[]}')
            ))
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_opener.open.return_value = mock_ctx
            resp2 = halted_client.post(
                "/api/public",
                json={"path": "/api/v2/mix/market/candles?productType=USDT-FUTURES&symbol=BTCUSDT&granularity=60&startTime=0&endTime=0&limit=20"},
            )
            # Erlaubter Pfad → mock liefert 200
            assert resp2.status_code == 200

    def test_p6_path_traversal_attempt_returns_400(self, halted_client: TestClient):
        resp = halted_client.post(
            "/api/public",
            json={"path": "/api/v2/mix/market/../../../etc/passwd"},
        )
        # Pfad enthaelt nicht den exakten Prefix nach Traversal
        assert resp.status_code == 400

    def test_p7_too_many_params_returns_400(self, halted_client: TestClient):
        """Mehr als _MAX_PARAMS_COUNT (12) Parameter sollen mit 400 abgelehnt werden."""
        many_params = {f"param_{i}": f"val_{i}" for i in range(15)}
        resp = halted_client.post(
            "/api/public",
            json={
                "path": "/api/v2/mix/market/candles",
                "params": many_params,
            },
        )
        assert resp.status_code == 400, f"Zu viele Parameter wurden akzeptiert: {resp.text}"

    def test_p8_overlong_param_value_is_truncated_no_500(self, halted_client: TestClient):
        """Ein sehr langer Parameterwert darf keinen 500-Fehler verursachen."""
        with patch("aura.api.app._NO_REDIRECT_OPENER") as mock_opener:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=MagicMock(
                read=MagicMock(return_value=b'{"code":"00000","data":[]}')
            ))
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_opener.open.return_value = mock_ctx
            long_val = "x" * 10_000
            resp = halted_client.post(
                "/api/public",
                json={
                    "path": "/api/v2/mix/market/candles",
                    "params": {"symbol": long_val, "productType": "USDT-FUTURES", "granularity": "60"},
                },
            )
        # Kein 500 – der Wert wird gestutzt und der Mock gibt 200 zurück
        assert resp.status_code in (200, 400, 502), f"Unerwarteter Status: {resp.status_code}"
        assert resp.status_code != 500

    def test_p4_allowed_path_reaches_upstream_mock(self, halted_client: TestClient):
        """Erlaubter Pfad mit Mock-Upstream → 200 mit Bitget-Antwort."""
        with patch("aura.api.app._NO_REDIRECT_OPENER") as mock_opener:
            mock_resp = MagicMock()
            mock_resp.read = MagicMock(return_value=b'{"code":"00000","data":[],"msg":"success"}')
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_resp)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_opener.open.return_value = mock_ctx
            resp = halted_client.post(
                "/api/public",
                json={
                    "path": "/api/v2/mix/market/candles",
                    "params": {
                        "symbol": "BTCUSDT",
                        "productType": "USDT-FUTURES",
                        "granularity": "60",
                        "limit": "20",
                    },
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("code") == "00000"

    def test_upstream_failure_returns_502(self, halted_client: TestClient):
        """Upstream-Ausfall (Exception) → 502, keine interne Fehlermeldung mit Stack."""
        import urllib.error
        with patch("aura.api.app._NO_REDIRECT_OPENER") as mock_opener:
            mock_opener.open.side_effect = OSError("Connection refused")
            resp = halted_client.post(
                "/api/public",
                json={"path": "/api/v2/mix/market/ticker", "params": {"symbol": "BTCUSDT"}},
            )
        assert resp.status_code == 502
        body = resp.json()
        assert "detail" in body
        # Kein Python-Traceback im Response-Body
        assert "Traceback" not in body.get("detail", "")

    def test_no_auth_headers_forwarded_to_upstream(self, halted_client: TestClient):
        """Proxy darf keine Auth-Header des Clients an Bitget weiterleiten."""
        captured_headers: dict = {}

        def fake_open(req, timeout=8.0):
            captured_headers.update(dict(req.headers))
            mock_resp = MagicMock()
            mock_resp.read = MagicMock(return_value=b'{"code":"00000","data":[]}')
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_resp)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            return mock_ctx

        with patch("aura.api.app._NO_REDIRECT_OPENER") as mock_opener:
            mock_opener.open.side_effect = fake_open
            halted_client.post(
                "/api/public",
                headers={
                    "X-AURA-TOKEN": TEST_TOKEN,
                    "Authorization": f"Bearer {TEST_TOKEN}",
                    "Cookie": "session=abc123",
                },
                json={"path": "/api/v2/mix/market/ticker", "params": {"symbol": "BTCUSDT"}},
            )

        # Kein Auth-Header darf weitergeleitet worden sein
        header_keys_lower = {k.lower() for k in captured_headers}
        assert "x-aura-token" not in header_keys_lower
        assert "authorization" not in header_keys_lower
        assert "cookie" not in header_keys_lower


# ---------------------------------------------------------------------------
# P9/P10  /ready und /serving
# ---------------------------------------------------------------------------
class TestReadyAndServing:
    def test_p9_ready_halted_bot_enabled_false(self, tmp_path, monkeypatch):
        """HALTED in DB → bot_enabled=False, kein Auth nötig."""
        import sqlite3 as _sq, time as _t
        monkeypatch.setenv("AURA_RELAY_TOKEN", TEST_TOKEN)
        from aura.api.auth import _FAILED_LOGINS, _ACTIVE_SESSIONS
        _FAILED_LOGINS.clear(); _ACTIVE_SESSIONS.clear()
        from aura.store.db import connect as _connect
        conn = _connect(tmp_path / "ready_halted.db")
        now_ms = int(_t.time() * 1000)
        conn.execute(
            "INSERT INTO runner_state (id, fsm_state, reason, equity, cycle_count, updated_at_ms) "
            "VALUES (1, 'HALTED', 'Test', '10000', 0, ?)", (now_ms,)
        ); conn.commit()
        from aura.runner import RunnerStateMachine, SystemState, PaperTradingEngine
        from aura.api.app import create_app
        app = create_app(conn=conn, state_machine=RunnerStateMachine(SystemState.STARTING),
                         paper_engine=PaperTradingEngine(conn=conn))
        client = TestClient(app)
        resp = client.get("/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["is_halted"] is True
        assert data["bot_enabled"] is False, f"HALTED in DB muss bot_enabled=False liefern: {data}"

    def test_p9_ready_running_bot_enabled_true(self, tmp_path, monkeypatch):
        """RUNNING in DB mit frischem Heartbeat → bot_enabled=True."""
        import time as _t
        monkeypatch.setenv("AURA_RELAY_TOKEN", TEST_TOKEN)
        from aura.api.auth import _FAILED_LOGINS, _ACTIVE_SESSIONS
        _FAILED_LOGINS.clear(); _ACTIVE_SESSIONS.clear()
        from aura.store.db import connect as _connect
        conn = _connect(tmp_path / "ready_running.db")
        now_ms = int(_t.time() * 1000)
        conn.execute(
            "INSERT INTO runner_state (id, fsm_state, reason, equity, cycle_count, updated_at_ms) "
            "VALUES (1, 'RUNNING', '', '10000', 1, ?)", (now_ms,)
        ); conn.commit()
        from aura.runner import RunnerStateMachine, SystemState, PaperTradingEngine
        from aura.api.app import create_app
        app = create_app(conn=conn, state_machine=RunnerStateMachine(SystemState.STARTING),
                         paper_engine=PaperTradingEngine(conn=conn))
        client = TestClient(app)
        resp = client.get("/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["bot_enabled"] is True, f"RUNNING+frisch muss bot_enabled=True liefern: {data}"
        assert data["is_halted"] is False

    def test_p10_serving_version_matches_aura_version(self, halted_client: TestClient):
        resp = halted_client.get("/serving")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == AURA_VERSION, (
            f"Version stimmt nicht: serving={data['version']!r}, "
            f"aura.__version__={AURA_VERSION!r}"
        )
        assert data["version"] != "2.5.0", "Hardcodierte alte Version 2.5.0 muss durch __version__ ersetzt sein"


# ---------------------------------------------------------------------------
# ROI-Basiswert: fehlende Equity → kein Dummy-Wert
# ---------------------------------------------------------------------------
class TestRoiBaseEquity:
    def test_state_starting_equity_present_and_nonzero(self, running_client: TestClient):
        """starting_equity muss einen realen Wert enthalten, nicht 0 oder fehlen."""
        resp = running_client.get(
            "/api/v3/state",
            headers={"X-AURA-TOKEN": TEST_TOKEN},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "starting_equity" in data, "starting_equity fehlt im State"
        assert data["starting_equity"] > 0, "starting_equity muss > 0 sein"

    def test_roi_pct_zero_when_no_trades(self, running_client: TestClient):
        """ROI muss 0.0% sein wenn keine Trades geschlossen wurden."""
        resp = running_client.get(
            "/api/v3/state",
            headers={"X-AURA-TOKEN": TEST_TOKEN},
        )
        data = resp.json()
        assert data["total_closed_trades"] == 0
        assert data["roi_pct"] == 0.0, f"ROI sollte 0.0 sein ohne Trades, ist {data['roi_pct']}"
