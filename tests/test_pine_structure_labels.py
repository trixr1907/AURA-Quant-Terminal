import unittest
from pathlib import Path


class TestPineStructureLabels(unittest.TestCase):
    def test_structure_labels_are_configurable_and_readable(self):
        pine = Path("Symbiose_Signal_System_v1.pine").read_text(encoding="utf-8")
        self.assertIn('grpV = "6) Darstellung"', pine)
        self.assertIn('structureLabelSize = input.string("Normal"', pine)
        self.assertIn('structureLabelOffsetAtr = input.float(0.35', pine)
        self.assertIn('strLabelSize =', pine)

        structure_block = pine[pine.index("// BOS/CHoCH-Labels"):pine.index("// ============================================================================\n//  DASHBOARD-TABLE")]
        self.assertNotIn("size=size.tiny", structure_block)
        self.assertIn("size=strLabelSize", structure_block)
        self.assertIn("high + strLabelOffset", structure_block)
        self.assertIn("low - strLabelOffset", structure_block)
        self.assertIn('color=color.new(#22c55e, 0)', structure_block)
        self.assertIn('color=color.new(#ef4444, 0)', structure_block)
        self.assertIn('color=color.new(#f59e0b, 0)', structure_block)
        self.assertIn('textcolor=color.white', structure_block)


if __name__ == "__main__":
    unittest.main()
