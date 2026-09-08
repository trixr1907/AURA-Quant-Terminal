import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("symbiose_start", ROOT / "start.py")
launcher = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(launcher)


class LauncherDependencyTests(unittest.TestCase):
    def test_windows_bootstrap_is_utf8_bom_for_powershell_51(self):
        data = (ROOT / "bootstrap.ps1").read_bytes()
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        self.assertIn("Prüfe Systemvoraussetzungen".encode("utf-8"), data)

    def test_playwright_probe_does_not_raise_expected_import_traceback(self):
        script = (ROOT / "bootstrap.ps1").read_text(encoding="utf-8-sig")
        self.assertNotIn('-c "import playwright"', script)
        self.assertIn("importlib.util.find_spec('playwright')", script)
        self.assertIn("$global:LASTEXITCODE = 0", script)

    def test_windows_batch_launcher_uses_ascii_only(self):
        data = (ROOT / "START.bat").read_bytes()
        self.assertTrue(all(byte < 128 for byte in data))

    def test_windows_batch_uses_absolute_system_powershell_path(self):
        script = (ROOT / "START.bat").read_text(encoding="ascii")
        self.assertIn(r"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe", script)
        self.assertNotIn("\npowershell.exe ", script)

    def test_cli_batch_uses_absolute_system_powershell_path(self):
        script = (ROOT / "START_OHNE_GUI.bat").read_text(encoding="ascii")
        self.assertIn(r"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe", script)
        self.assertNotIn("\npowershell.exe ", script)

    def test_windows_batch_quotes_the_absolute_powershell_executable(self):
        script = (ROOT / "START.bat").read_text(encoding="ascii")
        self.assertIn('"%POWERSHELL%" -NoLogo -NoProfile', script)
        self.assertIn('if not exist "%POWERSHELL%"', script)

    def test_node_bootstrap_has_official_portable_fallback_without_winget(self):
        script = (ROOT / "bootstrap.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("https://nodejs.org/dist/index.json", script)
        self.assertIn("SHASUMS256.txt", script)
        self.assertIn("Get-FileHash", script)
        self.assertIn("Get-AuthenticodeSignature", script)
        self.assertNotIn('Node.js fehlt und winget ist nicht verfügbar', script)

    def test_local_node_runtime_is_added_to_path(self):
        script = (ROOT / "bootstrap.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('Join-Path $Root ".runtime\\node\\node.exe"', script)
        self.assertIn('$env:Path = "$NodeDir;$env:Path"', script)
        self.assertIn('$env:SYM_NODE = $script:NodeExecutable', script)

    def test_dependency_plan_detects_missing_node_and_optional_python_modules(self):
        with mock.patch.dict(launcher.os.environ, {}, clear=True), \
             mock.patch.object(launcher.shutil, "which", return_value=None), \
             mock.patch.object(launcher.importlib.util, "find_spec", return_value=None):
            plan = launcher.dependency_plan()
        self.assertIn("node", plan["missing_required"])
        self.assertIn("playwright", plan["missing_optional"])

    def test_dependency_plan_requires_no_external_runtime_for_core_app(self):
        def which(name):
            return "/usr/bin/node" if name == "node" else None

        with mock.patch.dict(launcher.os.environ, {}, clear=True), \
             mock.patch.object(launcher.shutil, "which", side_effect=which), \
             mock.patch.object(launcher.importlib.util, "find_spec", return_value=object()):
            plan = launcher.dependency_plan()
        self.assertEqual([], plan["missing_required"])
        self.assertEqual([], plan["missing_optional"])

    def test_dependency_plan_accepts_verified_node_path_from_bootstrap(self):
        with tempfile.TemporaryDirectory() as td:
            node = Path(td) / "node.exe"
            node.write_bytes(b"fake executable for path resolution test")
            with mock.patch.dict(launcher.os.environ, {"SYM_NODE": str(node)}, clear=True), \
                 mock.patch.object(launcher.shutil, "which", return_value=None), \
                 mock.patch.object(launcher.importlib.util, "find_spec", return_value=object()):
                plan = launcher.dependency_plan()
            self.assertEqual([], plan["missing_required"])

    def test_dependency_plan_accepts_verified_node_path_from_windows_bootstrap(self):
        with tempfile.TemporaryDirectory() as td:
            node = Path(td) / "node.exe"
            node.write_bytes(b"fake executable for Windows path-resolution test")
            with mock.patch.dict(launcher.os.environ, {"SYM_NODE": str(node)}, clear=True), \
                 mock.patch.object(launcher.shutil, "which", return_value=None), \
                 mock.patch.object(launcher.importlib.util, "find_spec", return_value=object()):
                plan = launcher.dependency_plan()
            self.assertEqual([], plan["missing_required"])

    def test_dependency_plan_rejects_missing_configured_node_path_on_windows(self):
        missing = str(ROOT / ".runtime" / "node" / "missing-node.exe")
        with mock.patch.dict(launcher.os.environ, {"SYM_NODE": missing}, clear=True), \
             mock.patch.object(launcher.shutil, "which", return_value=None), \
             mock.patch.object(launcher.importlib.util, "find_spec", return_value=object()):
            plan = launcher.dependency_plan()
        self.assertEqual(["node"], plan["missing_required"])

    def test_release_scan_excludes_project_local_runtime(self):
        script = (ROOT / "scripts" / "release_check.py").read_text(encoding="utf-8")
        self.assertIn('RUNTIME_DIR_NAMES = {".runtime", ".venv"}', script)
        self.assertIn("is_runtime_path(path)", script)

    def test_release_subprocesses_use_explicit_utf8(self):
        script = (ROOT / "scripts" / "release_check.py").read_text(encoding="utf-8")
        self.assertIn('child_env["PYTHONIOENCODING"] = "utf-8"', script)
        self.assertIn('encoding="utf-8"', script)

    def test_run_command_enforces_utf8_child_output_on_windows(self):
        source = (ROOT / "start.py").read_text(encoding="utf-8")
        self.assertIn('env["PYTHONIOENCODING"] = "utf-8"', source)
        self.assertIn('env["PYTHONUTF8"] = "1"', source)

    def test_start_relay_enforces_utf8_child_environment(self):
        captured = {}

        def fake_popen(*args, **kwargs):
            captured["env"] = kwargs["env"]

            class Proc:
                def poll(self):
                    return 0

            return Proc()

        with mock.patch.object(launcher, "check_relay_health", return_value=None), \
             mock.patch.object(launcher.subprocess, "Popen", side_effect=fake_popen):
            self.assertFalse(launcher.start_relay(log=lambda _message: None))

        self.assertEqual("utf-8", captured["env"]["PYTHONIOENCODING"])
        self.assertEqual("1", captured["env"]["PYTHONUTF8"])

    def test_gui_mode_can_be_forced_off_for_reliable_cli_fallback(self):
        with mock.patch.dict(launcher.os.environ, {"SYM_NO_GUI": "1"}, clear=False):
            self.assertFalse(launcher.gui_available())

    def test_gui_mode_is_available_when_tkinter_imports(self):
        fake_tk = object()
        with mock.patch.dict(launcher.os.environ, {}, clear=True), \
             mock.patch.object(launcher, "load_tkinter", return_value=(fake_tk, object(), object())):
            self.assertTrue(launcher.gui_available())

    def test_launcher_describes_actions_below_buttons_in_grid_layout(self):
        source = (ROOT / "start.py").read_text(encoding="utf-8")
        self.assertIn(".grid(", source)
        self.assertIn("def action_card(", source)
        self.assertIn('action_card(2, "Universum updaten",', source)
        self.assertIn('action_card(3, "System prüfen",', source)
        self.assertNotIn('Coin-Universum updaten (Bitget Liste laden)\\\\n', source)
        self.assertNotIn('System prüfen\\\\n', source)

    def test_gui_failure_after_browser_open_does_not_open_dashboard_twice(self):
        def failing_gui():
            launcher.open_dashboard()
            raise RuntimeError("GUI loop failed")

        setattr(launcher, "DASHBOARD_OPENED", False)
        with mock.patch.object(launcher, "start_relay", return_value=True), \
             mock.patch.object(launcher, "gui_available", return_value=True), \
             mock.patch.object(launcher, "run_gui", side_effect=failing_gui), \
             mock.patch.object(launcher.webbrowser, "open", return_value=True) as browser_open, \
             mock.patch("builtins.input", return_value="q"):
            self.assertEqual(0, launcher.main())
        browser_open.assert_called_once_with(f"{launcher.BASE_URL}/")
        setattr(launcher, "DASHBOARD_OPENED", False)

    def test_universe_snapshot_is_stale_after_24_hours(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "universe.json"
            path.write_text(json.dumps({"synced_at": "2020-01-01T00:00:00Z"}), encoding="utf-8")
            self.assertTrue(launcher.universe_snapshot_is_stale(path, max_age_hours=24))

    def test_universe_snapshot_is_stale_when_missing(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertTrue(launcher.universe_snapshot_is_stale(Path(td) / "missing.json"))


if __name__ == "__main__":
    unittest.main()
