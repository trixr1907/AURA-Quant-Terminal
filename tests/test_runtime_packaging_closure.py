"""Tests for Auftrag 2: Runtime Packaging Closure Gate (fail-closed)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import scripts.release_check as rc

ROOT = Path(__file__).resolve().parent.parent


class TestRuntimePackagingClosure(unittest.TestCase):
    def test_current_repo_passes_packaging_closure(self):
        status, detail_json = rc.check_runtime_packaging_closure(ROOT)
        detail = json.loads(detail_json)
        self.assertEqual(status, "PASS", f"Closure gate failed: {detail_json}")
        self.assertIn("shadow_collector.js", detail.get("checked_dependencies", []))
        self.assertIn("headless_autobot.js", detail.get("checked_dependencies", []))

    def test_missing_manifest_entry_fails_closed(self):
        # Simulate manifest missing shadow_collector.js (as in v1.10.0 bug)
        manifest_without_shadow = [
            "VERSION", "start.py", "bitget_relay.py", "headless_autobot.js",
            "Symbiose_Dashboard.html", "SYMBIOSE_Tutorial.html", "data/"
        ]
        status, detail_json = rc.check_runtime_packaging_closure(
            ROOT, manifest_list=manifest_without_shadow
        )
        detail = json.loads(detail_json)
        self.assertEqual(status, "FAIL")
        self.assertIn("shadow_collector.js", detail.get("missing_in_manifest", []))

    def test_missing_dockerfile_copy_fails_closed(self):
        # Simulate Dockerfile missing COPY shadow_collector.js
        dockerfile_without_shadow = """
WORKDIR /app
COPY --chown=aura:aura bitget_relay.py .
COPY --chown=aura:aura headless_autobot.js .
COPY --chown=aura:aura VERSION .
COPY --chown=aura:aura Symbiose_Dashboard.html .
COPY --chown=aura:aura SYMBIOSE_Tutorial.html .
COPY --chown=aura:aura data/ ./data/
USER aura
"""
        status, detail_json = rc.check_runtime_packaging_closure(
            ROOT, dockerfile_content=dockerfile_without_shadow
        )
        detail = json.loads(detail_json)
        self.assertEqual(status, "FAIL")
        self.assertIn("shadow_collector.js", detail.get("missing_in_dockerfile", []))

    def test_transitive_dependency_resolution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmproot = Path(tmpdir)
            (tmproot / "bitget_relay.py").write_text("# relay", encoding="utf-8")
            (tmproot / "start.py").write_text("# start", encoding="utf-8")
            (tmproot / "Symbiose_Dashboard.html").write_text("<!-- html -->", encoding="utf-8")
            (tmproot / "SYMBIOSE_Tutorial.html").write_text("<!-- tutorial -->", encoding="utf-8")
            (tmproot / "headless_autobot.js").write_text("const a = require('./module_a.js');", encoding="utf-8")
            (tmproot / "module_a.js").write_text("const b = require('./module_b.js');", encoding="utf-8")
            (tmproot / "module_b.js").write_text("console.log('b');", encoding="utf-8")
            (tmproot / "scripts" / "ops").mkdir(parents=True)
            (tmproot / "scripts" / "state_migration.py").write_text("# migration", encoding="utf-8")
            (tmproot / "scripts" / "ops" / "aura_state_migrate.py").write_text(
                "from scripts.state_migration import migrate_state_directory\n", encoding="utf-8"
            )

            df_content = """
COPY bitget_relay.py .
COPY start.py .
COPY Symbiose_Dashboard.html .
COPY SYMBIOSE_Tutorial.html .
COPY headless_autobot.js .
COPY module_a.js .
COPY module_b.js .
COPY scripts/state_migration.py ./scripts/state_migration.py
COPY scripts/ops/aura_state_migrate.py ./scripts/ops/aura_state_migrate.py
"""
            # Manifest has module_a, but omits transitive module_b
            manifest = [
                "bitget_relay.py", "start.py", "Symbiose_Dashboard.html",
                "SYMBIOSE_Tutorial.html", "headless_autobot.js", "module_a.js",
                "scripts/state_migration.py", "scripts/ops/aura_state_migrate.py",
            ]

            status, detail_json = rc.check_runtime_packaging_closure(
                tmproot, manifest_list=manifest, dockerfile_content=df_content
            )
            detail = json.loads(detail_json)
            self.assertEqual(status, "FAIL")
            self.assertIn("module_b.js", detail.get("missing_in_manifest", []))

            # Now add module_b to manifest -> PASS
            manifest.append("module_b.js")
            status, detail_json = rc.check_runtime_packaging_closure(
                tmproot, manifest_list=manifest, dockerfile_content=df_content
            )
            detail = json.loads(detail_json)
            self.assertEqual(status, "PASS")
            self.assertIn("module_b.js", detail.get("checked_dependencies", []))

    def test_missing_file_on_disk_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmproot = Path(tmpdir)
            (tmproot / "bitget_relay.py").write_text("# relay", encoding="utf-8")
            (tmproot / "start.py").write_text("# start", encoding="utf-8")
            (tmproot / "Symbiose_Dashboard.html").write_text("<!-- html -->", encoding="utf-8")
            (tmproot / "SYMBIOSE_Tutorial.html").write_text("<!-- tutorial -->", encoding="utf-8")
            (tmproot / "headless_autobot.js").write_text("const missing = require('./ghost.js');", encoding="utf-8")

            manifest = ["bitget_relay.py", "start.py", "Symbiose_Dashboard.html", "SYMBIOSE_Tutorial.html", "headless_autobot.js", "ghost.js"]
            df_content = "COPY bitget_relay.py .\nCOPY start.py .\nCOPY Symbiose_Dashboard.html .\nCOPY SYMBIOSE_Tutorial.html .\nCOPY headless_autobot.js .\nCOPY ghost.js ."

            status, detail_json = rc.check_runtime_packaging_closure(
                tmproot, manifest_list=manifest, dockerfile_content=df_content
            )
            detail = json.loads(detail_json)
            self.assertEqual(status, "FAIL")
            self.assertIn("ghost.js", detail.get("missing_on_disk", []))

    def test_missing_python_dependency_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmproot = Path(tmpdir)
            fixtures = {
                "bitget_relay.py": "from scripts.state_migration import migrate_state_directory\n",
                "start.py": "# desktop\n",
                "Symbiose_Dashboard.html": "<!-- dashboard -->\n",
                "SYMBIOSE_Tutorial.html": "<!-- tutorial -->\n",
                "headless_autobot.js": "// runner\n",
                "scripts/state_migration.py": "from scripts.missing_runtime import helper\n",
                "scripts/ops/aura_state_migrate.py": "from scripts.state_migration import migrate_state_directory\n",
            }
            for rel, content in fixtures.items():
                path = tmproot / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            manifest = list(fixtures)
            dockerfile = "\n".join(f"COPY {rel} /app/{rel}" for rel in fixtures)
            status, detail_json = rc.check_runtime_packaging_closure(
                tmproot, manifest_list=manifest, dockerfile_content=dockerfile
            )
            detail = json.loads(detail_json)
            self.assertEqual(status, "FAIL")
            self.assertIn("scripts/missing_runtime.py", detail.get("missing_on_disk", []))

    def test_extract_js_relative_dependencies(self):
        sample = """
        const foo = require('./utils/math.js');
        const bar = require('../config.json');
        import helper from './helper';
        const external = require('express');
        """
        deps = rc.extract_js_relative_dependencies(sample)
        self.assertEqual(deps, ["../config.json", "./helper", "./utils/math.js"])


if __name__ == "__main__":
    unittest.main()
