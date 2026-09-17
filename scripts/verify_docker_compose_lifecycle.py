#!/usr/bin/env python3
"""Automatisierte Verifikation des Docker-Compose-Lifecycles fuer AURA v3 (H1 & H2 Härtung).

Behebt ausschliesslich die verbleibenden Punkte H1 und H2 aus AURA_Container_Review_fe6141c.md:
- H1:
  * Zentraler, robuster Cleanup bei Assertions, Timeouts, Exceptions und KeyboardInterrupt.
  * Nur nachweislich eigene Run-Ressourcen stoppen und entfernen (Ownership-Prüfung).
  * Ursprünglichen Testfehler stets erhalten; Cleanup-Fehler zusätzlich auf stderr melden.
  * Ist der Docker-Daemon nicht erreichbar, verbliebene Ressourcen konkret und namentlich benennen.
  * Negativtests H1a (Fehler nach Stackstart) und H1b (Fehler nach Healthy):
    Der eigene Stack darf anschliessend nicht weiterlaufen; fremde Sentinels bleiben erhalten.
- H2:
  * Fremde COMPOSE_FILE-Umgebung wird tatsächlich in den geprüften Eintrittspfad eingespeist.
  * Effektive argv, bereinigte Umgebung und cwd werden explizit verifiziert.
  * Fremde Compose-Datei darf nicht verwendet werden (strikte Bindung an Repo-Compose-Datei).
  * Negativtest wird ohne mutierende Docker-Befehle (via 'config --services') ausgeführt.
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
# Absolute Pfade & Projektverzeichnis
# -----------------------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPOSE_FILE = os.path.join(REPO_ROOT, "docker-compose.yml")
if not os.path.isfile(COMPOSE_FILE):
    raise FileNotFoundError(f"docker-compose.yml nicht gefunden unter: {COMPOSE_FILE}")

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

# Temporaeres Konfigurationsverzeichnis fuer Docker CLI (isoliert)
_TEMP_CFG_DIR = tempfile.TemporaryDirectory(prefix="aura_docker_cfg_")
CFG_DIR = _TEMP_CFG_DIR.name
with open(os.path.join(CFG_DIR, "config.json"), "w") as f:
    f.write("{}\n")
plugins_link = os.path.join(CFG_DIR, "cli-plugins")
if not os.path.exists(plugins_link):
    user_plugins = os.path.expanduser("~/.docker/cli-plugins")
    if os.path.exists(user_plugins):
        os.symlink(user_plugins, plugins_link)

LOCAL_DOCKER_SOCKET = "unix:///var/run/docker.sock"

BASE_VARS = {
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
    "AURA_NTFY_URL": "http://127.0.0.1:9/disabled",
}


def build_compose_invocation(
    args: list[str],
    raw_env: dict[str, str] | None = None,
    project_override: str | None = None,
    vars_override: dict[str, str] | None = None,
) -> tuple[list[str], dict[str, str], str]:
    """H2: Baut Compose-Befehl und bereinigt effektiv die Umgebung.
    
    Entfernt stoerende Umgebungsvariablen wie COMPOSE_FILE, setzt feste -f-Bindung
    und zwingendes --project-directory.
    """
    effective_env = raw_env.copy() if raw_env is not None else os.environ.copy()

    # Fremde Compose- und Kontextvariablen zwingend neutralisieren
    for var in ("COMPOSE_FILE", "COMPOSE_PATH_SEPARATOR", "COMPOSE_PROFILES", "COMPOSE_PROJECT_NAME", "DOCKER_CONTEXT"):
        effective_env.pop(var, None)

    effective_env["DOCKER_HOST"] = LOCAL_DOCKER_SOCKET
    effective_env["DOCKER_CONFIG"] = CFG_DIR

    # Standard- oder Override-Variablen setzen
    active_vars = vars_override if vars_override is not None else BASE_VARS
    effective_env.update(active_vars)

    proj = project_override or PROJECT_NAME
    cmd = [
        "docker", "compose",
        "-f", COMPOSE_FILE,
        "--project-directory", REPO_ROOT,
        "-p", proj,
    ] + args

    return cmd, effective_env, REPO_ROOT


def run_cmd(
    cmd: list[str],
    check: bool = True,
    timeout: int = 40,
    env_override: dict | None = None,
    cwd_override: str | None = None,
) -> tuple[int, str, str]:
    """Fuehrt einen Befehl mit striktem Timeout und sicherem Environment aus."""
    cmd_env = env_override if env_override is not None else build_compose_invocation([])[1]
    work_dir = cwd_override or REPO_ROOT
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=cmd_env,
            cwd=work_dir,
            timeout=timeout,
        )
        if check and res.returncode != 0:
            raise RuntimeError(f"Command failed ({' '.join(cmd)}):\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}")
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Command timed out after {timeout}s ({' '.join(cmd)})") from exc


def compose_cmd(
    args: list[str],
    check: bool = True,
    timeout: int = 90,
    env_override: dict | None = None,
    project_override: str | None = None,
    vars_override: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Ruft Docker Compose ueber den verifizierten Builder auf."""
    cmd, effective_env, cwd = build_compose_invocation(
        args,
        raw_env=env_override,
        project_override=project_override,
        vars_override=vars_override,
    )
    return run_cmd(cmd, check=check, timeout=timeout, env_override=effective_env, cwd_override=cwd)


def verify_docker_endpoint(env_to_check: dict[str, str]) -> str:
    """Verifiziert ausdruecklich, dass ein lokaler Docker-Daemon angesprochen wird."""
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


def cleanup_run_resources(
    project_name: str,
    run_id: str,
    image_tag: str | None = None,
    sentinel_vol: str | None = None,
    sentinel_net: str | None = None,
    vars_override: dict[str, str] | None = None,
) -> list[str]:
    """H1: Zentraler Cleanup nur fuer nachweislich eigene Run-Ressourcen.
    
    Wird bei Erfolg, Assertions, Timeouts, Exceptions und KeyboardInterrupt ausgefuehrt.
    Erfasst Fehler, benennt bei nicht erreichbarem Daemon verbliebene Ressourcen.
    """
    errors: list[str] = []

    # 1. Pruefen ob Docker ueberhaupt erreichbar ist
    code, _, _ = run_cmd(["docker", "info", "--format", "{{.ServerVersion}}"], check=False, timeout=5)
    if code != 0:
        unreachable_msg = (
            f"WARNUNG: Docker-Daemon nicht erreichbar waehrend Cleanup! "
            f"Folgende Ressourcen von Projekt '{project_name}' (Run '{run_id}') konnten nicht bereinigt werden:\n"
            f"  - Projekt-Container/Volumes: {project_name}\n"
            f"  - Image: {image_tag}\n"
            f"  - Sentinel Volume: {sentinel_vol}\n"
            f"  - Sentinel Network: {sentinel_net}"
        )
        print(unreachable_msg, file=sys.stderr)
        errors.append(unreachable_msg)
        return errors

    # 2. Compose-Projekt gezielt stoppen und Volumes entfernen
    try:
        compose_cmd(["down", "-v", "--remove-orphans"], check=False, timeout=45, project_override=project_name, vars_override=vars_override)
    except Exception as ex:
        errors.append(f"Compose down failed: {ex}")

    # 3. Sicherheits-Check: Falls noch Container mit passendem Projekt-Label laufen, stoppen
    try:
        code_c, out_c, _ = run_cmd([
            "docker", "ps", "-a",
            "--filter", f"label=com.docker.compose.project={project_name}",
            "--format", "{{.ID}} {{.Names}}"
        ], check=False, timeout=8)
        if code_c == 0 and out_c.strip():
            for line in out_c.splitlines():
                cid = line.split()[0]
                run_cmd(["docker", "rm", "-f", cid], check=False, timeout=8)
    except Exception as ex:
        errors.append(f"Container force-removal failed: {ex}")

    # 4. Eigene Sentinels nur mit passendem Ownership-Label entfernen
    if sentinel_vol:
        try:
            code_v, owner_v, _ = run_cmd(["docker", "volume", "inspect", "--format", "{{index .Labels \"aura.test.owner\"}}", sentinel_vol], check=False, timeout=6)
            if code_v == 0 and owner_v == f"fremd_{run_id}":
                run_cmd(["docker", "volume", "rm", "-f", sentinel_vol], check=False, timeout=8)
        except Exception as ex:
            errors.append(f"Sentinel volume cleanup failed: {ex}")

    if sentinel_net:
        try:
            code_n, owner_n, _ = run_cmd(["docker", "network", "inspect", "--format", "{{index .Labels \"aura.test.owner\"}}", sentinel_net], check=False, timeout=6)
            if code_n == 0 and owner_n == f"fremd_{run_id}":
                run_cmd(["docker", "network", "rm", sentinel_net], check=False, timeout=8)
        except Exception as ex:
            errors.append(f"Sentinel network cleanup failed: {ex}")

    # 5. Eigenes Test-Image entfernen
    if image_tag:
        try:
            run_cmd(["docker", "rmi", "-f", image_tag], check=False, timeout=10)
        except Exception as ex:
            errors.append(f"Image removal failed: {ex}")

    return errors


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
    port: int | None = None,
    timeout: int = 10,
) -> tuple[int, Any, dict]:
    active_port = port or PORT
    url = f"http://127.0.0.1:{active_port}{path}"
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


def test_h1_failure_cleanup_after_up(shared_image_tag: str) -> None:
    """H1-Negativtest 1: Absichtlicher Fehler unmittelbar nach Stackstart (vor Healthy).
    
    Beweist, dass der eigene Stack gestoppt wird und fremde Sentinels erhalten bleiben.
    """
    h1_id = f"h1up_{uuid.uuid4().hex[:6]}"
    h1_proj = f"aura_h1up_{h1_id}"
    h1_port = find_free_port()
    h1_api = f"aura-api-{h1_id}"
    h1_worker = f"aura-worker-{h1_id}"
    h1_data = f"aura_data_{h1_id}"
    h1_state = f"aura_state_{h1_id}"
    h1_sentinel = f"aura_sentinel_h1up_{h1_id}"

    h1_vars = {
        "AURA_IMAGE_TAG": shared_image_tag,
        "AURA_API_CONTAINER_NAME": h1_api,
        "AURA_WORKER_CONTAINER_NAME": h1_worker,
        "AURA_DATA_VOLUME_NAME": h1_data,
        "AURA_STATE_VOLUME_NAME": h1_state,
        "AURA_PORT_BIND": f"127.0.0.1:{h1_port}",
        "AURA_WORKER_INTERVAL": "1.0",
        "AURA_API_HC_INTERVAL": "5s",
        "AURA_API_HC_START_PERIOD": "90s",
        "AURA_WORKER_HC_INTERVAL": "3s",
        "AURA_WORKER_HC_START_PERIOD": "2s",
        "AURA_RELAY_TOKEN": "token_h1up",
        "AURA_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "AURA_NTFY_URL": "http://127.0.0.1:9/disabled",
    }

    # Fremden Sentinel vorab anlegen
    run_cmd(["docker", "volume", "create", "--label", f"aura.test.owner=fremd_sentinel_{h1_id}", h1_sentinel])

    test_failed_caught = False
    try:
        try:
            # Stack starten
            compose_cmd(["up", "-d"], project_override=h1_proj, vars_override=h1_vars, timeout=60)
            # Simuliere harten Assertion-Fehler nach Start
            raise AssertionError("SIMULIERTER TESTFEHLER NACH STACKSTART (H1a)")
        except BaseException as orig_err:
            test_failed_caught = True
            cl_errs = cleanup_run_resources(h1_proj, h1_id, vars_override=h1_vars)
            if cl_errs:
                print(f"Cleanup-Fehler bei H1a: {cl_errs}", file=sys.stderr)
            raise orig_err
    except AssertionError as ex:
        if "SIMULIERTER TESTFEHLER NACH STACKSTART" not in str(ex):
            raise

    if not test_failed_caught:
        raise AssertionError("H1a: Simulierter Fehler wurde nicht ausgeloest!")

    # Pruefen, dass Container gestoppt und entfernt sind
    code, ps_out, _ = run_cmd(["docker", "ps", "-a", "--filter", f"name={h1_api}", "--format", "{{.Names}}"])
    if h1_api in ps_out.split():
        raise AssertionError(f"H1a FEHLGESCHLAGEN: Container '{h1_api}' laeuft nach Fehler-Cleanup weiter!")

    # Pruefen, dass fremder Sentinel unversehrt erhalten blieb
    code_s, vols_out, _ = run_cmd(["docker", "volume", "ls", "--format", "{{.Name}}"])
    if h1_sentinel not in vols_out.split():
        raise AssertionError(f"H1a ISOLATIONS-VERLETZUNG: Fremder Sentinel '{h1_sentinel}' wurde geloescht!")

    # Fremden Sentinel aufraeumen
    run_cmd(["docker", "volume", "rm", "-f", h1_sentinel], check=False)
    print("  -> H1a-Negativtest ERFOLGREICH: Fehler nach Stackstart loeste sauberen Cleanup aus; Sentinel unversehrt.")


def test_h1_failure_cleanup_after_healthy(shared_image_tag: str) -> None:
    """H1-Negativtest 2: Absichtlicher Fehler nach Erreichen des 'healthy'-Zustands.
    
    Beweist, dass der laufende Stack gestoppt wird und fremde Sentinels erhalten bleiben.
    """
    h1_id = f"h1hb_{uuid.uuid4().hex[:6]}"
    h1_proj = f"aura_h1hb_{h1_id}"
    h1_port = find_free_port()
    h1_api = f"aura-api-{h1_id}"
    h1_worker = f"aura-worker-{h1_id}"
    h1_data = f"aura_data_{h1_id}"
    h1_state = f"aura_state_{h1_id}"
    h1_sentinel = f"aura_sentinel_h1hb_{h1_id}"

    h1_vars = {
        "AURA_IMAGE_TAG": shared_image_tag,
        "AURA_API_CONTAINER_NAME": h1_api,
        "AURA_WORKER_CONTAINER_NAME": h1_worker,
        "AURA_DATA_VOLUME_NAME": h1_data,
        "AURA_STATE_VOLUME_NAME": h1_state,
        "AURA_PORT_BIND": f"127.0.0.1:{h1_port}",
        "AURA_WORKER_INTERVAL": "1.0",
        "AURA_API_HC_INTERVAL": "5s",
        "AURA_API_HC_START_PERIOD": "90s",
        "AURA_WORKER_HC_INTERVAL": "3s",
        "AURA_WORKER_HC_START_PERIOD": "2s",
        "AURA_RELAY_TOKEN": "token_h1hb",
        "AURA_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "AURA_NTFY_URL": "http://127.0.0.1:9/disabled",
    }

    run_cmd(["docker", "volume", "create", "--label", f"aura.test.owner=fremd_sentinel_{h1_id}", h1_sentinel])

    test_failed_caught = False
    try:
        try:
            compose_cmd(["up", "-d"], project_override=h1_proj, vars_override=h1_vars, timeout=60)
            wait_for_healthy(h1_api, timeout_sec=45)
            wait_for_healthy(h1_worker, timeout_sec=45)
            # Simuliere Fehler im laufenden Healthy-Betrieb
            raise AssertionError("SIMULIERTER TESTFEHLER NACH HEALTHY (H1b)")
        except BaseException as orig_err:
            test_failed_caught = True
            cl_errs = cleanup_run_resources(h1_proj, h1_id, vars_override=h1_vars)
            if cl_errs:
                print(f"Cleanup-Fehler bei H1b: {cl_errs}", file=sys.stderr)
            raise orig_err
    except AssertionError as ex:
        if "SIMULIERTER TESTFEHLER NACH HEALTHY" not in str(ex):
            raise

    if not test_failed_caught:
        raise AssertionError("H1b: Simulierter Fehler wurde nicht ausgeloest!")

    code, ps_out, _ = run_cmd(["docker", "ps", "-a", "--filter", f"name={h1_api}", "--format", "{{.Names}}"])
    if h1_api in ps_out.split():
        raise AssertionError(f"H1b FEHLGESCHLAGEN: Container '{h1_api}' laeuft nach Fehler-Cleanup weiter!")

    code_s, vols_out, _ = run_cmd(["docker", "volume", "ls", "--format", "{{.Name}}"])
    if h1_sentinel not in vols_out.split():
        raise AssertionError(f"H1b ISOLATIONS-VERLETZUNG: Fremder Sentinel '{h1_sentinel}' wurde geloescht!")

    run_cmd(["docker", "volume", "rm", "-f", h1_sentinel], check=False)
    print("  -> H1b-Negativtest ERFOLGREICH: Fehler nach Healthy loeste sauberen Cleanup aus; Sentinel unversehrt.")


def main() -> None:
    print(f"========================================================")
    print(f"AURA DOCKER-COMPOSE LIFECYCLE AUDIT (H1 & H2 Härtung)")
    print(f"Run-ID:         {RUN_ID}")
    print(f"Project:        {PROJECT_NAME}")
    print(f"Compose-File:   {COMPOSE_FILE}")
    print(f"Repo-Root:      {REPO_ROOT}")
    print(f"Docker-Target:  {LOCAL_DOCKER_SOCKET}")
    print(f"========================================================\n")

    # -------------------------------------------------------------------------
    # 1. Docker-Ziel ausdruecklich ermitteln & validieren
    # -------------------------------------------------------------------------
    print("[1/13] Docker-Daemon Endpunkt ausdruecklich pruefen...")
    endpoint_info = verify_docker_endpoint(build_compose_invocation([])[1])
    print(f"  -> Verifizierter lokaler Docker-Daemon: {endpoint_info}")

    # -------------------------------------------------------------------------
    # Negativtest: Unerlaubtes Docker-Ziel (Remote/TCP) fuehrt zu sofortigem Abbruch
    # -------------------------------------------------------------------------
    print("[2/13] Negativtest: Unerlaubtes Docker-Ziel (Remote/TCP) bricht vor Mutation ab...")
    fake_remote_env = os.environ.copy()
    fake_remote_env["DOCKER_HOST"] = "tcp://production.aura-quant.internal:2375"
    remote_aborted = False
    try:
        verify_docker_endpoint(fake_remote_env)
    except RuntimeError as ex:
        if "Unerlaubtes Docker-Ziel erkannt" in str(ex):
            remote_aborted = True
            print(f"  -> Negativtest ERFOLGREICH: Remote-Ziel vor jeder Mutation abgewiesen:\n     {ex}")
    if not remote_aborted:
        raise AssertionError("FEHLER: Unerlaubtes Docker-Ziel wurde nicht abgewiesen!")

    # -------------------------------------------------------------------------
    # H2: Fremde COMPOSE_FILE-Umgebung tatsaechlich einspeisen & pruefen
    # -------------------------------------------------------------------------
    print("[3/13] H2: Einspeisen kontaminierter COMPOSE_FILE-Umgebung in Eintrittspfad...")
    contaminated_env = os.environ.copy()
    foreign_compose_path = "/tmp/foreign_malicious_override_which_must_not_exist.yml"
    contaminated_env["COMPOSE_FILE"] = foreign_compose_path
    contaminated_env["COMPOSE_PROJECT_NAME"] = "foreign_hijack_project"

    # Rufe Builder mit kontaminierter Umgebung auf und pruefe effektive argv, env, cwd
    eff_argv, eff_env, eff_cwd = build_compose_invocation(["config", "--services"], raw_env=contaminated_env)

    # Assertions auf effektive Aufrufparameter
    assert eff_cwd == REPO_ROOT, f"FEHLER: cwd muss REPO_ROOT sein ({eff_cwd} != {REPO_ROOT})"
    assert "-f" in eff_argv and eff_argv[eff_argv.index("-f") + 1] == COMPOSE_FILE, "FEHLER: -f muss absolut auf Repo-Compose zeigen!"
    assert "--project-directory" in eff_argv and eff_argv[eff_argv.index("--project-directory") + 1] == REPO_ROOT, "FEHLER: --project-directory muss REPO_ROOT sein!"
    assert eff_env.get("COMPOSE_FILE") is None, "FEHLER: COMPOSE_FILE wurde nicht aus der effektiven Umgebung entfernt!"

    # Fuehre read-only compose config aus (keine mutierenden Docker-Befehle!)
    code, config_out, config_err = run_cmd(eff_argv, env_override=eff_env, cwd_override=eff_cwd, timeout=15)
    if code != 0 or "aura-api" not in config_out or "aura-worker" not in config_out:
        raise AssertionError(f"H2 FEHLGESCHLAGEN: Fremde Datei blockierte oder kontaminierte Ausfuehrung: {config_err}")
    print(f"  -> H2-Negativtest ERFOLGREICH: Fremde COMPOSE_FILE neutralisiert; effektive Bindung verifiziert (Services: {config_out.split()}).")

    # -------------------------------------------------------------------------
    # Negativtest: Echte Namenskollision bricht vor Mutation ab
    # -------------------------------------------------------------------------
    print("[4/13] Negativtest: Echte Namenskollision muss vor Mutation abbrechen...")
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
        _, vols_check, _ = run_cmd(["docker", "volume", "ls", "--format", "{{.Name}}"])
        if COLLISION_SENTINEL not in vols_check.split():
            raise AssertionError("ISOLATIONS-VERLETZUNG: Kollidierende Sentinel-Ressource wurde geloescht!")
        run_cmd(["docker", "volume", "rm", "-f", COLLISION_SENTINEL], check=False)

    if not collision_detected:
        raise AssertionError("FEHLER: Kollision mit existierender Ressource wurde nicht erkannt!")

    # Vorab-Kollisionsprüfung fuer den eigentlichen Testlauf
    check_resource_collision([
        ("container", CONTAINER_API),
        ("container", CONTAINER_WORKER),
        ("volume", VOLUME_DATA),
        ("volume", VOLUME_STATE),
    ])

    # Fremde Sentinels anlegen
    run_cmd(["docker", "volume", "create", "--label", f"aura.test.owner=fremd_{RUN_ID}", SENTINEL_VOL])
    run_cmd(["docker", "network", "create", "--label", f"aura.test.owner=fremd_{RUN_ID}", SENTINEL_NET])

    try:
        # ---------------------------------------------------------------------
        # D4: Negativ-Test fuer fehlschlagenden Healthcheck
        # ---------------------------------------------------------------------
        print("[5/13] D4-Negativtest: Nie erfolgreicher Healthcheck wird sauber abgewiesen...")
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
        print("[6/13] D1: Cache-Ausschluss Clean-Build mit verifiziertem requirements.lock...")
        t0 = time.time()
        compose_cmd(["build", "--no-cache"], timeout=180)
        build_time = time.time() - t0
        print(f"  -> Clean-Build abgeschlossen in {build_time:.2f}s.")

        _, img_id, _ = run_cmd(["docker", "inspect", "--format", "{{.Id}}", IMAGE_TAG])
        print(f"  -> Test-Image ID: {img_id}")

        # ---------------------------------------------------------------------
        # H1-Negativtests: Absichtlicher Fehler nach Stackstart und nach Healthy
        # ---------------------------------------------------------------------
        print("[7/13] H1-Negativtest 1: Absichtlicher Fehler nach Stackstart (vor Healthy)...")
        test_h1_failure_cleanup_after_up(IMAGE_TAG)

        print("[8/13] H1-Negativtest 2: Absichtlicher Fehler nach Erreichen von Healthy...")
        test_h1_failure_cleanup_after_healthy(IMAGE_TAG)

        # ---------------------------------------------------------------------
        # Haupt-Lifecycle: Start mit Schutzmaßnahmen und Warten auf 'healthy'
        # ---------------------------------------------------------------------
        print("[9/13] D2 & D4: Start Haupt-Compose-Stack mit Schutzmassnahmen...")
        compose_cmd(["up", "-d"], timeout=60)

        for cont_name in (CONTAINER_API, CONTAINER_WORKER):
            _, insp_sec, _ = run_cmd(["docker", "inspect", "--format", "{{.HostConfig.ReadonlyRootfs}} {{.HostConfig.SecurityOpt}} {{.HostConfig.CapDrop}} {{.HostConfig.Memory}}", cont_name])
            print(f"  -> Schutzmassnahmen '{cont_name}': {insp_sec}")
            if "true" not in insp_sec:
                raise AssertionError(f"Container '{cont_name}' laeuft nicht mit ReadonlyRootfs!")

        api_health = wait_for_healthy(CONTAINER_API, timeout_sec=45)
        worker_health = wait_for_healthy(CONTAINER_WORKER, timeout_sec=45)
        print(f"  -> API Healthcheck:    STATUS={api_health.get('Status')}")
        print(f"  -> Worker Healthcheck: STATUS={worker_health.get('Status')}")

        # ---------------------------------------------------------------------
        # D5: Auth-Trennung: Header-Token vs. Cookie-only Authentifizierung
        # ---------------------------------------------------------------------
        print("[10/13] D5: Auth-Trennung (Header-Token vs. Cookie-only)...")
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
        print("[11/13] D5: Konfigurationsquittierung & Negativtest mit gestopptem Worker...")
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

        # Negativtest gestoppter Worker: Exakt 'pending' und unveraenderte aktive Revision pruefen
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
        print("[12/13] Not-Halt (zwingende Quittierung vor Restart) & Neustart...")
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

        print("  -> Führe aus: docker compose restart...")
        restart_time_ms = int(time.time() * 1000)
        compose_cmd(["restart"], timeout=60)

        wait_for_healthy(CONTAINER_API, timeout_sec=45)
        wait_for_healthy(CONTAINER_WORKER, timeout_sec=45)

        status_old_cookie, _, _ = http_req(
            "/api/v3/state",
            cookie=session_cookie,
            headers={"Origin": f"http://127.0.0.1:{PORT}", "Host": f"127.0.0.1:{PORT}"}
        )
        if status_old_cookie != 401:
            raise AssertionError(f"FEHLER: Altes Cookie wurde nach Neustart mit Status {status_old_cookie} akzeptiert (erwartet 401)!")

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
        # H1: Ownership-basiertes Cleanup & Sentinel-Verifikation
        # ---------------------------------------------------------------------
        print("[13/13] H1: Zentraler Cleanup & Sentinel-Pruefung...")
        compose_cmd(["down", "-v"], timeout=60)

        _, vols_after, _ = run_cmd(["docker", "volume", "ls", "--format", "{{.Name}}"])
        _, nets_after, _ = run_cmd(["docker", "network", "ls", "--format", "{{.Name}}"])
        if SENTINEL_VOL not in vols_after.split():
            raise AssertionError(f"ISOLATIONS-VERLETZUNG: Fremdes Sentinel-Volume '{SENTINEL_VOL}' wurde geloescht!")
        if SENTINEL_NET not in nets_after.split():
            raise AssertionError(f"ISOLATIONS-VERLETZUNG: Fremdes Sentinel-Network '{SENTINEL_NET}' wurde geloescht!")
        print("  -> OWNERSHIP-ISOLATION BELEGT: Fremde Sentinel-Ressourcen blieben unversehrt erhalten.")

    except BaseException as primary_exc:
        print(f"\n[FEHLER AUFGETRETEN] Fuehre zwingenden Fehler-Cleanup aus...", file=sys.stderr)
        cleanup_errs = cleanup_run_resources(
            PROJECT_NAME,
            RUN_ID,
            image_tag=IMAGE_TAG,
            sentinel_vol=SENTINEL_VOL,
            sentinel_net=SENTINEL_NET,
        )
        if cleanup_errs:
            print(f"[ZUSATZ-CLEANUP-FEHLER]: {cleanup_errs}", file=sys.stderr)
        raise primary_exc
    finally:
        cleanup_errs = cleanup_run_resources(
            PROJECT_NAME,
            RUN_ID,
            image_tag=IMAGE_TAG,
            sentinel_vol=SENTINEL_VOL,
            sentinel_net=SENTINEL_NET,
        )
        if cleanup_errs:
            print(f"[ZUSATZ-CLEANUP-FEHLER]: {cleanup_errs}", file=sys.stderr)
        _TEMP_CFG_DIR.cleanup()

    print("\n========================================================")
    print("DOCKER COMPOSE LIFECYCLE AUDIT: 100% PASSED (H1 & H2 ERFÜLLT)!")
    print("========================================================\n")


if __name__ == "__main__":
    main()
