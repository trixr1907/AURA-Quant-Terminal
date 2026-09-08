#!/usr/bin/env python3
"""Regression tests for TEIL 3: honest release gate + Bitget-first data sync."""
import hashlib
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import release_check  # noqa: E402
import sync_market_data  # noqa: E402


class TestSyncMarketDataSafety(unittest.TestCase):
    """sync_market_data safety: refuses JS Golden-Master score generation."""

    def test_golden_only_flag_exits_nonzero_with_clear_message(self):
        with mock.patch("sys.argv", ["sync_market_data.py", "--golden-only"]):
            rc = sync_market_data.main()
            self.assertNotEqual(rc, 0)

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

    def test_compute_verdict_fail_wins(self):
        results = [{"name": "engine suite", "status": "FAIL", "detail": ""}]
        verdict = release_check.compute_verdict(results, model_no_evidence=False)
        self.assertEqual(verdict, "FAIL")

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


if __name__ == "__main__":
    unittest.main()
