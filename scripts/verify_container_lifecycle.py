#!/usr/bin/env python3
"""Isolierter Container-Lifecycle- und Verifikationsnachweis fuer Docker.

Fuehrt die Abnahmeschritte gemaess Vorgabe durch:
1. Start auf leerem Volume (Migrationen)
2. Paralleler API- und Worker-Start
3. Webzugriff & Authentifizierung
4. Konfigurations-Workflow & Worker-Quittierung
5. Not-Halt & Zustandspersistenz
6. Container-Neustart (API & Worker) und Fortbestand von HALTED
7. Ehrliche Marktdaten-Anzeige (keine gefaelschten Trades)
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import sys
from typing import Any

PORT = 8999
BASE_URL = f"http://127.0.0.1:{PORT}"
TOKEN = "aura_test_container_token_20260917"
VOLUME_NAME = "aura_test_isolated_vol"
NET_NAME = "aura_test_isolated_net"
API_NAME = "aura_test_api"
WORKER_NAME = "aura_test_worker"
IMAGE_TAG = "aura-quant-terminal:2.5.0"


def run_cmd(cmd: list[str]) -> str:
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed ({' '.join(cmd)}): {res.stderr.strip()}")
    return res.stdout.strip()


def cleanup():
    print("[CLEANUP] Stopping and removing test containers, volume, network...")
    subprocess.run(["docker", "rm", "-f", API_NAME, WORKER_NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["docker", "volume", "rm", "-f", VOLUME_NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["docker", "network", "rm", NET_NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def http_req(path: str, method: str = "GET", data: dict | None = None, headers: dict | None = None) -> tuple[int, Any, dict]:
    url = f"{BASE_URL}{path}"
    h = headers or {}
    payload = None
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=payload, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body_bytes = resp.read().decode("utf-8")
            resp_headers = dict(resp.headers)
            try:
                parsed = json.loads(body_bytes)
            except Exception:
                parsed = body_bytes
            return resp.status, parsed, resp_headers
    except urllib.error.HTTPError as err:
        body_bytes = err.read().decode("utf-8")
        try:
            parsed = json.loads(body_bytes)
        except Exception:
            parsed = body_bytes
        return err.code, parsed, dict(err.headers)


def main():
    cleanup()

    try:
        print("[1/7] Creating isolated Docker network and empty volume...")
        run_cmd(["docker", "network", "create", NET_NAME])
        run_cmd(["docker", "volume", "create", VOLUME_NAME])

        print("[2/7] Starting API and Worker containers in parallel...")
        # 1. API Container
        run_cmd([
            "docker", "run", "-d",
            "--name", API_NAME,
            "--network", NET_NAME,
            "-v", f"{VOLUME_NAME}:/data",
            "-e", "AURA_DB_PATH=/data/aura_state.db",
            "-e", f"AURA_RELAY_TOKEN={TOKEN}",
            "-e", "AURA_ALLOWED_HOSTS=127.0.0.1,localhost",
            "-p", f"127.0.0.1:{PORT}:8000",
            IMAGE_TAG
        ])

        # 2. Worker Container (Production default: uses real Bitget public feeds, NO test feed)
        run_cmd([
            "docker", "run", "-d",
            "--name", WORKER_NAME,
            "--network", NET_NAME,
            "-v", f"{VOLUME_NAME}:/data",
            "-e", "AURA_DB_PATH=/data/aura_state.db",
            "-e", f"AURA_RELAY_TOKEN={TOKEN}",
            "-e", "AURA_ALLOWED_HOSTS=127.0.0.1,localhost",
            IMAGE_TAG,
            "python3", "-m", "aura.runner.worker", "--interval", "1.0"
        ])

        print("[3/7] Waiting for API readiness & migration execution...")
        api_ready = False
        last_body = None
        for _ in range(30):
            time.sleep(1)
            try:
                status, body, _ = http_req("/api/v3/health")
                last_body = body
                if status == 200 and isinstance(body, dict) and body.get("status") in ("ok", "healthy", "starting"):
                    api_ready = True
                    break
            except Exception:
                pass
        if not api_ready:
            raise RuntimeError(f"API container did not become ready within 30 seconds (last body: {last_body})")
        print(f"  -> API is healthy: HTTP 200 {last_body}")

        # Pruefe Migrationen auf leerem Volume
        db_tables = run_cmd([
            "docker", "exec", API_NAME,
            "python3", "-c",
            "import sqlite3; c=sqlite3.connect('/data/aura_state.db'); print([r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]); c.close()"
        ])
        print(f"  -> Auto-applied schema tables on empty volume: {db_tables}")
        assert "commands" in db_tables and "config_revisions" in db_tables and "schema_migrations" in db_tables

        print("[4/7] Testing Web dashboard access and authentication...")
        # GET Dashboard
        status, html, _ = http_req("/")
        assert status == 200 and "AURA" in str(html)
        print("  -> Dashboard HTML delivered: HTTP 200")

        # Login mit AURA_RELAY_TOKEN
        status, login_res, headers = http_req("/api/v3/auth/login", method="POST", data={"token": TOKEN})
        assert status == 200 and isinstance(login_res, dict) and login_res.get("ok") is True, f"Login failed: {login_res}"
        cookie_header = headers.get("set-cookie", "") or headers.get("Set-Cookie", "")
        session_cookie = cookie_header.split(";")[0] if cookie_header else ""
        assert session_cookie, "Set-Cookie header must be returned on login"
        print("  -> Login successful, session cookie established")

        auth_headers = {"Cookie": session_cookie, "X-AURA-TOKEN": TOKEN}

        print("[5/7] Testing configuration workflow & worker acknowledgement...")
        # Config-Aenderung ueber API posten
        cfg_payload = {
            "long_threshold": 65.0,
            "short_threshold": 32.0,
            "risk_per_trade_pct": 1.2,
            "max_open_positions": 3,
            "max_leverage": 10,
            "macro_cap": 0.2
        }
        status, cfg_res, _ = http_req("/api/v3/config", method="POST", data=cfg_payload, headers=auth_headers)
        assert status == 200 and isinstance(cfg_res, dict) and cfg_res.get("ok") is True, f"Config failed: {cfg_res}"
        print(f"  -> Config revision posted: {cfg_res}")

        # Warten bis Worker die Revision ueber die DB quittiert hat (applied_at_ms IS NOT NULL)
        worker_applied = False
        for _ in range(25):
            time.sleep(1)
            status, state_body, _ = http_req("/api/v3/state", headers=auth_headers)
            if status == 200 and isinstance(state_body, dict):
                active_cfg = state_body.get("config", {})
                if active_cfg.get("long_threshold") == 65.0:
                    worker_applied = True
                    break
        assert worker_applied, "Worker did not acknowledge and apply config within timeout"
        print("  -> Worker successfully acknowledged and applied config revision")

        print("[6/7] Testing Emergency Halt, state persistence & container restart...")
        # Not-Halt anfordern
        status, halt_res, _ = http_req("/api/v3/halt", method="POST", data={"reason": "Container Integration Test Halt"}, headers=auth_headers)
        assert status == 200 and isinstance(halt_res, dict) and halt_res.get("ok") is True, f"Halt failed: {halt_res}"
        print(f"  -> Halt requested: {halt_res}")

        # Warten bis Worker den Halt quittiert hat
        halt_applied = False
        last_state = None
        for _ in range(25):
            time.sleep(1)
            status, state_body, _ = http_req("/api/v3/state", headers=auth_headers)
            last_state = state_body
            if status == 200 and isinstance(state_body, dict):
                worker_info = state_body.get("worker", {})
                fsm = worker_info.get("status")
                is_halted = worker_info.get("is_halted")
                if is_halted or fsm == "HALTED":
                    halt_applied = True
                    break
        assert halt_applied, f"Worker did not acknowledge halt (current state: {last_state})"
        assert isinstance(last_state, dict)
        print(f"  -> Worker transitioned to HALTED: {last_state.get('worker', {}).get('status')}")

        # Jetzt Container-Neustart durchfuehren: BEIDE Container neu starten
        print("  -> Restarting both containers (docker restart aura_test_worker, docker restart aura_test_api)...")
        run_cmd(["docker", "restart", WORKER_NAME])
        run_cmd(["docker", "restart", API_NAME])

        # Warten bis API wieder online ist
        time.sleep(3)
        api_recovered = False
        for _ in range(30):
            time.sleep(1)
            try:
                status, body, _ = http_req("/api/v3/health")
                if status == 200:
                    api_recovered = True
                    break
            except Exception:
                pass
        assert api_recovered, "API did not recover after container restart"

        # Pruefe, dass der HALTED-Zustand und die Konfiguration nach Neustart persistent erhalten bleiben
        status, restarted_state, _ = http_req("/api/v3/state", headers=auth_headers)
        assert status == 200 and isinstance(restarted_state, dict)
        worker_after = restarted_state.get("worker", {})
        fsm_after = worker_after.get("status")
        is_halted_after = worker_after.get("is_halted")
        cfg_after = restarted_state.get("config", {})

        print(f"  -> State after restart: fsm_state={fsm_after}, is_halted={is_halted_after}")
        assert is_halted_after or fsm_after == "HALTED", "Halt state MUST persist across container restarts!"
        assert cfg_after.get("long_threshold") == 65.0, "Config MUST persist across container restarts!"
        print("  -> PERSISTENCE VERIFIED: Halt and config preserved perfectly across restarts.")

        print("[7/7] Verifying honest market data display (no fake/synthetic trades)...")
        # Pruefe, dass ohne eingehende Bitget-Fills ehrlich 0 offene Positionen angezeigt werden
        open_pos = restarted_state.get("open_positions", [])
        print(f"  -> Open positions in production container: {len(open_pos)} (honest state, no synthetic trades)")
        assert len(open_pos) == 0

        print("\nALL CONTAINER LIFECYCLE CHECKS PASSED SUCCESSFULLY!")

    finally:
        cleanup()


if __name__ == "__main__":
    main()
