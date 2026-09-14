#!/usr/bin/env python3
"""Secure GitHub release webhook receiver for AURA Quant Terminal deployments.

Reference implementation with Clean-Slate Bootstrap support:
- Validates HMAC-SHA256 signatures on GitHub release webhooks.
- Downloads release assets (symbiose.zip) with strict path traversal checks.
- Builds hardened Docker image (`aura-quant-terminal:<version>`).
- If an existing container exists: recycles container preserving existing config (rollback on failure).
- If NO existing container exists (clean-slate / fresh install): bootstraps container
  from canonical compose spec (--restart unless-stopped, --read-only, --cap-drop ALL,
  no-new-privileges, tmpfs /tmp, 8787 port, aura-state volume, --env-file if present).
- Sends fire-and-forget ntfy push notifications on success (P3) / failure (P4).
"""

from __future__ import annotations

import hashlib
import hmac
import http.server
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Any

PORT = int(os.environ.get("AURA_WEBHOOK_PORT", "8443"))
REPOSITORY = os.environ.get("AURA_WEBHOOK_REPOSITORY", "trixr1907/AURA-Quant-Terminal")
WEBHOOK_SECRET = os.environ.get("AURA_WEBHOOK_SECRET", "").encode("utf-8")
APP_DIR = Path(os.environ.get("AURA_APP_DIR", "/opt/aura"))
CONTAINER_NAME = os.environ.get("AURA_CONTAINER_NAME", "aura-terminal")
IMAGE_REPOSITORY = os.environ.get("AURA_IMAGE_REPOSITORY", "aura-quant-terminal")
STATUS_DIR = Path(os.environ.get("AURA_WEBHOOK_STATUS_DIR", "/var/lib/aura-webhook"))
STATUS_FILE = STATUS_DIR / "status.json"
MAX_PAYLOAD_BYTES = 2_000_000
MAX_ASSET_BYTES = 100_000_000
REQUIRED_PACKAGE_FILES = {
    "Dockerfile",
    "bitget_relay.py",
    "Symbiose_Dashboard.html",
    "SYMBIOSE_Tutorial.html",
    "VERSION",
}
DEPLOY_LOCK = threading.Lock()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("aura-webhook")


def _ntfy_notify(title: str, body: str, *, priority: int = 3, category: str = "deploy") -> bool:
    """Fire-and-forget ntfy push notification. Silent no-op when disabled."""
    url = os.environ.get("AURA_NTFY_URL", "").strip()
    if not url:
        return False
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            return False
    except Exception:
        return False

    safe_priority = min(5, max(1, int(priority)))
    safe_category = "".join(char for char in str(category).lower() if char.isalnum() or char in {"-", "_"})[:32] or "deploy"

    def _send() -> None:
        try:
            req = urllib.request.Request(
                url,
                data=body.encode("utf-8"),
                headers={
                    "X-Title": title,
                    "Priority": str(safe_priority),
                    "Tags": safe_category,
                    "Content-Type": "text/plain; charset=utf-8",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10):
                pass
        except Exception as exc:
            log.warning("ntfy deploy notification failed (non-critical): %s", exc)

    t = threading.Thread(target=_send, daemon=True, name="ntfy-deploy-notify")
    t.start()
    return True


def run(command: list[str], *, timeout: int = 600, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a command without invoking a shell."""
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.stdout.strip():
        log.info("%s", result.stdout.strip())
    if result.stderr.strip():
        log.info("%s", result.stderr.strip())
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)}")
    return result


def write_status(state: str, **details: Any) -> None:
    """Persist deployment state atomically for remote verification."""
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"state": state, "updated_at": int(time.time()), **details}
    temporary = STATUS_FILE.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    temporary.replace(STATUS_FILE)


def safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    """Extract a ZIP only when every member remains below destination."""
    destination_resolved = destination.resolve()
    for member in archive.infolist():
        member_path = (destination / member.filename).resolve()
        try:
            member_path.relative_to(destination_resolved)
        except ValueError as exc:
            raise ValueError(f"Unsafe ZIP member: {member.filename}") from exc
    archive.extractall(destination)


def find_package_root(extract_dir: Path) -> Path:
    """Locate the release root and require the production manifest."""
    candidates = [extract_dir, *(path for path in extract_dir.rglob("*") if path.is_dir())]
    for candidate in candidates:
        if REQUIRED_PACKAGE_FILES.issubset({path.name for path in candidate.iterdir()}):
            return candidate
    raise RuntimeError("Release asset does not contain the required AURA production files")


def download_asset(url: str, destination: Path, max_retries: int = 5, retry_delay: float = 2.0) -> None:
    """Download the public release asset with an explicit size limit and CDN propagation retries."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "objects.githubusercontent.com"}:
        raise ValueError("Release asset URL is not an allowed GitHub HTTPS URL")
    request = urllib.request.Request(url, headers={"User-Agent": "AURAWebhook/1.0"})
    
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            total = 0
            with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_ASSET_BYTES:
                        raise ValueError("Release asset exceeds the size limit")
                    output.write(chunk)
            if destination.stat().st_size > 0:
                return
        except Exception as exc:
            last_exc = exc
            log.warning("Asset download attempt %d/%d failed (%s), retrying in %.1fs...", attempt, max_retries, exc, retry_delay)
            time.sleep(retry_delay)
    raise RuntimeError(f"Failed to download release asset after {max_retries} attempts: {last_exc}")


def current_container_config() -> dict[str, Any] | None:
    """Read the running container settings so recreation preserves its contract.
    
    Returns None if no container exists (enabling clean-slate bootstrap).
    """
    result = run(["docker", "inspect", CONTAINER_NAME], check=False)
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
        if isinstance(data, list) and len(data) == 1:
            return data[0]
    except (json.JSONDecodeError, TypeError, IndexError):
        pass
    return None


def resolve_bot_env_file() -> Path | None:
    """Locate the persistent bot env file on host if present."""
    custom_path = os.environ.get("AURA_BOT_ENV_FILE", "/var/lib/aura/aura_bot.env")
    for candidate_str in (custom_path, "/var/lib/docker/volumes/aura-state/_data/aura_bot.env"):
        try:
            candidate = Path(candidate_str)
            if candidate.is_file():
                return candidate
        except (PermissionError, OSError):
            continue
    return None


def bootstrap_arguments(image: str) -> list[str]:
    """Build canonical docker run arguments for fresh installation (no prior container).
    
    Derived from canonical docker-compose.yml specification.
    """
    args = [
        "docker", "run", "-d",
        "--name", CONTAINER_NAME,
        "--restart", "unless-stopped",
        "--read-only",
        "--security-opt", "no-new-privileges:true",
        "--cap-drop", "ALL",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "-p", os.environ.get("AURA_PORT_BINDING", "127.0.0.1:8787:8787"),
        "-v", f"{os.environ.get('AURA_STATE_VOLUME', 'aura-state')}:/var/lib/aura",
        "-e", "SYM_PORT=8787",
        "-e", "SYM_HOST=0.0.0.0",
        "-e", f"AURA_ALLOWED_HOSTS={os.environ.get('AURA_ALLOWED_HOSTS', '127.0.0.1')}",
        "-e", "AURA_STATE_DIR=/var/lib/aura",
        "-e", "AURA_NTFY_BTC=1",
        "-e", "AURA_NTFY_BTC_COOLDOWN_MIN=30",
        "-e", "AURA_NTFY_DIGEST=1",
        "-e", "AURA_NTFY_DIGEST_UTC=7",
        "-e", "AURA_NTFY_ERRORS=1",
    ]
    
    ntfy_url = os.environ.get("AURA_NTFY_URL", "").strip()
    if ntfy_url:
        args.extend(["-e", f"AURA_NTFY_URL={ntfy_url}"])

    bot_mode = os.environ.get("AURA_BOT_MODE", "").strip()
    if bot_mode:
        args.extend(["-e", f"AURA_BOT_MODE={bot_mode}"])

    bot_env = resolve_bot_env_file()
    if bot_env is not None:
        args.extend(["--env-file", str(bot_env)])

    args.append(image)
    return args


def recreate_arguments(config: dict[str, Any], image: str) -> list[str]:
    """Build docker run arguments from the existing container configuration."""
    host_config = config.get("HostConfig") or {}
    args = ["docker", "run", "-d", "--name", CONTAINER_NAME]

    restart_name = ((host_config.get("RestartPolicy") or {}).get("Name") or "unless-stopped")
    args.extend(["--restart", restart_name])

    if host_config.get("ReadonlyRootfs"):
        args.append("--read-only")

    for sec_opt in host_config.get("SecurityOpt") or []:
        args.extend(["--security-opt", sec_opt])

    for cap in host_config.get("CapDrop") or []:
        args.extend(["--cap-drop", cap])

    for tmpfs_path, tmpfs_opts in (host_config.get("Tmpfs") or {}).items():
        opt_str = f":{tmpfs_opts}" if tmpfs_opts else ""
        args.extend(["--tmpfs", f"{tmpfs_path}{opt_str}"])

    for env_value in (config.get("Config") or {}).get("Env") or []:
        args.extend(["-e", env_value])

    bot_env = resolve_bot_env_file()
    if bot_env is not None:
        args.extend(["--env-file", str(bot_env)])

    for mount in config.get("Mounts") or []:
        mount_type = mount.get("Type")
        source = mount.get("Name") if mount_type == "volume" else mount.get("Source")
        destination = mount.get("Destination")
        if mount_type in {"volume", "bind"} and source and destination:
            value = f"{source}:{destination}"
            if not mount.get("RW", True):
                value += ":ro"
            args.extend(["-v", value])

    for container_port, bindings in (host_config.get("PortBindings") or {}).items():
        for binding in bindings or []:
            host_port = binding.get("HostPort")
            if not host_port:
                continue
            host_ip = binding.get("HostIp") or ""
            published = f"{host_ip}:{host_port}:{container_port}" if host_ip else f"{host_port}:{container_port}"
            args.extend(["-p", published])

    args.append(image)
    return args


def wait_for_health(expected_version: str, timeout_seconds: int = 90) -> None:
    """Require Docker health and the expected serving version."""
    deadline = time.monotonic() + timeout_seconds
    last_error = "not checked"
    while time.monotonic() < deadline:
        try:
            inspect = current_container_config()
            if inspect is None:
                raise RuntimeError("container not found")
            state = inspect.get("State") or {}
            health = (state.get("Health") or {}).get("Status", "none")
            if not state.get("Running") or state.get("OOMKilled") or state.get("Error"):
                raise RuntimeError(f"container state invalid: {state}")
            if health not in {"healthy", "none"}:
                raise RuntimeError(f"container health is {health}")
            with urllib.request.urlopen("http://127.0.0.1:8787/serving", timeout=5) as response:
                serving = json.load(response)
            if serving.get("ok") is not True:
                raise RuntimeError(f"serving endpoint is not healthy: {serving}")
            if str(serving.get("version")) != expected_version:
                raise RuntimeError(
                    f"serving version {serving.get('version')} does not match {expected_version}"
                )
            if health == "healthy":
                return
        except Exception as exc:  # Keep polling through the container start period.
            last_error = str(exc)
        time.sleep(3)
    raise RuntimeError(f"Health verification timed out: {last_error}")


def deploy_release(tag: str, asset_url: str, delivery_id: str) -> None:
    """Build and deploy a signed published release with clean-slate bootstrap or rollback on failure."""
    if not DEPLOY_LOCK.acquire(blocking=False):
        log.warning("Ignoring delivery %s because another deployment is active", delivery_id)
        return

    normalized_tag = tag[1:] if tag.startswith("v") else tag
    safe_tag = re.sub(r"[^A-Za-z0-9_.-]", "-", normalized_tag)
    image = f"{IMAGE_REPOSITORY}:{safe_tag}"
    next_dir = APP_DIR.with_name(f"{APP_DIR.name}.next")
    backup_dir = APP_DIR.with_name(f"{APP_DIR.name}.previous")
    rollback_name = f"{CONTAINER_NAME}-rollback"
    old_stopped = False
    source_swapped = False

    try:
        write_status("deploying", tag=tag, delivery_id=delivery_id)
        old_config = current_container_config()

        with tempfile.TemporaryDirectory(prefix="aura-release-") as temporary:
            temporary_path = Path(temporary)
            archive_path = temporary_path / "symbiose.zip"
            extract_dir = temporary_path / "extract"
            extract_dir.mkdir()
            download_asset(asset_url, archive_path)
            with zipfile.ZipFile(archive_path) as archive:
                safe_extract(archive, extract_dir)
            package_root = find_package_root(extract_dir)

            package_version = (package_root / "VERSION").read_text(encoding="utf-8").strip()
            if package_version != normalized_tag:
                raise RuntimeError(
                    f"Package VERSION {package_version!r} does not match release tag {tag!r}"
                )

            shutil.rmtree(next_dir, ignore_errors=True)
            shutil.copytree(package_root, next_dir)

        run(["docker", "build", "-t", image, str(next_dir)], timeout=1200)
        run(["docker", "tag", image, f"{IMAGE_REPOSITORY}:latest"])

        if old_config is not None:
            # Upgrade / Recreate path with rollback protection
            run(["docker", "rm", "-f", rollback_name], check=False)
            run(["docker", "stop", CONTAINER_NAME], timeout=90)
            old_stopped = True
            run(["docker", "rename", CONTAINER_NAME, rollback_name])
            run(recreate_arguments(old_config, image), timeout=90)
        else:
            # Bootstrap path (clean slate / first install)
            log.info("No existing %s container found — bootstrapping from canonical spec", CONTAINER_NAME)
            run(["docker", "rm", "-f", CONTAINER_NAME], check=False)
            run(bootstrap_arguments(image), timeout=90)

        wait_for_health(normalized_tag)

        shutil.rmtree(backup_dir, ignore_errors=True)
        if APP_DIR.exists():
            APP_DIR.replace(backup_dir)
        next_dir.replace(APP_DIR)
        source_swapped = True

        if old_config is not None:
            run(["docker", "rm", rollback_name], check=False)
        shutil.rmtree(backup_dir, ignore_errors=True)
        write_status("success", tag=tag, version=normalized_tag, delivery_id=delivery_id)
        _ntfy_notify(
            f"AURA Deploy erfolgreich: {tag}",
            f"Release {tag} erfolgreich gebaut, gestartet und verified auf {CONTAINER_NAME}.",
            priority=3,
        )
        log.info("Deployment %s completed and verified", tag)
    except Exception as exc:
        log.exception("Deployment %s failed", tag)
        try:
            run(["docker", "rm", "-f", CONTAINER_NAME], check=False)
            if old_stopped:
                run(["docker", "rename", rollback_name, CONTAINER_NAME], check=False)
                run(["docker", "start", CONTAINER_NAME], check=False)
            if source_swapped and backup_dir.exists():
                shutil.rmtree(APP_DIR, ignore_errors=True)
                backup_dir.replace(APP_DIR)
        finally:
            write_status("failed", tag=tag, delivery_id=delivery_id, error=str(exc))
            _ntfy_notify(
                f"AURA Deploy fehlgeschlagen: {tag}",
                f"Deploy fehlgeschlagen: {exc}",
                priority=4,
            )
    finally:
        DEPLOY_LOCK.release()


def signature_valid(body: bytes, supplied: str) -> bool:
    """Verify GitHub's HMAC-SHA256 signature in constant time."""
    if not WEBHOOK_SECRET or not supplied.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(WEBHOOK_SECRET, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied)


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "AURAWebhook/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        log.info("%s - %s", self.client_address[0], format % args)

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlsplit(self.path).path
        if path not in {"/", "/github-webhook"}:
            self.send_json(404, {"ok": False})
            return
        self.send_json(200, {"ok": True, "service": "aura-webhook-receiver"})

    def do_POST(self) -> None:  # noqa: N802
        if urllib.parse.urlsplit(self.path).path != "/github-webhook":
            self.send_json(404, {"status": "not_found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"status": "invalid_length"})
            return
        if content_length <= 0 or content_length > MAX_PAYLOAD_BYTES:
            self.send_json(413, {"status": "invalid_payload_size"})
            return

        body = self.rfile.read(content_length)
        if not signature_valid(body, self.headers.get("X-Hub-Signature-256", "")):
            self.send_json(401, {"status": "invalid_signature"})
            return

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_json(400, {"status": "invalid_json"})
            return

        event = self.headers.get("X-GitHub-Event", "")
        delivery_id = self.headers.get("X-GitHub-Delivery", "unknown")
        if event == "ping":
            self.send_json(202, {"status": "pong"})
            return
        if event != "release":
            self.send_json(202, {"status": "ignored_event"})
            return
        if payload.get("action") != "published":
            self.send_json(202, {"status": "ignored_action"})
            return
        if (payload.get("repository") or {}).get("full_name") != REPOSITORY:
            self.send_json(403, {"status": "wrong_repository"})
            return

        release = payload.get("release") or {}
        if release.get("draft") or release.get("prerelease"):
            self.send_json(202, {"status": "ignored_non_final_release"})
            return
        tag = str(release.get("tag_name") or "")
        asset_url = next(
            (
                str(asset.get("browser_download_url"))
                for asset in release.get("assets") or []
                if asset.get("name") == "symbiose.zip"
            ),
            "",
        )
        if not tag or not asset_url:
            self.send_json(422, {"status": "missing_release_asset"})
            return

        if DEPLOY_LOCK.locked():
            self.send_json(202, {"status": "deployment_already_running"})
            return

        thread = threading.Thread(
            target=deploy_release,
            args=(tag, asset_url, delivery_id),
            daemon=True,
            name=f"aura-deploy-{delivery_id}",
        )
        thread.start()
        self.send_json(202, {"status": "deployment_started", "tag": tag})


def main() -> None:
    if len(WEBHOOK_SECRET) < 32:
        raise SystemExit("AURA_WEBHOOK_SECRET must contain at least 32 characters")
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    log.info("Secure AURA webhook receiver listening on port %s", PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
