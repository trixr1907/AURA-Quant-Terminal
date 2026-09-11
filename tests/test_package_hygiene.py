#!/usr/bin/env python3
"""Regression checks for the lean end-user release package."""
from pathlib import Path
import sys

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
        "RELEASE_v1.1.8.md",
        "RELEASE_v1.2.0.md",
        "RELEASE_v1.2.1.md",
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
        "RELEASE_v1.2.2.md",
        "assets/aura_logo.svg",
        "assets/aura_logo_horizontal.svg",
    }
    assert required.issubset(files)
