# AURA Edge-Forschung Phase D — Fairer Geometrie-Vergleich & Abschlussbericht

**Datum:** 2026-09-10  
**Gegenstand:** Bewertung des Diagnose-Experiments **EXP-025 (D1: Fold-1-Geometrie-Fix)** auf voller Fixture-Tiefe und Anwendung der vorab festgelegten **D2-Stopp-Regel**.  
**Ergebnis EXP-025:** **TEILWEISE BESTANDEN** (Fold-1-Trade-Anteil im Fixture-Mittel $26.5\,\%$, aber SOL einzeln $42.3\,\%$; selektive Trainingskapazität auf 4h nicht hergestellt).  
**D2 Stopp-Entscheidung:** **STOPP (NO_EVIDENCE)** — konservativ aggregierter OOS-DSR $= 0.038 < 0.50$ (205 gepoolte Trades, $T=9\times5=45$ Cross-Fixture-Hypothesen). Selbst die lokale $T=9$-Lesart erreicht nur $0.152$. B3 (TP1/R:R-Tuning) wird **NICHT** durchgeführt.

---

## 1. Executive Summary & Ehrliches Abschlussverdikt

> **„Mit der fairen Fold-1-Geometrie (Initial-Training 2000 Bars auf 1h / 500 Bars auf 4h) sinkt der Fold-1-Trade-Anteil auf 26.5 % im ungewichteten Fixture-Mittel. Die Walk-Forward wählt auf BTC 1h in allen 4 Folds organisch `regimeGate = true` und verbessert die 1h-Gated-Expectancy auf $+0.083\text{ R}$ (ETH $+0.126\text{ R}$, SOL $+0.147\text{ R}$). Der konservativ aggregierte DSR über alle 205 Gated-OOS-Trades erreicht bei $T=45$ nur $0.038$ (lokal $T=9$: $0.152$) und verfehlt die vorab festgelegte Zertifizierungsschwelle von $0.50$ klar. Gemäß bindender D2-Stopp-Regel wird die Edge-Forschung beendet und B3 (TP1-Tuning) nicht durchgeführt, um Overfitting zu verhindern."**

---

## 2. Versuchsaufbau EXP-025: Faire Fold-1-Geometrie

### 2.1 Problem & Behebung
- **Alte Geometrie (300 Bars Initial-Train):** Fold 1 verfügte über zu wenige Bars für selektive Strategien ($n < 2$), wählte zwingend ungatetes Chop-Trading und erzeugte bis zu $75.6\,\%$ aller OOS-Trades.
- **Faire Geometrie (EXP-025):**
  - Für 1h-Assets ($TF \le 60\text{m}$): `minTrainBars = 2000` Bars ($\approx 83$ Tage)
  - Für 4h-Assets ($TF \ge 240\text{m}$): `minTrainBars = 500` Bars ($\approx 83$ Tage)
  - $K = 4$ Folds beibehalten, $t1$-sichere Purge-Grenzen unverändert.

---

## 3. Gesamtergebnisse auf voller Fixture-Tiefe (Baseline vs. Gated)

| Fixture | Total Bars | Base N | Gated N | Base Net Exp | Gated Net Exp | Δ Net Exp | Base WR | Gated WR | Base DSR | Gated DSR | Base RG Folds |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **BTC 1h** | 14.773 | 55 | 55 | −0.023 R | **−0.023 R** | +0.000 R | 29.1% | 29.1% | 0.028 | 0.056 | **4 / 4** |
| **ETH 1h** | 14.773 | 241 | 56 | −0.073 R | **+0.126 R** | **+0.199 R** | 27.0% | 30.4% | 0.015 | **0.126** | 2 / 4 |
| **SOL 1h** | 14.773 | 246 | 47 | −0.063 R | **+0.147 R** | **+0.210 R** | 32.1% | 38.3% | 0.009 | **0.164** | 2 / 4 |
| **XRP 4h** | 10.270 | 205 | 21 | +0.058 R | **−0.003 R** | −0.060 R | 32.7% | 28.6% | 0.048 | 0.064 | 1 / 4 |
| **DOGE 4h**| 10.270 | 317 | 26 | +0.115 R | **+0.056 R** | −0.059 R | 33.8% | 38.5% | 0.156 | 0.090 | 0 / 4 |
| **Ø GESAMT**| — | **212.8** | **41.0** | **+0.003 R** | **+0.060 R** | **+0.058 R** | — | — | **0.051** | **0.100** | **9 / 20 (45%)** |

---

## 4. Formale Auswertung der Erfolgskriterien (EXP-025)

1. **Kriterium 1: Fold-1-Anteil an den Gesamt-Trades sinkt auf $\le 40\,\%$**
   - BTC 1h: $12 / 55 = \mathbf{21.8\,\%}$ (vorher $74.2\,\%$)
   - ETH 1h: $16 / 241 = \mathbf{6.6\,\%}$ (vorher $43.0\,\%$)
   - SOL 1h: $104 / 246 = \mathbf{42.3\,\%}$ (vorher $75.6\,\%$)
   - XRP 4h: $76 / 205 = \mathbf{37.1\,\%}$ (vorher $46.7\,\%$)
   - DOGE 4h: $79 / 317 = \mathbf{24.9\,\%}$ (vorher $24.8\,\%$)
   - **Status: TEILWEISE.** Der ungewichtete Fixture-Mittelwert $26.5\,\%$ liegt unter $40\,\%$; als je-Fixture-Kriterium verfehlt SOL mit $42.3\,\%$ die Schranke knapp.

2. **Kriterium 2: Selektive Konfigurationen erreichen $\ge 5$ Train-Trades**
   - Auf 1h (BTC, ETH, SOL) generiert bereits Fold 1 maximal 6, 10 bzw. 9 geschlossene Gated-Trades im Training; spätere Folds liegen darüber.
   - Auf 4h erreicht XRP Fold 1 nur 1 und DOGE Fold 1 0 geschlossene Gated-Trades. Auch XRP Fold 2 erreicht nur 3.
   - **Status: TEILWEISE / VERFEHLT als All-Folds-Kriterium.** Die prä-registrierten 500 Bars sind für die 4h-Fixtures nicht ausreichend, um Kriterium 2 zu erfüllen. Gemäß Ein-Geometrie-Regel wird nicht nachjustiert.

3. **Kriterium 3: Vollständiger Gated vs. Ungated Vergleich je Fixture und je Fold**
   - Vollständig dokumentiert in Tabelle 3 und Abschnitt 5.
   - **Status: BESTANDEN.**

---

## 5. Fold-by-Fold Detailergebnisse (Faire Geometrie)

### 5.1 BTC 1h (14.773 Bars, 4 Folds)
- **Fold 1** (Train 2.000 / Test 3.134): `lt:72, st:22, rg:true` | Train Trades: 6 | Test Trades: 12 | Net Exp: $+0.643\text{ R}$ | PF: 2.39
- **Fold 2** (Train 5.134 / Test 3.134): `lt:75, st:28, rg:true` | Train Trades: 17 | Test Trades: 18 | Net Exp: $-0.487\text{ R}$ | PF: 0.47
- **Fold 3** (Train 8.268 / Test 3.134): `lt:75, st:22, rg:true` | Train Trades: 34 | Test Trades: 15 | Net Exp: $-0.654\text{ R}$ | PF: 0.19
- **Fold 4** (Train 11.402 / Test 3.134): `lt:75, st:22, rg:true` | Train Trades: 49 | Test Trades: 10 | Net Exp: $+0.957\text{ R}$ | PF: 2.78

### 5.2 ETH 1h (14.773 Bars, 4 Folds)
- **Fold 1** (Train 2.000 / Test 3.134): `lt:75, st:22, rg:true` | Train Trades: 9 | Test Trades: 16 | Net Exp: $+0.034\text{ R}$ | PF: 1.04
- **Fold 2** (Train 5.134 / Test 3.134): `lt:78, st:22, rg:false` | Train Trades: 162 | Test Trades: 97 | Net Exp: $-0.023\text{ R}$ | PF: 0.96 *(Gated: $+0.496\text{ R}$)*
- **Fold 3** (Train 8.268 / Test 3.134): `lt:75, st:25, rg:true` | Train Trades: 37 | Test Trades: 17 | Net Exp: $-0.255\text{ R}$ | PF: 0.68
- **Fold 4** (Train 11.402 / Test 3.134): `lt:78, st:22, rg:false` | Train Trades: 354 | Test Trades: 111 | Net Exp: $-0.104\text{ R}$ | PF: 0.86 *(Gated: $+0.442\text{ R}$)*

### 5.3 SOL 1h (14.773 Bars, 4 Folds)
- **Fold 1** (Train 2.000 / Test 3.134): `lt:72, st:28, rg:false` | Train Trades: 64 | Test Trades: 104 | Net Exp: $+0.053\text{ R}$ | PF: 1.08 *(Gated: $+0.550\text{ R}$)*
- **Fold 2** (Train 5.134 / Test 3.134): `lt:72, st:28, rg:false` | Train Trades: 168 | Test Trades: 119 | Net Exp: $-0.160\text{ R}$ | PF: 0.76 *(Gated: $+0.284\text{ R}$)*
- **Fold 3** (Train 8.268 / Test 3.134): `lt:72, st:22, rg:true` | Train Trades: 34 | Test Trades: 14 | Net Exp: $-0.531\text{ R}$ | PF: 0.34
- **Fold 4** (Train 11.402 / Test 3.134): `lt:72, st:28, rg:true` | Train Trades: 49 | Test Trades: 9 | Net Exp: $+0.599\text{ R}$ | PF: 2.15

### 5.4 XRP 4h (10.270 Bars, 4 Folds)
- **Fold 1** (Train 500 / Test 2.383): `lt:78, st:25, rg:false` | Train Trades: 13 | Test Trades: 76 | Net Exp: $-0.113\text{ R}$ | PF: 0.82
- **Fold 2** (Train 2.883 / Test 2.383): `lt:78, st:22, rg:false` | Train Trades: 86 | Test Trades: 48 | Net Exp: $-0.351\text{ R}$ | PF: 0.54
- **Fold 3** (Train 5.266 / Test 2.383): `lt:78, st:28, rg:false` | Train Trades: 146 | Test Trades: 77 | Net Exp: $+0.510\text{ R}$ | PF: 1.89
- **Fold 4** (Train 7.649 / Test 2.384): `lt:78, st:22, rg:true` | Train Trades: 17 | Test Trades: 4 | Net Exp: $-0.482\text{ R}$ | PF: 0.39

### 5.5 DOGE 4h (10.270 Bars, 4 Folds)
- **Fold 1** (Train 500 / Test 2.383): `lt:72, st:25, rg:false` | Train Trades: 18 | Test Trades: 79 | Net Exp: $+0.207\text{ R}$ | PF: 1.33
- **Fold 2** (Train 2.883 / Test 2.383): `lt:78, st:25, rg:false` | Train Trades: 90 | Test Trades: 82 | Net Exp: $-0.064\text{ R}$ | PF: 0.90
- **Fold 3** (Train 5.266 / Test 2.383): `lt:78, st:28, rg:false` | Train Trades: 172 | Test Trades: 71 | Net Exp: $+0.450\text{ R}$ | PF: 1.85
- **Fold 4** (Train 7.649 / Test 2.384): `lt:78, st:28, rg:false` | Train Trades: 244 | Test Trades: 85 | Net Exp: $-0.077\text{ R}$ | PF: 0.89

---

## 6. Anwendung der D2-STOPP-Regel (Bindend)

| Metrik | Soll (GO-Schwelle) | Ist (Gated-Variante, Fair) | Befund |
|---|---|---|---|
| **Aggregierter OOS-DSR (205 gepoolte Trades, $T=45$)** | $\ge \mathbf{0.50}$ | **$0.038$** | **VERFEHLT ($0.038 \ll 0.50$)** |
| **Lokale Sensitivität ($T=9$)** | — | **$0.152$** | Ebenfalls unter 0.50 |
| **BTC 1h DSR** | — | 0.056 | Nicht signifikant |
| **ETH 1h DSR** | — | 0.126 | Positiv, aber unter Schwelle |
| **SOL 1h DSR** | — | 0.164 | Positiv, aber unter Schwelle |
| **XRP 4h DSR** | — | 0.064 | Nicht signifikant |
| **DOGE 4h DSR** | — | 0.090 | Nicht signifikant |

### Bindendes Abschlussurteil:
1. **Keine zertifizierbare Out-of-Sample-Evidenz:** Auf den 5 realen Golden Master Fixtures erreicht der aggregierte DSR auch unter korrekter Regime-Filterung und fairer Fold-Geometrie nicht die statistische Zertifizierungsgrenze ($\text{DSR} \ge 0.50$). Das Modell verbleibt ehrlich im Zustand `MODEL_NO_EVIDENCE`.
2. **B3 (TP1 / R:R-Tuning) wird NICHT durchgeführt:** Jede weitere Parameter-Optimierung auf diesen historischen Daten würde unweigerlich zu Data-Snooping (*p-Hacking*) führen.
3. **Schutz der Lockbox:** Die gesperrten Bars ($\ge 2026-09-10$) bleiben unberührt.
