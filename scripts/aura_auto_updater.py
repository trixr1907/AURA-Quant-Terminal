#!/usr/bin/env python3
"""
aura_auto_updater.py — Automated Continuous Deployment for AURA Quant Terminal
=============================================================================
Runs on Docker Host / VM 201 as a systemd service or background daemon.
Polls GitHub Releases API and automatically updates the Docker container
whenever a new version is published. Zero open ports required.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

REPO = os.environ.get("AURA_REPO", "trixr1907/AURA-Quant-Terminal")
CHECK_INTERVAL_SEC = int(os.environ.get("AURA_UPDATE_INTERVAL", "60"))
APP_DIR = os.environ.get("AURA_APP_DIR", "/opt/aura-terminal")
CONTAINER_NAME = os.environ.get("AURA_CONTAINER_NAME", "aura-terminal")
PORT = os.environ.get("AURA_PORT", "8787")
STATE_VOLUME = os.environ.get("AURA_STATE_VOLUME", "aura-state")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [AURA-Updater] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("AURAUpdater")


def get_current_running_version() -> str | None:
    """Reads the current running version from the local serving endpoint."""
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/serving",
            headers={"User-Agent": "AURAAutoUpdater/1.0"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("version")
    except Exception:
        pass
    
    # Fallback to VERSION file in app directory
    version_file = os.path.join(APP_DIR, "VERSION")
    if os.path.isfile(version_file):
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return None


def fetch_latest_release() -> tuple[str, str] | None:
    """Queries GitHub API for the latest published release tag and asset URL."""
    url = f"https://api.github.com/repos/{REPO}/releases/latest"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "AURAAutoUpdater/1.0",
                "Accept": "application/vnd.github.v3+json"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                tag = str(data.get("tag_name", "")).lstrip("v")
                assets = data.get("assets", [])
                zip_url: str | None = None
                for asset in assets:
                    if asset.get("name") == "symbiose.zip":
                        zip_url = asset.get("browser_download_url")
                        break
                if not zip_url and data.get("zipball_url"):
                    zip_url = str(data.get("zipball_url"))
                if tag and zip_url:
                    return tag, zip_url
    except Exception as e:
        log.warning(f"Fehler beim Abrufen des neuesten GitHub Releases: {e}")
    return None


def update_and_redeploy(tag: str, zip_url: str) -> bool:
    """Downloads the release asset, extracts it to APP_DIR, and rebuilds Docker container."""
    log.info(f"🚀 Starte automatische Aktualisierung auf v{tag}...")
    with tempfile.TemporaryDirectory() as tmpdir:
        archive_path = os.path.join(tmpdir, "release.zip")
        extract_path = os.path.join(tmpdir, "extracted")
        
        # 1. Download
        log.info(f"Lade Release-Paket herunter von {zip_url}...")
        try:
            req = urllib.request.Request(zip_url, headers={"User-Agent": "AURAAutoUpdater/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(archive_path, "wb") as out_file:
                shutil.copyfileobj(resp, out_file)
        except Exception as e:
            log.error(f"Download fehlgeschlagen: {e}")
            return False

        # 2. Extract
        log.info("Entpacke Release-Paket...")
        try:
            with zipfile.ZipFile(archive_path, "r") as z:
                z.extractall(extract_path)
        except Exception as e:
            log.error(f"Entpacken fehlgeschlagen: {e}")
            return False

        # If extracted in a subfolder, locate files
        source_dir = extract_path
        if not os.path.isfile(os.path.join(source_dir, "Symbiose_Dashboard.html")):
            for root, _, files in os.walk(extract_path):
                if "Symbiose_Dashboard.html" in files:
                    source_dir = root
                    break

        # 3. Copy files to APP_DIR
        os.makedirs(APP_DIR, exist_ok=True)
        log.info(f"Kopiere Dateien nach {APP_DIR}...")
        for item in os.listdir(source_dir):
            s = os.path.join(source_dir, item)
            d = os.path.join(APP_DIR, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)

        # 4. Rebuild Docker Image & Recreate Container
        log.info(f"Baue Docker-Image {CONTAINER_NAME}:v{tag}...")
        try:
            build_res = subprocess.run(
                ["docker", "build", "-t", f"{CONTAINER_NAME}:latest", "-t", f"{CONTAINER_NAME}:{tag}", APP_DIR],
                capture_output=True, text=True, check=True
            )
        except subprocess.CalledProcessError as e:
            log.error(f"Docker Build fehlgeschlagen:\n{e.stderr}")
            return False

        log.info(f"Stoppe und ersetze Container {CONTAINER_NAME}...")
        subprocess.run(["docker", "stop", CONTAINER_NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["docker", "rm", CONTAINER_NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        run_cmd = [
            "docker", "run", "-d",
            "--name", CONTAINER_NAME,
            "--restart", "unless-stopped",
            "-p", f"{PORT}:{PORT}",
            "-v", f"{STATE_VOLUME}:/var/lib/aura",
            f"{CONTAINER_NAME}:latest"
        ]
        
        try:
            run_res = subprocess.run(run_cmd, capture_output=True, text=True, check=True)
            log.info(f"Container gestartet: {run_res.stdout.strip()[:12]}")
        except subprocess.CalledProcessError as e:
            log.error(f"Docker Run fehlgeschlagen:\n{e.stderr}")
            return False

        # 5. Verify Healthcheck
        log.info("Prüfe Container-Gesundheit...")
        deadline = time.time() + 20
        while time.time() < deadline:
            time.sleep(2)
            cur_ver = get_current_running_version()
            if cur_ver == tag:
                log.info(f"✅ Update auf v{tag} erfolgreich abgeschlossen! Service ist bereit.")
                return True

        log.warning("Healthcheck nach 20s noch nicht bereit, bitte Logs prüfen.")
        return True


def main():
    log.info("=========================================================")
    log.info(f"  AURA Auto-Updater gestartet für Repo {REPO}")
    log.info(f"  Prüfintervall: alle {CHECK_INTERVAL_SEC} Sekunden")
    log.info("=========================================================")

    while True:
        try:
            current_ver = get_current_running_version()
            release_info = fetch_latest_release()
            
            if release_info:
                latest_ver, zip_url = release_info
                if current_ver != latest_ver and zip_url:
                    log.info(f"Neues Release erkannt! Aktuell: v{current_ver or 'unbekannt'} -> Neu: v{latest_ver}")
                    update_and_redeploy(latest_ver, zip_url)
                else:
                    log.debug(f"Version ist aktuell (v{current_ver}).")
            
        except Exception as e:
            log.error(f"Unerwarteter Fehler im Update-Loop: {e}")

        time.sleep(CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    main()
