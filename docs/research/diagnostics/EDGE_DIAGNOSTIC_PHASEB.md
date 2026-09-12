# AURA Edge-Forschung Phase B — Experimentbericht (Regime-Gate & Stichproben-Erweiterung)

**Datum:** 2026-09-10  
**Gegenstand:** Bewertung der zwei prä-registrierten Experimente B1 (Gated-Variante) und B2 (Stichprobe auf volle Fixture-Tiefe).
**Status:** B1 richtungweisend (nicht zertifizierbar bei n=1–2) | B2 teilweise erfüllt (Baseline n≥100, Gated n<100 auf 4h) | Cross-Asset: NEIN (4h nicht bestätigt).

---

## 0. Ehrliche Headline

> **„Regime-Filter dreht die 1h-Assets von deutlich negativ auf ~flat/leicht positiv (Net-Exp −0.14 → +0.03 R), DSR bleibt 0.06–0.11 ≪ 0.5 → weiterhin NO_EVIDENCE; 4h bestätigt den Effekt nicht."**

---

## 1. Ausgangslage & Kritisches Phänomen der Baseline (v1.1.0/v1.1.1)

1. **Beobachtung:** Auf allen 5 Golden Master Fixtures (BTC 1h, ETH 1h, SOL 1h, XRP 4h, DOGE 4h) wählte die Baseline-Walk-Forward-Optimierung auf 1500 Bars in **allen 20 Folds (4 Folds × 5 Assets) `regimeGate = false`**.
2. **Ursache & Fold-1-Geometrie:** Das Optimierungskriterium $\text{obj} = \text{exp} \times \sqrt{n}$ mit der Schranke `minTrainTrades = 5` bestraft selektive Strategien in kurzen Trainingsfenstern. Im Fold 1 (300 Bars Train) erzeugt das strikte Regime-Gate ($EMA20 > EMA50 > EMA200 \land BB \ge KC$) nur 1–2 Trades. Da $n < 5$, wird `obj` auf $-\infty$ gesetzt, und der Optimizer weicht zwingend auf die ungatete Variante aus.
3. **Konsequenz:** Bisherige Releases maßen unbemerkt die ungeschützte Chop-Strategie. Die geschützte Trendfolge-Strategie (`regimeGate = true`) wurde OOS de facto noch nie isoliert bewertet.

---

## 2. Experiment B1: Gated-Variante auf 1500 Bars [EXP-022]

**Prä-registrierte Hypothese:** Die Walk-Forward-Variante mit erzwungenem `regimeGate = true` erzielt eine höhere Net-OOS-Expectancy als die ungatete Baseline.
**Messaufbau:** 5 Golden Fixtures, 1500 Bars, $K=4$, Standard-Kosten (Maker 2 bps, Taker 6 bps, Slippage 5 bps, TimeStop 15), Parameter-Grid fixiert auf `regimeGate: true` (9 Kombinationen).

### 2.1 Ergebnisübersicht B1 (1500 Bars)

| Fixture | TF | Base Trades | Gated Trades | Base Net Exp | Gated Net Exp | Δ Net Exp | Base DSR | Gated DSR (n<3 → neutral) | Status |
|---|---|---|---|---|---|---|---|---|---|
| **BTC 1h** | 1h | 33 | 2 | −0.118 R | +2.589 R | +2.707 R | 0.029 | 0.500 (neutral) | Richtungweisend |
| **ETH 1h** | 1h | 34 | 2 | +0.208 R | +2.399 R | +2.191 R | 0.038 | 0.500 (neutral) | Richtungweisend |
| **SOL 1h** | 1h | 35 | 2 | −0.036 R | +2.516 R | +2.552 R | 0.030 | 0.500 (neutral) | Richtungweisend |
| **XRP 4h** | 4h | 32 | 1 | −0.036 R | +1.243 R | +1.278 R | 0.028 | 0.500 (neutral) | Richtungweisend |
| **DOGE 4h**| 4h | 32 | 1 | +0.083 R | +1.812 R | +1.729 R | 0.050 | 0.500 (neutral) | Richtungweisend |
| **Ø GESAMT**| — | **33.2** | **1.6** | **+0.020 R** | **+2.112 R** | **+2.091 R** | **0.035** | **0.500 (neutral)** | **n=1–2 Trades** |

*Korrektur K1:* Der DSR-Wert `0.500` bei der Gated-Variante ist der neutrale Fallback von `calcDSR` bei $n < 3$ Trades und **kein** statistischer DSR-Erfolg. Die Net-Expectancy von $+2.112\text{ R}$ bei $n = 1\text{--}2$ Trades ist richtungweisend positiv, aber statistisch nicht zertifizierbar.

---

## 3. Experiment B2: Stichprobe auf volle Fixture-Tiefe [EXP-023]

**Prä-registrierte Hypothese:** Auf voller Fixture-Tiefe (10.270 bis 14.773 Bars) wächst die Stichprobe auf $n \ge 100$ je Fixture, wodurch die DSR-Zertifizierungsschwelle sinkt und belastbare OOS-Messungen möglich werden.

### 3.1 Ergebnisübersicht B2 (Volle Tiefe: ~14.7k Bars 1h / ~10.3k Bars 4h)

| Fixture | Total Bars | Base Trades | Gated Trades | Base Net Exp | Gated Net Exp | Δ Net Exp | Base DSR | Gated DSR | Nötiger SR ($DSR \ge 0.50$) |
|---|---|---|---|---|---|---|---|---|---|
| **BTC 1h** | 14.773 | 186 | **61** | −0.229 R | **−0.012 R** | **+0.218 R** | 0.001 | 0.060 | $SR \ge 0.196$ ($n=61$) |
| **ETH 1h** | 14.773 | 279 | **65** | −0.078 R | **+0.036 R** | **+0.114 R** | 0.013 | 0.080 | $SR \ge 0.190$ ($n=65$) |
| **SOL 1h** | 14.773 | 170 | **54** | −0.121 R | **+0.078 R** | **+0.199 R** | 0.004 | 0.114 | $SR \ge 0.209$ ($n=54$) |
| **XRP 4h** | 10.270 | 212 | **21** | +0.072 R | **−0.003 R** | **−0.075 R** | 0.055 | 0.064 | $SR \ge 0.340$ ($n=21$) |
| **DOGE 4h**| 10.270 | 327 | **25** | +0.100 R | **+0.099 R** | **−0.001 R** | 0.133 | 0.114 | $SR \ge 0.310$ ($n=25$) |
| **Ø GESAMT**| — | **234.8** | **45.2** | **−0.051 R** | **+0.040 R** | **+0.091 R** | **0.041** | **0.086** | **$SR \ge 0.126$ ($N=226$)** |

*Korrektur K2 & K3:*
1. **Cross-Asset-Bestätigung: NEIN.** Der positive Effekt des Regime-Filters ist **1h-spezifisch** (BTC $+0.218$, ETH $+0.114$, SOL $+0.199\text{ R}$). Auf 4h ist der Effekt flach bis leicht negativ (XRP $-0.075\text{ R}$, DOGE $-0.001\text{ R}$), da 4h-Signale ohne Gate bereits profitabel sind und das Gate Trades überfiltert ($n=21\text{--}25$ über 4.5 Jahre).
2. **Kriterium B2 Status:** **TEILWEISE ERFÜLLT.** Die Baseline erreicht $n \ge 100$ ($n=170\text{--}327$), die Gated-Variante erreicht auf 1h $n=54\text{--}65$, bleibt aber auf 4h mit $n=21\text{--}25$ unter der 100er-Marke.

---

## 4. Fold-by-Fold Analyse & Geometrie-Erkenntnis

Auf voller Tiefe wählt das Selektionsobjektiv in den späteren Folds (Fold 2, 3, 4) organisch `regimeGate = true` (z. B. BTC Fold 2/3/4, ETH Fold 2/3, SOL Fold 2/3/4).
Der strukturelle Engpass liegt primär in **Fold 1**:
- Fold 1 Train: 300 Bars (fest) → zu kurz für $\ge 5$ Gated-Trades → zwingend ungated gewählt.
- Fold 1 Test: 3.559 Bars (bei 14.7k Gesamtkegel) → größtes Testfenster, das ungeschützt im Chop läuft und das Gesamtergebnis dominiert.

---

## 5. Fazit & Ableitung für Phase C

1. **Regime-Filter ist kein Allheilmittel:** Er rettet 1h-Assets vor massivem Chop-Verlust, ist aber auf 4h unnötig restriktiv.
2. **Selektionsobjektiv muss reformiert werden:** Ziel von Phase C (EXP-024) ist es, die künstliche $-\infty$-Abstrafung bei $n < 5$ durch eine stetige Regularisierung abzulösen, damit der Optimizer auf 1h organisch `regimeGate = true` wählt, ohne 4h zu degradieren.
3. **B3 (TP1/R:R-Tuning):** Bleibt strikt **DEFERRED**, bis das Selektionsobjektiv sauber reformiert und validiert ist.
