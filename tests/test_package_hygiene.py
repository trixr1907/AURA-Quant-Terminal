#!/usr/bin/env python3
"""Regression checks for the lean end-user release package."""
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_package  # noqa: E402


def test_release_package_excludes_development_corpus():
    files = build_package.collect_files()
    assert not any(path == "tests" or path.startswith("tests/") for path in files)
    assert "pytest.ini" not in files
    assert "scripts/release_check.py" not in files
    assert "scripts/build_package.py" not in files


def test_release_package_excludes_historical_and_homelab_material():
    files = build_package.collect_files()
    forbidden = {
        "RELEASE_v1.2.0.md",
        "RELEASE_v1.2.1.md",
        "RELEASE_v1.2.2.md",
        "RELEASE_v1.2.3.md",
        "RELEASE_v1.2.4.md",
        "RELEASE_v1.2.5.md",
        "RELEASE_v1.2.6.md",
        "proxmox_lxc_install.sh",
        "smart_homelab_installer.sh",
        "PROXMOX_DEPLOY.bat",
        "PROXMOX_GUIDE.md",
        "deep_infrastructure_scanner.sh",
    }
    assert forbidden.isdisjoint(files)


def test_release_package_keeps_runtime_and_current_docs():
    files = build_package.collect_files()
    required = {
        "VERSION",
        "start.py",
        "bitget_relay.py",
        "Symbiose_Dashboard.html",
        "Symbiose_Signal_System_v1.pine",
        "README.md",
        "RELEASE_v1.2.13.md",
        "assets/aura_logo.svg",
        "assets/aura_logo_horizontal.svg",
    }
    assert required.issubset(files)


def test_dockerfile_copies_version_file():
    dockerfile_text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"COPY\s+.*VERSION\s+\.", dockerfile_text), "Dockerfile must copy VERSION into image"


def test_bitget_relay_no_hardcoded_version_fallback():
    relay_text = (ROOT / "bitget_relay.py").read_text(encoding="utf-8")
    assert not re.search(r'else\s+["\']1\.2\.\d+["\']', relay_text), "bitget_relay.py must not contain hardcoded version fallback"


def test_bitget_relay_version_matches_version_file():
    sys.path.insert(0, str(ROOT))
    import bitget_relay
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert bitget_relay.VERSION == expected, f"bitget_relay.VERSION ({bitget_relay.VERSION}) must match VERSION file ({expected})"


def test_bitget_relay_fails_fast_when_version_file_missing():
    import subprocess
    code = "import bitget_relay"
    with tempfile.TemporaryDirectory() as tmpdir:
        # Run python from a directory that does NOT have a VERSION file next to a copied relay
        tmp_relay = Path(tmpdir) / "bitget_relay.py"
        tmp_relay.write_text((ROOT / "bitget_relay.py").read_text(encoding="utf-8"), encoding="utf-8")
        res = subprocess.run([sys.executable, "-c", code], cwd=tmpdir, capture_output=True, text=True)
        assert res.returncode != 0, "Importing relay without VERSION file must fail fast"
        assert "CRITICAL DEPLOYMENT ERROR: VERSION file missing" in res.stderr

