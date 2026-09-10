# AURA Edge-Forschung Phase C — Experimentbericht (Selektionsobjektiv-Reform & Fold-1-Bias)

**Datum:** 2026-09-10  
**Gegenstand:** Bewertung des prä-registrierten Modellexperiments **EXP-024 (C1: Selektionsobjektiv-Reform)** und Quantifizierung des **Fold-1-Geometrie-Bias (C2)** auf voller Fixture-Tiefe.  
**Ergebnis EXP-024:** **BESTANDEN** über alle 4 vorab definierten Kriterien.  
**B3 Status:** Weiterhin strikt **DEFERRED**.

---

## 1. Executive Summary & Headline

> **„Die regularisierte Objektiv-Reform (EXP-024: $n \ge 2$, Penalisierung $(1 - 1/(1+n))$) hebt die aggregierte Net-Expectancy auf voller Tiefe um $+0.032\text{ R}$ und wählt organisch in 50 % aller Folds `regimeGate = true`. Der Effekt ist sowohl auf 1h ($+0.028\text{ R}$) als auch auf 4h ($+0.039\text{ R}$) positiv. Die Quantifizierung des Fold-1-Bias deckt auf, dass bis zu 75.6 % aller Backtest-Trades im 300-Bar-Fold-1-Fenster erzeugt werden."**

---

## 2. Prä-Registriertes Experiment C1: Selektionsobjektiv-Reform [EXP-024]

### 2.1 Hypothese & Formel (vorab festgelegt)

Ersatz der harten Stufe:
$$\text{obj}_{\text{alt}} = \begin{cases} \text{exp} \cdot \sqrt{n} & \text{falls } n \ge 5 \\ -\infty & \text{sonst} \end{cases}$$

durch die regularisierte Zielfunktion:
$$\text{obj}_{\text{neu}} = \begin{cases} \text{exp} \cdot \sqrt{n} \cdot \left(1 - \frac{1}{1+n}\right) & \text{falls } n \ge 2 \\ -\infty & \text{sonst} \end{cases}$$

**Wirkungsweise:** Selektive Strategien mit $n \in [2, 4]$ Trades im Trainingsfenster werden nicht mehr mit $-\infty$ verworfen, sondern fließend skaliert ($n=2 \rightarrow \times 0.67$, $n=5 \rightarrow \times 0.83$, $n=15 \rightarrow \times 0.94$).

---

### 2.2 Gesamtergebnisse auf voller Fixture-Tiefe (EXP-024)

| Fixture | Total Bars | Base N | Ref N | Base Net Exp | Ref Net Exp | Δ Net Exp | Base WR | Ref WR | Base DSR | Ref DSR | Gated Folds |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **BTC 1h** | 14.773 | 186 | 186 | −0.229 R | **−0.229 R** | +0.000 R | 24.2% | 24.2% | 0.001 | 0.001 | 3 / 4 |
| **ETH 1h** | 14.773 | 279 | 279 | −0.078 R | **−0.078 R** | +0.000 R | 30.5% | 30.5% | 0.013 | 0.013 | 2 / 4 |
| **SOL 1h** | 14.773 | 170 | 168 | −0.121 R | **−0.037 R** | **+0.084 R** | 30.0% | 32.7% | 0.004 | 0.017 | 3 / 4 |
| **XRP 4h** | 10.270 | 212 | 167 | +0.072 R | **+0.150 R** | **+0.078 R** | 33.0% | 35.3% | 0.055 | 0.079 | 2 / 4 |
| **DOGE 4h**| 10.270 | 327 | 327 | +0.100 R | **+0.100 R** | +0.000 R | 33.6% | 33.6% | 0.133 | 0.133 | 0 / 4 |
| **Ø GESAMT**| — | **234.8** | **225.4** | **−0.051 R** | **−0.019 R** | **+0.032 R** | — | — | **0.041** | **0.049** | **10 / 20 (50%)** |

---

### 2.3 Formale Auswertung der vorab definierten Erfolgskriterien (1–4)

1. **Kriterium 1: Aggregierte OOS-Net-Expectancy steigt gegenüber Baseline**  
   - Baseline Ø: $-0.051\text{ R}$ $\rightarrow$ Reform Ø: **$-0.019\text{ R}$** ($\Delta = \mathbf{+0.032\text{ R}}$).  
   - **Status: BESTANDEN.**

2. **Kriterium 2: `regimeGate = true` wird in $\ge 50\,\%$ der Folds organisch gewählt**  
   - Gated-Folds: $10 / 20$ Folds ($50.0\,\%$).  
   - BTC: 3/4 Folds (`rg=true`), ETH: 2/4 Folds (`rg=true`), SOL: 3/4 Folds (`rg=true`), XRP: 2/4 Folds (`rg=true`), DOGE: 0/4 Folds.  
   - **Status: BESTANDEN.**

3. **Kriterium 3: Cross-Asset-Richtung (1h positiv, 4h nicht-negativ)**  
   - **1h-Gruppe (BTC, ETH, SOL):** $\Delta = \frac{0.000 + 0.000 + 0.084}{3} = \mathbf{+0.028\text{ R}}$ (positiv).  
   - **4h-Gruppe (XRP, DOGE):** $\Delta = \frac{+0.078 + 0.000}{2} = \mathbf{+0.039\text{ R}}$ (nicht-negativ, sogar deutlich positiv).  
   - **Status: BESTANDEN (Voll bestätigt über alle Timeframes).**

4. **Kriterium 4: DSR-Verhalten (Transparenz, keine $\ge 0.5$ Anforderung)**  
   - Setup-DSR steigt im Mittel von $0.041$ auf **$0.049$**.  
   - Bleibt erwartungsgemäß unter $0.50$, da $n$ und per-Trade-Sharpe noch unter der Zertifizierungsgrenze liegen.  
   - **Status: ERFÜLLT (im Rahmen der Definition).**

---

## 3. Fold-by-Fold Detailanalyse

### 3.1 BTC 1h (14.773 Bars, 4 Folds)
- **Fold 1** (Train 300 / Test 3.559): `lt:72, st:22, rg:false` | Train Trades: 11 | Test Trades: 138 | Net Exp: $-0.276\text{ R}$ | PF: 0.64
- **Fold 2** (Train 3.859 / Test 3.559): `lt:75, st:28, rg:true` | Train Trades: 12 | Test Trades: 16 | Net Exp: $-0.042\text{ R}$ | PF: 0.95
- **Fold 3** (Train 7.418 / Test 3.559): `lt:75, st:22, rg:true` | Train Trades: 27 | Test Trades: 19 | Net Exp: $-0.554\text{ R}$ | PF: 0.28
- **Fold 4** (Train 10.977 / Test 3.559): `lt:75, st:22, rg:true` | Train Trades: 46 | Test Trades: 13 | Net Exp: $+0.507\text{ R}$ | PF: 1.79

### 3.2 ETH 1h (14.773 Bars, 4 Folds)
- **Fold 1** (Train 300 / Test 3.559): `lt:78, st:22, rg:false` | Train Trades: 10 | Test Trades: 120 | Net Exp: $-0.020\text{ R}$ | PF: 0.97
- **Fold 2** (Train 3.859 / Test 3.559): `lt:75, st:22, rg:true` | Train Trades: 18 | Test Trades: 16 | Net Exp: $+0.136\text{ R}$ | PF: 1.22
- **Fold 3** (Train 7.418 / Test 3.559): `lt:75, st:25, rg:true` | Train Trades: 34 | Test Trades: 16 | Net Exp: $-0.106\text{ R}$ | PF: 0.86
- **Fold 4** (Train 10.977 / Test 3.559): `lt:78, st:22, rg:false` | Train Trades: 339 | Test Trades: 127 | Net Exp: $-0.156\text{ R}$ | PF: 0.79

### 3.3 SOL 1h (14.773 Bars, 4 Folds)
- **Fold 1** (Train 300 / Test 3.559): `lt:72, st:28, rg:false` | Train Trades: 4 | Test Trades: 127 | Net Exp: $-0.060\text{ R}$ | PF: 0.91 *(Verbesserung von $-0.170\text{ R}$)*
- **Fold 2** (Train 3.859 / Test 3.559): `lt:72, st:22, rg:true` | Train Trades: 15 | Test Trades: 12 | Net Exp: $+0.721\text{ R}$ | PF: 3.45
- **Fold 3** (Train 7.418 / Test 3.559): `lt:72, st:22, rg:true` | Train Trades: 27 | Test Trades: 18 | Net Exp: $-0.576\text{ R}$ | PF: 0.27
- **Fold 4** (Train 10.977 / Test 3.559): `lt:72, st:28, rg:true` | Train Trades: 47 | Test Trades: 11 | Net Exp: $+0.281\text{ R}$ | PF: 1.44

### 3.4 XRP 4h (10.270 Bars, 4 Folds)
- **Fold 1** (Train 300 / Test 2.433): `lt:78, st:25, rg:false` | Train Trades: 8 | Test Trades: 78 | Net Exp: $-0.081\text{ R}$ | PF: 0.87
- **Fold 2** (Train 2.733 / Test 2.433): `lt:78, st:22, rg:true` | Train Trades: 2 | Test Trades: 5 | Net Exp: $-0.605\text{ R}$ | PF: 0.28 *(Eliminiert 45 unrentable Chop-Trades)*
- **Fold 3** (Train 5.166 / Test 2.433): `lt:78, st:28, rg:false` | Train Trades: 146 | Test Trades: 80 | Net Exp: $+0.454\text{ R}$ | PF: 1.76
- **Fold 4** (Train 7.599 / Test 2.434): `lt:78, st:22, rg:true` | Train Trades: 17 | Test Trades: 4 | Net Exp: $-0.482\text{ R}$ | PF: 0.39

### 3.5 DOGE 4h (10.270 Bars, 4 Folds)
- **Fold 1** (Train 300 / Test 2.433): `lt:72, st:25, rg:false` | Train Trades: 8 | Test Trades: 81 | Net Exp: $+0.165\text{ R}$ | PF: 1.26
- **Fold 2** (Train 2.733 / Test 2.433): `lt:78, st:25, rg:false` | Train Trades: 85 | Test Trades: 84 | Net Exp: $-0.103\text{ R}$ | PF: 0.84
- **Fold 3** (Train 5.166 / Test 2.433): `lt:78, st:28, rg:false` | Train Trades: 169 | Test Trades: 76 | Net Exp: $+0.433\text{ R}$ | PF: 1.80
- **Fold 4** (Train 7.599 / Test 2.434): `lt:78, st:28, rg:false` | Train Trades: 244 | Test Trades: 86 | Net Exp: $-0.058\text{ R}$ | PF: 0.91

---

## 4. Fold-1-Geometrie-Bias Quantifizierung (C2)

| Fixture | Test Bars (Fold 1) | Anteil Bars | Trades Fold 1 | Total Trades | Anteil Trades | Net Exp Fold 1 | Net Exp Overall |
|---|---|---|---|---|---|---|---|
| **BTC 1h** | 3.559 | 24.1 % | **138** | 186 | **74.2 %** | −0.276 R | −0.229 R |
| **ETH 1h** | 3.559 | 24.1 % | **120** | 279 | **43.0 %** | −0.020 R | −0.078 R |
| **SOL 1h** | 3.559 | 24.1 % | **127** | 168 | **75.6 %** | −0.060 R | −0.037 R |
| **XRP 4h** | 2.433 | 23.7 % | **78** | 167 | **46.7 %** | −0.081 R | +0.150 R |
| **DOGE 4h**| 2.433 | 23.7 % | **81** | 327 | **24.8 %** | +0.165 R | +0.100 R |

### 4.1 Ursachenanalyse des Fold-1-Bias
1. **Asymmetrische Trade-Produktion:** Obwohl Fold 1 zeitlich nur knapp ein Viertel der Test-Historie darstellt ($24\,\%$), produziert Fold 1 auf den 1h-Assets **bis zu $75.6\,\%$ aller Out-of-Sample-Trades**.
2. **Mechanismus:** Im 300-Bar-Trainingsfenster von Fold 1 können selektive Trendfolge-Filter nicht genügend Signale etablieren. Dadurch wird fast immer die ungatete Konfiguration gewählt. Diese schüttet im anschließenden 3.559-Bar-Testfenster hunderte ungefilterte Chop-Trades aus, die das Gesamtergebnis belasten.
3. **Erkenntnis:** Die expanding Walk-Forward mit starrem 300-Bar-Initialfenster erzeugt eine strukturelle Übergewichtung von ungefilterten Chop-Phasen in Fold 1.

---

## 5. Status von B3 (TP1 / R:R-Tuning) & Empfehlung

- **B3 (TP1/R:R-Tuning) bleibt DEFERRED.**
- **Begründung:** Solange die Walk-Forward-Geometrie (Initial-Trainingsgröße vs. Testfold-Größe) die Trade-Verteilung dominiert, würde ein vorzeitiges TP1-Tuning auf den aggregierten Trades primär versuchen, die Fold-1-Chop-Trades zu fitten (*p-Hacking*).
- **Nächster logischer Forschungsschritt:** Evaluierung einer adaptiven Fold-Geometrie (z. B. proportionales Initial-Training `minTrainBars = Math.floor(testableBars / (K + 1))` oder Rolling Window) als sauber isoliertes Modellexperiment.
