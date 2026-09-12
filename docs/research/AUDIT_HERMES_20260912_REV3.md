# AURA Quant Terminal — Gesamtaudit Revisionsbericht 3

**Revisionsdatum:** 2026-09-12
**Auditor:** Senior Quant Systems Auditor (Hermes Agent)
**Baseline-Commit:** `0b7bc94b5dbb63b63cdbe9e0e81225b80cb839c8`
**Audit-Branch:** `audit/hermes-gesamtaudit-20260912`
**Vorgängerberichte:** `docs/research/AUDIT_HERMES_20260912.md` & `docs/research/AUDIT_HERMES_20260912_REV2.md`

---

## 1. Management Summary (Revision 3)

Revision 3 baut direkt auf der belastbaren Methodik von Revision 2 auf und schließt die verbliebenen offenen Fragen auf Ursachenebene:

1. **F-16 Paritätsanalyse auf Ursachenebene:** Die in Revision 2 als „nicht erklärbar“ geführten 20 Feld-Mismatches (auf 10 Einzelkerzen) wurden vollständig auf Bitebene und Termebene zerlegt. Sie zerfallen in **drei distinkte Klassen**:
   - **Klasse 1 (4 Fälle, Delta = +20):** Floating-Point-Asymmetrie bei strikter Gleichheit (`close == hlc3 == vwapD`) am Tageswechsel (00:00 UTC). Pine wertet `close > vwapD` als `false` aus (-10), JS leidet unter einem IEEE-754-ULP-Unterlauf bei `(h+l+c)/3` und wertet als `true` aus (+10). Hypothese H1 (Zeitzonendrift) und H1b (CVD-Drift) wurden **widerlegt**.
   - **Klasse 2 (5 Fälle, Delta = ±3 / +8):** Messerschneiden-Artefakte an den harten ADX-Stufenschwellen 18.0 und 25.0. Verbleibende kontinuierliche RMA-Restdifferenzen von 0.01 bis 0.8 Punkten kippen die diskrete Stufenfunktion.
   - **Klasse 3 (1 Fall, Delta = 0.4487):** Reines kontinuierliches RMA-Restkonvergenzrauschen in RSI / Stoch-RSI.
2. **Kanonizitäts-Entscheidungsvorlage:** Entscheidungsmatrix (UTC vs. Chart-Zeitzone) für den System-Eigentümer ausgearbeitet.
3. **Vollständige Absicherung des produktiven Exit-Pfads (F-17, F-18, F-19, F-20):**
   - Direkte behavior-basierte Testsuite `tests/test_autobot_timestop_behavior.js` für `Autobot.updateActiveTrades()` / In-Trade-Monitoring implementiert.
   - Analytischer Kelly-Oracle-Test `tests/test_kelly_oracle.js` mit formelgetreuer mathematischer Ableitung ($f^* = p - q/b$) implementiert.
   - **Wirksamkeitsnachweis:** Alle 3 überlebenden Mutationen (M13, M14, M15) sowie M04 werden von den neuen Tests sofort **rot gefangen**.
   - **Gesamtergebnis Mutationstest:** **15 von 15 Mutationen getötet (100% Mutation Coverage)** bei bytegenauer Wiederherstellung (`SHA-256: a993f1b15db0e1180b225b5ca35f03e2e43a45886a9e8764baa5d9a0e2dd778e`).

---

## 2. Aufgabe A — F-16 Ursachenanalyse und Klassenzerlegung

### 2.1 Formelprüfung (A1)
Die mathematischen Formeln in Pine und JavaScript sind strukturell deckungsgleich:

- **Volume Score:**
  - Pine `Symbiose_Signal_System_v1.pine:475-480`:
    `50 + 15*(obv>emaObv) + 10*(close>vwapD) + clamp((vol/smaVol - 1)*20, -10, 10)*(c>o?1:-1) + 10*(cvd>emaCvd)`
  - JS `Symbiose_Dashboard.html:1221-1222`:
    `clamp(50 + (obv > eobv ? 15 : -15) + (c > vwap ? 10 : -10) + (clamp((v/vref - 1)*20, -10, 10)*(c > o ? 1 : -1)) + (cvd > ecvd ? 10 : -10), 0, 100)`

- **Trend Score:**
  - Pine `Symbiose_Signal_System_v1.pine:460-466`:
    `50 + 8*(close>emaFast) + 8*(emaFast>emaMid) + 7*(emaMid>emaSlow) + 12*stDir + [adx>=25 ? (emaFast>emaMid ? 8 : -8) : (adx<18 ? -3 : 0)]`
  - JS `Symbiose_Dashboard.html:1218-1219`:
    `clamp(50 + (c > e20 ? 8 : -8) + (e20 > e50 ? 8 : -8) + (e50 > e200 ? 7 : -7) + (st.dir === 1 ? 12 : -12) + ai, 0, 100)`

Daraus folgt: Die Divergenzen resultieren ausschließlich aus den Eingängen und Zwischenwerten.

---

### 2.2 Klasse 1 — `volumeScore` (+20 um 00:00 UTC)

#### Beobachtete Fälle (4 von 4 Fällen)
| Fixture | Bar | UTC-Zeitstempel | Open | High | Low | Close | Pine | JS | Delta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DOGEUSDT_4h | 1644 | 2022-10-02 00:00:00Z | 0.060552 | 0.060923 | 0.060495 | 0.060709 | 5.0 | 25.0 | +20.0 |
| ETHUSDT_1h | 2448 | 2025-04-13 00:00:00Z | 1643.52 | 1648.55 | 1634.03 | 1641.29 | 75.0 | 95.0 | +20.0 |
| XRPUSDT_4h | 1422 | 2022-08-26 00:00:00Z | 0.3485 | 0.3487 | 0.3455 | 0.3471 | 18.487846 | 38.487846 | +20.0 |
| XRPUSDT_4h | 1746 | 2022-10-19 00:00:00Z | 0.4655 | 0.4661 | 0.4579 | 0.4620 | 29.032044 | 49.032044 | +20.0 |

#### Hypothesenprüfung
1. **Hypothese H1 (Zeitzonendrift bei TradingView-Export):** **WIDERLEGT**.
   - *Befund:* Die empirische Inspektion aller Daily-Resets in den CSV-Fixtures zeigt, dass der VWAP-Reset in allen 5 Golden-Fixtures exakt um `00:00:00Z` stattfindet. Sowohl Pine `timeframe.change("1D")` als auch JS `Math.floor(ms / 86400000)` triggern zeitgleich.
   - *TradingView Re-Export:* Im CLI-Audit-Umfeld `NICHT GEPRÜFT` (keine interaktive GUI-Sitzung), jedoch durch den analytischen Nachweis vollständig substituiert.
2. **Hypothese H1b (`cvd > emaCvd` als Ursache):** **WIDERLEGT**.
   - *Befund:* Auf allen 4 Kerzen stimmen die CVD-Terme in Pine und JS überein (ETH: +10 in beiden; XRP 1422: -10 in beiden; XRP 1746: +10 in beiden; DOGE: -10 in beiden).
3. **Tatsächliche Ursache (Float-Asymmetrie bei Gleichheit an der Tagesgrenze):** **BESTÄTIGT**.
   - Auf allen vier Kerzen ist die Kerze exakt symmetrisch bezüglich High und Low: `close == (high + low) / 2`.
   - Dadurch ist `hlc3 = (high + low + close) / 3` mathematisch identisch zu `close`.
   - Am ersten Bar des Tages gilt: $\text{vwapD} = \text{hlc3} = \text{close}$.
   - Mathematisch gilt: $\text{close} > \text{vwapD}$ ist **FALSCH** ($\text{close} == \text{vwapD}$).
   - Pine Script wertet `close > vwapD` als `false` aus $\implies$ Term `-10`.
   - JavaScript berechnet `((h + l + c) / 3 * v) / v` in 64-Bit-IEEE-754-Arithmetik. Durch die Division durch 3 entsteht ein ULP-Unterlauf von $10^{-13}$ bis $10^{-17}$ (z.B. ETH `1641.2899999999997` vs `1641.29`). Die strikte Ungleichung `c[i] > vwap[i]` evaluiert zu `true` $\implies$ Term `+10`.
   - Das Delta beträgt exakt $+10 - (-10) = +20$ Punkte.

---

### 2.3 Klasse 2 — `trend` (±3 und +8, 5 Bars)

#### Beobachtete Fälle und ADX-Wertetabelle
| Fixture | Bar | UTC-Zeitstempel | JS ADX | Pine Impl. ADX | JS ADX-Term | Pine ADX-Term | JS Trend | Pine Trend | Delta | Schwelle |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SOLUSDT_1h | 11461 | 2026-04-23 13:00Z | 24.99402 | $\ge 25.0$ | 0 | -8 | 29.0 | 21.0 | +8.0 | 25.0 |
| SOLUSDT_1h | 11462 | 2026-04-23 14:00Z | 24.15410 | $\ge 25.0$ | 0 | -8 | 29.0 | 21.0 | +8.0 | 25.0 |
| SOLUSDT_1h | 11486 | 2026-04-24 14:00Z | 17.24202 | $\ge 18.0$ | -3 | 0 | 42.0 | 45.0 | -3.0 | 18.0 |
| SOLUSDT_1h | 12158 | 2026-05-22 14:00Z | 18.18179 | $< 18.0$ | 0 | -3 | 55.0 | 52.0 | +3.0 | 18.0 |
| XRPUSDT_4h | 1215 | 2022-07-22 12:00Z | 17.65488 | $\ge 18.0$ | -3 | 0 | 66.0 | 69.0 | -3.0 | 18.0 |

#### Hypothesenprüfung & Fachliche Bewertung
- **Hypothese H2 (ADX-Schwellenüberschreitung 18/25):** **BESTÄTIGT**.
- *Befund:* Alle 5 Fälle resultieren ausschließlich daraus, dass der ADX-Wert die harten Schwellen 18.0 oder 25.0 knapp über- oder unterschreitet. Alle anderen Trendkomponenten (EMA20, EMA50, EMA200, SuperTrend) stimmen exakt überein.
- *Ursache:* ADX verwendet Wilder's Smoothing (RMA, 14 Perioden). Pine akkumuliert ab Listing-Datum, JS ab Fensterstart. Nach 1.200 Warmup-Bars verbleibt eine kontinuierliche Restdifferenz von 0.01 bis 0.8 Punkten.
- *Fachliches Urteil:* Es handelt sich um ein **inhärentes Messerschneiden-Artefakt** diskreter Stufenfunktionen auf geglätteten Filtern. Bei Werten abseits der Schwellen ist die Auswirkung 0; an der Grenze kippt die Stufe um exakt 3 bzw. 8 Punkte. Dies ist als bekanntes Verhalten zu dokumentieren.

---

### 2.4 Klasse 3 — `momentum` (0.4487, 1 Bar)

- **Fixture:** `SOLUSDT_1h.csv` Bar 14772 (2026-09-08 12:00Z).
- **Werte:** Pine Momentum = 10.752615, JS Momentum = 10.303913, Delta = 0.448701.
- **Ursache:** Kontinuierliche Restdifferenz in RSI ($\Delta \approx 0.15$) und Stoch-RSI, skaliert durch $1.5 \times \Delta\text{RSI} + 0.8 \times \Delta\text{SRSI} = 0.4487$.
- **Urteil:** Reine numerische Gleitkomma-Restkonvergenz der Wilders-RMA-Filter. Kein Logikfehler.

---

### 2.5 Kanonizitäts-Entscheidungsvorlage für den Eigentümer

| Kriterium | Option 1: Kanonisch UTC (Empfohlen) | Option 2: Kanonisch TradingView Chart-Zeitzone |
| --- | --- | --- |
| **Implementierung** | JS bleibt strikt auf UTC (`Math.floor(ms / 86400000)`). In Pine wird `timeframe.change("1D")` mit `timezone="UTC"` fixiert bzw. als Chart-Standard dokumentiert. JS erhält Epsilon-Gleichheitsschutz (`Math.abs(c - vwap) < 1e-9`). | JS erhält konfigurierbaren Zeitzonen- bzw. Session-Offset, um abweichende Chart-Einstellungen in TradingView nachzubilden. |
| **Vorteile** | Vollständig deterministisch über alle Server, Container, Relays, Zeitzonen und OOS-Backtests. | Bildet manuelle TradingView-Layouts in lokalen Benutzerzeitzonen (z.B. UTC+2) ohne Umstellung nach. |
| **Nachteile** | TradingView-Anwender müssen Chartzeitzone auf UTC stellen, um 100%ige optische Parität zu erhalten. | Verlust der globalen zeitlichen Invarianz; Risiko von Fehlentscheidungen durch lokale Betriebssystem-Zeitzonen. |
| **Status** | **Vorbereitet zur Eigentümerentscheidung.** Keine eigenmächtige Änderung im Audit-Branch. |

---

## 3. Aufgabe B — Absicherung des produktiven Exit-Pfads

### 3.1 Behavior-basierte Testarchitektur (`tests/test_autobot_timestop_behavior.js`)
Die neu erstellte Testsuite prüft die reale Methode `Autobot.updateActiveTrades()` unter kontrollierter Zeitmanipulation (`Date.now` Mocking) und realistischen PnL-Zuständen:

- **Timeframe-Matrix:** 15m, 1h, 4h, 1d (`tfToMinutes * 60000` Skalierung).
- **Deadline-Matrix:** 50% vor Ablauf (offen), 100% exakt auf Deadline (offen), 100% + 1s nach Ablauf (geschlossen).
- **Asymmetrische PnL-Bedingung:**
  - Gewinner (+5% ROI): bleibt offen.
  - Break-Even aktiv (`beActive = true`): bleibt offen.
  - Kleiner Verlust (-2% ROI, > -3%): bleibt offen.
  - Stagnierender Verlust (-5% / -10% ROI, < -3%): schließt via `TIME_STOP_DYNAMIC`.
- **Fallback-Pfad:** 12-Bar-Fallback schließt exakt nach 12 Bars, wenn `timeStopBars` nicht gesetzt ist.

### 3.2 Analytische Kelly-Oracle-Testsuite (`tests/test_kelly_oracle.js`)
Formelgetreue mathematische Verifikation von `calcKelly()` gegen die theoretische Wahrscheinlichkeitsformel:
$$f^* = p - \frac{1 - p}{b} = \frac{p \cdot (b + 1) - 1}{b}$$
$$\text{halfKelly} = 0.5 \cdot f^*, \quad \text{finalFrac} = \min(\text{halfKelly}, \text{hardCap}) \cdot \text{sampleMultiplier}$$
Geprüft über 25 Parameterkombinationen sowie asymmetrische Auszahlungsverhältnisse und Stichprobengrößen.

---

### 3.3 Mutationsmatrix & Wirksamkeitsnachweis (15/15 getötet)

```bash
# Befehl zur reproduzierbaren Verifikation:
python3 scripts/audit_rev2_mutations.py
```

| ID | Bereich | Mutation | Status Rev2 | Status Rev3 | Fangender Test / Trigger |
| --- | --- | --- | --- | --- | --- |
| **M01** | Score | Trend-Gewicht 0.30 → 0.35 | KILLED | **KILLED** | `test_audit_integrity.js`, `test_model_evidence_real.js` |
| **M02** | Score | Momentum-Gewicht 0.25 → 0.20 | KILLED | **KILLED** | `test_audit_integrity.js`, `test_model_evidence_real.js` |
| **M03** | Score | Volume-Gewicht 0.25 → 0.30 | KILLED | **KILLED** | `test_audit_integrity.js`, `test_model_evidence_real.js` |
| **M04** | calcKelly | `(p*(b+1)-1)/b` → `(p*b-1)/b` | SURVIVED | **KILLED** | `tests/test_kelly_oracle.js` |
| **M05** | calcKelly | `p*b-(1-p)` → `p*b-1` | KILLED | **KILLED** | `test_engine_full.js`, `test_kelly_oracle.js` |
| **M06** | calcKelly | Penalty `/ 10` → `/ 12` | KILLED | **KILLED** | `test_engine_full.js`, `test_kelly_oracle.js` |
| **M07** | Regime | Invertiere `regimeLongOk` | KILLED | **KILLED** | `tests/test_engine_full.js` |
| **M08** | Regime | Invertiere `regimeShortOk` | KILLED | **KILLED** | `test_engine_full.js`, `test_model_evidence_real.js` |
| **M09** | Regime | Hardcode `regimeLongOk = true` | KILLED | **KILLED** | `test_engine_full.js`, `test_model_evidence_real.js` |
| **M10** | Liquidität | `min24hVol` 500k → 100k | KILLED | **KILLED** | `test_autobot_scan_diagnostics.js`, `test_fallback_liquidity.js` |
| **M11** | Liquidität | `min24hVol` 500k → 2.5M | KILLED | **KILLED** | `test_autobot_scan_diagnostics.js`, `test_autobot_universe_adjustment.js` |
| **M12** | Liquidität | Logik `\|\|` → `&&` | KILLED | **KILLED** | `tests/test_autobot_scan_diagnostics.js` |
| **M13** | Time-Stop | `* 60000` → `/ 60000` | SURVIVED | **KILLED** | `tests/test_autobot_timestop_behavior.js` |
| **M14** | Time-Stop | `curRoi < -3.0` → `> -3.0` | SURVIVED | **KILLED** | `tests/test_autobot_timestop_behavior.js` |
| **M15** | Time-Stop | Fallback `12` → `13` Bars | SURVIVED | **KILLED** | `tests/test_autobot_timestop_behavior.js` |

**Ergebnis:** 15/15 Mutanten getötet (0 überlebend).
**Dashboard-Integrität:** `SHA-256: a993f1b15db0e1180b225b5ca35f03e2e43a45886a9e8764baa5d9a0e2dd778e` (bytegenau wiederhergestellt, `git diff` leer).

---

## 4. Aktualisierte Befundtabelle und Schichturteile

### Befundstatus nach Revision 3
| ID | Schwere | Komponente | Beschreibung | Status |
| --- | --- | --- | --- | --- |
| **F-01** | CRITICAL | Bitget Relay | SSRF & Remote-Code-Execution | BEHOBEN (Rev 1, Commit `d0d6fee`) |
| **F-03** | LOW | Cockpit / Paper | Entriegelung manuelles Cockpit-Trading | KLARGESTELLT (Rev 2, Commit `a8ee49e`) |
| **F-06** | MEDIUM | Supply Chain / Ledger | Transaktionsintegrität Ledger | ZUGEORDNET (Welle W3) |
| **F-16** | HIGH | Signal-Parität | Pine↔JS Paritätsabweichungen | AUFGEKLÄRT (Rev 3: 3 Klassen; Entscheidungsvorlage) |
| **F-17** | MEDIUM | Statistik | calcKelly positive Oracle-Absicherung | BEHOBEN (Rev 3, `test_kelly_oracle.js`) |
| **F-18** | HIGH | Autobot Exit | Time-Stop Millisekunden-Skalierung | BEHOBEN (Rev 3, `test_autobot_timestop_behavior.js`) |
| **F-19** | HIGH | Autobot Exit | Invertierte Verlustbedingung Time-Stop | BEHOBEN (Rev 3, `test_autobot_timestop_behavior.js`) |
| **F-20** | MEDIUM | Autobot Exit | 12-Bar Fallback Time-Stop | BEHOBEN (Rev 3, `test_autobot_timestop_behavior.js`) |
| **F-21** | HIGH | CI / CD | Ungepinnte GitHub Actions | BEHOBEN (Rev 2, Commit `83cf989`) |

### Aktualisierte Schichturteile
- **L1 (Infrastruktur / Relay / Deployment):** **SAUBER**
- **L2 (Autobot / Risikomanagement / Exit-Pfade):** **SAUBER** *(hochgestuft von MÄNGEL nach Behebung von F-17 bis F-20 und 100% Mutation Kill-Rate)*
- **L3 (Mathematik / Signal-Engine / Parität):** **MÄNGEL** *(bleibt bis zur formalen Eigentümerentscheidung zu VWAP-Kanonizität und Epsilon-Gleichheit)*
- **L4 (Makro / Marktstruktur):** **SAUBER**
- **L5 (Statistische Validierung / OOS-Evidenz):** **MÄNGEL** *(MODEL_NO_EVIDENCE auf realen Daten)*
- **L6 (CI / CD / Supply Chain):** **SAUBER**

---

## 5. Neubewertung der drei Hinderungsgründe für den Produktiveinsatz

1. **Pine↔Dashboard-Parität (Präzisiert und entdramatisiert):**
   Die Sachlage ist nun vollständig transparent: Es liegt kein tiefer mathematischer Architekturfehler vor. Die 20 Mismatches sind zu 100% aufgeklärt (4x Floating-Point-Gleichheitsunterlauf am Tageswechsel, 5x ADX-Stufen-Messerschneide, 1x RMA-Restkonvergenz). Das Verhalten ist berechenbar und bis zur Eigentümerentscheidung bezüglich Epsilon-Gleichheit/Kanonizität dokumentiert.
2. **Fehlende Out-of-Sample-Alpha-Evidenz (`MODEL_NO_EVIDENCE`):**
   Unverändert der primäre fachliche Hinderungsgrund für echtes Kapital. AURA bleibt ein leistungsfähiges Research- und Paper-Simulationsterminal.
3. **Monolithische Dashboard-Architektur (Testlücken im Exit-Pfad geschlossen):**
   Die operationelle Gefahr unbemerkter Exit-Fehler (Time-Stop, Kelly) ist durch die neuen behavior-basierten Tests eliminiert. Der Monolith (`Symbiose_Dashboard.html` mit 8.971 Zeilen) bleibt ein Wartbarkeits- und Refactoring-Risiko für zukünftige Entwicklungen.

---

## 6. Verifikationsbefehle

```bash
# 1. Volle Testsuite ausführen (193 Pytest-Tests + 42 JS-Testsuiten)
python3 -m pytest -q
node tests/test_kelly_oracle.js
node tests/test_autobot_timestop_behavior.js

# 2. Reproduzierbarer 15-Mutations-Audit (15/15 KILLED)
python3 scripts/audit_rev2_mutations.py

# 3. Release-Gate (Audit-Modus)
python3 scripts/release_check.py --allow-current-version

# 4. Git-Diff & Arbeitsbaum prüfen
git status --porcelain=v1
git diff --check
```
