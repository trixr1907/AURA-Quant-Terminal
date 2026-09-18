"""Sicherheits- und API-Tests fuer aura.api (P6).

Prueft Authentifizierung, negative Auth-Faelle (401, 403), Schema-Validierung (422),
Not-Halt-Steuerung und Security-Header.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aura.api.app import create_app
from aura.runner import PaperTradingEngine, RunnerStateMachine, SystemState
from aura.store.db import connect

TEST_TOKEN = "test_secret_token_12345"


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("AURA_RELAY_TOKEN", TEST_TOKEN)
    from aura.api.auth import _FAILED_LOGINS, _ACTIVE_SESSIONS
    _FAILED_LOGINS.clear()
    _ACTIVE_SESSIONS.clear()
    db_file = tmp_path / "test_api.db"
    conn = connect(db_file)
    sm = RunnerStateMachine(SystemState.RUNNING)
    pe = PaperTradingEngine(conn=conn)
    app = create_app(conn=conn, state_machine=sm, paper_engine=pe)
    return TestClient(app)


class TestApiPublicEndpoints:
    def test_health_endpoint_public(self, api_client: TestClient):
        resp = api_client.get("/api/v3/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["system_state"] == "RUNNING"
        assert data["version"] == "3.0.0-dev"

    def test_security_headers_present(self, api_client: TestClient):
        resp = api_client.get("/api/v3/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert "Content-Security-Policy" in resp.headers


class TestApiAuthSecurity:
    def test_config_update_without_token_returns_401(self, api_client: TestClient):
        payload = {
            "risk_per_trade_pct": 1.5,
            "max_open_positions": 3,
            "max_leverage": 10,
            "long_threshold": 65.0,
            "short_threshold": 35.0,
            "macro_cap": 15.0,
            "dry_run": True,
            "ntfy_enabled": True,
        }
        resp = api_client.post("/api/v3/config", json=payload)
        assert resp.status_code == 401

    def test_config_update_with_invalid_token_returns_403(self, api_client: TestClient):
        payload = {
            "risk_per_trade_pct": 1.5,
            "max_open_positions": 3,
            "max_leverage": 10,
            "long_threshold": 65.0,
            "short_threshold": 35.0,
            "macro_cap": 15.0,
            "dry_run": True,
            "ntfy_enabled": True,
        }
        headers = {"X-AURA-TOKEN": "wrong_token"}
        resp = api_client.post("/api/v3/config", json=payload, headers=headers)
        assert resp.status_code == 403

    def test_config_update_with_valid_token_succeeds(self, api_client: TestClient):
        payload = {
            "risk_per_trade_pct": 2.0,
            "max_open_positions": 4,
            "max_leverage": 10,
            "long_threshold": 70.0,
            "short_threshold": 30.0,
            "macro_cap": 12.0,
            "dry_run": True,
            "ntfy_enabled": True,
        }
        headers = {"X-AURA-TOKEN": TEST_TOKEN}
        resp = api_client.post("/api/v3/config", json=payload, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_config_validation_rejects_out_of_bounds_values(self, api_client: TestClient):
        # Risk 10% (>5.0 max) -> 422 Unprocessable Entity
        payload = {
            "risk_per_trade_pct": 10.0,
            "max_open_positions": 3,
            "max_leverage": 10,
            "long_threshold": 65.0,
            "short_threshold": 35.0,
            "macro_cap": 15.0,
            "dry_run": True,
            "ntfy_enabled": True,
        }
        headers = {"X-AURA-TOKEN": TEST_TOKEN}
        resp = api_client.post("/api/v3/config", json=payload, headers=headers)
        assert resp.status_code == 422

    def test_emergency_halt_and_resume_lifecycle(self, api_client: TestClient):
        headers = {"Authorization": f"Bearer {TEST_TOKEN}"}

        # 1. Not-Halt ausloesen
        halt_resp = api_client.post("/api/v3/halt", json={"reason": "Test Not-Halt"}, headers=headers)
        assert halt_resp.status_code == 200
        assert halt_resp.json()["ok"] is True

        # Health pruefen
        h_resp = api_client.get("/api/v3/health")
        assert h_resp.json()["status"] == "halted"

        # 2. Wiederaufnahme
        res_resp = api_client.post("/api/v3/resume", json={"reason": "Test Resume"}, headers=headers)
        assert res_resp.status_code == 200
        assert res_resp.json()["ok"] is True


class TestApiSessionAuthAndConflict:
    def test_login_with_valid_token_sets_http_only_cookie(self, api_client: TestClient):
        resp = api_client.post("/api/v3/auth/login", json={"token": TEST_TOKEN})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["data"]["authenticated"] is True
        assert "aura_session" in resp.cookies

        # Status endpoint mit Cookie pruefen
        status_resp = api_client.get("/api/v3/auth/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["authenticated"] is True

        # Mutation mit Session-Cookie ohne Header ausfuehren
        cfg_resp = api_client.post(
            "/api/v3/config",
            json={
                "risk_per_trade_pct": 1.0,
                "max_open_positions": 2,
                "max_leverage": 5,
                "long_threshold": 75.0,
                "short_threshold": 25.0,
                "macro_cap": 10.0,
                "dry_run": True,
                "ntfy_enabled": False,
            },
        )
        assert cfg_resp.status_code == 200
        assert cfg_resp.json()["ok"] is True

        # Logout loescht Cookie
        logout_resp = api_client.post("/api/v3/auth/logout")
        assert logout_resp.status_code == 200
        assert logout_resp.json()["data"]["authenticated"] is False

        # Status endpoint nach Logout muss unauthenticated sein
        status_resp2 = api_client.get("/api/v3/auth/status")
        assert status_resp2.status_code == 200
        assert status_resp2.json()["authenticated"] is False

    def test_login_with_invalid_token_returns_403(self, api_client: TestClient):
        resp = api_client.post("/api/v3/auth/login", json={"token": "invalid_password"})
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Zugriff verweigert: Ungueltiger Authentifizierungs-Token"

    def test_login_rate_limit_triggers_429_after_5_failures(self, api_client: TestClient):
        for _ in range(5):
            r = api_client.post("/api/v3/auth/login", json={"token": "bad_token"})
            assert r.status_code == 403
        r_locked = api_client.post("/api/v3/auth/login", json={"token": "bad_token"})
        assert r_locked.status_code == 429
        assert "Zu viele fehlgeschlagene" in r_locked.json()["detail"]

    def test_cookie_authenticated_mutating_request_fails_on_foreign_origin_csrf(self, api_client: TestClient):
        # 1. Login with valid token -> sets session cookie
        login_resp = api_client.post("/api/v3/auth/login", json={"token": TEST_TOKEN})
        assert login_resp.status_code == 200

        # 2. Mutating POST with foreign Origin header -> 403 CSRF rejection
        resp = api_client.post(
            "/api/v3/halt",
            json={"reason": "CSRF Attack"},
            headers={"Origin": "https://malicious-site.example.com"},
        )
        assert resp.status_code == 403
        assert "CSRF" in resp.json()["detail"]

    def test_config_update_with_stale_expected_rev_returns_409(self, api_client: TestClient):
        headers = {"X-AURA-TOKEN": TEST_TOKEN}
        payload = {
            "risk_per_trade_pct": 1.0,
            "max_open_positions": 2,
            "max_leverage": 5,
            "long_threshold": 75.0,
            "short_threshold": 25.0,
            "macro_cap": 10.0,
            "dry_run": True,
            "ntfy_enabled": False,
            "expected_rev": 999,  # Nicht existierende oder alte Revision
        }
        resp = api_client.post("/api/v3/config", json=payload, headers=headers)
        assert resp.status_code == 409
        assert "Konfigurationskonflikt" in str(resp.json())
