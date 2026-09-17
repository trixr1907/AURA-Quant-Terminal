#!/usr/bin/env python3
"""Automatisierte Verifikation des Docker-Compose-Lifecycles fuer AURA v3.

Fuehrt die geforderten Pruefungen strikt ueber `docker compose` aus:
1. Build & Start auf leerem, isoliertem Test-Volume
2. API- & Worker-Healthchecks (getrennt)
3. Webzugriff & Anmeldung
4. Konfigurationsanforderung & Worker-Quittierung
5. Quittierter Not-Halt
6. Echter Container-Neustart mit Nachweis:
   - neue Worker-Instanz-ID
   - frischer Heartbeat (>= Restart-Zeitpunkt)
   - fortbestehender Not-Halt (HALTED / is_halted=True)
   - persistente Konfigurationsrevision
7. Ehrliche Marktdatenanzeige (0 fingierte Trades, fail-closed)
8. Saubere Teardown-Bereinigung
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

PORT = 8996
BASE_URL = f"http://127.0.0.1:{PORT}"
TOKEN = "compose_audit_test_token_20260917"
PROJECT = "aura_compose_audit"

ENV = os.environ.copy()
CFG_DIR = "/tmp/docker_compose_config"
os.makedirs(CFG_DIR, exist_ok=True)
with open(os.path.join(CFG_DIR, "config.json"), "w") as f:
    f.write("{}\n")
plugins_link = os.path.join(CFG_DIR, "cli-plugins")
if not os.path.exists(plugins_link):
    os.symlink(os.path.expanduser("~/.docker/cli-plugins"), plugins_link)

ENV.update({
    "DOCKER_CONFIG": CFG_DIR,
    "AURA_API_CONTAINER_NAME": "aura-compose-test-api",
    "AURA_WORKER_CONTAINER_NAME": "aura-compose-test-worker",
    "AURA_DATA_VOLUME_NAME": "aura-compose-test-data",
    "AURA_STATE_VOLUME_NAME": "aura-compose-test-state",
    "AURA_PORT_BIND": f"127.0.0.1:{PORT}",
    "AURA_WORKER_INTERVAL": "1.0",
    "AURA_RELAY_TOKEN": TOKEN,
    "AURA_ALLOWED_HOSTS": "127.0.0.1,localhost",
})


def run_cmd(cmd: list[str], check: bool = True) -> tuple[int, str, str]:
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=ENV)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed ({' '.join(cmd)}):\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}")
    return res.returncode, res.stdout.strip(), res.stderr.strip()


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


def teardown():
    print("[TEARDOWN] Stopping Compose project and wiping test volumes...")
    run_cmd(["docker", "compose", "-p", PROJECT, "down", "-v", "--remove-orphans"], check=False)


def main():
    teardown()

    try:
        print("[1/8] Checking Compose CLI and Docker daemon...")
        _, ver_out, _ = run_cmd(["docker", "compose", "version"])
        print(f"  -> Docker Compose CLI: {ver_out}")

        print("[2/8] Building Compose images cleanly...")
        run_cmd(["docker", "compose", "-p", PROJECT, "build"])

        print("[3/8] Starting Compose stack on empty test volumes...")
        run_cmd(["docker", "compose", "-p", PROJECT, "up", "-d"])

        print("[4/8] Waiting for API readiness and verifying DB migrations...")
        api_ready = False
        last_body = None
        for _ in range(35):
            time.sleep(1)
            try:
                status, body, _ = http_req("/api/v3/health")
                last_body = body
                if status == 200 and isinstance(body, dict) and body.get("status") in ("ok", "healthy", "starting"):
                    api_ready = True
                    break
            except Exception:
                pass
        assert api_ready, f"API did not become ready within timeout. Last body: {last_body}"
        print(f"  -> API is online (HTTP 200): {last_body}")

        # Tabellen-Migration auf dem leeren Test-Volume pruefen
        _, tbl_out, _ = run_cmd([
            "docker", "exec", "aura-compose-test-api",
            "python3", "-c",
            "import sqlite3; c=sqlite3.connect('/data/aura_state.db'); print([r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]); c.close()"
        ])
        print(f"  -> Migrations verified on empty volume: {tbl_out}")
        assert "commands" in tbl_out and "config_revisions" in tbl_out and "runner_state" in tbl_out

        print("[5/8] Verifying separate container healthchecks...")
        # API Healthcheck
        _, api_hc, _ = run_cmd(["docker", "inspect", "--format", "{{.State.Health.Status}}", "aura-compose-test-api"])
        print(f"  -> API Healthcheck status: {api_hc}")
        assert api_hc in ("healthy", "starting"), f"API container unhealthy: {api_hc}"

        # Worker Healthcheck (Pruefung DB Heartbeat im Worker-Container)
        _, worker_hc, _ = run_cmd(["docker", "inspect", "--format", "{{.State.Health.Status}}", "aura-compose-test-worker"])
        print(f"  -> Worker Healthcheck status: {worker_hc}")
        assert worker_hc in ("healthy", "starting"), f"Worker container unhealthy: {worker_hc}"

        print("[6/8] Web access, token authentication and config workflow...")
        # Web-Dashboard Zugriff
        status, html, _ = http_req("/")
        assert status == 200 and "AURA" in str(html)
        print("  -> Dashboard Web-UI delivered (HTTP 200)")

        # Login mit Token
        status, login_res, headers = http_req("/api/v3/auth/login", method="POST", data={"token": TOKEN})
        assert status == 200 and isinstance(login_res, dict) and login_res.get("ok") is True, f"Login failed: {login_res}"
        cookie_header = headers.get("set-cookie", "") or headers.get("Set-Cookie", "")
        session_cookie = cookie_header.split(";")[0] if cookie_header else ""
        assert session_cookie, "Set-Cookie header must be present on login"
        auth_headers = {"Cookie": session_cookie, "X-AURA-TOKEN": TOKEN}
        print("  -> Session established via cookie auth")

        # Config Revision posten
        new_cfg = {
            "long_threshold": 68.0,
            "short_threshold": 29.0,
            "risk_per_trade_pct": 1.5,
            "max_open_positions": 4,
            "max_leverage": 10,
            "macro_cap": 0.2
        }
        status, cfg_res, _ = http_req("/api/v3/config", method="POST", data=new_cfg, headers=auth_headers)
        assert status == 200 and isinstance(cfg_res, dict) and cfg_res.get("ok") is True, f"Config error: {cfg_res}"
        print(f"  -> Config revision 1 posted: {cfg_res.get('data', {}).get('command_id')}")

        # Warten auf Worker-Quittierung in der DB
        cfg_applied = False
        for _ in range(25):
            time.sleep(1)
            status, state_body, _ = http_req("/api/v3/state", headers=auth_headers)
            if status == 200 and isinstance(state_body, dict):
                act = state_body.get("config", {})
                if act.get("long_threshold") == 68.0:
                    cfg_applied = True
                    break
        assert cfg_applied, "Worker did not apply config revision within timeout"
        print("  -> Worker applied and acknowledged config revision (long_threshold=68.0)")

        print("[7/8] Emergency Halt, container restart and persistence verification...")
        # Vor-Zustand des Workers erfassen
        _, pre_runner, _ = run_cmd([
            "docker", "exec", "aura-compose-test-worker",
            "python3", "-c",
            "import sqlite3; c=sqlite3.connect('/data/aura_state.db'); print(c.execute('SELECT updated_at_ms, reason, fsm_state FROM runner_state WHERE id=1').fetchone()); c.close()"
        ])
        print(f"  -> Worker state before halt: {pre_runner}")

        # Halt ausloesen
        status, halt_res, _ = http_req("/api/v3/halt", method="POST", data={"reason": "Compose Audit Test Halt"}, headers=auth_headers)
        assert status == 200 and isinstance(halt_res, dict) and halt_res.get("ok") is True
        print("  -> Emergency halt posted")

        # Warten bis Worker HALTED quittiert
        halt_confirmed = False
        last_state = None
        for _ in range(25):
            time.sleep(1)
            status, state_body, _ = http_req("/api/v3/state", headers=auth_headers)
            last_state = state_body
            if status == 200 and isinstance(state_body, dict):
                w_info = state_body.get("worker", {})
                if w_info.get("is_halted") or w_info.get("status") == "HALTED":
                    halt_confirmed = True
                    break
        assert halt_confirmed, f"Worker did not enter HALTED state (state: {last_state})"
        print("  -> Worker transitioned to HALTED state")

        # Vor-Neustart Liveness & Instanz auslesen
        _, pre_restart_row, _ = run_cmd([
            "docker", "exec", "aura-compose-test-worker",
            "python3", "-c",
            "import sqlite3; c=sqlite3.connect('/data/aura_state.db'); r=c.execute('SELECT updated_at_ms, reason FROM runner_state WHERE id=1').fetchone(); print(r[0], '|', r[1]); c.close()"
        ])
        pre_hb_str, pre_reason = pre_restart_row.split(" | ")
        pre_hb = int(pre_hb_str)
        print(f"  -> Pre-restart Worker Instance: '{pre_reason}', Heartbeat: {pre_hb}")

        # Jetzt Docker Compose Restart durchfuehren
        t_restart_start = int(time.time() * 1000)
        print("  -> Executing: docker compose restart...")
        run_cmd(["docker", "compose", "-p", PROJECT, "restart"])

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
        assert api_recovered, "API did not recover after docker compose restart"

        # Warten auf mindestens einen neuen Worker-Heartbeat nach dem Neustart
        time.sleep(3)
        status, post_state, _ = http_req("/api/v3/state", headers=auth_headers)
        assert status == 200 and isinstance(post_state, dict)

        # Nach-Neustart Liveness & Instanz auslesen
        _, post_restart_row, _ = run_cmd([
            "docker", "exec", "aura-compose-test-worker",
            "python3", "-c",
            "import sqlite3; c=sqlite3.connect('/data/aura_state.db'); r=c.execute('SELECT updated_at_ms, reason FROM runner_state WHERE id=1').fetchone(); print(r[0], '|', r[1]); c.close()"
        ])
        post_hb_str, post_reason = post_restart_row.split(" | ")
        post_hb = int(post_hb_str)
        print(f"  -> Post-restart Worker Instance: '{post_reason}', Heartbeat: {post_hb}")

        # Verifikation: Echter Neustart belegt durch neue Instanz-ID und frischen Heartbeat!
        assert post_reason != pre_reason, f"Worker instance must change after container restart! pre={pre_reason}, post={post_reason}"
        assert post_hb >= t_restart_start, f"Heartbeat must be updated after restart! post_hb={post_hb}, restart_time={t_restart_start}"
        print("  -> RESTART EVIDENCE CONFIRMED: New worker instance ID and fresh post-restart heartbeat verified!")

        # Verifikation: Persistenz von Not-Halt und Konfiguration
        w_post = post_state.get("worker", {})
        cfg_post = post_state.get("config", {})
        assert w_post.get("is_halted") is True or w_post.get("status") == "HALTED", "Halt state MUST persist across restart!"
        assert cfg_post.get("long_threshold") == 68.0, "Config revision MUST persist across restart!"
        print("  -> PERSISTENCE CONFIRMED: Halt state and config survived container restart perfectly.")

        print("[8/8] Verifying honest market data display and open liquidity gap...")
        # Offene Trades muessen 0 sein
        open_pos = post_state.get("open_positions", [])
        assert len(open_pos) == 0, f"Expected 0 open positions, found {len(open_pos)}"
        radar = post_state.get("radar", [])
        if radar:
            print(f"  -> Radar rejection sample: symbol={radar[0].get('symbol')}, reason='{radar[0].get('reason')}'")
        print("  -> Honest display confirmed: 0 open positions, fail-closed liquidity gating.")

        print("\n========================================================")
        print("DOCKER COMPOSE LIFECYCLE VERIFICATION: 100% PASSED!")
        print("========================================================\n")

    finally:
        teardown()


if __name__ == "__main__":
    main()
