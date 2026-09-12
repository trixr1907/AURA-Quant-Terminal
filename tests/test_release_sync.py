#!/usr/bin/env python3
"""Regression tests for TEIL 3: honest release gate + Bitget-first data sync."""
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import release_check  # noqa: E402
import sync_market_data  # noqa: E402

BUILD_PACKAGE_SPEC = importlib.util.spec_from_file_location(
    "build_package", SCRIPTS / "build_package.py"
)
build_package = importlib.util.module_from_spec(BUILD_PACKAGE_SPEC)
assert BUILD_PACKAGE_SPEC.loader is not None
BUILD_PACKAGE_SPEC.loader.exec_module(build_package)


class TestSyncMarketDataSafety(unittest.TestCase):
    """sync_market_data safety: refuses JS Golden-Master score generation."""

    def test_golden_only_flag_exits_nonzero_with_clear_message(self):
        with mock.patch("sys.argv", ["sync_market_data.py", "--golden-only"]):
            rc = sync_market_data.main()
            self.assertNotEqual(rc, 0)


class TestPackageRuntimeStateExclusion(unittest.TestCase):
    """Release archives must never contain generated user runtime state."""

    RUNTIME_STATE_VARIANTS = (
        "aura_shared_state.json",
        "aura_shared_state.json.tmp",
        "aura_shared_state.tmp",
        "aura_shared_state.json.bak",
    )

    def test_real_manifest_only_collects_the_explicit_static_dataset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data = root / "data"
            data.mkdir()
            (data / "bitget_usdt_futures_universe.json").write_text(
                "harmless universe sentinel", encoding="utf-8"
            )
            (data / "unlisted_fixture.json").write_text(
                "harmless unlisted sentinel", encoding="utf-8"
            )
            with mock.patch.object(build_package, "ROOT", root):
                files = build_package.collect_files()
            self.assertEqual(files, ["data/bitget_usdt_futures_universe.json"])

    def test_runtime_state_family_is_excluded_from_collection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data = root / "data"
            data.mkdir()
            for variant in self.RUNTIME_STATE_VARIANTS:
                (data / variant).write_text("harmless runtime sentinel", encoding="utf-8")
            with mock.patch.object(build_package, "ROOT", root), mock.patch.object(
                build_package, "MANIFEST", ["data/"]
            ):
                files = build_package.collect_files()
            self.assertEqual(files, [])

    def test_explicit_static_dataset_remains_in_normal_package(self):
        self.assertIn("data/bitget_usdt_futures_universe.json", build_package.collect_files())

    def test_archive_builder_rejects_every_runtime_state_family_variant(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data = root / "data"
            data.mkdir()
            for variant in self.RUNTIME_STATE_VARIANTS:
                (data / variant).write_text("harmless runtime sentinel", encoding="utf-8")
            with mock.patch.object(build_package, "ROOT", root):
                for variant in self.RUNTIME_STATE_VARIANTS:
                    with self.subTest(variant=variant), self.assertRaises(ValueError):
                        build_package.build_archive([f"data/{variant}"], root / "out.zip")

    def test_allowed_static_dataset_can_be_archived(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data = root / "data"
            data.mkdir()
            fixture = data / "bitget_usdt_futures_universe.json"
            fixture.write_text("harmless universe sentinel", encoding="utf-8")
            output = root / "out.zip"
            with mock.patch.object(build_package, "ROOT", root):
                build_package.build_archive(["data/bitget_usdt_futures_universe.json"], output)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.namelist(), ["data/bitget_usdt_futures_universe.json"])

    def test_archive_builder_rejects_unknown_file_outside_explicit_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data = root / "data"
            data.mkdir()
            (data / "bitget_usdt_futures_universe.json").write_text(
                "harmless universe sentinel", encoding="utf-8"
            )
            (data / "secret_fixture.json").write_text(
                "harmless unknown sentinel", encoding="utf-8"
            )
            with mock.patch.object(
                build_package, "ROOT", root
            ), mock.patch.object(
                build_package, "MANIFEST", ["data/bitget_usdt_futures_universe.json"]
            ):
                with self.assertRaises(ValueError):
                    build_package.build_archive(["data/secret_fixture.json"], root / "out.zip")

    def test_archive_builder_accepts_safe_child_of_manifest_directory_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            tests_dir = root / "tests"
            data_dir = root / "data"
            tests_dir.mkdir()
            data_dir.mkdir()
            (tests_dir / "fixture.txt").write_text("harmless child sentinel", encoding="utf-8")
            (data_dir / "outside.txt").write_text("harmless outside sentinel", encoding="utf-8")
            with mock.patch.object(build_package, "ROOT", root), mock.patch.object(
                build_package, "MANIFEST", ["tests/"]
            ):
                output = root / "out.zip"
                build_package.build_archive(["tests/fixture.txt"], output)
                with zipfile.ZipFile(output) as archive:
                    self.assertEqual(archive.namelist(), ["tests/fixture.txt"])
                with self.assertRaises(ValueError):
                    build_package.build_archive(["data/outside.txt"], root / "outside.zip")

    def test_archive_builder_rejects_runtime_state_even_if_list_is_tampered(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data = root / "data"
            data.mkdir()
            state = data / "aura_shared_state.json"
            state.write_text("harmless runtime sentinel", encoding="utf-8")
            with mock.patch.object(build_package, "ROOT", root):
                with self.assertRaises(ValueError):
                    build_package.build_archive(["data/aura_shared_state.json"], root / "out.zip")


class TestPackagePathSafety(unittest.TestCase):
    """Package sources must stay inside ROOT and never traverse symlinks."""

    def test_parent_traversal_manifest_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            root = workspace / "root"
            root.mkdir()
            outside = workspace / "outside.txt"
            outside.write_text("harmless traversal fixture", encoding="utf-8")
            with mock.patch.object(build_package, "ROOT", root):
                with self.assertRaises(ValueError):
                    build_package.build_archive(["../outside.txt"], root / "out.zip")

    def test_absolute_manifest_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            root = workspace / "root"
            root.mkdir()
            outside = workspace / "absolute.txt"
            outside.write_text("harmless absolute-path fixture", encoding="utf-8")
            with mock.patch.object(build_package, "ROOT", root):
                with self.assertRaises(ValueError):
                    build_package.build_archive([str(outside)], root / "out.zip")

    def test_symlink_file_is_excluded_from_collection_and_rejected_if_injected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            root = workspace / "root"
            data = root / "data"
            data.mkdir(parents=True)
            outside = workspace / "outside.txt"
            outside.write_text("harmless symlink fixture", encoding="utf-8")
            link = data / "linked.txt"
            link.symlink_to(outside)
            fixture = data / "market_fixture.json"
            fixture.write_text("fixture", encoding="utf-8")
            with mock.patch.object(build_package, "ROOT", root), mock.patch.object(
                build_package, "MANIFEST", ["data/"]
            ):
                files = build_package.collect_files()
                self.assertNotIn("data/linked.txt", files)
                self.assertIn("data/market_fixture.json", files)
                with self.assertRaises(ValueError):
                    build_package.build_archive(["data/linked.txt"], root / "out.zip")

    def test_symlink_directory_is_not_traversed_or_packaged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            root = workspace / "root"
            data = root / "data"
            data.mkdir(parents=True)
            outside = workspace / "external-data"
            outside.mkdir()
            (outside / "leak.txt").write_text("harmless symlink-dir fixture", encoding="utf-8")
            (data / "linked-dir").symlink_to(outside, target_is_directory=True)
            with mock.patch.object(build_package, "ROOT", root), mock.patch.object(
                build_package, "MANIFEST", ["data/"]
            ):
                files = build_package.collect_files()
            self.assertNotIn("data/linked-dir/leak.txt", files)
            self.assertNotIn("data/linked-dir", files)

    def test_normal_fixture_remains_allowed_and_archive_name_is_normalized(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data = root / "data"
            data.mkdir()
            fixture = data / "market_fixture.json"
            fixture.write_text("fixture", encoding="utf-8")
            output = root / "out.zip"
            with mock.patch.object(build_package, "ROOT", root), mock.patch.object(
                build_package, "MANIFEST", ["data/"]
            ):
                build_package.build_archive(["data/./market_fixture.json"], output)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.namelist(), ["data/market_fixture.json"])


class TestVersionConsistencyFailClosed(unittest.TestCase):
    """Version check must be fail-closed across release artifacts."""

    def test_current_release_version_is_synchronized(self):
        expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertRegex(expected, r"^\d+\.\d+\.\d+$")
        sources = {
            "VERSION": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
            "relay": (ROOT / "bitget_relay.py").read_text(encoding="utf-8"),
            "README": (ROOT / "README.md").read_text(encoding="utf-8"),
            "dashboard": (ROOT / "Symbiose_Dashboard.html").read_text(encoding="utf-8"),
            "tutorial": (ROOT / "SYMBIOSE_Tutorial.html").read_text(encoding="utf-8"),
            "Dockerfile": (ROOT / "Dockerfile").read_text(encoding="utf-8"),
        }
        self.assertEqual(sources["VERSION"], expected)
        for name in ("relay", "README", "dashboard", "tutorial", "Dockerfile"):
            with self.subTest(name=name):
                self.assertIn(expected, sources[name])

    def test_stale_tutorial_and_pine_current_metadata_fails(self):
        status, detail = release_check.check_version_consistency(
            'const meta = { "version": "1.0.7" };', '# AURA v1.0.7 - Architecture',
            '<span>AURA Quant Terminal v1.0.7</span>',
            '<nav><span class="nav-logo">AURA v1.0.3</span></nav><h1>AURA v1.0.7</h1><footer>AURA v1.0.7</footer>',
            '// AURA v1.0.7 — Header\nf_hdr(0, "AURA v1.0.3")\njsn = \'{"type":"symbiose.v1.0.7"}\'',
        )
        self.assertEqual(status, "FAIL")
        self.assertIn("tutorial navigation", detail)

    def test_missing_dashboard_version_fails(self):
        relay_src = 'const meta = { "version": "1.0.0" };'
        readme = '# AURA v1.0.0 - Architecture'
        dashboard = '<div>No version here</div>'
        status, detail = release_check.check_version_consistency(relay_src, readme, dashboard)
        self.assertEqual(status, "FAIL")
        parsed = json.loads(detail)
        self.assertIsNone(parsed["versions"]["dashboard footer"])
        self.assertEqual(parsed["error"], "missing version")

    def test_missing_relay_version_fails(self):
        relay_src = 'const meta = {};'
        readme = '# AURA v1.0.0 - Architecture'
        dashboard = '<span id="ft-v">AURA Quant Terminal v1.0.0</span>'
        status, detail = release_check.check_version_consistency(relay_src, readme, dashboard)
        self.assertEqual(status, "FAIL")
        parsed = json.loads(detail)
        self.assertIsNone(parsed["versions"]["relay /serving"])
        self.assertEqual(parsed["error"], "missing version")

    def test_missing_readme_version_fails(self):
        relay_src = 'const meta = { "version": "1.0.0" };'
        readme = 'No header version'
        dashboard = '<span id="ft-v">AURA Quant Terminal v1.0.0</span>'
        status, detail = release_check.check_version_consistency(relay_src, readme, dashboard)
        self.assertEqual(status, "FAIL")
        parsed = json.loads(detail)
        self.assertIsNone(parsed["versions"]["README header"])
        self.assertEqual(parsed["error"], "missing version")

    def test_version_mismatch_fails(self):
        relay_src = 'const meta = { "version": "0.9.0" };'
        readme = '# AURA v1.0.0 - Architecture'
        dashboard = '<span id="ft-v">AURA Quant Terminal v1.0.0</span>'
        status, detail = release_check.check_version_consistency(relay_src, readme, dashboard)
        self.assertEqual(status, "FAIL")
        parsed = json.loads(detail)
        self.assertEqual(parsed["error"], "mismatched versions")

    def test_all_versions_matching_passes(self):
        relay_src = 'const meta = { "version": "1.0.0" };'
        readme = '# AURA v1.0.0 - Architecture'
        dashboard = '<span id="ft-v">AURA Quant Terminal v1.0.0</span>'
        status, detail = release_check.check_version_consistency(relay_src, readme, dashboard)
        self.assertEqual(status, "PASS")
        parsed = json.loads(detail)
        self.assertEqual(parsed["versions"]["relay /serving"], "1.0.0")
        self.assertEqual(parsed["versions"]["README header"], "1.0.0")
        self.assertEqual(parsed["versions"]["dashboard footer"], "1.0.0")

class TestVersionProgression(unittest.TestCase):
    def test_two_component_version_is_rejected(self):
        status, _ = release_check.check_version_progression("1.4", None, False)
        self.assertEqual(status, "FAIL")

    def test_update_without_bump_is_rejected(self):
        status, detail = release_check.check_version_progression("1.0.0", "v1.0.0", True)
        self.assertEqual(status, "FAIL")
        self.assertIn("version bump required", detail)

    def test_patch_increment_is_accepted(self):
        status, _ = release_check.check_version_progression("1.0.1", "v1.0.0", True)
        self.assertEqual(status, "PASS")

    def test_latest_semver_tag_uses_highest_version_not_input_order(self):
        refs = "\n".join([
            "deadbeef\trefs/tags/v1.2.5",
            "deadbeef\trefs/tags/v1.2.3",
            "deadbeef\trefs/tags/not-semver",
            "deadbeef\trefs/tags/v1.2.4^{}",
        ])
        self.assertEqual(release_check.latest_semver_tag_from_refs(refs), "v1.2.5")

    def test_remote_tag_state_is_used_to_detect_a_stale_local_clone(self):
        responses = [
            (0, "v1.2.2\n", ""),
            (0, "abc\trefs/tags/v1.2.5\n", ""),
        ]
        with mock.patch.object(release_check, "run", side_effect=responses):
            local_tag, remote_tag, error = release_check.inspect_version_tag_state()
        self.assertEqual(local_tag, "v1.2.2")
        self.assertEqual(remote_tag, "v1.2.5")
        self.assertIsNone(error)

    def test_remote_tag_lookup_failure_is_fail_closed_metadata(self):
        responses = [
            (0, "v1.2.2\n", ""),
            (1, "", "network unavailable"),
        ]
        with mock.patch.object(release_check, "run", side_effect=responses):
            local_tag, remote_tag, error = release_check.inspect_version_tag_state()
        self.assertEqual(local_tag, "v1.2.2")
        self.assertIsNone(remote_tag)
        self.assertIn("network unavailable", error)


class TestGoldenMasterAuthenticity(unittest.TestCase):
    """Golden Master authenticity must fail-closed with machine-readable provenance."""

    def test_local_self_comparison_pattern_rejected(self):
        header = "timestamp,open,high,low,close,volume,GM Trend Score,GM Momentum Score,GM Volume Score,GM Structure Score,GM Core Score"
        rows = [header]
        for i in range(250):
            ts = 1600000000000 + i * 3600000
            if i < 235:
                rows.append(f"{ts},100.0,105.0,99.0,102.0,1000.0,50.00,50.00,50.00,50.00,50.00")
            else:
                rows.append(f"{ts},100.0,105.0,99.0,102.0,1000.0,55.20,62.10,48.30,51.00,54.15")
        csv_content = "\n".join(rows)

        is_self_comp, reason = release_check.is_self_comparison_csv(csv_content)
        self.assertTrue(is_self_comp)
        self.assertIn("matches known local self-comparison generator pattern", reason)

    def test_plausible_external_csv_with_warmup_na_accepted_by_pattern_check(self):
        header = "timestamp,open,high,low,close,volume,GM Trend Score,GM Momentum Score,GM Volume Score,GM Structure Score,GM Core Score"
        rows = [header]
        for i in range(250):
            ts = 1600000000000 + i * 3600000
            if i < 50:
                rows.append(f"{ts},100.0,105.0,99.0,102.0,1000.0,na,na,na,na,na")
            else:
                rows.append(f"{ts},100.0,105.0,99.0,102.0,1000.0,55.20,62.10,48.30,51.00,54.15")
        csv_content = "\n".join(rows)

        is_self_comp, reason = release_check.is_self_comparison_csv(csv_content)
        self.assertFalse(is_self_comp)
        self.assertIn("contains na/NaN/empty score cells", reason)

    def test_missing_provenance_returns_nogo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            files = ["BTCUSDT_1h.csv"]
            (td / "BTCUSDT_1h.csv").write_text("timestamp,open,high,low,close,volume\n1,2,3,4,5,6\n", encoding="utf-8")
            status, detail = release_check.verify_golden_authenticity(td, files)
            self.assertEqual(status, "NO-GO")
            self.assertIn("GOLDEN_MASTER_UNVERIFIED", detail)
            self.assertIn("missing provenance manifest", detail)

    def test_invalid_source_returns_nogo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            files = ["BTCUSDT_1h.csv"]
            csv_path = td / "BTCUSDT_1h.csv"
            csv_path.write_text("timestamp,open,high,low,close,volume\n1,2,3,4,5,6\n", encoding="utf-8")
            sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()
            prov = {
                "BTCUSDT_1h.csv": {
                    "sha256": sha,
                    "source": "unauthorized_generator_or_random_source",
                    "export_time": "2026-09-04T12:00:00Z",
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                }
            }
            (td / "provenance.json").write_text(json.dumps(prov), encoding="utf-8")
            status, detail = release_check.verify_golden_authenticity(td, files)
            self.assertEqual(status, "NO-GO")
            self.assertIn("GOLDEN_MASTER_UNVERIFIED", detail)
            self.assertIn("untrusted provenance source", detail)

    def test_hash_mismatch_returns_nogo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            files = ["BTCUSDT_1h.csv"]
            csv_path = td / "BTCUSDT_1h.csv"
            csv_path.write_text("timestamp,open,high,low,close,volume\n1,2,3,4,5,6\n", encoding="utf-8")
            prov = {
                "BTCUSDT_1h.csv": {
                    "sha256": "0" * 64,
                    "source": "TradingView/Pine",
                    "export_time": "2026-09-04T12:00:00Z",
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                }
            }
            (td / "provenance.json").write_text(json.dumps(prov), encoding="utf-8")
            status, detail = release_check.verify_golden_authenticity(td, files)
            self.assertEqual(status, "NO-GO")
            self.assertIn("GOLDEN_MASTER_UNVERIFIED", detail)
            self.assertIn("sha256 mismatch", detail)

    def test_synthetic_valid_provenance_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            files = ["BTCUSDT_1h.csv", "ETHUSDT_1h.csv"]
            prov = {}
            for f in files:
                csv_path = td / f
                # Genuine-looking export with warmup na to avoid self-comp heuristic trigger
                lines = ["timestamp,open,high,low,close,volume,GM Trend Score,GM Momentum Score,GM Volume Score,GM Structure Score,GM Core Score"]
                for i in range(10):
                    lines.append(f"{1600000000000 + i * 3600000},100,105,95,102,1000,na,na,na,na,na")
                csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()
                sym = f.split("_")[0]
                tf = f.split("_")[1].replace(".csv", "")
                prov[f] = {
                    "sha256": sha,
                    "source": "TradingView/Pine",
                    "export_time": "2026-09-04T12:00:00Z",
                    "symbol": sym,
                    "timeframe": tf,
                }
            (td / "provenance.json").write_text(json.dumps(prov), encoding="utf-8")
            status, detail = release_check.verify_golden_authenticity(td, files)
            self.assertEqual(status, "PASS")
            self.assertIn("all golden master fixtures verified with independent provenance", detail)

    def test_self_comparison_fixture_rejected_despite_matching_hash_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            files = ["BTCUSDT_1h.csv"]
            csv_path = td / "BTCUSDT_1h.csv"
            # Build self-comparison pattern with 235 rows of 50.00
            header = "timestamp,open,high,low,close,volume,GM Trend Score,GM Momentum Score,GM Volume Score,GM Structure Score,GM Core Score"
            rows = [header]
            for i in range(250):
                ts = 1600000000000 + i * 3600000
                if i < 235:
                    rows.append(f"{ts},100.0,105.0,99.0,102.0,1000.0,50.00,50.00,50.00,50.00,50.00")
                else:
                    rows.append(f"{ts},100.0,105.0,99.0,102.0,1000.0,55.20,62.10,48.30,51.00,54.15")
            csv_path.write_text("\n".join(rows), encoding="utf-8")
            sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()
            prov = {
                "BTCUSDT_1h.csv": {
                    "sha256": sha,
                    "source": "TradingView/Pine",
                    "export_time": "2026-09-04T12:00:00Z",
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                }
            }
            (td / "provenance.json").write_text(json.dumps(prov), encoding="utf-8")
            status, detail = release_check.verify_golden_authenticity(td, files)
            self.assertEqual(status, "NO-GO")
            self.assertIn("GOLDEN_MASTER_UNVERIFIED", detail)
            self.assertIn("self-comparison fixture detected", detail)

    def test_verify_golden_authenticity_passes_for_current_fixtures(self):
        """After real TradingView exports + provenance.json are in place, the gate must PASS."""
        status, detail = release_check.verify_golden_authenticity(
            release_check.GOLDEN_DIR, release_check.GOLDEN_FILES
        )
        self.assertEqual(status, "PASS", f"Golden master gate unexpectedly failed: {detail}")

    def test_invalid_lockbox_metadata_returns_nogo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            td = Path(tmpdir)
            files = ["BTCUSDT_1h.csv"]
            csv_path = td / "BTCUSDT_1h.csv"
            lines = ["timestamp,open,high,low,close,volume,GM Trend Score,GM Momentum Score,GM Volume Score,GM Structure Score,GM Core Score"]
            for i in range(10):
                lines.append(f"{1600000000000 + i * 3600000},100,105,95,102,1000,na,na,na,na,na")
            csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()
            prov = {
                "lockbox": {
                    "description": "missing cutoff_time and locked_span_days"
                },
                "BTCUSDT_1h.csv": {
                    "sha256": sha,
                    "source": "TradingView/Pine",
                    "export_time": "2026-09-04T12:00:00Z",
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                }
            }
            (td / "provenance.json").write_text(json.dumps(prov), encoding="utf-8")
            status, detail = release_check.verify_golden_authenticity(td, files)
            self.assertEqual(status, "NO-GO")
            self.assertIn("lockbox entry missing required cutoff_time, locked_span_days, status=LOCKED, or mode=forward_holdout", detail)

    def test_summary_reports_real_model_verdict_and_synthetic_label(self):
        """Release summary must separate real model evidence verdict from synthetic sensitivity fixture integrity."""
        real_status, real_detail, real_verdict = release_check.run_model_evidence_real_gate()
        self.assertEqual(real_status, "PASS")
        self.assertEqual(real_verdict, "NO_EVIDENCE")

        sens_status, sens_detail, sens_release = release_check.run_sensitivity_gate()
        self.assertEqual(sens_status, "PASS")
        self.assertEqual(sens_release, "PAPER_CANDIDATE")

        results = [{"status": "PASS"}]
        verdict = release_check.compute_verdict(results, model_no_evidence=(real_verdict == "NO_EVIDENCE"))
        self.assertEqual(verdict, "SOFTWARE_GO / MODEL_NO_EVIDENCE")

        summary_line = f"VERDICT: SOFTWARE_GO / MODEL_{real_verdict} (real) · synthetic-gate: {sens_release}"
        self.assertIn("MODEL_NO_EVIDENCE (real)", summary_line)
        self.assertIn("synthetic-gate: PAPER_CANDIDATE", summary_line)
        self.assertNotIn("MODEL_PAPER_CANDIDATE", summary_line)


class TestReleaseWorkflowDependencies(unittest.TestCase):
    """The release runner must prepare the browser gate before fail-closed checks."""

    WORKFLOW = ROOT / ".github" / "workflows" / "publish-release.yml"

    def test_pinned_playwright_and_chromium_system_dependencies_precede_release_gate(self):
        workflow = self.WORKFLOW.read_text(encoding="utf-8")
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

        self.assertRegex(requirements, r"(?m)^playwright==[^\s]+$")
        action_refs = re.findall(r"uses:\s+(actions/[^@\s]+)@([0-9a-f]{40})", workflow)
        self.assertIn("actions/checkout", {name for name, _ in action_refs})
        self.assertIn("actions/setup-python", {name for name, _ in action_refs})
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", sha) for _, sha in action_refs))
        self.assertIn(
            "python3 -m pip install --disable-pip-version-check -r requirements.txt",
            workflow,
        )
        self.assertIn("python3 -m playwright install --with-deps chromium", workflow)
        self.assertIn("python3 scripts/release_check.py --allow-current-version", workflow)

        checkout = workflow.index("actions/checkout@")
        setup = workflow.index("actions/setup-python@")
        dependencies = workflow.index("python3 -m pip install")
        browser = workflow.index("python3 -m playwright install --with-deps chromium")
        release_check = workflow.index("python3 scripts/release_check.py")
        publish = workflow.index("gh release create")

        self.assertLess(checkout, setup)
        self.assertLess(setup, dependencies)
        self.assertLess(dependencies, browser)
        self.assertLess(browser, release_check)
        self.assertLess(release_check, publish)


class TestHonestReleaseVerdict(unittest.TestCase):
    """release_check must never emit a clean GO when the model has no edge."""

    def test_compute_verdict_no_evidence_is_not_go(self):
        results = [{"name": "engine suite", "status": "PASS", "detail": ""}]
        verdict = release_check.compute_verdict(results, model_no_evidence=True)
        self.assertEqual(verdict, "SOFTWARE_GO / MODEL_NO_EVIDENCE")

    def test_compute_verdict_go_only_when_clean_and_evidence(self):
        results = [{"name": "engine suite", "status": "PASS", "detail": ""}]
        verdict = release_check.compute_verdict(results, model_no_evidence=False)
        self.assertEqual(verdict, "GO")

    def test_compute_verdict_warn_is_not_go(self):
        self.assertEqual(release_check.compute_verdict([{"name": "hygiene", "status": "WARN"}]), "WARN")
        self.assertNotEqual(release_check.compute_verdict([{"name": "pass", "status": "PASS"}, {"name": "warn", "status": "WARN"}]), "GO")

    def test_compute_verdict_conditional_is_not_go(self):
        results = [{"name": "browser", "status": "CONDITIONAL", "detail": ""}]
        self.assertEqual(release_check.compute_verdict(results), "CONDITIONAL")

    def test_compute_verdict_no_go_is_preserved(self):
        results = [{"name": "golden", "status": "NO-GO", "detail": ""}]
        self.assertEqual(release_check.compute_verdict(results), "NO-GO")

    def test_compute_verdict_unknown_or_missing_status_fails_closed(self):
        self.assertNotEqual(release_check.compute_verdict([{"name": "x"}]), "GO")
        self.assertNotEqual(release_check.compute_verdict([{"name": "x", "status": "UNKNOWN"}]), "GO")

    def test_exit_code_for_verdict_accepts_software_go_and_rejects_fails(self):
        for verdict in ("GO", "SOFTWARE_GO", "SOFTWARE_GO / MODEL_NO_EVIDENCE"):
            with self.subTest(verdict=verdict):
                self.assertEqual(release_check.exit_code_for_verdict(verdict), 0)
        for verdict in ("FAIL", "NO-GO", "CONDITIONAL", "UNKNOWN", None):
            with self.subTest(verdict=verdict):
                self.assertNotEqual(release_check.exit_code_for_verdict(verdict), 0)

    def test_package_guard_accepts_software_go_and_rejects_fails(self):
        for verdict in ("GO", "SOFTWARE_GO", "SOFTWARE_GO / MODEL_NO_EVIDENCE"):
            with self.subTest(verdict=verdict):
                self.assertTrue(build_package.verdict_allows_packaging(verdict))
        for verdict in ("FAIL", "NO-GO", "CONDITIONAL", "UNKNOWN", None):
            with self.subTest(verdict=verdict):
                self.assertFalse(build_package.verdict_allows_packaging(verdict))

    def test_parse_sensitivity_no_evidence(self):
        report = json.dumps({"release": "NO_EVIDENCE", "reasons": ["expectancy -0.010R <= 0"]})
        parsed = release_check.parse_sensitivity_report(report)
        self.assertEqual(parsed["release"], "NO_EVIDENCE")

    def test_parse_sensitivity_invalid_json_returns_none(self):
        self.assertIsNone(release_check.parse_sensitivity_report("not json"))

    def test_classify_sensitivity_no_evidence_blocks(self):
        status, _detail = release_check.classify_sensitivity({"release": "NO_EVIDENCE", "reasons": ["x"]})
        self.assertEqual(status, "NO-GO")

    def test_classify_sensitivity_paper_candidate_passes(self):
        status, _detail = release_check.classify_sensitivity({"release": "PAPER_CANDIDATE", "reasons": []})
        self.assertEqual(status, "PASS")

    def test_classify_sensitivity_research_only_warns(self):
        status, _detail = release_check.classify_sensitivity({"release": "RESEARCH_ONLY", "reasons": ["unstable"]})
        self.assertEqual(status, "CONDITIONAL")

    def test_software_go_model_no_evidence_exits_zero_and_software_fail_exits_two(self):
        # Scenario 1: All software checks PASS, but model evidence is NO_EVIDENCE -> exit 0
        all_software_pass = [
            {"name": "engine suite", "status": "PASS", "detail": "121 passed"},
            {"name": "real data model evidence", "status": "PASS", "detail": "NO_EVIDENCE"},
        ]
        verdict = release_check.compute_verdict(all_software_pass, model_no_evidence=True)
        self.assertEqual(verdict, "SOFTWARE_GO / MODEL_NO_EVIDENCE")
        self.assertEqual(release_check.exit_code_for_verdict(verdict), 0)

        # Scenario 2: Injected software failure (e.g. test fails or secret leak) -> exit 2
        software_fail = [
            {"name": "engine suite", "status": "FAIL", "detail": "syntax error"},
            {"name": "real data model evidence", "status": "PASS", "detail": "NO_EVIDENCE"},
        ]
        fail_verdict = release_check.compute_verdict(software_fail, model_no_evidence=True)
        self.assertEqual(fail_verdict, "FAIL")
        self.assertEqual(release_check.exit_code_for_verdict(fail_verdict), 2)


    def test_reference_backtest_oracle_passes(self):
        """Require reference_backtest.py to pass with EXP-024 selection objective parity."""
        import subprocess
        res = subprocess.run([sys.executable, str(ROOT / "tests" / "reference_backtest.py")], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"reference_backtest failed: {res.stderr}\n{res.stdout}")
        self.assertIn("REFERENCE BACKTEST: ALL ASSERTIONS PASSED", res.stdout)


if __name__ == "__main__":
    unittest.main()
