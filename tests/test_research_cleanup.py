from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class ResearchOnlyCleanupTests(unittest.TestCase):
    def test_aura_branding_replaces_legacy_product_name(self):
        legacy_names = ("SYM" + "BIOSE", "Sym" + "biose")
        ignored_parts = {".git", ".runtime", ".venv", "__pycache__", ".pytest_cache"}
        text_suffixes = {".bat", ".csv", ".html", ".js", ".json", ".md", ".pine", ".ps1", ".py", ".sh", ".txt"}
        technical_names = {
            "Symbiose_Dashboard.html",
            "Symbiose_Signal_System_v1.pine",
            "SYMBIOSE_Tutorial.html",
            "SYMBIOSE_Model_Validation.md",
            "SYMBIOSE_Reliability_Audit.md",
        }
        offenders = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in text_suffixes:
                continue
            if any(part in ignored_parts for part in path.relative_to(ROOT).parts):
                continue
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            for technical_name in technical_names:
                text = text.replace(technical_name, "")
            for legacy in legacy_names:
                if legacy in text:
                    offenders.append(f"{path.relative_to(ROOT)}: {legacy}")
        self.assertEqual([], offenders)
        self.assertTrue((ROOT / "Symbiose_Dashboard.html").is_file())

    def test_browser_harness_allows_both_binance_websocket_hosts(self):
        source = (ROOT / "tests" / "browser_research_harness.py").read_text(encoding="utf-8")
        self.assertIn("ALLOWED_WS_HOSTS", source)
        self.assertIn('"stream.binance.com"', source)
        self.assertIn('"data-stream.binance.vision"', source)
        self.assertIn("assert set(ws_hosts) <= ALLOWED_WS_HOSTS", source)

    def test_trade_tracker_contract_uses_leverage_and_live_projection(self):
        html = (ROOT / "Symbiose_Dashboard.html").read_text(encoding="utf-8")
        self.assertIn('id="trade-leverage"', html)
        self.assertIn('id="trade-projection"', html)
        self.assertIn("calculateTradeProjection", html)
        self.assertIn("Notional", html)
        self.assertIn("Live-PnL", html)

    def test_risk_slider_and_warning_have_stable_layout_contract(self):
        html = (ROOT / "Symbiose_Dashboard.html").read_text(encoding="utf-8")
        self.assertRegex(html, r'<input[^>]+id="risk"[^>]+min="0\.5"[^>]+value="1\.0"[^>]+step="0\.5"')
        self.assertIn("#risk-warning", html)
        self.assertRegex(html, r'#risk-warning\s*\{[^}]*display:block[^}]*font-size:9px[^}]*margin-top:2px[^}]*min-height:13px')
        self.assertIn("rw.style.opacity", html)
        self.assertNotIn("rw.style.display", html)

    def test_time_stop_copy_is_setup_scoped_and_radar_stays_independent(self):
        html = (ROOT / "Symbiose_Dashboard.html").read_text(encoding="utf-8")
        self.assertIn("Gilt nur für das aktuell geladene Setup. Schließt den Trade nach X Bars, falls er im Verlust oder bei ±0 steht (Kapital-Effizienz).", html)
        radar_start = html.index("async function loadRadar()")
        radar_end = html.index("\nfunction renderRadar()", radar_start)
        radar_source = html[radar_start:radar_end]
        self.assertNotIn("timeStop", radar_source)
        self.assertNotIn("simulateRange", radar_source)
        self.assertNotIn("runWalkForwardBacktest", radar_source)

    def test_launcher_describes_universe_and_release_actions(self):
        source = (ROOT / "start.py").read_text(encoding="utf-8")
        self.assertIn("Lädt die aktuellsten 700+ Coins von der Exchange herunter.", source)
        self.assertIn("Führt alle Sicherheits- und Mathematik-Tests (Release Check) aus.", source)

    def test_launcher_has_no_execution_status(self):
        source = (ROOT / "start.py").read_text(encoding="utf-8")
        forbidden = (
            "def order_text(",
            "orders_enabled",
            "live_armed",
            "Orders: DISARMED",
            "Live-Trading",
            "Trading Signal System",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)
        self.assertIn("Quant Research & Setup Discovery", source)

    def test_distribution_contains_no_execution_only_artifacts(self):
        for artifact in (
            "OPERATIONS_RUNBOOK.md",
            "SYMBIOSE_Reliability_Audit.md",
            "docs/THREAT_MODEL.md",
            "tests/fixtures/bitget_signature_vectors.json",
            "tests/test_security_refactor.js",
        ):
            with self.subTest(artifact=artifact):
                self.assertFalse((ROOT / artifact).exists())

    def test_user_docs_describe_read_only_research(self):
        forbidden = (
            "BITGET_API_KEY",
            "SYM_ENABLE_ORDERS",
            "SYM_ALLOW_LIVE",
            "/api/private",
            "/api/op",
            "Bitget Execution",
        )
        for relative in ("README.md", "RELEASE_CHECKLIST.md", "SYMBIOSE_Tutorial.html"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            for token in forbidden:
                with self.subTest(file=relative, token=token):
                    self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main()
