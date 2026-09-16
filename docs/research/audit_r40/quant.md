# Quant-Math Audit & Formel-Inventar: AURA v2.5.0 (Commit de25830)

**Auditor:** Quant-Research-Auditor (Runde 40)  
**Datum:** 17. September 2026  
**Repository:** `/home/ivo/projects/AURA_v2` (Commit: `de25830`, Version: `v2.5.0`)  
**Geprüfte Dateien:**
1. `Symbiose_Dashboard.html` (613 KB Single-File Web Terminal)
2. `headless_autobot.js` (Server-side Autobot Paper Runner)
3. `shadow_collector.js` (Autobot Shadow Decision & Outcome Tracking)
4. `bitget_relay.py` (Relay Server, Universe, Cache, BTC Regime Classifier)
5. `tests/reference_backtest.py` (Mathematisches Orakel für DSR, PAVA, Accounting)
6. `Symbiose_Signal_System_v1.pine` (TradingView Pine Script v6 Referenz-Engine)

---

## 1. Zusammenfassung & Mandats-Prüfung (12 Kernrisiken)

| Mandats-Risiko | Status | Zusammenfassung der Prüfung |
|---|---|---|
| **(1) Einheiten & Skalierung (%, bps, ms/s, Base/Quote)** | 🟡 PASS WITH FINDINGS | `riskPct` wird als Prozentwert (z.B. 1.0 für 1%) an `calcKelly` übergeben und intern durch 100 geteilt. Gebühren und Slippage (`makerFee: 0.001`, `slippage: 0.0005`) sind als Dezimalbrüche definiert. Bitget-Kerzen liefern ms-Zeitstempel; `vwapArr` setzt ms voraus (Sekunden würden Tagesreset blockieren, vgl. Finding 9). Base-/Quote-Mengen in Notional und PnL sind mathematisch sauber getrennt ($Q = \text{Notional}/\text{Entry}$, $\text{PnL} = Q \cdot \Delta P \cdot \text{Dir}$). |
| **(2) Stichproben- vs Populationsvarianz & Annualisierung** | 🟡 PASS WITH FINDINGS | DSR (`calcDSR`) und `evaluateAutobotEdge` nutzen korrekte Stichprobenvarianz mit $N-1$ (ddof=1). `calcFundingBias` und `bitget_relay.py` (BB) nutzen Populationsvarianz mit $N$ (ddof=0, vgl. Finding 5 & 10). DSR nutzt trade-level Renditen ohne künstliche 252/365-Tage-Annualisierung, da Stichprobengröße $N$ direkt die Anzahl der Trades ist. |
| **(3) Nullteiler, leere Reihen, NaN/Infinity, kurze Historien** | 🟢 PASS | Alle Kernfunktionen (`rsiArr`, `atrArr`, `adxArr`, `cvdSeries`, `calcDSR`, `calcFundingBias`, `calcOIBias`, `sizePosition`) besitzen strikte Guards gegen Division durch 0 (z.B. `std <= 1e-8`, `H == L`, `indexPrice <= 0`). Kurze Historien werden via `effWarmup` und Fallbacks abgesichert. |
| **(4) Float-Rundung & Lot/Tick-Size** | 🟢 PASS | `sizePosition` implementiert Contract-Truncation (`Math.floor(contracts)`), Lot-Step-Präzision (`spec.ctVal`), und einen ULP-Guard (`actualRiskAmt > riskAmt -> contracts -= 1`). `headless_autobot.js` nutzt kontinuierliche Paper-Quantities. |
| **(5) Kelly-Inputs, Caps & Unsicherheit** | 🟢 PASS | `calcKelly` implementiert $f^* = \frac{p(b+1)-1}{b}$, Half-Kelly ($0.5 \cdot f^*$), Hard-Cap $\min(0.25, \text{riskPct}/100)$ und lineare Unsicherheits-Dämpfung für kleine Stichproben ($N \in [5, 15)$). Negativer Edge liefert sofort 0. |
| **(6) CVD-Approximation & Proxy-Labeling** | 🟢 PASS | CVD wird aus Kerzengeometrie approximiert ($\Delta V = V \cdot \frac{2C - H - L}{H - L}$). Er ist im Code, in der UI und im Pine Script explizit als Range-Approximation / Proxy dokumentiert und verifiziert (`scripts/cvd_reference.py`). |
| **(7) Liquidationsberechnung & Marginregeln** | 🟡 PASS WITH FINDINGS | `recommendLeverage` berechnet einen approximierten Liquidationspuffer $\frac{100}{\text{Leverage}} - 0.5$ mit pauschaler 0.5% MMR. Börsenspezifische Bitget-MMR-Stufentabellen (Tiered Maintenance Margin) sind nicht hinterlegt (vgl. Finding 6). |
| **(8) Funding-Gebühren Zeitbezug** | 🟡 PASS WITH FINDINGS | Funding-Raten (8h-Intervall) fließen als Z-Score und Streak-Indikator in den Confluence-Score ein (`calcFundingBias`). Im Walk-Forward Backtest (`simulateRange`) und Shadow-Collector werden keine laufenden Haltekosten (Carry) verrechnet (vgl. Finding 7). |
| **(9) Sharpe/Sortino/DSR vs Literatur** | 🟢 PASS | `calcDSR` folgt exakt der Methodik von Bailey & Lopez de Prado (2014): Stichproben-Momente (Mean, Var, Skew, Kurtosis), asymptotische Varianz nach Mertens/Lo und Gumbel-Extremwert für $\text{SR}^*$. |
| **(10) Hebel-Logik & Absolute Stops** | 🟢 PASS | Hebel $L$ bestimmt ausschließlich die benötigte Margin ($\text{Margin} = \text{Notional} / L$). Die Stop-Distanz wird strikt über ATR und Preis berechnet und niemals durch den Hebel verändert. |
| **(11) Intrabar SL/TP-Policy** | 🟢 PASS | Sowohl `simulateRange` (Backtest) als auch `shadow_collector.js` implementieren die konservative Richtlinie: Berühren High und Low in derselben Kerze SL und TP, wird **ausnahmslos SL zuerst** ausgeführt. |
| **(12) Score-Gewichte & Clamping** | 🟢 PASS | Subscores (Trend 30%, Momentum 25%, Volume 25%, Struktur 20%) summieren sich exakt zu 1.00. Jeder Subscore und der Gesamtscore werden strikt auf $[0, 100]$ geclampt. |

---

## 2. Vollständiges Formel-Inventar (65 Formeln)

| ID | Name | Datei : Zeile | Mathematische Definition | Inputs & Einheiten | Bekannte Risiken & Guards |
|---|---|---|---|---|---|
| **F01** | Exponential Moving Average (EMA) | `Symbiose_Dashboard.html:1086` | $\text{EMA}_t = C_t \cdot k + \text{EMA}_{t-1} \cdot (1-k)$, $k = \frac{2}{p+1}$ | `src`: float[] (USDT), `p`: int (Bars) | Warmup-Phase erforderlich ($N \ge 3p$). Erster Wert $\text{EMA}_0 = C_0$. |
| **F02** | Simple Moving Average (SMA) | `Symbiose_Dashboard.html:1093` | $\text{SMA}_t = \frac{1}{p} \sum_{i=0}^{p-1} C_{t-i}$ | `src`: float[], `p`: int (Bars) | Verzögerung um $(p-1)/2$ Bars. Gibt 0 zurück für $i < p-1$. |
| **F03** | Relative Strength Index (RSI) | `Symbiose_Dashboard.html:1099` | $\text{RSI} = 100 - \frac{100}{1 + \text{RS}}$, $\text{RS} = \frac{\text{WilderEMA}(\text{Gain})}{\text{WilderEMA}(\text{Loss})}$ | `c`: float[] (USDT), `p`: int (14) | Division durch 0 bei Loss=0 abgefangen (ergibt 100 bzw. 50 bei Flatline). |
| **F04** | Average True Range (ATR) | `Symbiose_Dashboard.html:1114` | $\text{TR}_t = \max(H-L, \|H-C_{t-1}\|, \|L-C_{t-1}\|)$, $\text{ATR} = \text{WilderEMA}(\text{TR}, p)$ | `h, l, c`: float[] (USDT), `p`: int (14) | Erster Bar $\text{TR}_0 = H_0 - L_0$. ATR=0 bei konstanter Flatline. |
| **F05** | Average Directional Index (ADX/DMI) | `Symbiose_Dashboard.html:1125` | $\text{DX} = 100 \cdot \frac{\|+DI - -DI\|}{+DI + -DI}$, $\text{ADX} = \text{WilderEMA}(\text{DX}, p)$ | `h, l, c`: float[] (USDT), `p`: int (14) | Nullteiler bei $\text{ATR}=0$ oder $+DI + -DI = 0$ abgefangen (DX=0, DI=0). |
| **F06** | Moving Average Convergence Divergence (MACD) | `Symbiose_Dashboard.html:1152` | $\text{MACD} = \text{EMA}(C,12) - \text{EMA}(C,26)$, $\text{Sig} = \text{EMA}(\text{MACD},9)$, $\text{Hist} = \text{MACD} - \text{Sig}$ | `c`: float[] (USDT) | Konvergenzzeit von EMA26 beachten. |
| **F07** | Stochastic RSI (StochRSI) | `Symbiose_Dashboard.html:1160` | $\text{StochRSI} = \text{SMA}\left( \frac{\text{RSI} - \min(\text{RSI}_p)}{\max(\text{RSI}_p) - \min(\text{RSI}_p)} \cdot 100, 3 \right)$ | `c`: float[] (USDT), `p`: int (14) | Nullteiler bei Flatline ($\max = \min$) abgefangen mit Fallback 50. |
| **F08** | SuperTrend Indicator | `Symbiose_Dashboard.html:1170` | $\text{Up} = \frac{H+L}{2} + m \cdot \text{ATR}$, $\text{Dn} = \frac{H+L}{2} - m \cdot \text{ATR}$, State-Machine | `h, l, c`: float[] (USDT), `atrP`: 10, `mul`: 3.0 | Diskontinuierliche Niveausprünge bei Durchbruch des Schlusskurses. |
| **F09** | On-Balance Volume (OBV) | `Symbiose_Dashboard.html:1190` | $\text{OBV}_t = \text{OBV}_{t-1} + (V_t \text{ if } C_t > C_{t-1} \text{ else } -V_t \text{ if } C_t < C_{t-1} \text{ else } 0)$ | `c`: float[] (USDT), `v`: float[] (Volumen) | Index $i=0$ greift auf $c[-1]$ zu (`undefined` in JS, ergibt 0, vgl. Finding 8). |
| **F10** | Volume Weighted Average Price (VWAP) | `Symbiose_Dashboard.html:1196` | $\text{VWAP} = \frac{\sum (H+L+C)/3 \cdot V}{\sum V}$, täglicher Reset um 00:00 UTC | `ms`: int[] (Unix ms), `h, l, c, v`: float[] | Setzt Millisekunden voraus; Division durch $\sum V = 0$ liefert $(H+L+C)/3$. |
| **F11** | Cumulative Volume Delta Proxy (CVD) | `Symbiose_Dashboard.html:1207` | $\Delta V_i = V_i \cdot \frac{2C_i - H_i - L_i}{H_i - L_i} \text{ if } (H-L)>0 \text{ else } 0$; $\text{CVD} = \sum \Delta V$ | `v, tbv, h, l, c`: float[] | Kerzenbereichs-Approximation (Proxy). Nullteiler bei $H=L$ abgefangen. |
| **F12** | Swing Pivots (High / Low) | `Symbiose_Dashboard.html:1229` | $\text{PH} = H_i \text{ if } H_i > \max(H_{i-l..i-1}) \land H_i \ge \max(H_{i+1..i+r})$ | `h, l`: float[], `left=5, right=5` | Verzögerung um `right=5` Bars vor Bestätigung (kein Look-Ahead). |
| **F13** | Fair Value Gap (FVG) & Mitigation | `Symbiose_Dashboard.html:1322` | Bull FVG: $L_t > H_{t-2}$; Bear FVG: $H_t < L_{t-2}$; Mitigation: $L_t \le \text{Bot} \lor H_t \ge \text{Top}$ | `h, l`: float[], `ms`: int[] | Zonen bleiben aktiv bis Mitigation; max 8 mitigierte Zonen im Speicher. |
| **F14** | Equal Highs / Lows (Liquidity Pools) | `Symbiose_Dashboard.html:1358` | $\|\text{PH}_a - \text{PH}_b\| \le 0.35 \cdot \text{ATR} \land \text{PH} > C_t$; $\text{Lvl} = (\text{PH}_a + \text{PH}_b)/2$ | `h, l, c, atr`: float[] | $O(N^2)$ Suche über `phPool` (max 8 Elemente), Schwellenwert $0.35 \cdot \text{ATR}$. |
| **F15** | Trend Subscore | `Symbiose_Dashboard.html:1381` | $\text{TS} = \text{clamp}(50 + 8 \cdot \mathbb{I}_{C>E20} + 8 \cdot \mathbb{I}_{E20>E50} + 7 \cdot \mathbb{I}_{E50>E200} + 12 \cdot \mathbb{I}_{ST=1} + \text{ADX}_{\text{adj}}, 0, 100)$ | `c, e20, e50, e200, st, adx`: float[] | Diskrete Indikatorsprünge, strikt geclampt auf $[0, 100]$. |
| **F16** | Momentum Subscore | `Symbiose_Dashboard.html:1382` | $\text{MS} = \text{clamp}(50 + \text{clamp}(1.5(RSI-50), -30, 30) + 12 \cdot \mathbb{I}_{MACD>Sig} + 8 \cdot \mathbb{I}_{Hist>0} + \text{clamp}(0.8(Stoch-50), -20, 20), 0, 100)$ | `rsi, macd, hist, srk`: float[] | Kombiniert stetige RSI/StochRSI-Terme mit diskreten MACD-Signalen. |
| **F17** | Volume Subscore | `Symbiose_Dashboard.html:1386` | $\text{VS} = \text{clamp}(50 + 15 \cdot \mathbb{I}_{OBV>EOBV} + 10 \cdot \mathbb{I}_{C>VWAP+\epsilon} + \text{clamp}(20(\frac{V}{SMAV}-1), -10, 10) \cdot \text{dir} + 10 \cdot \mathbb{I}_{CVD>ECVD}, 0, 100)$ | `obv, eobv, c, vwap, v, smav, cvd, ecvd`: float[] | $\epsilon$-geschützte VWAP-Bedingung verhindert Float-Flipping. |
| **F18** | Structure Subscore | `Symbiose_Dashboard.html:1387` | $\text{SS} = \text{clamp}(50 + 15 \cdot \mathbb{I}_{BOS\le 6} + 10 \cdot \mathbb{I}_{CH\le 6} + 10 \cdot \mathbb{I}_{FVG} + 7 \cdot \mathbb{I}_{EQH/EQL} + 8 \cdot \mathbb{I}_{Struct=1}, 0, 100)$ | `bos, ch, fvg, eqh, eql, structTrend`: float/int | Decay-Logik ($\le 6$ Bars) belohnt frische Struktursignale. |
| **F19** | Aggregate Confluence Score | `Symbiose_Dashboard.html:1078` | $\text{Score} = \text{clamp}(0.30 \cdot \text{TS} + 0.25 \cdot \text{MS} + 0.25 \cdot \text{VS} + 0.20 \cdot \text{SS}, 0, 100)$ | `trend, mom, vol, str`: float $[0..100]$ | Gewichtssumme $0.30 + 0.25 + 0.25 + 0.20 = 1.00$. |
| **F20** | Funding Rate Z-Score & Bias | `Symbiose_Dashboard.html:1591` | $Z = \frac{\text{Rate}_t - \bar{R}}{\sigma_R}$; $\text{Bias} = \text{clamp}(-(Z \mp 1.5) \cdot 35 \mp 30 \mp \text{streak}, -100, 100)$ | `rawRates`: float[] (8h Raten) | Verwendet Populationsvarianz / $N$ (vgl. Finding 5). $\sigma \le 10^{-8}$ liefert $Z=0$. |
| **F21** | Open Interest Quadrant Bias | `Symbiose_Dashboard.html:1631` | $\Delta \text{OI} = \frac{\text{OI}_t - \text{OI}_{t-4h}}{\text{OI}_{t-4h}}$, $\Delta P = \frac{P_t - P_{t-4h}}{P_{t-4h}}$; Quadranten: LB (+70), SB (-70), LC (+30), SS (-30) | `oiHist, currentPrice, price4hAgo`: float | Division durch $\text{OI}_{t-4h}=0$ oder $P_{t-4h}=0$ abgefangen. |
| **F22** | Basis (Spot-Perp Spread) Bias | `Symbiose_Dashboard.html:1666` | $\text{Basis} = \frac{\text{Mark} - \text{Index}}{\text{Index}}$; $\text{Bias} = \text{clamp}\left(\frac{\text{Basis}}{\text{threshold}} \cdot 50, -100, 100\right)$ | `markPrice, indexPrice`: float (USDT), `thr`: 0.0005 | Nullteiler bei `indexPrice <= 0` abgefangen. |
| **F23** | Macro Score Adjustment & Veto | `Symbiose_Dashboard.html:1919` | $\text{MacroAdj} = \text{clamp}(\text{FundAdj} + \text{OIAdj}, -25, 25)$; $\text{Total} = \text{clamp}(\text{Core} \pm \text{FG}_{\text{adj}} + \text{Macro} + \text{Basis} + \text{MTF}, 0, 100)$ | `core, fg, fundBias, oiBias, basisBias, mtfBonus` | Veto schützt vor Signal-Ausführung bei extremem Derivate-Gegenwind. |
| **F24** | Squeeze Compression Ratio | `Symbiose_Dashboard.html:1706` | $\text{BB}_W = \frac{4 \cdot \sigma_C}{\mu_C}$, $\text{KC}_W = \frac{4 \cdot \text{ATR}}{\mu_C}$; $\text{Comp} = \frac{\text{BB}_W}{\text{KC}_W}$; $\text{Active} = (\text{BB}_W < \text{KC}_W \land \text{ATR}>0)$ | `A`: EngineState, `idx`: int | $\mu_C \le 0$ abgefangen mit Fallback 1.0; $\text{KC}_W \le 0$ liefert NaN. |
| **F25** | Dynamic Take Profit 1 (DynTP1) | `Symbiose_Dashboard.html:1899` | $\text{DynTP1} = \text{Closest Opposing Structure Level in } [\text{Entry} + 1.0R, \text{Entry} + 2.0R)$ | `A`: EngineState, `idx, dir, entry, r`: float | Garantiert $R \in [1.0, 2.0]$; Fallback auf Standard $\text{Entry} + 1.5R$. |
| **F26** | Deflated Sharpe Ratio (DSR) | `Symbiose_Dashboard.html:1464` | $\text{DSR} = \Phi\left( \frac{\widehat{SR} - SR^*}{\sqrt{\hat{V}[\widehat{SR}]}} \right)$, $SR^* = \frac{(1-\gamma)Z_1 + \gamma Z_2}{\sqrt{N-1}}$ | `returns`: float[] (R-units), `numTrials`: int | Sample-Varianz $N-1$; Fallback `dsr=0.5` bei $N<3$ oder $\sigma \le 10^{-8}$. |
| **F27** | Isotonic Regression (PAVA) P(Win) | `Symbiose_Dashboard.html:1497` | $\text{PAVA}(\text{Scores}, \text{Outcomes}) \to \text{Monotone } P(\text{Win} \mid \text{Score})$; Bayesian Smoothing Prior $N=20$ | `oosTrades`: {score, outcome}[] | Garantiert strenge Monotonie des kalibrierten Siegwahrscheinlichkeits-Outputs. |
| **F28** | Fractional Kelly Criterion & Shrinkage | `Symbiose_Dashboard.html:1561` | $f^* = \frac{p(b+1)-1}{b}$; $\text{HalfKelly} = 0.5 f^*$; $\text{Mult} = \text{clamp}\left(\frac{N-5}{10}, 0, 1\right)$; $\text{Frac} = \min(\text{HalfKelly}, \text{Cap}) \cdot \text{Mult}$ | `probWin, avgWinR, avgLossR, riskPct, equity, N` | Negativer Edge liefert 0; Hard-Cap $\le 25\%$; Shrinkage dämpft bei $N<15$. |
| **F29** | Position Sizing & Contract Steps | `Symbiose_Dashboard.html:1781` | $\text{RawCt} = \frac{\text{RiskAmt}/\text{StopDist}}{\text{ctVal}}$; $\text{Ct} = \lfloor \text{RawCt} \rfloor$; $Q = \text{Ct} \cdot \text{ctVal}$; Guard: $\text{Ct}-=1 \text{ if } Q \cdot \text{Stop} > \text{Risk}$ | `riskAmt, entry, stopDist, leverage, spec` | Exakter Float-Overshoot-Schutz; Truncation auf 8 Dezimalstellen. |
| **F30** | Recommended Leverage & Liq Buffer | `Symbiose_Dashboard.html:1826` | $\text{Needed} = \lceil \frac{\text{Notional}}{0.35 \cdot \text{Equity}} \rceil$; $\text{SafeMax} = \lfloor \frac{100}{3 \cdot \text{StopPct} + 0.5} \rfloor$; $\text{LiqBuffer} = \frac{100}{\text{Lev}} - 0.5$ | `entry, sl, notional, equity, maxLever` | Hebel verändert Stop-Distanz nicht; LiqBuffer ist 1/Lev Näherung (vgl. Finding 6). |
| **F31** | Walk-Forward Selection Objective | `Symbiose_Dashboard.html:2109` | $\text{Obj} = \text{Exp} \cdot \sqrt{N} \cdot \left(1 - \frac{1}{1+N}\right) \text{ if } N \ge \text{minTrades} \text{ else } -\infty$ | `exp`: float (Mean R), `total`: int ($N$) | Hyperbolische Bestrafung kleiner Stichproben skaliert mit $\sqrt{N}$. |
| **F32** | Walk-Forward K-Fold Embargo Split | `Symbiose_Dashboard.html:2124` | $N_{\text{usable}} = N - \text{Warmup}$; $\text{Fold} = \lfloor \frac{N_{\text{usable}}}{K+1} \rfloor$; $\text{TrainEnd}_k = \text{Warmup} + (k+1)\text{Fold}$ | `candles.length, warmup=235, k=4` | T1-Safe: Keine Look-Ahead-Lecks, strikte Trennung von Train- und Test-Folds. |
| **F33** | Intrabar SL/TP Tie-Breaker | `Symbiose_Dashboard.html:1994` | $\text{if } (L \le \text{Stop} \lor H \ge \text{Stop}) \to \text{SL first}$; TP nur bei intakter Position | `candles[j], runnerStop, tp1` | Konservative Worst-Case-Annahme schützt vor optimistischer Bias. |
| **F34** | Backtest Accounting Reconciliation | `Symbiose_Dashboard.html:2055` | $\text{EndEq} = \text{StartEq} + \text{RealizedPnL} + \text{UnrealizedPnL} - \text{Fees}$; $\Delta = \text{EndEq} - \text{Expected}$ | `startingEquity, trades: {grossPnl, fees, rNet}` | Prüft exakte Erhaltungsgleichung auf $\|\Delta\| \le 10^{-8}$. |
| **F35** | Trade Metrics (MFE / MAE) | `Symbiose_Dashboard.html:7026` | $\text{MFE} = \max(0, H - \text{Entry}) \cdot Q$; $\text{MAE} = -\max(0, \text{Entry} - L) \cdot Q$; in USDT und R | `trade, currentPrice`: float | Erfasst maximale günstige/ungünstige Kursexkursionen. |
| **F36** | Target Notional & Price Risk % | `headless_autobot.js:913` | $\text{PriceRiskPct} = \frac{\text{slDist}}{\text{execPrice}}$; $\text{TargetNotional} = \min(\text{Equity} \cdot 2.5, \frac{\text{KellyRisk}}{\text{PriceRiskPct}})$ | `slDist, execPrice, equity, kelly.riskAmt` | Deckelt maximales Notional auf 2.5x Account Equity. |
| **F37** | Dynamic Leverage Selection | `headless_autobot.js:915` | $\text{Lev} = \min(\text{MaxLev}, \max(2, \lceil \frac{\text{TargetNotional}}{\text{Equity} \cdot 0.25} \rceil))$; $\text{Margin} = \lfloor \frac{\text{Notional}}{\text{Lev}} \rceil$ | `targetNotional, equity, maxLeverage` | Wählt kleinsten Hebel, der Notional innerhalb von 25% Equity hält. |
| **F38** | In-Trade Auto Break-Even (+1R) | `headless_autobot.js:339` | $R = \frac{(\text{Mark} - \text{Entry}) \cdot \text{Dir}}{\|\text{Entry} - \text{InitialSL}\|}$; $\text{if } R \ge 1.0 \to \text{CurrentSL} = \text{Entry}$ | `trade, markPrice` | Zieht SL bei Erreichen von +1R risikofrei auf Einstieg nach. |
| **F39** | Tick-Based TP/SL Event Detection | `headless_autobot.js:323` | $\text{Hit}(P) = \text{Mark} \ge P \text{ (Long)} \lor \text{Mark} \le P \text{ (Short)}$; Events: `tp1`, `tp2`, `tp3`, `sl_close` | `trade, markPrice` | Unterdrückt fälschlicherweise SL bei `hit(tp1)` (vgl. Finding 3). |
| **F40** | Closed Trade PnL & Realized R | `headless_autobot.js:1064` | $\text{PnL} = (\text{Exit} - \text{Entry}) \cdot \text{Dir} \cdot \frac{\text{Notional}}{\text{Entry}}$; $R = \frac{(\text{Exit} - \text{Entry}) \cdot \text{Dir}}{\|\text{Entry} - \text{InitialSL}\|}$ | `trade, exitPrice, reason` | Berechnet PnL korrekt, wird aber nicht in `state.equity` addiert (vgl. Finding 1). |
| **F41** | Time-Stop Horizon in Milliseconds | `headless_autobot.js:352` | $\text{MaxMs} = \text{maxHoldHours} \cdot 3600 \cdot 1000$; $\text{HeldMs} = \text{Now} - \text{OpenedAt}$ | `trade.maxHoldHours, trade.openedAt` | Reiner Zeitvergleich ohne ROI-Filter (im Dashboard erst ab ROI < -3%). |
| **F42** | 24h Funnel Aggregator | `headless_autobot.js:362` | $\text{Scanned} = \sum \text{Scanned}_{24h}$; $\text{Passed} = \sum \text{Passed}_{24h}$; $\text{Selected} = \sum \text{Selected}_{24h}$ | `funnelCycles: {scanned, passed, selected, ts}[]` | Rolling 24h Window mit Time-Pruning alter Zyklen. |
| **F43** | Deterministic Outcome Simulator | `shadow_collector.js:93` | Iteriert Candles $1..24$; prüft `slTouched`, `tp1Touched`, `tp2Touched` sequentiell | `record, candles: {o, h, l, c}[], options` | Konservative SL-First Regel bei gleichzeitiger Berührung. |
| **F44** | Transaction Cost Model in R-Units | `shadow_collector.js:83` | $\text{Cost}_R = \frac{(\text{Fee}_{\text{entry}} + \text{Slip}) \cdot \text{Price}}{\text{slDist}}$; $R_{\text{net}} = R_{\text{gross}} - \text{Cost}_{R,\text{entry}} - \text{Cost}_{R,\text{exit}}$ | `exitP, exitCostPct, weight, signalPrice, slDist` | Saubere Umrechnung von prozentualen Gebühren in R-Verlust. |
| **F45** | Scale-Out Trail-to-Break-Even | `shadow_collector.js:135` | $R_{\text{net}} = 0.5 \cdot \text{NetR}(\text{TP1}, \text{Fee}_{\text{maker}}) + 0.5 \cdot \text{NetR}(\text{Entry}, \text{Fee}_{\text{taker}})$ | `tp1Price, signalPrice, costs` | Modelliert 50% TP1 Gewinn + 50% Breakeven-Ausstieg exakt. |
| **F46** | Config Fingerprint Hash | `shadow_collector.js:29` | $\text{Hash} = \text{SHA256}(\text{CanonicalJSON}(\text{Config}))$ | `config: BotConfig` | Deterministiche Zuordnung von Shadow-Entscheidungen zum Profil. |
| **F47** | BTC Regime Classification | `bitget_relay.py:645` | $\text{Bull} = (C > E200 \land E50 > E200)$; $\text{Bear} = (C < E200 \land E50 < E200)$; $\text{Squeeze} = (\text{BB}_W < \text{KC}_W)$ | `candles: list[dict] (min 200 bars)` | Squeeze überschreibt Bull/Bear auf `SIDEWAYS`. |
| **F48** | Token Bucket Rate Limiter | `bitget_relay.py:1085` | $\text{Tokens} = \min(\text{Cap}, \text{Tokens} + (\text{Now} - \text{Last}) \cdot \text{Rate})$; $\text{Allowed} = \text{Tokens} \ge \text{Cost}$ | `rate=10.0, capacity=20.0, amount=1.0` | Verhindert Bitget API 429 Rate-Limits zuverlässig. |
| **F49** | Signal Event Claim & Dedup | `bitget_relay.py:270` | $\text{Key} = \text{SHA256}(\text{Coin} + \text{Side} + \text{Event} + \lfloor \text{Now}/300 \rfloor)$; $\text{Claim} = \text{Key} \notin \text{Claims}$ | `event: dict, now: float` | 5-Minuten Dedup-Fenster verhindert doppelte Telegram/Ntfy-Alarme. |
| **F50** | Python Exponential Moving Average | `bitget_relay.py:596` | $\text{EMA}_t = C_t \cdot k + \text{EMA}_{t-1} \cdot (1-k)$, $k = \frac{2}{p+1}$ | `values: list[float], period: int` | Exakte mathematische Parität zu JS `emaArr`. |
| **F51** | Python Average True Range Series | `bitget_relay.py:605` | $\text{TR}_t = \max(H-L, \|H-C_{t-1}\|, \|L-C_{t-1}\|)$, $\text{ATR} = \text{WilderEMA}(\text{TR}, p)$ | `high, low, close: list[float], period: int` | Exakte mathematische Parität zu JS `atrArr`. |
| **F52** | Python Average Directional Index | `bitget_relay.py:614` | $\text{DX} = 100 \cdot \frac{\|+DI - -DI\|}{+DI + -DI}$, $\text{ADX} = \text{WilderEMA}(\text{DX}, p)$ | `high, low, close: list[float], period: int` | Exakte mathematische Parität zu JS `adxArr`. |
| **F53** | Reference DSR Oracle (Python) | `tests/reference_backtest.py:121` | $\text{calc\_dsr}(\text{returns}, \text{num\_trials})$ | `returns: list[float], num_trials: int` | Unabhängige Python-Referenz nach Bailey & Lopez de Prado (2014). |
| **F54** | Chebyshev Error Function | `tests/reference_backtest.py:82` | $\text{erf}(x) = 1 - (a_1 t + a_2 t^2 + \dots + a_5 t^5) e^{-x^2}$, $t = \frac{1}{1 + p x}$ | `x: float` | Maximaler Approximationsfehler $< 1.5 \cdot 10^{-7}$. |
| **F55** | Normal Cumulative Distribution CDF | `tests/reference_backtest.py:90` | $\Phi(z) = 0.5 \cdot (1 + \text{erf}(z / \sqrt{2}))$ | `z: float` | Standardnormalverteilungs-Integral. |
| **F56** | Acklam Inverse Normal CDF | `tests/reference_backtest.py:93` | $\Phi^{-1}(p) = \text{RationalApproximation}(p)$ | `p: float (0..1)` | Präzision $< 1.15 \cdot 10^{-9}$ über das gesamte Intervall $(0, 1)$. |
| **F57** | Reference PAVA Isotonic Calibration | `tests/reference_backtest.py:155` | $\text{PAVA}(\text{Scores}, \text{Outcomes})$ | `trades: list[dict]` | Unabhängiges Python-Orakel für monotone Siegwahrscheinlichkeiten. |
| **F58** | Reference Trade Evaluator | `tests/reference_backtest.py:192` | $\text{WR} = W/N$, $\text{PF} = \sum W_R / \|\sum L_R\|$, $\text{MaxDD} = \max(\text{Peak} - \text{Cum})$ | `trades: list[dict]` | Exakte Parität zu JS `evaluateTrades`. |
| **F59** | Reference Accounting Reconciler | `tests/reference_backtest.py:218` | $\text{EndingEquity} = \text{Start} + \text{Realized} + \text{Unrealized} - \text{Fees}$ | `starting_equity, trades, risk_per_r` | Exakte Parität zu JS `reconcileBacktestAccounting`. |
| **F60** | Pine Confluence Core Score | `Symbiose_Signal_System_v1.pine:500` | $\text{coreScore} = \text{clamp}(0.30 \cdot \text{TS} + 0.25 \cdot \text{MS} + 0.25 \cdot \text{VS} + 0.20 \cdot \text{SS}, 0, 100)$ | Pine Script v6 floats | Exakte Parität zu JS `aggregateConfluenceScore`. |
| **F61** | Pine Multi-Timeframe Alignment | `Symbiose_Signal_System_v1.pine:458` | $\text{alignedBull} = \sum_{k=1}^4 \mathbb{I}_{\text{mtfD}_k = 1}$, `lookahead=barmerge.lookahead_off` | `request.security(...)` | Garantiert lookahead-freie HTF-Aggregation in TradingView. |
| **F62** | Pine Dynamic TP1 Function | `Symbiose_Signal_System_v1.pine:125` | `f_dynTP1`: Sucht nächste gegensätzliche FVG/EQH/EQL-Struktur in $[1.0R, 2.0R)$ | `dir, entry, r, fAct, fDir, fTop, fBot, eqhLv, eqlLv` | Exakte Parität zu JS `dynamicTp1At`. |
| **F63** | Pine Volume Delta & CVD | `Symbiose_Signal_System_v1.pine:218` | $\text{volDelta} = \text{barRange} > 0 \text{ ? } V \cdot \frac{2C - H - L}{H - L} \text{ : } 0.0$; $\text{CVD} = \text{cum}(\text{volDelta})$ | `volume, high, low, close` | Exakte Parität zu JS `cvdSeries`. |
| **F64** | Pine SuperTrend Indicator | `Symbiose_Signal_System_v1.pine:187` | `ta.supertrend(atrLen=10, factor=3.0)` | `close, high, low` | Exakte Parität zu JS `stArr`. |
| **F65** | Pine Macro Adjustment & Veto | `Symbiose_Signal_System_v1.pine:514` | `fgAdj, fundAdj, oiAdj, basisAdj, macroAdj` Parität zu JS `macroAdjust` | `inFundingBias, inFundingZ, inOIBias, inFG` | Exakte Parität zu JS `macroAdjust`. |

---

## 3. Detaillierte Befunde (Quant-Math-Audit)

### Befund 1: Fehlende Netto-PnL- und Gebührengutschrift auf Runner-Equity bei Trade-Close
* **Was:** `headless_autobot.js` führt beim Schließen eines Trades ausschließlich `state.equity += updated.margin;` aus. Der realisierte PnL (`histEntry.realizedPnl`) und anfallende Transaktionsgebühren werden der Kontobalance niemals gutgeschrieben oder abgezogen.
* **Wo:** `headless_autobot.js:644` (im Vergleich zu `Symbiose_Dashboard.html:10366`)
* **Warum kritisch [CRITICAL]:** Die Server-Runner-Equity bleibt dauerhaft auf `initialEquity` eingefroren (resettet sich nach Positionsschluss immer auf den Startwert). Kelly-Sizing (`calcKelly(..., state.equity)`) und maximales Positionsnotional können dadurch weder auf Kontogewinne skalieren (Compounding unmöglich) noch auf Kontoverluste reagieren (Drawdown-Schutz außer Kraft gesetzt).
* **Fix-Vorschlag:** In `headless_autobot.js:644` analog zum Dashboard L10366 anpassen:
  ```javascript
  const netPnl = (histEntry.realizedPnl || 0) - (histEntry.fees || 0);
  state.equity = Math.max(0, state.equity + updated.margin + netPnl);
  ```

---

### Befund 2: Fehlender Take-Profit-Exit-Pfad in Headless Autobot (Drift zur Browser-Engine)
* **Was:** Erreicht ein Trade TP1, TP2 oder TP3, setzt `headless_autobot.js` lediglich ein Status-Flag (`updated[`${event}Hit`] = true`) und emittiert ein Event. Ein Teilverkauf (Scale-Out von 50% Margin wie im Dashboard L10270) oder ein vollständiger Exit bei TP3 erfolgt nicht.
* **Wo:** `headless_autobot.js:628-631` (im Vergleich zu `Symbiose_Dashboard.html:10270-10310` und `10341-10354`)
* **Warum kritisch [CRITICAL]:** Ein Trade verbleibt in `headless_autobot.js` trotz Erreichen des Kursziels so lange im Markt, bis der Kurs wieder zum Stop-Loss (oder Breakeven) zurückfällt (`sl_close`) oder der Time-Stop greift. Ein profitabler TP-Trade kann im Headless-Runner niemals als Take-Profit-Gewinn abgeschlossen werden.
* **Fix-Vorschlag:** 
  1. Bei TP2: 50% Scale-Out mit Margin-Reduktion (`updated.margin *= 0.5; updated.notional *= 0.5`) und Nachziehen des Trailing-SL.
  2. Bei TP3 (oder maximalem TP): Vollständiges Schließen der Restposition (`closed = true; closeReason = 'tp3_max'`).

---

### Befund 3: Fehlerhafte Unterdrückung der SL-Prüfung bei TP1-Trigger in Headless Autobot
* **Was:** In `checkTpSlHits` wird die Stop-Loss-Bedingung durch `if (!trade.slHit && !hit(trade.tp1 || trade.tp))` maskiert.
* **Wo:** `headless_autobot.js:332`
* **Warum kritisch [HIGH]:** Wenn der Preis in einer schnellen Kerze TP1 überschreitet oder `hit(trade.tp1)` wahr ist, wird der SL-Zweig komplett übersprungen. Falls `trade.currentSl` auf Breakeven liegt und der Kurs schwankt, ist die Verknüpfung mit dem aktuellen Preis anstelle des historischen Status `trade.tp1Hit` logisch inkonsistent.
* **Fix-Vorschlag:** Entkopplung der Prüfzweige:
  ```javascript
  if (!trade.slHit) {
    if (dir === 1 && markPrice <= trade.currentSl) events.push('sl_close');
    if (dir === -1 && markPrice >= trade.currentSl) events.push('sl_close');
  }
  ```

---

### Befund 4: Falscher Exit-Grund `'sl_close'` bei Time-Stop-Schließungen in Runner-History
* **Was:** In `headless_autobot.js:642` wird `closeTradeRecord(updated, markPrice, closed ? 'sl_close' : 'timestop')` aufgerufen. Da der Aufruf innerhalb von `if (closed)` steht, ist `closed` immer `true`.
* **Wo:** `headless_autobot.js:642`
* **Warum kritisch [HIGH]:** Jeder per Time-Stop geschlossene Trade wird in der Historie fälschlicherweise als `'sl_close'` protokolliert. Dies verfälscht die Attributionsstatistiken (SL-Rate vs Time-Stop-Rate) in der Shadow- und Autobot-Analyse.
* **Fix-Vorschlag:** Den tatsächlichen Schließungsgrund als Variable übergeben:
  ```javascript
  let closeReason = 'sl_close';
  if (!closed && checkTimeStop(updated)) {
    closed = true;
    closeReason = 'timestop';
    await emitTradeEvent(engine, updated, 'other_close', { price: markPrice, reason: 'Time-Stop' });
  }
  if (closed) {
    ...
    const histEntry = closeTradeRecord(updated, markPrice, closeReason);
  }
  ```

---

### Befund 5: Populationsvarianz ($N$) statt Stichprobenvarianz ($N-1$) im Funding Rate Z-Score
* **Was:** `calcFundingBias` berechnet die Varianz über `const variance = rates.reduce(...) / n`.
* **Wo:** `Symbiose_Dashboard.html:1599`
* **Warum kritisch [MEDIUM]:** Bei typischen Stichprobengrößen von $N=10..20$ Raten unterschätzt die Division durch $N$ die Standardabweichung um $\approx 2.5\% - 5\%$. Der Z-Score $Z = (\text{Rate} - \mu)/\sigma$ fällt dadurch systematisch leicht überhöht aus, wodurch Extremwert-Schwellen ($|Z| > 2.5$) etwas zu sensibel ansprechen.
* **Fix-Vorschlag:** Auf unvoreingenommene Stichprobenvarianz mit $N-1$ umstellen:
  ```javascript
  const variance = rates.length > 1 
    ? rates.reduce((a, b) => a + (b - mean) ** 2, 0) / (n - 1)
    : 0;
  ```

---

### Befund 6: Approximierter Liquidationspuffer ohne börsenspezifische MMR-Stufentabellen
* **Was:** `recommendLeverage` verwendet die Faustformel $\text{LiqBuffer} = \frac{100}{\text{Leverage}} - 0.5\%$ unter Annahme einer fixen $0.5\%$ Maintenance Margin Rate (MMR).
* **Wo:** `Symbiose_Dashboard.html:1837`
* **Warum kritisch [MEDIUM]:** Bitget v2 Futures nutzen gestaffelte MMR-Tiers (Tiered Maintenance Margin) abhängig vom Positionsnotional. Bei großen Positionen steigt die MMR auf bis zu $1.5\% - 5\%$, wodurch der tatsächliche Liquidationspreis näher am Einstieg liegt als durch die lineare Näherung suggeriert.
* **Fix-Vorschlag:** In der Benutzeroberfläche und in Tooltips klarstellen: *"Geschätzter Liquidationspuffer bei Standard-MMR (0.5%)"*. Für Großpositionen die Bitget-Kontraktspezifikation `spec.maintenanceMarginRate` dynamisch einbeziehen.

---

### Befund 7: Unberücksichtigte Funding-Haltekosten (Carry) im Walk-Forward Backtest
* **Was:** Im Walk-Forward Backtest (`simulateRange`) und im Shadow Collector werden Transaktionsgebühren und Slippage modelliert, aber keine Finanzierungsgebühren (Funding Rates) während der Haltedauer abgezogen.
* **Wo:** `Symbiose_Dashboard.html:1992` & `shadow_collector.js:83-87`
* **Warum kritisch [MEDIUM]:** Positionen können bis zu 200 Kerzen gehalten werden (z.B. auf 4h bis zu 33 Tage). In starken Bullenmärkten mit dauerhaft positivem Funding zahlen Long-Positionen ca. $0.01\% - 0.05\%$ pro 8h-Intervall. Das Weglassen der Funding-Kosten führt zu einer leicht optimistischen Schätzung der $R_{\text{net}}$-Erwartung für Swing-Trades.
* **Fix-Vorschlag:** Bei Trades mit mehr als 8 Stunden Haltedauer ein durchschnittliches Finanzierungsentgelt (z.B. $0.01\%$ je 8h Intervall) in `simulateRange` als Haltekostenfaktor anrechnen.

---

### Befund 8: Out-of-Bounds Indexzugriff bei $i=0$ in `obvArr`
* **Was:** In `obvArr` wird in der ersten Iteration $i=0$ auf `c[-1]` zugegriffen.
* **Wo:** `Symbiose_Dashboard.html:1193`
* **Warum kritisch [LOW]:** In JavaScript liefert `c[-1]` den Wert `undefined`. Vergleiche mit `undefined` ergeben `false`, wodurch `out[0] = 0` gesetzt wird. Dies verursacht keinen Laufzeitfehler, verhindert jedoch V8-JIT-Monomorphismus-Optimierungen und ist formal fehlerhafter Code.
* **Fix-Vorschlag:** 
  ```javascript
  out[0] = 0;
  for (let i = 1; i < n; i++) {
    o += c[i] > c[i - 1] ? v[i] : c[i] < c[i - 1] ? -v[i] : 0;
    out[i] = o;
  }
  ```

---

### Befund 9: Fehlende Absicherung gegen Sekunden-Zeitstempel in `vwapArr`
* **Was:** `vwapArr` berechnet den Tagessprung über `Math.floor(ms[i] / 86400000)`.
* **Wo:** `Symbiose_Dashboard.html:1200`
* **Warum kritisch [LOW]:** Werden künftig Datenquellen angebunden, die Unix-Zeitstempel in Sekunden liefern (z.B. 10-stellig), ergibt die Division durch $86\,400\,000$ für alle Bars den Wert 0. Der VWAP setzt sich dann niemals um 00:00 UTC zurück, sondern akkumuliert unendlich weiter.
* **Fix-Vorschlag:** 
  ```javascript
  const ts = ms[i] > 1e11 ? ms[i] : ms[i] * 1000;
  const day = Math.floor(ts / 86400000);
  ```

---

### Befund 10: Populationsvarianz bei BTC Squeeze-Filterung im Relay
* **Was:** `bitget_relay.py:663` dividiert bei der Bollinger-Band-Varianz durch 20 statt 19.
* **Wo:** `bitget_relay.py:663`
* **Warum kritisch [LOW]:** Die Standardabweichung ist dadurch um $\approx 2.56\%$ geringer als bei Bessel-korrigierter Stichprobenvarianz. Da `Symbiose_Dashboard.html:1714` dieselbe Formel nutzt, besteht Parität zwischen den Komponenten; statistisch ist es jedoch eine Populations- anstelle einer Stichprobenstreuung.
* **Fix-Vorschlag:** Dokumentieren als deterministische BB-Squeeze-Konvention oder synchron auf $N-1$ umstellen.

---

## 4. Top-10-Befunde (Zusammenfassung)

1. **[CRITICAL] Fehlende PnL-Verrechnung auf Server-Equity:** `headless_autobot.js:644` addiert nach Trade-Close nur `margin` zurück; `state.equity` ignoriert realisierten PnL komplett.
2. **[CRITICAL] Fehlender TP-Exit-Pfad in Headless Autobot:** `headless_autobot.js:628-631` führt bei Erreichen von TP1/TP2/TP3 keinen Teilverkauf oder Exit durch; Trades laufen immer bis SL/Time-Stop.
3. **[HIGH] Unterdrückte SL-Prüfung bei TP1 in Headless Autobot:** `headless_autobot.js:332` überspringt `sl_close` wenn `hit(tp1)` aktiv ist.
4. **[HIGH] Falscher Exit-Grund bei Time-Stop:** `headless_autobot.js:642` protokolliert Time-Stop-Schließungen fälschlicherweise immer als `'sl_close'`.
5. **[MEDIUM] Populationsvarianz im Funding Z-Score:** `Symbiose_Dashboard.html:1599` dividiert durch $N$ statt $N-1$, was $Z$ bei $N \le 20$ leicht überhöht.
6. **[MEDIUM] Unvollständige Liquidationsmargin-Modellierung:** `Symbiose_Dashboard.html:1837` nutzt fixe 0.5% MMR ohne gestaffelte Bitget-MMR-Tiers.
7. **[MEDIUM] Fehlende Funding-Haltekosten im Backtest:** `Symbiose_Dashboard.html:1992` & `shadow_collector.js:83` berücksichtigen keinen 8h-Funding-Carry bei Mehrtages-Trades.
8. **[LOW] Array-Index-Underflow bei OBV:** `Symbiose_Dashboard.html:1193` greift bei $i=0$ auf `c[-1]` zu (`undefined` in JS).
9. **[LOW] Zeitstempel-Annahme in VWAP:** `Symbiose_Dashboard.html:1200` setzt strikt Millisekunden für den täglichen Reset um 00:00 UTC voraus.
10. **[LOW] Populationsvarianz im Relay-Squeeze:** `bitget_relay.py:663` nutzt 20 statt 19 als Divisor für 20-Bar-Bollinger-Bänder.

---

## 5. Fazit & Quant-Verdict

* **Formel-Inventar:** 65 erfasste mathematische Definitionen über alle 6 Kernkomponenten.
* **Mathematische Integrität der Research-Engine:** Die mathematischen Kernoracles (`calcDSR`, PAVA, Kelly-Sizing, Confluence-Scoring, Pine-Script-Parität) sind theoretisch fundiert, strikt gegen Division durch 0 abgesichert und stimmen mit der Literatur (Bailey & Lopez de Prado 2014) überein.
* **Server-Runner Drift:** Der Server-Paper-Runner (`headless_autobot.js`) weist jedoch erhebliche Abweichungen zum Dashboard bei der Trade-Verwaltung (kein TP-Exit, keine PnL-Equity-Verrechnung) auf, die vor einem Produktiveinsatz behoben werden müssen.
* **Quant-Verdict:** `SOFTWARE_GO / MODEL_NO_EVIDENCE` (Baseline grün, mathematische Kernoracles konsistent; Behebung der 4 Runner-Trade-Management-Befunde empfohlen).
