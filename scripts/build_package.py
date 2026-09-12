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
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "symbiose.zip"
STAMP = ROOT / "scripts" / ".release_verdict.json"

# Explicit allowlist. Paths are relative to ROOT. Directories are recursive but
# still filtered by EXCLUDE_DIRS / EXCLUDE_SUFFIXES below.
MANIFEST = [
    # launchers
    "VERSION",
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
    # documentation and brand assets
    "README.md",
    "RELEASE_v1.2.5.md",
    "SYMBIOSE_Model_Validation.md",
    "SYMBIOSE_Tutorial.html",
    "assets/",
    # optional Docker runtime
    "Dockerfile",
    "docker-compose.yml",
    "docker_start.sh",
    "DOCKER_START.bat",
    "DOCKER_STOP.bat",
    "DOCKER_GUIDE.md",
    ".dockerignore",
    ".env.example",
    # public universe snapshot
    "data/bitget_usdt_futures_universe.json",
]
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".hermes", ".git", "node_modules"}
EXCLUDE_SUFFIXES = {".pyc", ".png", ".log", ".zip"}
EXCLUDE_NAMES = {".release_dashboard_check.js", ".release_verdict.json", ".DS_Store"}
RUNTIME_STATE_BASENAME = "aura_shared_state"


def _is_runtime_state_family(name: str) -> bool:
    """Reject every filename whose stem starts with the runtime-state basename."""
    return Path(name).name.split(".", 1)[0] == RUNTIME_STATE_BASENAME


def _normalized_relative_path(rel: str | Path) -> str:
    """Return a safe POSIX archive path or reject it before filesystem access."""
    raw = os.fspath(rel)
    if not raw or "\\" in raw:
        raise ValueError(f"refusing unsafe package path: {rel!r}")
    posix = PurePosixPath(raw)
    windows = PureWindowsPath(raw)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise ValueError(f"refusing unsafe package path: {rel!r}")
    if any(part == ".." for part in posix.parts):
        raise ValueError(f"refusing unsafe package path: {rel!r}")
    normalized = posix.as_posix()
    if normalized in {"", "."}:
        raise ValueError(f"refusing unsafe package path: {rel!r}")
    return normalized


def _path_is_safe(p: Path) -> bool:
    """Require p and every path segment below ROOT to be non-symlinks."""
    root = ROOT.resolve()
    try:
        p.relative_to(root)
        resolved = p.resolve(strict=False)
    except ValueError:
        return False
    if root != resolved and root not in resolved.parents:
        return False
    current = p
    while current != root:
        if current.is_symlink():
            return False
        current = current.parent
    return True


def _validate_package_path(rel: str | Path, *, allow_missing: bool = False) -> tuple[Path, str]:
    """Validate a manifest/list path and return its source plus ZIP arcname."""
    normalized = _normalized_relative_path(rel)
    root = ROOT.resolve()
    source = root / Path(normalized)
    if not _path_is_safe(source):
        raise ValueError(f"refusing unsafe package path: {rel!r}")
    if not allow_missing and not source.exists():
        raise ValueError(f"refusing missing package path: {rel!r}")
    return source, normalized


def _resolve_manifest_files() -> list[str]:
    """Resolve the current MANIFEST into safe, filtered archive paths."""
    files: list[str] = []
    for entry in MANIFEST:
        path, normalized_entry = _validate_package_path(entry, allow_missing=True)
        if path.is_dir():
            for p in sorted(path.rglob("*")):
                if p.is_symlink():
                    continue
                if p.is_file() and _allowed(p):
                    relative = p.relative_to(ROOT.resolve()).as_posix()
                    _validate_package_path(relative)
                    files.append(relative)
        elif path.is_file() and _allowed(path):
            files.append(normalized_entry)
        else:
            print(f"WARNING: manifest entry missing, skipped: {entry}", file=sys.stderr)
    return sorted(set(files))


def collect_files() -> list[str]:
    return _resolve_manifest_files()


def _allowed(p: Path) -> bool:
    if not _path_is_safe(p):
        return False
    if any(seg in EXCLUDE_DIRS for seg in p.parts):
        return False
    if p.suffix.lower() in EXCLUDE_SUFFIXES:
        return False
    if p.name in EXCLUDE_NAMES or _is_runtime_state_family(p.name):
        return False
    return True


def build_archive(files: list[str], output: Path) -> None:
    """Write an archive only from the current resolved manifest allowlist."""
    allowed_files = set(_resolve_manifest_files())
    validated = []
    for rel in files:
        source, arcname = _validate_package_path(rel)
        if arcname not in allowed_files:
            raise ValueError(f"refusing non-manifest package path: {rel}")
        if not source.is_file() or not _allowed(source):
            raise ValueError(f"refusing forbidden package path: {rel}")
        validated.append((source, arcname))

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for source, arcname in validated:
            zf.write(source, arcname=arcname)


def verdict_allows_packaging(verdict: str | None) -> bool:
    """Packaging is permitted for valid software releases (even under research-only model verdict)."""
    return verdict in {"GO", "SOFTWARE_GO", "SOFTWARE_GO / MODEL_NO_EVIDENCE"}


def guard() -> None:
    if "--force" in sys.argv:
        return
    if not STAMP.exists():
        print("ERROR: no release verdict stamp — run scripts/release_check.py first "
              "(or pass --force).", file=sys.stderr)
        sys.exit(3)
    stamp_data = json.loads(STAMP.read_text(encoding="utf-8"))
    verdict = stamp_data.get("verdict")
    software_verdict = stamp_data.get("software_verdict")
    checks = stamp_data.get("checks", [])
    has_fail = any(c.get("status") == "FAIL" for c in checks)
    if has_fail or not verdict_allows_packaging(verdict) or (software_verdict and software_verdict != "SOFTWARE_GO"):
        print(f"ERROR: last release verdict is {verdict!r} (software: {software_verdict!r}) — "
              "refusing to package. Software checks must pass (or pass --force).",
              file=sys.stderr)
        sys.exit(3)


def smoke_test(extract_dir: Path) -> int:
    """Runtime smoke tests inside a clean end-user extraction."""
    cmds = [
        [sys.executable, "-m", "py_compile", "start.py", "bitget_relay.py"],
        [sys.executable, "-c", "import bitget_relay; assert bitget_relay.VERSION"],
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
    build_archive(files, tmp_zip)

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
