# AURA v3 — Mathematische Formel-Spezifikation (FORMULA_SPEC.md)

**Status:** Kanonische Spezifikation v3.0 · **Datum:** 2026-09-17 · **Geltung:** Verbindlich fuer alle Berechnungen (Engine, API, Runner, UI, Tests, Pine-Paritaet)

---

## 1. Grundsaetze mathematischer Korrektheit

1. **Eine kanonische Produktionsimplementierung:** Alle produktiven Berechnungen laufen in `aura.core` in Python. Weder Browser-JS noch Runner duerfen abweichende Formeln berechnen.
2. **Deterministische Reinheit:** Jede Kernberechnung ist eine reine Funktion ohne unkontrollierte Nebeneffekte.
3. **Absicherung gegen numerische Instabilitaeten:**
   - Nullteiler-Schutz bei allen Ratios (RSI, DSR, Kelly, Sharpe, Profit Factor, Basis, Z-Scores).
   - NaN/Infinity/Leere-Reihen-Guards mit definierten neutralen Fallbacks.
   - Truncation statt kaufmaennischem Aufrunden bei Lot-Größen mit ULP-Schutz gegen Budget-Overshoots.
4. **Strikte Einheiten und Zeitbezuege:**
   - Interne Zeitstempel immer UTC-Millisekunden (`INTEGER`).
   - Geldbetraege und Margin mit Erhaltungsgarantie (`EndingEquity = StartingEquity + Realized + Unrealized - Fees`).
   - Jahresnormalisierung bei 24/7-Kryptomaerkten: 365 Tage (bzw. 8760 Stunden).
5. **Transparente Modellstatus- und Unsicherheitsfuehrung:**
   - Heuristische Scores (z.B. Confluence [0..100]) sind keine Wahrscheinlichkeiten.
   - Kalibrierte Wahrscheinlichkeiten nur via PAVA Isotonic Regression mit Bayes'schem Prior.
   - Ohne unabhaengige Holdout-Evidenz gilt immer der Modellstatus `MODEL_NO_EVIDENCE`.

---

## 2. Formel-Katalog

### 2.1 Technische Indikatoren & Oszillatoren

| ID | Name | Mathematische Definition | Warm-up | Randfall / Guard | Implementierung | Test-ID |
|---|---|---|---|---|---|---|
| **F01** | Exponential Moving Average (EMA) | $EMA_t = C_t \cdot \alpha + EMA_{t-1} \cdot (1-\alpha)$, $\alpha = \frac{2}{N+1}$ | $N$ Bars | $t=0 \implies EMA_0 = C_0$ | `aura.core.indicators.ema_series` | `test_ema_series_hand_calculated` |
| **F02** | Simple Moving Average (SMA) | $SMA_t = \frac{1}{N} \sum_{i=0}^{N-1} C_{t-i}$ | $N$ Bars | $t < N-1 \implies 0.0$ | `aura.core.indicators.sma_series` | `test_sma_series_hand_calculated` |
| **F03** | Relative Strength Index (RSI) | $RSI = 100 - \frac{100}{1 + RS}$, $RS = \frac{EMA(Gain, 14)}{EMA(Loss, 14)}$ | 14 Bars | $Loss=0 \implies RSI=100$; $Gain=Loss=0 \implies 50$ | `aura.core.indicators.rsi_series` | `test_rsi_constant_prices_returns_neutral` |
| **F04** | Average True Range (ATR) | $TR = \max(H-L, \|H-C_{t-1}\|, \|L-C_{t-1}\|)$; $ATR = EMA(TR, 14)$ | 14 Bars | $t=0 \implies TR=H-L$ | `aura.core.indicators.atr_series` | `test_atr_hand_calculated` |
| **F05** | Average Directional Index (ADX/DMI) | $+DM, -DM$; Smoothed Wilder; $DX = \frac{\|+DI - -DI\|}{+DI + -DI} \cdot 100$; $ADX = EMA(DX, 14)$ | 28 Bars | $+DI + -DI = 0 \implies DX=0$ | `aura.core.indicators.adx_series` | `test_adx_flatline_handles_zero_division` |
| **F06** | Moving Average Convergence Divergence (MACD) | $MACD = EMA_{12}(C) - EMA_{26}(C)$; $Signal = EMA_9(MACD)$; $Hist = MACD - Signal$ | 34 Bars | Array-Laenge < 26 $\implies 0.0$ | `aura.core.indicators.macd_series` | `TestMacd` |
| **F07** | Stochastic RSI (%K / %D) | $StochRSI = \frac{RSI - \min(RSI, 14)}{\max(RSI, 14) - \min(RSI, 14)}$; $\%K = SMA_3(StochRSI)$ | 31 Bars | $\max(RSI) == \min(RSI) \implies 50.0$ | `aura.core.indicators.stoch_rsi_series` | `TestStochRsi` |
| **F08** | SuperTrend (ATR Trailing Stop) | Upper/Lower Band = $hl2 \pm 3 \cdot ATR_{10}$; Flip bei Close-Durchbruch | 10 Bars | Ratchet-Logik: Bands ziehen nur nach, nie zurueck | `aura.core.indicators.supertrend_series` | `test_supertrend_invariant_direction` |
| **F09** | On-Balance Volume (OBV) | $OBV_t = OBV_{t-1} + V_t \cdot \text{sgn}(C_t - C_{t-1})$ | 1 Bar | $OBV_0 = 0.0$ (definierter Nullstart) | `aura.core.indicators.obv_series` | `test_obv_hand_calculated` |
| **F10** | Volume Weighted Average Price (VWAP) | $VWAP = \frac{\sum (hlc3 \cdot V)}{\sum V}$, UTC-Mitternacht-Reset | 1 Bar | $\sum V = 0 \implies hlc3$; Sek/ms-Timestamp-Normalisierung | `aura.core.indicators.vwap_series` | `test_vwap_utc_midnight_reset` |
| **F11** | Cumulative Volume Delta (CVD Proxy) | $\Delta = V \cdot \frac{2C - H - L}{H - L}$; $CVD_t = CVD_{t-1} + \Delta$ | 1 Bar | $H == L \implies \Delta = 0.0$; Explizit als Proxy markiert | `aura.core.indicators.cvd_series` | `test_cvd_proxy_labeling_and_range_formula` |
| **F12** | Swing Pivots (High/Low) | $PH: H_i = \max(H_{i-5..i+5})$; $PL: L_i = \min(L_{i-5..i+5})$ | 11 Bars | Unbestaetigt bis Bar $i+5$ abgeschlossen ist | `aura.core.indicators.swing_pivots` | `TestPivots` |
| **F13** | Fair Value Gap (FVG) | Bull: $L_t > H_{t-2}$; Bear: $H_t < L_{t-2}$; Mitigiert bei Durchkreuzung | 3 Bars | Schwellwert $0.15 \cdot ATR_{14}$ gegen Rauschen | `aura.core.scoring.analyze_candles` | `TestFvg` |
| **F14** | Squeeze Metrics (BB vs. KC) | BB: $SMA_{20} \pm 2\sigma$; KC: $SMA_{20} \pm 1.5 \cdot ATR_{20}$; Squeeze wenn $BB \subset KC$ | 20 Bars | $\sigma \le 1e-8 \implies$ Squeeze aktiv | `aura.core.indicators.squeeze_metrics_at` | `test_squeeze_compression_calculation` |

---

### 2.2 Confluence, Regime & Makro-Adjustments

| ID | Name | Mathematische Definition | Bereich | Logik | Implementierung | Test-ID |
|---|---|---|---|---|---|---|
| **F15** | Aggregate Confluence Score | $S_{core} = \text{clamp}(0.30 \cdot S_{tr} + 0.25 \cdot S_{mom} + 0.25 \cdot S_{vol} + 0.20 \cdot S_{str}, 0, 100)$ | [0, 100] | Gewichte summieren exakt zu 1.0 (100%) | `aura.core.scoring.aggregate_confluence_score` | `test_aggregate_score_hand_calculated` |
| **F16** | Trend Subscore (30%) | EMA-Faecher (20/50/200), SuperTrend, ADX-Trendstaerke | [0, 100] | Bull > 50, Bear < 50 | `aura.core.scoring.analyze_candles` | `test_analyze_candles_synthetic_series` |
| **F17** | Momentum Subscore (25%) | RSI, MACD-Histogramm, StochRSI, RSI-Divergenzen | [0, 100] | Bull > 50, Bear < 50 | `aura.core.scoring.analyze_candles` | `test_analyze_candles_synthetic_series` |
| **F18** | Volume Subscore (25%) | Volumen ueber SMA20, VWAP-Position, CVD-Trend | [0, 100] | Bull > 50, Bear < 50 | `aura.core.scoring.analyze_candles` | `test_analyze_candles_synthetic_series` |
| **F19** | Structure Subscore (20%) | Market Structure (HH/HL vs LH/LL), FVG-Naehe, EQH/EQL-Sweep | [0, 100] | Bull > 50, Bear < 50 | `aura.core.scoring.analyze_candles` | `test_analyze_candles_synthetic_series` |
| **F20** | Funding Bias & Z-Score | $Z = \frac{FR_{last} - \bar{FR}}{\sigma_{FR}}$; Contrarian Bias bis $\pm 100$ | [-100, +100] | $\sigma \le 1e-8 \implies Z=0$; Streak $\ge 6 \implies \pm 25$ | `aura.core.scoring.calc_funding_bias` | `test_funding_bias_contrarian` |
| **F21** | Open Interest Bias | Quadranten-Matrix: $\Delta P_{4h} \times \Delta OI_{4h}$ (Long/Short Build-Up/Unwinding) | [-100, +100] | OI-Spike bei $\Delta OI > 5\%$ und $\|\Delta P\| < 0.5\%$ | `aura.core.scoring.calc_oi_bias` | `test_oi_bias_accumulation` |
| **F22** | Spot-Perp-Basis Bias | $Basis = \frac{P_{mark} - P_{index}}{P_{index}}$; Contango = Short, Backwardation = Long | [-100, +100] | Schwellwert $0.05\%$; Neutral bei Mark $\le 0$ | `aura.core.scoring.calc_basis_bias` | `test_basis_bias_contango_backwardation` |
| **F23** | Macro Adjustment | $S_{final} = \text{clamp}(S_{core} \pm FG_{adj} + \text{clamp}(Fund + OI, -15, 15) + Basis + MTF, 0, 100)$ | [0, 100] | Hard Cap von $\pm 15$ Punkten fuer Makro | `aura.core.scoring.macro_adjust` | `test_macro_adjust_hard_cap_15` |
| **F24** | Regime Classification | BULL_STRONG, BULL_NORMAL, BEAR_STRONG, BEAR_NORMAL, RANGE | Enum | Basiert auf EMA200, ADX-Schwelle 25, SuperTrend | `aura.core.scoring.regime_of` | `test_analyze_candles_synthetic_series` |
| **F25** | Dynamic TP1 Calculation | Naechster unmitigierter Pivot / Opposing FVG $\ge 1.2R$, Fallback $2.0R$ | Price | Verhindert unrealistische Mini-TPs | `aura.core.scoring.dynamic_tp1_at` | `TestDynamicTp` |

---

### 2.3 Risikomanagement, Sizing & Hebel

| ID | Name | Mathematische Definition | Grenzen / Schutz | Implementierung | Test-ID |
|---|---|---|---|---|---|
| **F28** | Fractional Kelly Sizing | $f^* = \frac{p(b+1) - 1}{b}$; Half-Kelly = $0.5 \cdot f^*$; Hard Cap $\min(25\%, \text{RiskPct})$ | Shrinkage bei $N \in [5, 15)$; $N < 5 \implies 0$ | `aura.core.risk.calc_kelly` | `test_kelly_positive_edge_hand_calculated`, `test_kelly_sample_shrinkage` |
| **F29** | Lot / Contract Sizing | $Contracts = \lfloor \frac{\text{RiskAmt}}{\|Entry - SL\| \cdot ctVal} \rfloor$; $Qty = Contracts \cdot ctVal$ | Truncation (Abrunden); ULP-Guard; MinSize / MinNotional Check | `aura.core.risk.size_position` | `test_size_position_hand_calculated`, `test_size_position_never_exceeds_risk_budget` |
| **F30** | Hebelempfehlung & Margin | $L = \min(\lceil \frac{Notional}{0.35 \cdot Equity} \rceil, \lfloor \frac{100}{3 \cdot SL_{\%} + 0.5} \rfloor, L_{max})$ | Hebel bestimmt Margin, NIE den SL! Liq-Puffer = $\frac{100}{L} - 0.5\%$ | `aura.core.risk.recommend_leverage` | `test_recommend_leverage_invariant`, `test_leverage_does_not_change_stop_loss_distance` |

---

### 2.4 Statistik, Validierung & Accounting

| ID | Name | Mathematische Definition | Referenz / Standard | Implementierung | Test-ID |
|---|---|---|---|---|---|
| **F26** | Deflated Sharpe Ratio (DSR) | $DSR = \Phi\left( \frac{SR - SR^*}{\sqrt{\mathbb{V}[\widehat{SR}]}} \right)$; $SR^* = \sqrt{\frac{\mathbb{V}}{N-1}} ((1-\gamma)Z_1 + \gamma Z_2)$ | Bailey & López de Prado (2014); Acklam norm_inv | `aura.core.stats.calc_dsr` | `test_dsr_trials_deflation_property`, `test_dsr_parity_with_reference` |
| **F27** | PAVA Isotonic Calibration | Monotone nicht-fallende Regression auf OOS-Bins mit Bayes'schem Sigmoid-Prior | Ayer et al. (1955); Schranken [0.05, 0.95] | `aura.core.stats.calibrate_probabilities` | `test_pava_monotonicity_invariant`, `test_pava_parity_with_reference` |
| **F31** | Selection Objective | $Obj = Exp_R \cdot \sqrt{N} \cdot (1 - \frac{1}{1+N})$ | EXP-024 Walk-Forward Optimierungsziel | `aura.core.stats.selection_objective` | `test_selection_objective_parity` |
| **F32** | Anchored Walk-Forward Folds | $TrainEnd_f = Warmup + f \cdot L - 1$; $TestStart_f = TrainEnd_f + 2$ | t1-safe: kein Zukunftsleak von Train in Test | `aura.core.stats.walk_forward_folds` | `test_walk_forward_folds_no_overlap` |
| **F34 / F59** | Accounting-Erhaltungsgleichung | $Equity_{end} = Equity_{start} + \text{RealizedPnl} + \text{UnrealizedPnl} - \text{Fees}$ | Erhaltungssatz: Discrepancy $\le 1e-8$ | `aura.core.stats.reconcile_accounting` | `test_reconcile_accounting_closed_and_open_trades` |
| **F58** | Trade Evaluation (R-Multiple) | $WR = \frac{N_{win}}{N}$; $PF = \frac{\sum R_{win}}{\|\sum R_{loss}\|}$; $Exp_R = \frac{\sum R}{N}$; $MaxDD_R$ | R-Multiple normalisiert ueber Initialrisiko $R$ | `aura.core.stats.evaluate_trades` | `test_evaluate_trades_hand_calculated` |
