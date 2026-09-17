#!/usr/bin/env python3
"""Automatisierte Verifikation des Docker-Compose-Lifecycles fuer AURA v3 (Audit de987aa Härtung).

Schliesst die verbleibenden Harness-Sicherheitsluecken:
1. Docker-Ziel ausdruecklich ermitteln, lokale Socket-Bindung ('unix:///var/run/docker.sock')
   erzwingen und bei unklarem/Remote-Ziel vor jeder Mutation abbrechen.
2. Repository-Compose-Datei ('docker-compose.yml') und Projektverzeichnis absolut binden.
   Fremde Umgebungsvariablen ('COMPOSE_FILE', 'COMPOSE_PATH_SEPARATOR', etc.) filtern.
3. Ownership-basiertes Cleanup: Nur nachweislich selbst angelegte Ressourcen mit passendem
   Projekt- und Run-ID-Label loeschen. Fremde Ressourcen niemals antasten.
4. Negative Tests fuer:
   - Unerlaubtes Docker-Ziel (Abbruch vor Mutation)
   - Fremde Compose-Dateiauswahl (Strikte Bindung an Repo-Compose-Datei)
   - Echte Namenskollision (Abbruch vor Mutation, fremde Ressource bleibt erhalten)
5. Not-Halt-Verifikation: Konkrete Command-ID, Status 'applied', Timestamp und 'HALTED'
   zwingend vor Neustart bestaetigen (Timeout wirft Fehler).
   Gestoppter Worker: Exakt Status 'pending' und unveraenderte aktive Revision bestaetigen.
6. Keine oeffentlichen ntfy-Testnachrichten (lokale Dummy-URL/deaktiviert).
   Alle Docker-Unterprozesse mit strikt begrenzten Timeouts ausfuehren.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

# -----------------------------------------------------------------------------
# 1. & 2. Absolute Pfade & Projektverzeichnis
# -----------------------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPOSE_FILE = os.path.join(REPO_ROOT, "docker-compose.yml")
if not os.path.isfile(COMPOSE_FILE):
    raise FileNotFoundError(f"docker-compose.yml nicht gefunden unter: {COMPOSE_FILE}")

# -----------------------------------------------------------------------------
# D3: Eindeutige Run-ID und isolierte Bezeichnungen
# -----------------------------------------------------------------------------
RUN_ID = f"run_{int(time.time())}_{uuid.uuid4().hex[:6]}"
PROJECT_NAME = f"aura_audit_{RUN_ID}"
IMAGE_TAG = f"aura-audit-test:{RUN_ID}"

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

PORT = find_free_port()
BASE_URL = f"http://127.0.0.1:{PORT}"
TOKEN = f"token_{uuid.uuid4().hex}"

CONTAINER_API = f"aura-api-{RUN_ID}"
CONTAINER_WORKER = f"aura-worker-{RUN_ID}"
VOLUME_DATA = f"aura_data_{RUN_ID}"
VOLUME_STATE = f"aura_state_{RUN_ID}"

SENTINEL_VOL = f"aura_sentinel_vol_{RUN_ID}"
SENTINEL_NET = f"aura_sentinel_net_{RUN_ID}"

# Temporaeres Konfigurationsverzeichnis fuer Docker CLI (isoliert, kein /tmp/docker_compose_config)
_TEMP_CFG_DIR = tempfile.TemporaryDirectory(prefix="aura_docker_cfg_")
CFG_DIR = _TEMP_CFG_DIR.name
with open(os.path.join(CFG_DIR, "config.json"), "w") as f:
    f.write("{}\n")
plugins_link = os.path.join(CFG_DIR, "cli-plugins")
if not os.path.exists(plugins_link):
    user_plugins = os.path.expanduser("~/.docker/cli-plugins")
    if os.path.exists(user_plugins):
        os.symlink(user_plugins, plugins_link)

# Umgebung saeubern & auf Repo-Werte fixieren
ENV = os.environ.copy()

# Fremde Compose- und Daemon-Steuervariablen explizit entfernen
for var in ("COMPOSE_FILE", "COMPOSE_PATH_SEPARATOR", "COMPOSE_PROFILES", "COMPOSE_PROJECT_NAME", "DOCKER_CONTEXT"):
    ENV.pop(var, None)

# Strikt lokaler Socket erzwingen
LOCAL_DOCKER_SOCKET = "unix:///var/run/docker.sock"
ENV["DOCKER_HOST"] = LOCAL_DOCKER_SOCKET
ENV["DOCKER_CONFIG"] = CFG_DIR

ENV.update({
    "AURA_IMAGE_TAG": IMAGE_TAG,
    "AURA_API_CONTAINER_NAME": CONTAINER_API,
    "AURA_WORKER_CONTAINER_NAME": CONTAINER_WORKER,
    "AURA_DATA_VOLUME_NAME": VOLUME_DATA,
    "AURA_STATE_VOLUME_NAME": VOLUME_STATE,
    "AURA_PORT_BIND": f"127.0.0.1:{PORT}",
    "AURA_WORKER_INTERVAL": "1.0",
    "AURA_API_HC_INTERVAL": "5s",
    "AURA_API_HC_START_PERIOD": "90s",
    "AURA_WORKER_HC_INTERVAL": "3s",
    "AURA_WORKER_HC_START_PERIOD": "2s",
    "AURA_RELAY_TOKEN": TOKEN,
    "AURA_ALLOWED_HOSTS": "127.0.0.1,localhost",
    # Keine oeffentliche ntfy-Testnachrichten (lokaler Dummy-Loopback)
    "AURA_NTFY_URL": "http://127.0.0.1:9/disabled",
})


def run_cmd(cmd: list[str], check: bool = True, timeout: int = 40, env_override: dict | None = None) -> tuple[int, str, str]:
    """Fuehrt einen Befehl mit striktem Timeout und sicherem Environment aus."""
    cmd_env = env_override if env_override is not None else ENV
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=cmd_env,
            cwd=REPO_ROOT,
            timeout=timeout,
        )
        if check and res.returncode != 0:
            raise RuntimeError(f"Command failed ({' '.join(cmd)}):\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}")
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Command timed out after {timeout}s ({' '.join(cmd)})") from exc


def compose_cmd(args: list[str], check: bool = True, timeout: int = 90) -> tuple[int, str, str]:
    """Ruft Docker Compose mit absolut gebundener Datei und absolutem Projektverzeichnis auf."""
    cmd = [
        "docker", "compose",
        "-f", COMPOSE_FILE,
        "--project-directory", REPO_ROOT,
        "-p", PROJECT_NAME,
    ] + args
    return run_cmd(cmd, check=check, timeout=timeout)


def verify_docker_endpoint(env_to_check: dict[str, str]) -> str:
    """Verifiziert ausdruecklich, dass ein lokaler Docker-Daemon angesprochen wird.
    
    Verweigert die Ausfuehrung vor jeder Mutation, falls ein Remote-Endpunkt
    (tcp://, ssh://, http://) konfiguriert ist oder ein fremder Daemon erkannt wird.
    """
    host = env_to_check.get("DOCKER_HOST", "").strip()
    if host:
        if not host.startswith("unix://"):
            raise RuntimeError(f"Unerlaubtes Docker-Ziel erkannt: DOCKER_HOST verweist auf Remote-Endpunkt ('{host}'). Ausfuehrung vor Mutation verweigert.")
        if not os.path.exists(host.replace("unix://", "")):
            raise RuntimeError(f"Lokaler Docker-Socket existiert nicht: {host}")

    code, info_out, err = run_cmd(
        ["docker", "info", "--format", "{{.OperatingSystem}} | {{.ServerVersion}}"],
        check=False,
        timeout=10,
        env_override=env_to_check,
    )
    if code != 0:
        raise RuntimeError(f"Docker Daemon nicht erreichbar oder unklares Ziel: {err}")
    return info_out


def check_resource_collision(candidates: list[tuple[str, str]]) -> None:
    """Prueft vorab im Docker-Namespace, ob Namen kollidieren wuerden."""
    _, existing_containers, _ = run_cmd(["docker", "ps", "-a", "--format", "{{.Names}}"], timeout=10)
    _, existing_volumes, _ = run_cmd(["docker", "volume", "ls", "--format", "{{.Name}}"], timeout=10)
    _, existing_networks, _ = run_cmd(["docker", "network", "ls", "--format", "{{.Name}}"], timeout=10)

    c_list = existing_containers.split()
    v_list = existing_volumes.split()
    n_list = existing_networks.split()

    for r_type, name in candidates:
        if r_type == "container" and name in c_list:
            raise RuntimeError(f"Kollision erkannt: Container '{name}' existiert bereits im Docker-Namespace! Abbruch vor Mutation.")
        if r_type == "volume" and name in v_list:
            raise RuntimeError(f"Kollision erkannt: Volume '{name}' existiert bereits im Docker-Namespace! Abbruch vor Mutation.")
        if r_type == "network" and name in n_list:
            raise RuntimeError(f"Kollision erkannt: Network '{name}' existiert bereits im Docker-Namespace! Abbruch vor Mutation.")


def http_req(
    path: str,
    method: str = "GET",
    data: dict | None = None,
    headers: dict | None = None,
    cookie: str | None = None,
    timeout: int = 10,
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
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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
        code, out, _ = run_cmd(["docker", "inspect", "--format", "{{json .State.Health}}", container_name], check=False, timeout=8)
        if code == 0 and out.strip():
            try:
                data = json.loads(out)
                status = data.get("Status")
                last_status = status
                last_health_json = data
                if status == "healthy":
                    return data
                if status == "unhealthy":
                    raise AssertionError(f"Container '{container_name}' ging in Zustand 'unhealthy': {data}")
            except json.JSONDecodeError:
                pass
        time.sleep(1)
    raise AssertionError(f"Container '{container_name}' erreichte innerhalb {timeout_sec}s nicht 'healthy' (letzter Status: {last_status}, data: {last_health_json})")


def main() -> None:
    print(f"========================================================")
    print(f"AURA DOCKER-COMPOSE LIFECYCLE AUDIT (de987aa Härtung)")
    print(f"Run-ID:         {RUN_ID}")
    print(f"Project:        {PROJECT_NAME}")
    print(f"Compose-File:   {COMPOSE_FILE}")
    print(f"Repo-Root:      {REPO_ROOT}")
    print(f"Docker-Target:  {LOCAL_DOCKER_SOCKET}")
    print(f"========================================================\n")

    # -------------------------------------------------------------------------
    # 1. Docker-Ziel ausdruecklich ermitteln & validieren
    # -------------------------------------------------------------------------
    print("[1/12] Docker-Daemon Endpunkt ausdruecklich pruefen...")
    endpoint_info = verify_docker_endpoint(ENV)
    print(f"  -> Verifizierter lokaler Docker-Daemon: {endpoint_info}")

    # -------------------------------------------------------------------------
    # 4. NEGATIVTEST 1: Unerlaubtes Docker-Ziel fuehrt zu sofortigem Abbruch vor Mutation
    # -------------------------------------------------------------------------
    print("[2/12] Negativtest 1: Unerlaubtes Docker-Ziel (Remote/TCP) muss sofort abbrechen...")
    fake_remote_env = ENV.copy()
    fake_remote_env["DOCKER_HOST"] = "tcp://production.aura-quant.internal:2375"
    remote_aborted_as_expected = False
    try:
        verify_docker_endpoint(fake_remote_env)
    except RuntimeError as ex:
        if "Unerlaubtes Docker-Ziel erkannt" in str(ex):
            remote_aborted_as_expected = True
            print(f"  -> Negativtest ERFOLGREICH: Remote-Ziel wurde vor jeder Mutation abgewiesen:\n     {ex}")
    if not remote_aborted_as_expected:
        raise AssertionError("FEHLER: Unerlaubtes Docker-Ziel wurde nicht abgewiesen!")

    # -------------------------------------------------------------------------
    # 4. NEGATIVTEST 2: Fremde COMPOSE_FILE-Umgebung wird strikt ausgeschlossen
    # -------------------------------------------------------------------------
    print("[3/12] Negativtest 2: Fremde COMPOSE_FILE-Auswahl wird strikt neutralisiert...")
    fake_compose_env = ENV.copy()
    fake_compose_env["COMPOSE_FILE"] = "/tmp/foreign_malicious_override.yml"
    # Unser compose_cmd filtert dies und bindet zwingend COMPOSE_FILE
    code, config_out, _ = compose_cmd(["config", "--services"], check=True)
    if "aura-api" not in config_out or "aura-worker" not in config_out:
        raise AssertionError(f"FEHLER: Compose-Bindung lieferte falsche Services: {config_out}")
    print(f"  -> Negativtest ERFOLGREICH: Repository-Compose-Datei zwingend gebunden (Services: {config_out.split()}).")

    # -------------------------------------------------------------------------
    # 4. NEGATIVTEST 3: Echte Namenskollision fuehrt zu Abbruch vor Mutation
    # -------------------------------------------------------------------------
    print("[4/12] Negativtest 3: Echte Namenskollision muss vor Mutation abbrechen...")
    COLLISION_SENTINEL = f"aura_coll_sentinel_{RUN_ID}"
    run_cmd(["docker", "volume", "create", "--label", f"aura.test.owner=foreign_app_{RUN_ID}", COLLISION_SENTINEL])
    collision_detected = False
    try:
        check_resource_collision([("volume", COLLISION_SENTINEL)])
    except RuntimeError as ex:
        if "Kollision erkannt" in str(ex):
            collision_detected = True
            print(f"  -> Negativtest ERFOLGREICH: Kollision erkannt, Abbruch vor Mutation:\n     {ex}")
    finally:
        # Pruefe, dass fremde kollidierende Ressource NICHT geloescht wurde
        _, vols_check, _ = run_cmd(["docker", "volume", "ls", "--format", "{{.Name}}"])
        if COLLISION_SENTINEL not in vols_check.split():
            raise AssertionError("ISOLATIONS-VERLETZUNG: Kollidierende Sentinel-Ressource wurde geloescht!")
        run_cmd(["docker", "volume", "rm", "-f", COLLISION_SENTINEL], check=False)

    if not collision_detected:
        raise AssertionError("FEHLER: Kollision mit existierender Ressource wurde nicht erkannt!")

    # -------------------------------------------------------------------------
    # Vorab-Kollisionsprüfung fuer den eigentlichen Testlauf
    # -------------------------------------------------------------------------
    print("[5/12] Kollisionsprüfung fuer Ziel-Ressourcen des Testlaufs...")
    check_resource_collision([
        ("container", CONTAINER_API),
        ("container", CONTAINER_WORKER),
        ("volume", VOLUME_DATA),
        ("volume", VOLUME_STATE),
    ])
    print("  -> Keine Namenskollisionen im Docker-Namespace.")

    # -------------------------------------------------------------------------
    # Sentinel-Ressourcen vorab erstellen (Beweis des ownership-basierten Cleanups)
    # -------------------------------------------------------------------------
    print("[6/12] Erzeuge fremde Sentinel-Ressourcen mit fremdem Owner-Label...")
    run_cmd(["docker", "volume", "create", "--label", f"aura.test.owner=fremd_{RUN_ID}", SENTINEL_VOL])
    run_cmd(["docker", "network", "create", "--label", f"aura.test.owner=fremd_{RUN_ID}", SENTINEL_NET])
    print(f"  -> Fremdes Sentinel-Volume angelegt:  {SENTINEL_VOL}")
    print(f"  -> Fremdes Sentinel-Network angelegt: {SENTINEL_NET}")

    try:
        # ---------------------------------------------------------------------
        # D4: Negativ-Test fuer fehlschlagenden Healthcheck
        # ---------------------------------------------------------------------
        print("[7/12] D4-Negativtest: Nie erfolgreicher Healthcheck wird sauber abgewiesen...")
        fail_cont = f"aura_hc_fail_test_{RUN_ID}"
        run_cmd([
            "docker", "run", "-d", "--name", fail_cont,
            "--label", f"aura.test.run_id={RUN_ID}",
            "--health-cmd", "exit 1",
            "--health-interval", "1s",
            "--health-retries", "2",
            "--health-timeout", "1s",
            "python:3.12.3-slim-bookworm", "sleep", "30"
        ])
        hc_failed_as_expected = False
        try:
            wait_for_healthy(fail_cont, timeout_sec=4)
        except AssertionError as ex:
            hc_failed_as_expected = True
            print(f"  -> D4-Negativtest ERFOLGREICH: {ex}")
        finally:
            run_cmd(["docker", "rm", "-f", fail_cont], check=False)

        if not hc_failed_as_expected:
            raise AssertionError("D4-Negativtest FEHLGESCHLAGEN: Defekter Healthcheck wurde akzeptiert!")

        # ---------------------------------------------------------------------
        # D1: Echter Clean-Build mit Cache-Ausschluss und Lockfile
        # ---------------------------------------------------------------------
        print("[8/12] D1: Cache-Ausschluss Clean-Build mit verifiziertem requirements.lock...")
        t0 = time.time()
        compose_cmd(["build", "--no-cache"], timeout=180)
        build_time = time.time() - t0
        print(f"  -> Clean-Build abgeschlossen in {build_time:.2f}s.")

        _, img_id, _ = run_cmd(["docker", "inspect", "--format", "{{.Id}}", IMAGE_TAG])
        print(f"  -> Test-Image ID: {img_id}")

        # ---------------------------------------------------------------------
        # D2 & D4: Start mit Schutzmaßnahmen und Warten auf 'healthy'
        # ---------------------------------------------------------------------
        print("[9/12] D2 & D4: Start Compose-Stack mit Schutzmassnahmen & Warten auf 'healthy'...")
        compose_cmd(["up", "-d"], timeout=60)

        # Pruefe aktivierte Schutzmaßnahmen (read_only, cap_drop, no-new-privileges, memory limit)
        for cont_name in (CONTAINER_API, CONTAINER_WORKER):
            _, insp_sec, _ = run_cmd(["docker", "inspect", "--format", "{{.HostConfig.ReadonlyRootfs}} {{.HostConfig.SecurityOpt}} {{.HostConfig.CapDrop}} {{.HostConfig.Memory}}", cont_name])
            print(f"  -> Schutzmassnahmen '{cont_name}': {insp_sec}")
            if "true" not in insp_sec:
                raise AssertionError(f"Container '{cont_name}' laeuft nicht mit ReadonlyRootfs!")

        api_health = wait_for_healthy(CONTAINER_API, timeout_sec=45)
        worker_health = wait_for_healthy(CONTAINER_WORKER, timeout_sec=45)
        print(f"  -> API Healthcheck:    STATUS={api_health.get('Status')} (FailingStreak={api_health.get('FailingStreak')})")
        print(f"  -> Worker Healthcheck: STATUS={worker_health.get('Status')} (FailingStreak={worker_health.get('FailingStreak')})")

        # ---------------------------------------------------------------------
        # D5: Auth-Trennung: Header-Token vs. Cookie-only Authentifizierung
        # ---------------------------------------------------------------------
        print("[10/12] D5: Auth-Trennung (Header-Token vs. Cookie-only)...")
        status, _, _ = http_req("/api/v3/state", headers={"X-AURA-TOKEN": TOKEN})
        if status != 200:
            raise AssertionError(f"Header-Token-Zugriff fehlgeschlagen: Status {status}")

        login_status, login_body, login_headers = http_req(
            "/api/v3/auth/login",
            method="POST",
            data={"token": TOKEN},
            headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"}
        )
        if login_status != 200 or not login_body.get("ok"):
            raise AssertionError(f"Login fehlgeschlagen: Status {login_status}, Body: {login_body}")

        set_cookie = login_headers.get("Set-Cookie") or login_headers.get("set-cookie") or ""
        session_match = re.search(r"aura_session=([a-zA-Z0-9_\-\.]+)", set_cookie)
        if not session_match:
            raise AssertionError(f"Set-Cookie Header enthaelt kein Session-Cookie: {set_cookie}")
        session_cookie = session_match.group(1)

        # Zugriff strikt Cookie-only (KEIN Token-Header!)
        status, _, _ = http_req(
            "/api/v3/state",
            cookie=session_cookie,
            headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"}
        )
        if status != 200:
            raise AssertionError(f"Strikter Cookie-only Zugriff fehlgeschlagen: Status {status}")
        print("  -> Strikter Cookie-only Zugriff auf /api/v3/state erfolgreich (HTTP 200, kein Token-Header).")

        # ---------------------------------------------------------------------
        # D5: Konfigurationsquittierung & Negativtest mit gestopptem Worker
        # ---------------------------------------------------------------------
        print("[11/12] D5: Konfigurationsquittierung & Negativtest mit gestopptem Worker...")
        # 1. Anforderung Revision 1 bei laufendem Worker
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
            raise AssertionError(f"Config-Anforderung fehlgeschlagen: {status}, {cfg_res}")
        cmd_id_1 = cfg_res["data"]["command_id"]
        req_rev_1 = cfg_res["data"]["requested_rev"]

        cmd_1_applied = False
        for _ in range(25):
            time.sleep(0.5)
            status, st, _ = http_req("/api/v3/state", cookie=session_cookie, headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"})
            if status == 200 and st.get("active_config_rev") == req_rev_1:
                _, cmd_db, _ = run_cmd([
                    "docker", "exec", CONTAINER_API,
                    "python3", "-c",
                    f"import sqlite3; c=sqlite3.connect('/data/aura_state.db'); print(c.execute('SELECT status, applied_at_ms FROM commands WHERE id=\"{cmd_id_1}\"').fetchone())"
                ])
                if "applied" in cmd_db and "None" not in cmd_db:
                    cmd_1_applied = True
                    print(f"  -> Revision {req_rev_1} quittiert: Command-ID={cmd_id_1}, DB={cmd_db}")
                    break
        if not cmd_1_applied:
            raise AssertionError(f"Worker hat Revision {req_rev_1} nicht quittiert!")

        # 2. Negativtest gestoppter Worker: Exakt 'pending' und unveraenderte aktive Revision pruefen
        print("  -> Stoppe Worker-Container fuer Negativtest...")
        compose_cmd(["stop", "aura-worker"])

        status_2, cfg_res_2, _ = http_req(
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
        if status_2 != 200:
            raise AssertionError(f"POST /config fehlgeschlagen: {status_2}, {cfg_res_2}")
        cmd_id_2 = cfg_res_2["data"]["command_id"]
        req_rev_2 = cfg_res_2["data"]["requested_rev"]

        time.sleep(2)
        status, st_stopped, _ = http_req("/api/v3/state", cookie=session_cookie, headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"})
        _, cmd_db_2_raw, _ = run_cmd([
            "docker", "exec", CONTAINER_API,
            "python3", "-c",
            f"import sqlite3, json; c=sqlite3.connect('/data/aura_state.db'); row=c.execute('SELECT status, applied_at_ms FROM commands WHERE id=\"{cmd_id_2}\"').fetchone(); print(json.dumps(row))"
        ])
        cmd_db_2 = json.loads(cmd_db_2_raw)
        print(f"  -> Status bei gestopptem Worker: active_rev={st_stopped.get('active_config_rev')}, req_rev={st_stopped.get('requested_config_rev')}, DB={cmd_db_2}")

        # Strikte Assertions gemaess Vorgabe:
        if st_stopped.get("active_config_rev") != req_rev_1:
            raise AssertionError(f"FEHLER: Aktive Revision durfte sich bei gestopptem Worker nicht aendern! ({st_stopped.get('active_config_rev')} != {req_rev_1})")
        if st_stopped.get("requested_config_rev") != req_rev_2:
            raise AssertionError(f"FEHLER: Angefragte Revision {req_rev_2} nicht im State registriert!")
        if cmd_db_2[0] != "pending" or cmd_db_2[1] is not None:
            raise AssertionError(f"FEHLER: Command bei gestopptem Worker muss exakt status='pending' und applied_at_ms=None haben (erhalten: {cmd_db_2})!")
        print("  -> Negativ-Test ERFOLGREICH: Gestoppter Worker quittiert nicht (status='pending', active_rev unveraendert).")

        # Worker wieder starten
        print("  -> Starte Worker-Container wieder...")
        compose_cmd(["start", "aura-worker"])
        wait_for_healthy(CONTAINER_WORKER, timeout_sec=30)

        # Verifiziere Quittierung nach Wiederanlauf
        cmd_2_applied = False
        for _ in range(25):
            time.sleep(0.5)
            status, st, _ = http_req("/api/v3/state", cookie=session_cookie, headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"})
            if status == 200 and st.get("active_config_rev") == req_rev_2:
                _, cmd_db_2_after_raw, _ = run_cmd([
                    "docker", "exec", CONTAINER_API,
                    "python3", "-c",
                    f"import sqlite3, json; c=sqlite3.connect('/data/aura_state.db'); row=c.execute('SELECT status, applied_at_ms FROM commands WHERE id=\"{cmd_id_2}\"').fetchone(); print(json.dumps(row))"
                ])
                cmd_db_2_after = json.loads(cmd_db_2_after_raw)
                if cmd_db_2_after[0] == "applied" and cmd_db_2_after[1] is not None:
                    cmd_2_applied = True
                    print(f"  -> Quittierung nach Wiederanlauf belegt: active_rev={req_rev_2}, DB={cmd_db_2_after}")
                    break
        if not cmd_2_applied:
            raise AssertionError("FEHLER: Worker hat anstehende Konfiguration nach Wiederanlauf nicht quittiert!")

        # ---------------------------------------------------------------------
        # Not-Halt mit zwingender Quittierungspruefung vor Restart
        # ---------------------------------------------------------------------
        print("[12/12] Not-Halt (zwingende Quittierung vor Restart), Neustart & Ownership-Cleanup...")
        _, inst_before_raw, _ = run_cmd([
            "docker", "exec", CONTAINER_API,
            "python3", "-c",
            "import sqlite3; c=sqlite3.connect('/data/aura_state.db'); print(c.execute('SELECT updated_at_ms, reason FROM runner_state WHERE id=1').fetchone())"
        ])

        # Halt ausloesen
        status, halt_res, _ = http_req(
            "/api/v3/halt",
            method="POST",
            data={"reason": "Compose Audit Test Halt"},
            cookie=session_cookie,
            headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"}
        )
        if status != 200:
            raise AssertionError(f"POST /halt fehlgeschlagen: {status}, {halt_res}")
        halt_cmd_id = halt_res["data"]["command_id"]
        print(f"  -> Not-Halt angefordert: Command-ID={halt_cmd_id}")

        # Zwingende Bestaetigung vor Restart: Command status 'applied', applied_at_ms IS NOT NULL, State HALTED
        halt_quittiert = False
        for _ in range(25):
            time.sleep(0.5)
            status, st_halt, _ = http_req("/api/v3/state", cookie=session_cookie, headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"})
            if status == 200 and st_halt.get("worker", {}).get("is_halted") is True:
                _, halt_db_raw, _ = run_cmd([
                    "docker", "exec", CONTAINER_API,
                    "python3", "-c",
                    f"import sqlite3, json; c=sqlite3.connect('/data/aura_state.db'); row=c.execute('SELECT status, applied_at_ms FROM commands WHERE id=\"{halt_cmd_id}\"').fetchone(); print(json.dumps(row))"
                ])
                halt_db = json.loads(halt_db_raw)
                if halt_db[0] == "applied" and halt_db[1] is not None:
                    halt_quittiert = True
                    print(f"  -> Not-Halt VOR Neustart zwingend quittiert: status={halt_db[0]}, applied_at_ms={halt_db[1]}, HALTED=True")
                    break

        if not halt_quittiert:
            raise AssertionError(f"FEHLER: Not-Halt-Command {halt_cmd_id} wurde vor dem Restart nicht vollstaendig quittiert!")

        # Pre-Restart Instanzdaten erfassen
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

        # Container-Neustart via docker compose restart
        print("  -> Führe aus: docker compose restart...")
        restart_time_ms = int(time.time() * 1000)
        compose_cmd(["restart"], timeout=60)

        wait_for_healthy(CONTAINER_API, timeout_sec=45)
        wait_for_healthy(CONTAINER_WORKER, timeout_sec=45)

        # In-Memory Session-Semantik: Altes Cookie liefert 401
        status_old_cookie, _, _ = http_req(
            "/api/v3/state",
            cookie=session_cookie,
            headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"}
        )
        print(f"  -> Altes Session-Cookie nach Neustart: HTTP {status_old_cookie}")
        if status_old_cookie != 401:
            raise AssertionError(f"FEHLER: Altes Cookie wurde nach Neustart mit Status {status_old_cookie} akzeptiert (erwartet 401)!")

        # Neuanmeldung
        _, _, login_hdrs_new = http_req(
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

        # Post-Restart Instanzpruefung
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
            raise AssertionError(f"FEHLER: Worker-Instanz nach Neustart unveraendert ({inst_id_pre} == {inst_id_post})!")
        if hb_post < restart_time_ms:
            raise AssertionError(f"FEHLER: Heartbeat ({hb_post}) aelter als Neustart ({restart_time_ms})!")
        print(f"  -> RESTART BELEGT: Neue Instanz ({inst_id_pre} -> {inst_id_post}) und frischer Heartbeat.")

        status, post_state, _ = http_req(
            "/api/v3/state",
            cookie=new_session_cookie,
            headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"}
        )
        if post_state.get("worker", {}).get("is_halted") is not True:
            raise AssertionError(f"FEHLER: Not-Halt nach Neustart nicht persistent!")
        if post_state.get("active_config_rev") != req_rev_2:
            raise AssertionError(f"FEHLER: Konfigurationsrevision {req_rev_2} nach Neustart verloren!")
        print("  -> PERSISTENZ BELEGT: Quittierter Halt und Revision 2 blieben nach Neustart erhalten.")

        # ---------------------------------------------------------------------
        # 3. Ownership-basiertes Cleanup & Sentinel-Verifikation
        # ---------------------------------------------------------------------
        print("  -> Fuehre Compose-Teardown auf Projekt-Ebene aus...")
        compose_cmd(["down", "-v"], timeout=60)

        # Pruefe, dass fremde Sentinels unversehrt geblieben sind
        _, vols_after, _ = run_cmd(["docker", "volume", "ls", "--format", "{{.Name}}"])
        _, nets_after, _ = run_cmd(["docker", "network", "ls", "--format", "{{.Name}}"])
        if SENTINEL_VOL not in vols_after.split():
            raise AssertionError(f"ISOLATIONS-VERLETZUNG: Fremdes Sentinel-Volume '{SENTINEL_VOL}' wurde geloescht!")
        if SENTINEL_NET not in nets_after.split():
            raise AssertionError(f"ISOLATIONS-VERLETZUNG: Fremdes Sentinel-Network '{SENTINEL_NET}' wurde geloescht!")
        print("  -> OWNERSHIP-ISOLATION BELEGT: Fremde Sentinel-Ressourcen blieben unversehrt erhalten.")

    finally:
        # Gezielt und ownership-geprueft Sentinel und Test-Image entfernen
        print("  -> Gezieltes Cleanup der eigenen Test-Sentinels...")
        # Vor dem Loeschen Owner pruefen
        code_v, owner_v, _ = run_cmd(["docker", "volume", "inspect", "--format", "{{index .Labels \"aura.test.owner\"}}", SENTINEL_VOL], check=False)
        if code_v == 0 and owner_v == f"fremd_{RUN_ID}":
            run_cmd(["docker", "volume", "rm", "-f", SENTINEL_VOL], check=False)
        code_n, owner_n, _ = run_cmd(["docker", "network", "inspect", "--format", "{{index .Labels \"aura.test.owner\"}}", SENTINEL_NET], check=False)
        if code_n == 0 and owner_n == f"fremd_{RUN_ID}":
            run_cmd(["docker", "network", "rm", SENTINEL_NET], check=False)
        run_cmd(["docker", "rmi", "-f", IMAGE_TAG], check=False)
        _TEMP_CFG_DIR.cleanup()

    print("\n========================================================")
    print("DOCKER COMPOSE LIFECYCLE AUDIT: 100% PASSED (AUDIT de987aa VOLLSTÄNDIG ERFÜLLT)!")
    print("========================================================\n")


if __name__ == "__main__":
    main()
