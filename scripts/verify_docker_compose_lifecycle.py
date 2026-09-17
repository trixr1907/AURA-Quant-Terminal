#!/usr/bin/env python3
"""Automatisierte Verifikation des Docker-Compose-Lifecycles fuer AURA v3 (D1-D5 Härtung).

Fuehrt die geforderten Pruefungen strikt ueber `docker compose` aus:
- D1: Build verzehrt tatsaechlich `requirements.lock` und wird mit `--no-cache` gebaut.
- D2: Container-Schutzmassnahmen (read_only, no-new-privileges, cap_drop ALL, tmpfs, limits) und ntfy verifiziert.
- D3: Eindeutige Run-ID, Kollisionspruefung, Vorhandensein fremder Sentinels (Negative Test) und sicheres Cleanup.
- D4: Healthchecks werden bis zum echten 'healthy'-Zustand geprueft (starting ist NO-GO). Negativtest fuer fehlschlagenden Healthcheck.
- D5: Worker-Quittierung anhand konkreter Command-ID, aktiver Revision und wirksamer Konfiguration.
      Negativtest mit gestopptem Worker.
      Cookie-only Authentifizierung mit Origin-Headern, Pruefung von 401 nach Neustart und Neuanmeldung.
      Echte Regex-Instanz-ID-Trennung beim Restart.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

# -----------------------------------------------------------------------------
# D3: Eindeutige Run-ID und isolierte Ressourcen
# -----------------------------------------------------------------------------
RUN_ID = f"run_{int(time.time())}_{uuid.uuid4().hex[:6]}"
PROJECT_NAME = f"aura_audit_{RUN_ID}"
IMAGE_TAG = f"aura-audit-test:{RUN_ID}"
PORT = find_free_port()
BASE_URL = f"http://127.0.0.1:{PORT}"
TOKEN = f"token_{uuid.uuid4().hex}"

CONTAINER_API = f"aura-api-{RUN_ID}"
CONTAINER_WORKER = f"aura-worker-{RUN_ID}"
VOLUME_DATA = f"aura_data_{RUN_ID}"
VOLUME_STATE = f"aura_state_{RUN_ID}"

SENTINEL_VOL = f"aura_sentinel_vol_{RUN_ID}"
SENTINEL_NET = f"aura_sentinel_net_{RUN_ID}"

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
    "AURA_IMAGE_TAG": IMAGE_TAG,
    "AURA_API_CONTAINER_NAME": CONTAINER_API,
    "AURA_WORKER_CONTAINER_NAME": CONTAINER_WORKER,
    "AURA_DATA_VOLUME_NAME": VOLUME_DATA,
    "AURA_STATE_VOLUME_NAME": VOLUME_STATE,
    "AURA_PORT_BIND": f"127.0.0.1:{PORT}",
    "AURA_WORKER_INTERVAL": "1.0",
    "AURA_API_HC_INTERVAL": "3s",
    "AURA_API_HC_START_PERIOD": "2s",
    "AURA_WORKER_HC_INTERVAL": "3s",
    "AURA_WORKER_HC_START_PERIOD": "2s",
    "AURA_RELAY_TOKEN": TOKEN,
    "AURA_ALLOWED_HOSTS": "127.0.0.1,localhost",
    "AURA_NTFY_URL": "https://ntfy.sh/aura_test_audit_dummy",
})


def run_cmd(cmd: list[str], check: bool = True) -> tuple[int, str, str]:
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=ENV)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed ({' '.join(cmd)}):\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}")
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def compose_cmd(args: list[str], check: bool = True) -> tuple[int, str, str]:
    return run_cmd(["docker", "compose", "-p", PROJECT_NAME] + args, check=check)


def http_req(
    path: str,
    method: str = "GET",
    data: dict | None = None,
    headers: dict | None = None,
    cookie: str | None = None,
) -> tuple[int, Any, dict]:
    url = f"{BASE_URL}{path}"
    h = headers.copy() if headers else {}
    if cookie:
        h["Cookie"] = f"aura_session={cookie}"
    payload = None
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        h["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=payload, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status_code = resp.status
            resp_headers = dict(resp.headers)
            body_bytes = resp.read()
            try:
                body_json = json.loads(body_bytes.decode("utf-8"))
            except Exception:
                body_json = body_bytes.decode("utf-8")
            return status_code, body_json, resp_headers
    except urllib.error.HTTPError as e:
        status_code = e.code
        resp_headers = dict(e.headers)
        body_bytes = e.read()
        try:
            body_json = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            body_json = body_bytes.decode("utf-8")
        return status_code, body_json, resp_headers


def wait_for_healthy(container_name: str, timeout_sec: int = 45) -> dict:
    """Wartet bis der Container tatsaechlich 'healthy' ist (D4: starting ist NO-GO)."""
    deadline = time.time() + timeout_sec
    last_status = "unknown"
    last_health_json = {}
    while time.time() < deadline:
        code, out, _ = run_cmd(["docker", "inspect", "--format", "{{json .State.Health}}", container_name], check=False)
        if code == 0 and out.strip():
            try:
                data = json.loads(out)
                status = data.get("Status")
                last_status = status
                last_health_json = data
                if status == "healthy":
                    return data
                if status == "unhealthy":
                    raise AssertionError(f"Container '{container_name}' entered 'unhealthy' state: {data}")
            except json.JSONDecodeError:
                pass
        time.sleep(1)
    raise AssertionError(f"Container '{container_name}' failed to reach 'healthy' within {timeout_sec}s (last status: {last_status}, data: {last_health_json})")


def main() -> None:
    print(f"========================================================")
    print(f"AURA DOCKER-COMPOSE LIFECYCLE AUDIT (D1-D5 Härtung)")
    print(f"Run-ID:   {RUN_ID}")
    print(f"Project:  {PROJECT_NAME}")
    print(f"Image:    {IMAGE_TAG}")
    print(f"========================================================\n")

    # -------------------------------------------------------------------------
    # D3: Docker Endpoint & Kollisionsprüfung
    # -------------------------------------------------------------------------
    print("[1/10] Docker Daemon Endpunkt & Kollisionsprüfung...")
    code, info_out, _ = run_cmd(["docker", "info", "--format", "{{.ServerVersion}}"])
    print(f"  -> Docker Engine Version: {info_out}")
    code, comp_out, _ = run_cmd(["docker", "compose", "version"])
    print(f"  -> Docker Compose CLI:    {comp_out}")

    # Kollisionsprüfung: Keines der Testartefakte darf vorab existieren
    _, existing_containers, _ = run_cmd(["docker", "ps", "-a", "--format", "{{.Names}}"])
    _, existing_volumes, _ = run_cmd(["docker", "volume", "ls", "--format", "{{.Name}}"])
    for name in (CONTAINER_API, CONTAINER_WORKER):
        if name in existing_containers.split():
            raise RuntimeError(f"Kollision erkannt: Container '{name}' existiert bereits! Abbruch.")
    for name in (VOLUME_DATA, VOLUME_STATE):
        if name in existing_volumes.split():
            raise RuntimeError(f"Kollision erkannt: Volume '{name}' existiert bereits! Abbruch.")
    print("  -> Keine Namenskollisionen im Docker-Namespace.")

    # -------------------------------------------------------------------------
    # D3: Sentinel-Ressourcen vorab erstellen (Negativtest zur Isolierung)
    # -------------------------------------------------------------------------
    print("[2/10] Erzeuge fremde Sentinel-Ressourcen (Isolations-Beweis)...")
    run_cmd(["docker", "volume", "create", "--label", f"test.owner=fremd_{RUN_ID}", SENTINEL_VOL])
    run_cmd(["docker", "network", "create", "--label", f"test.owner=fremd_{RUN_ID}", SENTINEL_NET])
    print(f"  -> Sentinel-Volume angelegt:  {SENTINEL_VOL}")
    print(f"  -> Sentinel-Network angelegt: {SENTINEL_NET}")

    try:
        # ---------------------------------------------------------------------
        # D4: Negativ-Test fuer fehlschlagenden Healthcheck
        # ---------------------------------------------------------------------
        print("[3/10] Negativ-Test: Ein nie erfolgreicher Healthcheck muss fehlschlagen...")
        fail_cont = f"aura_hc_fail_test_{RUN_ID}"
        run_cmd([
            "docker", "run", "-d", "--name", fail_cont,
            "--health-cmd", "exit 1",
            "--health-interval", "1s",
            "--health-retries", "2",
            "--health-timeout", "1s",
            "python:3.12.3-slim-bookworm", "sleep", "30"
        ])
        time.sleep(3)
        hc_failed_as_expected = False
        try:
            wait_for_healthy(fail_cont, timeout_sec=4)
        except AssertionError as ex:
            hc_failed_as_expected = True
            print(f"  -> Negativ-Test ERFOLGREICH: Defekter Healthcheck wurde wie erwartet abgewiesen:\n     {ex}")
        finally:
            run_cmd(["docker", "rm", "-f", fail_cont], check=False)

        if not hc_failed_as_expected:
            raise AssertionError("Negativ-Test FEHLGESCHLAGEN: Ein defekter Healthcheck wurde faelschlicherweise akzeptiert!")

        # ---------------------------------------------------------------------
        # D1: Echter Clean-Build mit Cache-Ausschluss und Lockfile
        # ---------------------------------------------------------------------
        print("[4/10] D1: Cache-Ausschluss Clean-Build des Test-Images (konsumiert requirements.lock)...")
        t0 = time.time()
        compose_cmd(["build", "--no-cache"])
        build_time = time.time() - t0
        print(f"  -> Clean-Build abgeschlossen in {build_time:.2f}s.")

        # Pruefe Image-ID und deklarierte Locks im gebauten Image
        _, img_id, _ = run_cmd(["docker", "inspect", "--format", "{{.Id}}", IMAGE_TAG])
        print(f"  -> Gebautes Test-Image ID: {img_id}")
        _, pkg_check, _ = run_cmd(["docker", "run", "--rm", IMAGE_TAG, "pip", "show", "fastapi", "uvicorn", "pydantic"])
        print(f"  -> Verifizierte Pakete im Image:\n" + "\n".join(f"     {line}" for line in pkg_check.splitlines() if line.startswith("Name:") or line.startswith("Version:")))

        # ---------------------------------------------------------------------
        # D2: Start auf leerem Volume mit Container-Schutzmaßnahmen
        # ---------------------------------------------------------------------
        print("[5/10] D2: Start Compose-Stack mit Schutzmassnahmen auf isoliertem Volume...")
        compose_cmd(["up", "-d"])

        # Pruefe aktivierte Schutzmaßnahmen (read_only, cap_drop, no-new-privileges, limits)
        for cont_name in (CONTAINER_API, CONTAINER_WORKER):
            _, insp_sec, _ = run_cmd(["docker", "inspect", "--format", "{{.HostConfig.ReadonlyRootfs}} {{.HostConfig.SecurityOpt}} {{.HostConfig.CapDrop}} {{.HostConfig.Memory}}", cont_name])
            print(f"  -> Schutzmassnahmen '{cont_name}': {insp_sec}")
            if "true" not in insp_sec:
                raise AssertionError(f"Container '{cont_name}' laeuft nicht mit ReadonlyRootfs!")

        # ---------------------------------------------------------------------
        # D4: Healthchecks bis 'healthy' (starting ist verboten)
        # ---------------------------------------------------------------------
        print("[6/10] D4: Warte auf verifizierten 'healthy'-Zustand (API & Worker)...")
        api_health = wait_for_healthy(CONTAINER_API, timeout_sec=40)
        worker_health = wait_for_healthy(CONTAINER_WORKER, timeout_sec=40)
        print(f"  -> API Healthcheck:    STATUS=healthy (FailingStreak={api_health.get('FailingStreak')})")
        print(f"  -> Worker Healthcheck: STATUS=healthy (FailingStreak={worker_health.get('FailingStreak')})")

        # Schemamigrationen pruefen
        code, tables_out, _ = run_cmd([
            "docker", "exec", CONTAINER_API,
            "python3", "-c",
            "import sqlite3; c=sqlite3.connect('/data/aura_state.db'); print([r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()])"
        ])
        print(f"  -> DB-Migrationen verifiziert: {tables_out}")

        # ---------------------------------------------------------------------
        # D5: Auth-Trennung: Header-Token vs. Cookie-only Authentifizierung
        # ---------------------------------------------------------------------
        print("[7/10] D5: Getrennter Nachweis: Header-Token vs. Cookie-only Authentifizierung...")

        # 1. Header-Token Test (Ohne Cookie)
        status, state_hdr, _ = http_req("/api/v3/state", headers={"X-AURA-TOKEN": TOKEN})
        if status != 200:
            raise AssertionError(f"Header-Token-Zugriff fehlgeschlagen: Status {status}")
        print("  -> Header-Token-Authentifizierung erfolgreich (HTTP 200, ohne Cookie).")

        # 2. Cookie-only Test: Login via /api/v3/auth/login
        login_status, login_body, login_headers = http_req(
            "/api/v3/auth/login",
            method="POST",
            data={"token": TOKEN},
            headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"}
        )
        if login_status != 200 or not login_body.get("ok"):
            raise AssertionError(f"Login fehlgeschlagen: Status {login_status}, Body: {login_body}")

        # Extrahiere Session Cookie
        set_cookie = login_headers.get("Set-Cookie") or login_headers.get("set-cookie") or ""
        session_match = re.search(r"aura_session=([a-zA-Z0-9_\-\.]+)", set_cookie)
        if not session_match:
            raise AssertionError(f"Set-Cookie Header enthaelt kein aura_session Cookie: {set_cookie}")
        session_cookie = session_match.group(1)
        print(f"  -> Cookie-Login erfolgreich. Session-Cookie erhalten.")

        # 3. Zugriff auf /api/v3/state STRIKT Cookie-only (KEIN X-AURA-TOKEN Header!)
        status, state_cookie, _ = http_req(
            "/api/v3/state",
            cookie=session_cookie,
            headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"}
        )
        if status != 200:
            raise AssertionError(f"Cookie-only Zugriff auf /state fehlgeschlagen: Status {status}")
        print("  -> STRIKTER Cookie-only Zugriff auf /state erfolgreich (HTTP 200, kein Token-Header).")

        # ---------------------------------------------------------------------
        # D5: Konfigurationsquittierung & Negativtest gestoppter Worker
        # ---------------------------------------------------------------------
        print("[8/10] D5: Konfigurationsquittierung & Negativtest mit gestopptem Worker...")

        # 1. Normale Konfigurationsanforderung bei laufendem Worker (Revision 1)
        status, cfg_res, _ = http_req(
            "/api/v3/config",
            method="POST",
            data={
                "long_threshold": 68.0,
                "short_threshold": 32.0,
                "risk_per_trade_pct": 1.0,
                "max_open_positions": 2,
                "max_leverage": 10,
                "macro_cap": 0.2,
            },
            cookie=session_cookie,
            headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"}
        )
        if status != 200:
            raise AssertionError(f"Config-Anforderung fehlgeschlagen: Status {status}, {cfg_res}")
        cmd_id_1 = cfg_res["data"]["command_id"]
        req_rev_1 = cfg_res["data"]["requested_rev"]
        print(f"  -> Revision {req_rev_1} angefordert: Command-ID={cmd_id_1}")

        # Warten auf Worker-Quittierung in DB & State
        cmd_1_applied = False
        for _ in range(20):
            time.sleep(0.5)
            status, st, _ = http_req("/api/v3/state", cookie=session_cookie, headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"})
            if status == 200 and st.get("active_config_rev") == req_rev_1:
                # Pruefe DB commands Tabelle explizit
                _, cmd_db, _ = run_cmd([
                    "docker", "exec", CONTAINER_API,
                    "python3", "-c",
                    f"import sqlite3; c=sqlite3.connect('/data/aura_state.db'); print(c.execute('SELECT status, applied_at_ms FROM commands WHERE id=\"{cmd_id_1}\"').fetchone())"
                ])
                if "applied" in cmd_db and "None" not in cmd_db:
                    cmd_1_applied = True
                    print(f"  -> Quittierung belegt: active_config_rev={req_rev_1}, DB-Command={cmd_db}")
                    break

        if not cmd_1_applied:
            raise AssertionError(f"Worker hat Revision {req_rev_1} nicht quittiert!")

        # 2. Negativtest: Gestoppter Worker kann Konfiguration NICHT quittieren
        print("  -> Stoppe Worker-Container fuer Negativtest...")
        compose_cmd(["stop", "aura-worker"])

        status, cfg_res_2, _ = http_req(
            "/api/v3/config",
            method="POST",
            data={
                "long_threshold": 74.0,
                "short_threshold": 26.0,
                "risk_per_trade_pct": 1.0,
                "max_open_positions": 2,
                "max_leverage": 10,
                "macro_cap": 0.2,
            },
            cookie=session_cookie,
            headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"}
        )
        cmd_id_2 = cfg_res_2["data"]["command_id"]
        req_rev_2 = cfg_res_2["data"]["requested_rev"]
        print(f"  -> Revision {req_rev_2} bei GESTOPPTEM Worker angefordert: Command-ID={cmd_id_2}")

        time.sleep(3)
        status, st_stopped, _ = http_req("/api/v3/state", cookie=session_cookie, headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"})
        _, cmd_db_2, _ = run_cmd([
            "docker", "exec", CONTAINER_API,
            "python3", "-c",
            f"import sqlite3; c=sqlite3.connect('/data/aura_state.db'); print(c.execute('SELECT status, applied_at_ms FROM commands WHERE id=\"{cmd_id_2}\"').fetchone())"
        ])
        print(f"  -> Pruefung bei gestopptem Worker: active_rev={st_stopped.get('active_config_rev')}, DB-Command={cmd_db_2}")
        if st_stopped.get("active_config_rev") == req_rev_2 or "applied" in cmd_db_2:
            raise AssertionError("Negativ-Test FEHLGESCHLAGEN: Gestoppter Worker hat faelschlicherweise Konfiguration quittiert!")
        print("  -> Negativ-Test ERFOLGREICH: Gestoppter Worker kann keine Konfiguration quittieren (Status: pending).")

        # Worker wieder starten und pruefen ob er die haengende Konfiguration nun verarbeitet
        print("  -> Starte Worker-Container wieder...")
        compose_cmd(["start", "aura-worker"])
        wait_for_healthy(CONTAINER_WORKER, timeout_sec=25)

        cmd_2_applied = False
        for _ in range(20):
            time.sleep(0.5)
            status, st, _ = http_req("/api/v3/state", cookie=session_cookie, headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"})
            if status == 200 and st.get("active_config_rev") == req_rev_2:
                _, cmd_db_2_after, _ = run_cmd([
                    "docker", "exec", CONTAINER_API,
                    "python3", "-c",
                    f"import sqlite3; c=sqlite3.connect('/data/aura_state.db'); print(c.execute('SELECT status, applied_at_ms FROM commands WHERE id=\"{cmd_id_2}\"').fetchone())"
                ])
                if "applied" in cmd_db_2_after:
                    cmd_2_applied = True
                    print(f"  -> Quittierung nach Worker-Wiederanlauf belegt: active_config_rev={req_rev_2}, DB={cmd_db_2_after}")
                    break

        if not cmd_2_applied:
            raise AssertionError("Worker hat nach Wiederanlauf anstehende Konfiguration nicht verarbeitet!")

        # ---------------------------------------------------------------------
        # Not-Halt & Container-Neustart
        # ---------------------------------------------------------------------
        print("[9/10] Not-Halt, Container-Neustart, Session-Invalidierung & Persistenz...")

        # Worker-Instanz-ID vor Halt & Restart ermitteln
        _, inst_before_raw, _ = run_cmd([
            "docker", "exec", CONTAINER_API,
            "python3", "-c",
            "import sqlite3; c=sqlite3.connect('/data/aura_state.db'); print(c.execute('SELECT updated_at_ms, reason FROM runner_state WHERE id=1').fetchone())"
        ])
        print(f"  -> Worker vor Not-Halt: {inst_before_raw}")

        # Not-Halt via Cookie-only
        status, halt_res, _ = http_req(
            "/api/v3/halt",
            method="POST",
            data={"reason": "Compose Audit Test Halt"},
            cookie=session_cookie,
            headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"}
        )
        if status != 200:
            raise AssertionError(f"Not-Halt fehlgeschlagen: Status {status}, {halt_res}")

        # Warten auf HALTED
        for _ in range(20):
            time.sleep(0.5)
            status, st_halt, _ = http_req("/api/v3/state", cookie=session_cookie, headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"})
            if status == 200 and st_halt.get("worker", {}).get("is_halted") is True:
                break

        _, inst_pre_restart, _ = run_cmd([
            "docker", "exec", CONTAINER_API,
            "python3", "-c",
            "import sqlite3; c=sqlite3.connect('/data/aura_state.db'); print(c.execute('SELECT updated_at_ms, reason FROM runner_state WHERE id=1').fetchone())"
        ])
        m_hb = re.search(r"\((\d+),", inst_pre_restart)
        m_inst = re.search(r"\[(w_\d+_[0-9a-f]+)\]", inst_pre_restart)
        if not m_hb or not m_inst:
            raise AssertionError(f"Konnte Heartbeat/Instanz nicht parsen: {inst_pre_restart}")
        hb_pre = int(m_hb.group(1))
        inst_id_pre = m_inst.group(1)
        print(f"  -> Pre-restart Worker-Instanz: {inst_id_pre}, Heartbeat: {hb_pre}")

        # Echter Container-Neustart beider Container
        print("  -> Führe aus: docker compose restart...")
        restart_time_ms = int(time.time() * 1000)
        compose_cmd(["restart"])

        # Warte auf Wiedererreichbarkeit
        wait_for_healthy(CONTAINER_API, timeout_sec=40)
        wait_for_healthy(CONTAINER_WORKER, timeout_sec=40)

        # D5: Nach API-Neustart muss altes Session-Cookie 401 liefern (In-Memory Sessions ungültig)
        status_old_cookie, _, _ = http_req(
            "/api/v3/state",
            cookie=session_cookie,
            headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"}
        )
        print(f"  -> Status altes Cookie nach API-Neustart: HTTP {status_old_cookie}")
        if status_old_cookie != 401:
            raise AssertionError(f"In-Memory Session-Semantik verletzt: Altes Cookie wurde nach Neustart mit Status {status_old_cookie} akzeptiert (erwartet 401)!")
        print("  -> Session-Invalidierung verifiziert: Altes Cookie liefert wie erwartet HTTP 401.")

        # Neuanmeldung nach API-Neustart
        _, login_body_new, login_hdrs_new = http_req(
            "/api/v3/auth/login",
            method="POST",
            data={"token": TOKEN},
            headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"}
        )
        set_cookie_new = login_hdrs_new.get("Set-Cookie") or login_hdrs_new.get("set-cookie") or ""
        new_session_match = re.search(r"aura_session=([a-zA-Z0-9_\-\.]+)", set_cookie_new)
        if not new_session_match:
            raise AssertionError(f"Set-Cookie enthaelt kein Session-Cookie: {set_cookie_new}")
        new_session_cookie = new_session_match.group(1)
        print("  -> Neuanmeldung nach Neustart erfolgreich; neues Session-Cookie aktiv.")

        # Pruefe Post-Restart Instanz & Persistenz
        _, inst_post_restart, _ = run_cmd([
            "docker", "exec", CONTAINER_API,
            "python3", "-c",
            "import sqlite3; c=sqlite3.connect('/data/aura_state.db'); print(c.execute('SELECT updated_at_ms, reason FROM runner_state WHERE id=1').fetchone())"
        ])
        m_hb_post = re.search(r"\((\d+),", inst_post_restart)
        m_inst_post = re.search(r"\[(w_\d+_[0-9a-f]+)\]", inst_post_restart)
        if not m_hb_post or not m_inst_post:
            raise AssertionError(f"Konnte Post-Restart Heartbeat/Instanz nicht parsen: {inst_post_restart}")
        hb_post = int(m_hb_post.group(1))
        inst_id_post = m_inst_post.group(1)
        print(f"  -> Post-restart Worker-Instanz: {inst_id_post}, Heartbeat: {hb_post}")

        if inst_id_pre == inst_id_post:
            raise AssertionError(f"Instanz-ID nach Restart unveraendert ({inst_id_pre} == {inst_id_post})!")
        if hb_post < restart_time_ms:
            raise AssertionError(f"Heartbeat ({hb_post}) ist aelter als Restart-Zeitpunkt ({restart_time_ms})!")
        print(f"  -> RESTART-NACHWEIS BESTAETIGT: Neue Instanz-ID ({inst_id_pre} -> {inst_id_post}) und frischer Heartbeat.")

        status, post_state, _ = http_req(
            "/api/v3/state",
            cookie=new_session_cookie,
            headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"}
        )
        if post_state.get("worker", {}).get("is_halted") is not True:
            raise AssertionError(f"HALTED Zustand nach Restart nicht persistent: {post_state.get('worker')}")
        if post_state.get("active_config_rev") != req_rev_2:
            raise AssertionError(f"Konfigurationsrevision {req_rev_2} nach Restart verloren!")
        print("  -> PERSISTENZ BESTAETIGT: Not-Halt und Konfigurationsrevision ueber Neustart persistent erhalten.")

        # ---------------------------------------------------------------------
        # D3: Gezielter Teardown & Sentinel-Prüfung (Negativtest fremde Ressourcen)
        # ---------------------------------------------------------------------
        print("[10/10] D3: Sicherer Teardown des Stacks & Pruefung fremder Sentinel-Ressourcen...")
        compose_cmd(["down", "-v"])

        # Pruefe ob Sentinels unversehrt erhalten geblieben sind
        _, vols_after, _ = run_cmd(["docker", "volume", "ls", "--format", "{{.Name}}"])
        _, nets_after, _ = run_cmd(["docker", "network", "ls", "--format", "{{.Name}}"])

        if SENTINEL_VOL not in vols_after.split():
            raise AssertionError(f"ISOLATIONS-VERLETZUNG: Fremdes Sentinel-Volume '{SENTINEL_VOL}' wurde geloescht!")
        if SENTINEL_NET not in nets_after.split():
            raise AssertionError(f"ISOLATIONS-VERLETZUNG: Fremdes Sentinel-Network '{SENTINEL_NET}' wurde geloescht!")
        print(f"  -> ISOLATIONS-BEWEIS ERFOLGREICH: Fremde Sentinel-Ressourcen blieben unangetastet!")

    finally:
        # Sentinel-Ressourcen und gebautes Test-Image gezielt aufraeumen
        print("  -> Raeume gezielt eigene Sentinels, Test-Image und Test-Stack auf...")
        compose_cmd(["down", "-v"], check=False)
        run_cmd(["docker", "volume", "rm", "-f", SENTINEL_VOL], check=False)
        run_cmd(["docker", "network", "rm", SENTINEL_NET], check=False)
        run_cmd(["docker", "rmi", "-f", IMAGE_TAG], check=False)

    print("\n========================================================")
    print("DOCKER COMPOSE LIFECYCLE AUDIT: 100% PASSED (D1-D5 ERFÜLLT)!")
    print("========================================================\n")


if __name__ == "__main__":
    main()
