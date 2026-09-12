#!/usr/bin/env python3
"""Synchronously update version references across all system components."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def bump_version(new_ver: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", new_ver):
        raise ValueError(f"Version must follow SemVer format (e.g. 1.1.6), got: {new_ver}")

    old_ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    print(f"Bumping version: {old_ver} -> {new_ver}")

    # 1. VERSION
    (ROOT / "VERSION").write_text(f"{new_ver}\n", encoding="utf-8")

    # 1b. README.md
    readme = ROOT / "README.md"
    readme_text = readme.read_text(encoding="utf-8")
    readme_text = re.sub(r'#\s*AURA\s+v\d+\.\d+\.\d+', f'# AURA v{new_ver}', readme_text)
    readme_text = re.sub(r'badge/version-\d+\.\d+\.\d+', f'badge/version-{new_ver}', readme_text)
    readme_text = re.sub(r'alt="Version\s+\d+\.\d+\.\d+"', f'alt="Version {new_ver}"', readme_text)
    readme.write_text(readme_text, encoding="utf-8")

    # 2. Dockerfile
    dockerfile = ROOT / "Dockerfile"
    dockerfile_text = re.sub(
        r'LABEL version="[^"]+"',
        f'LABEL version="{new_ver}"',
        dockerfile.read_text(encoding="utf-8"),
    )
    dockerfile.write_text(dockerfile_text, encoding="utf-8")

    # 3. bitget_relay.py
    relay = ROOT / "bitget_relay.py"
    relay_text = relay.read_text(encoding="utf-8")
    relay_text = re.sub(r'bitget_relay\.py — AURA v\d+\.\d+\.\d+', f'bitget_relay.py — AURA v{new_ver}', relay_text)
    relay_text = re.sub(r'"version":\s*"\d+\.\d+\.\d+"', f'"version": "{new_ver}"', relay_text)
    relay_text = re.sub(r'VERSION\s*=\s*"\d+\.\d+\.\d+"', f'VERSION = "{new_ver}"', relay_text)
    relay_text = re.sub(r'AURA Relay v\d+\.\d+\.\d+', f'AURA Relay v{new_ver}', relay_text)
    relay.write_text(relay_text, encoding="utf-8")

    # 4. start.py
    start_py = ROOT / "start.py"
    start_text = start_py.read_text(encoding="utf-8")
    start_text = re.sub(r'AURALauncher/\d+\.\d+\.\d+', f'AURALauncher/{new_ver}', start_text)
    start_text = re.sub(r'\(v\{health\.get\("version", "[^"]+"\)\}\)', f'(v{{health.get("version", "{new_ver}")}})', start_text)
    start_text = re.sub(r'AURA Quant Terminal — Quant Research & Setup Discovery v\d+\.\d+\.\d+', f'AURA Quant Terminal — Quant Research & Setup Discovery v{new_ver}', start_text)
    start_py.write_text(start_text, encoding="utf-8")

    # 5. START.bat and START_OHNE_GUI.bat
    start_bat = ROOT / "START.bat"
    start_bat_text = start_bat.read_text(encoding="ascii")
    start_bat_text = re.sub(r'AURA v\d+\.\d+\.\d+', f'AURA v{new_ver}', start_bat_text)
    start_bat.write_text(start_bat_text, encoding="ascii")

    cli_bat = ROOT / "START_OHNE_GUI.bat"
    cli_bat_text = cli_bat.read_text(encoding="ascii")
    cli_bat_text = re.sub(r'AURA v\d+\.\d+\.\d+', f'AURA v{new_ver}', cli_bat_text)
    cli_bat.write_text(cli_bat_text, encoding="ascii")

    # 6. bootstrap.ps1
    boot_ps1 = ROOT / "bootstrap.ps1"
    boot_text = boot_ps1.read_text(encoding="utf-8-sig")
    boot_text = re.sub(r'AURA\\\d+\.\d+\.\d+', lambda _: f'AURA\\{new_ver}', boot_text)
    boot_ps1.write_text(boot_text, encoding="utf-8-sig")

    # 7. docs/architecture.md
    arch = ROOT / "docs" / "architecture.md"
    arch_text = arch.read_text(encoding="utf-8")
    arch_text = re.sub(r'\*\*Version:\*\*\s*\d+\.\d+\.\d+', f'**Version:** {new_ver}', arch_text)
    arch.write_text(arch_text, encoding="utf-8")

    # 8. scripts/sync_market_data.py
    sync_py = ROOT / "scripts" / "sync_market_data.py"
    sync_text = sync_py.read_text(encoding="utf-8")
    sync_text = re.sub(r'AURA/\d+\.\d+\.\d+', f'AURA/{new_ver}', sync_text)
    sync_py.write_text(sync_text, encoding="utf-8")

    # 9. SYMBIOSE_Tutorial.html
    tut = ROOT / "SYMBIOSE_Tutorial.html"
    tut_text = tut.read_text(encoding="utf-8")
    tut_text = re.sub(r'<title>AURA v\d+\.\d+\.\d+', f'<title>AURA v{new_ver}', tut_text)
    tut_text = re.sub(r'class="nav-logo">AURA\s+v\d+\.\d+\.\d+', f'class="nav-logo">AURA v{new_ver}', tut_text)
    tut_text = re.sub(r'<h1>AURA\s+v\d+\.\d+\.\d+', f'<h1>AURA v{new_ver}', tut_text)
    tut_text = re.sub(r'wie AURA v\d+\.\d+\.\d+ Trades beendet', f'wie AURA v{new_ver} Trades beendet', tut_text)
    tut_text = re.sub(r'Die Makro-Daten sind in v\d+\.\d+\.\d+', f'Die Makro-Daten sind in v{new_ver}', tut_text)
    tut_text = re.sub(r'<footer>\s*AURA\s+v\d+\.\d+\.\d+', f'<footer>\n  AURA v{new_ver}', tut_text)
    tut.write_text(tut_text, encoding="utf-8")

    # 10. Symbiose_Signal_System_v1.pine
    pine = ROOT / "Symbiose_Signal_System_v1.pine"
    pine_text = pine.read_text(encoding="utf-8")
    pine_text = re.sub(r'//\s+AURA v\d+\.\d+\.\d+\s+—\s+Confluence', f'//  AURA v{new_ver} — Confluence', pine_text)
    pine_text = re.sub(r'//\s+v\d+\.\d+\.\d+\s+CURRENT:', f'//  v{new_ver} CURRENT:', pine_text)
    pine_text = re.sub(r'symbiose\.v\d+\.\d+\.\d+\s+alert contract', f'symbiose.v{new_ver} alert contract', pine_text)
    pine_text = re.sub(r'f_hdr\(0,\s*"AURA v\d+\.\d+\.\d+"', f'f_hdr(0, "AURA v{new_ver}"', pine_text)
    pine_text = re.sub(r'Trade-State \(v\d+\.\d+\.\d+\)', f'Trade-State (v{new_ver})', pine_text)
    pine_text = re.sub(r'// JSON-Payload includes v\d+\.\d+\.\d+ fields', f'// JSON-Payload includes v{new_ver} fields', pine_text)
    pine_text = re.sub(r'"type":"symbiose\.v\d+\.\d+\.\d+"', f'"type":"symbiose.v{new_ver}"', pine_text)
    pine_text = re.sub(r'//\s+ENDE — AURA v\d+\.\d+\.\d+', f'//  ENDE — AURA v{new_ver}', pine_text)
    pine.write_text(pine_text, encoding="utf-8")

    # 11. Symbiose_Dashboard.html
    dash = ROOT / "Symbiose_Dashboard.html"
    dash_text = dash.read_text(encoding="utf-8")
    dash_text = re.sub(r'Was ist neu in AURA v\d+\.\d+\.\d+\?', f'Was ist neu in AURA v{new_ver}?', dash_text)
    dash_text = re.sub(r'<b>AURA Quant Terminal v\d+\.\d+\.\d+</b>', f'<b>AURA Quant Terminal v{new_ver}</b>', dash_text)
    dash_text = re.sub(r"showReleaseNotesOnce\('\d+\.\d+\.\d+'\);", f"showReleaseNotesOnce('{new_ver}');", dash_text)
    dash.write_text(dash_text, encoding="utf-8")

    # 12. scripts/generate_claims.py
    claims_gen = ROOT / "scripts" / "generate_claims.py"
    claims_text = claims_gen.read_text(encoding="utf-8")
    claims_text = re.sub(r'Version \d+\.\d+\.\d+ einheitlich', f'Version {new_ver} einheitlich', claims_text)
    claims_text = re.sub(r"matchen exakt '\d+\.\d+\.\d+'", f"matchen exakt '{new_ver}'", claims_text)
    claims_gen.write_text(claims_text, encoding="utf-8")

    # 13. build_package.py and test_package_hygiene.py
    pkg = ROOT / "scripts" / "build_package.py"
    pkg_text = pkg.read_text(encoding="utf-8")
    pkg_text = re.sub(r'RELEASE_v\d+\.\d+\.\d+\.md', f'RELEASE_v{new_ver}.md', pkg_text)
    pkg.write_text(pkg_text, encoding="utf-8")

    pkg_test = ROOT / "tests" / "test_package_hygiene.py"
    pkg_test_text = pkg_test.read_text(encoding="utf-8")
    pkg_test_text = re.sub(r'RELEASE_v\d+\.\d+\.\d+\.md', f'RELEASE_v{new_ver}.md', pkg_test_text)
    pkg_test.write_text(pkg_test_text, encoding="utf-8")

    print("All component version markers updated.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/bump_version.py <MAJOR.MINOR.PATCH>")
        sys.exit(1)
    bump_version(sys.argv[1])
