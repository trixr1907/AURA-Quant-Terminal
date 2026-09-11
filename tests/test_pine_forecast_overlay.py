import unittest
from pathlib import Path

PINE_PATH = Path(__file__).resolve().parent.parent / "Symbiose_Signal_System_v1.pine"

class TestPineForecastOverlay(unittest.TestCase):
    def test_forecast_inputs_and_overlay_present(self):
        text = PINE_PATH.read_text(encoding="utf-8")
        self.assertIn('grpFC = "7) Trade Forecasting & Long/Short Position Tool"', text)
        self.assertIn('fcShow     = input.bool(true, "Position Tool visualisieren"', text)
        self.assertIn('fcMode     = input.string("Auto", "Modus"', text)
        self.assertIn('fcEntry    = input.float(0.0, "Entry Preis (Custom)"', text)
        self.assertIn('fcSl       = input.float(0.0, "Stop Loss (Custom)"', text)
        self.assertIn('fcTp1      = input.float(0.0, "TP1 Preis (Custom)"', text)
        self.assertIn('fcTp2      = input.float(0.0, "TP2 Preis (Custom)"', text)
        self.assertIn('fcTp3      = input.float(0.0, "TP3 Preis (Custom)"', text)
        self.assertIn('fcEquity   = input.float(1000.0, "Kontogröße (USDT)"', text)
        self.assertIn('fcRiskPct  = input.float(5.0, "Risiko (%)"', text)
        self.assertIn('fcLev      = input.int(10, "Hebel (Leverage)"', text)
        self.assertIn('fcLineEntry := line.new', text)
        self.assertIn('fcBoxProfit := box.new', text)
        self.assertIn('fcBoxLoss   := box.new', text)
        self.assertIn('fcLabelCard := label.new', text)

if __name__ == "__main__":
    unittest.main()
