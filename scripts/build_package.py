#!/usr/bin/env python3
"""
AURA — reproducible package builder.

Builds symbiose.zip from an explicit allowlisted manifest, emits SHA-256, and
smoke-tests the archive in a fresh temp directory (non-browser tests only).

Refuses to run if release_check.py last reported a required FAIL (it records a
stamp in scripts/.release_verdict.json). Override only with --force.

Usage:
  python3 scripts/build_package.py          # build + smoke test
  python3 scripts/build_package.py --force  # skip the release verdict guard
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "symbiose.zip"
STAMP = ROOT / "scripts" / ".release_verdict.json"

# Explicit allowlist. Paths are relative to ROOT. Directories are recursive but
# still filtered by EXCLUDE_DIRS / EXCLUDE_SUFFIXES below.
MANIFEST = [
    # launchers
    "start.py",
    "START.bat",
    "START_OHNE_GUI.bat",
    "bootstrap.ps1",
    "start.sh",
    "requirements.txt",
    # source
    "bitget_relay.py",
    "Symbiose_Dashboard.html",
    "Symbiose_Signal_System_v1.pine",
    # documentation
    "README.md",
    "RELEASE_CHECKLIST.md",
    "SYMBIOSE_Model_Validation.md",
    "SYMBIOSE_Tutorial.html",
    # docker & containers
    "Dockerfile",
    "docker-compose.yml",
    "docker_start.sh",
    "DOCKER_START.bat",
    "DOCKER_STOP.bat",
    "DOCKER_GUIDE.md",
    ".dockerignore",
    ".env.example",
    # proxmox & homelab deployment
    "proxmox_lxc_install.sh",
    "smart_homelab_installer.sh",
    "PROXMOX_DEPLOY.bat",
    "PROXMOX_GUIDE.md",
    "deep_infrastructure_scanner.sh",
    # scripts
    "scripts/release_check.py",
    "scripts/build_package.py",
    "scripts/sync_market_data.py",
    # data
    "data/",
    # tests + fixtures
    "pytest.ini",
    "tests/",
]
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".hermes", ".git", "node_modules"}
EXCLUDE_SUFFIXES = {".pyc", ".png", ".log", ".zip"}
EXCLUDE_NAMES = {".release_dashboard_check.js", ".release_verdict.json", ".DS_Store"}


def collect_files() -> list[str]:
    files: list[str] = []
    for entry in MANIFEST:
        path = ROOT / entry
        if path.is_dir():
            for p in sorted(path.rglob("*")):
                if p.is_file() and _allowed(p):
                    files.append(str(p.relative_to(ROOT)))
        elif path.is_file():
            files.append(entry)
        else:
            print(f"WARNING: manifest entry missing, skipped: {entry}", file=sys.stderr)
    # dedupe, keep order
    return sorted(set(files))


def _allowed(p: Path) -> bool:
    if any(seg in EXCLUDE_DIRS for seg in p.parts):
        return False
    if p.suffix.lower() in EXCLUDE_SUFFIXES:
        return False
    if p.name in EXCLUDE_NAMES:
        return False
    return True


def guard() -> None:
    if "--force" in sys.argv:
        return
    if not STAMP.exists():
        print("ERROR: no release verdict stamp — run scripts/release_check.py first "
              "(or pass --force).", file=sys.stderr)
        sys.exit(3)
    verdict = json.loads(STAMP.read_text(encoding="utf-8")).get("verdict")
    if verdict == "FAIL":
        print("ERROR: last release check was FAIL — refusing to package. "
              "Fix the failures or pass --force.", file=sys.stderr)
        sys.exit(3)
    if "MODEL_NO_EVIDENCE" in (verdict or ""):
        print("ERROR: last release check reports MODEL_NO_EVIDENCE — the statistical "
              "model has no validated edge. Refusing to package a strategy without "
              "mathematical edge (pass --force only if you truly understand).",
              file=sys.stderr)
        sys.exit(3)


def smoke_test(extract_dir: Path) -> int:
    """Non-browser smoke tests inside a clean extraction."""
    cmds = [
        [sys.executable, "-m", "py_compile", "start.py", "bitget_relay.py", "tests/browser_research_harness.py"],
        [sys.executable, "-m", "unittest", "tests/test_launcher.py"],
        [sys.executable, "-m", "unittest", "tests/test_research_cleanup.py"],
        ["node", "tests/test_radar_progressive.js"],
        ["node", "tests/test_engine_full.js"],
        [sys.executable, "tests/reference_backtest.py"],
        [sys.executable, "-m", "unittest", "tests/test_relay_full.py"],
    ]
    failed = 0
    for cmd in cmds:
        proc = subprocess.run(cmd, cwd=str(extract_dir), capture_output=True, text=True, timeout=600)
        status = "PASS" if proc.returncode == 0 else "FAIL"
        tail = (proc.stdout or proc.stderr).strip().splitlines()
        last = tail[-1] if tail else "(no output)"
        print(f"  [{status}] {' '.join(cmd)}  ->  {last[:120]}")
        failed += proc.returncode != 0
    return failed


def main() -> int:
    guard()
    files = collect_files()
    if not files:
        print("ERROR: manifest resolved to zero files.", file=sys.stderr)
        return 3

    # build
    tmp_zip = OUT.with_suffix(".tmp.zip")
    with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            zf.write(ROOT / rel, arcname=rel)

    sha = hashlib.sha256(tmp_zip.read_bytes()).hexdigest()
    tmp_zip.replace(OUT)

    print(f"Built {OUT.name}: {len(files)} files")
    print(f"SHA-256: {sha}")

    # smoke test in clean temp dir
    with tempfile.TemporaryDirectory(prefix="symbiose-smoke-") as td:
        extract = Path(td) / "extract"
        extract.mkdir()
        with zipfile.ZipFile(OUT) as zf:
            zf.extractall(extract)
        print(f"Smoke test in {extract}:")
        failed = smoke_test(extract)
        if failed:
            print(f"SMOKE TEST: {failed} check(s) failed", file=sys.stderr)
            return 2

    print("SMOKE TEST: all non-browser checks passed from clean extraction")
    return 0


if __name__ == "__main__":
    sys.exit(main())
