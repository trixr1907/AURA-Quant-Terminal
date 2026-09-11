#!/usr/bin/env python3
"""Regression contract for bounded Pine FVG drawing storage."""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PINE = ROOT / "Symbiose_Signal_System_v1.pine"


class TestPineFvgCapacity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PINE.read_text(encoding="utf-8")
        start = cls.source.index("// --- Fair Value Gaps")
        end = cls.source.index("// --- Liquiditäts-Pools")
        cls.fvg_block = cls.source[start:end]

    def test_capacity_exhaustion_never_aborts_chart_execution(self):
        self.assertNotIn("runtime.error", self.fvg_block)
        self.assertNotIn("FVG box limit reached", self.fvg_block)

    def test_oldest_zone_is_fallback_when_all_zones_are_active(self):
        self.assertRegex(
            self.fvg_block,
            re.compile(
                r"if\s+na\(removeIdx\)\s*\n\s*removeIdx\s*:=\s*0"
                r"[\s\S]*box\.delete\(array\.get\(fvgBoxes, removeIdx\)\)"
            ),
        )

    def test_visual_zone_count_is_bounded_below_tradingview_limit(self):
        self.assertIn("MAX_FVG_ZONES = 30", self.source)
        self.assertIn("array.size(fvgBoxes) > MAX_FVG_ZONES", self.fvg_block)
        self.assertIn("max_boxes_count=500", self.source)


if __name__ == "__main__":
    unittest.main()
