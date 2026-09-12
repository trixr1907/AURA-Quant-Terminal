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
        "RELEASE_v1.3.2.md",
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


def test_dashboard_footer_version_matches_version_file():
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    dash_text = (ROOT / "Symbiose_Dashboard.html").read_text(encoding="utf-8")
    match = re.search(r"<footer>.*?<b>AURA\s+(?:Confluence|Quant)\s+Terminal\s+v(\d+\.\d+\.\d+)</b>", dash_text, re.DOTALL)
    assert match is not None, "Dashboard must have a visible footer version line"
    assert match.group(1) == expected, f"Dashboard footer version ({match.group(1)}) must match VERSION file ({expected})"


def test_dashboard_modal_title_matches_version_file():
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    dash_text = (ROOT / "Symbiose_Dashboard.html").read_text(encoding="utf-8")
    match = re.search(r'<h2\s+id="release-notes-title"[^>]*>Was ist neu in AURA v(\d+\.\d+\.\d+)\?</h2>', dash_text)
    assert match is not None, "Dashboard must have a release notes modal title with version"
    assert match.group(1) == expected, f"Modal title version ({match.group(1)}) must match VERSION file ({expected})"


def test_dashboard_release_notes_entry_exists_for_version():
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    dash_text = (ROOT / "Symbiose_Dashboard.html").read_text(encoding="utf-8")
    # Must contain a non-empty entry for the current version in AURA_RELEASE_NOTES
    pattern = rf'["\']?{re.escape(expected)}["\']?:\s*\{{(?:(?!}}).)*?["\']?title["\']?:\s*"([^"]+)",(?:(?!}}).)*?["\']?summary["\']?:\s*"([^"]+)",(?:(?!}}).)*?["\']?highlights["\']?:\s*\[(.*?)\]'
    match = re.search(pattern, dash_text, re.DOTALL)
    assert match is not None, f"AURA_RELEASE_NOTES in Symbiose_Dashboard.html must contain valid entry for v{expected}"
    title, summary, highlights = match.group(1), match.group(2), match.group(3)
    assert len(title.strip()) > 0, "Release notes entry must have a title"
    assert len(summary.strip()) > 0, "Release notes entry must have a summary"
    bullet_count = len(re.findall(r'"[^"]+"', highlights))
    assert bullet_count >= 3, f"Release notes highlights must contain at least 3 bullets, found {bullet_count}"


def test_all_surfaces_version_synchronization():
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    surfaces = {
        "README.md": (ROOT / "README.md").read_text(encoding="utf-8"),
        "Dockerfile": (ROOT / "Dockerfile").read_text(encoding="utf-8"),
        "bitget_relay.py": (ROOT / "bitget_relay.py").read_text(encoding="utf-8"),
        "start.py": (ROOT / "start.py").read_text(encoding="utf-8"),
        "START.bat": (ROOT / "START.bat").read_text(encoding="ascii"),
        "START_OHNE_GUI.bat": (ROOT / "START_OHNE_GUI.bat").read_text(encoding="ascii"),
        "bootstrap.ps1": (ROOT / "bootstrap.ps1").read_text(encoding="utf-8-sig"),
        "docs/architecture.md": (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8"),
        "SYMBIOSE_Tutorial.html": (ROOT / "SYMBIOSE_Tutorial.html").read_text(encoding="utf-8"),
        "Symbiose_Signal_System_v1.pine": (ROOT / "Symbiose_Signal_System_v1.pine").read_text(encoding="utf-8"),
        "Symbiose_Dashboard.html": (ROOT / "Symbiose_Dashboard.html").read_text(encoding="utf-8"),
    }
    for name, content in surfaces.items():
        assert expected in content, f"Surface {name} must contain current version {expected}"

