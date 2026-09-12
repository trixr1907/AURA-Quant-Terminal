import unittest
from pathlib import Path

PINE_PATH = Path(__file__).resolve().parent.parent / "Symbiose_Signal_System_v1.pine"
HTML_PATH = Path(__file__).resolve().parent.parent / "Symbiose_Dashboard.html"

class TestPineForecastOverlay(unittest.TestCase):
    def test_pure_indicator_and_position_tool_separation(self):
        pine_text = PINE_PATH.read_text(encoding="utf-8")
        html_text = HTML_PATH.read_text(encoding="utf-8")

        # 1. Main indicator has high visual limits and signals without intrusive forecast boxes
        self.assertIn('indicator("AURA — Confluence Signal-System"', pine_text)
        self.assertIn('max_boxes_count=500', pine_text)
        self.assertIn('max_labels_count=500', pine_text)
        self.assertIn('max_lines_count=500', pine_text)

        # 2. Standalone 1:1 Position Tool Generator is present in Dashboard
        self.assertIn('function generateTradingViewPositionScript', html_text)
        self.assertIn('data-tv-overlay=', html_text)
        self.assertIn('43000517002', html_text)
        self.assertIn('43000516992', html_text)
        self.assertIn('#089981', html_text) # TV Green profit zone
        self.assertIn('#f23645', html_text) # TV Red loss zone

if __name__ == "__main__":
    unittest.main()
