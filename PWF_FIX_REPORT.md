# PWF-Korrekturbericht

## Ergebnis

Der korrigierte Diff ist für den PWF-Scope fachlich freigegeben. Die Freigabe bedeutet:
die Walk-Forward-Grenzen, Trial-Bilanzierung, Timeframe-Skalierung und Autobot-Gates sind
methodisch konsistent und durch Tests belegt. Sie ist **kein Live-Trading-GO**.

## Audit-Urteil und Umsetzung

| Punkt | Urteil | Umsetzung |
|---|---|---|
| M1 | bestätigt | Exakter foldbezogener t1-Schutz: letzter Train-Signalindex `testStart-2`, Exit-Grenze `testStart-1`; offene Grenzereignisse werden als `purgedByT1` berichtet. Kein p95-Pilot-Purge. |
| M2 | teilweise | Die historische 1%-Embargo-Regel wurde entfernt. Kein Post-Test-Embargo bei vergangenheitsbasiertem Forward-Walk. |
| M3 | teilweise | Anchored K=4 bleibt bewusster Default; `minTrainBars=300`, `minTrainTrades=5`. Kein Rolling-Default. |
| M4 | bestätigt | Train reicht bis direkt vor den Test; nur vollständig vor `testStart` geschlossene Events gehen in die Auswahl ein. |
| M5 | bestätigt | DSR nutzt effektive Trials: Parametergrid × tatsächlicher Auswahlfamilie. TimeStop übergibt die reale Sweepgröße, Autobot die aktuelle Kandidatenzahl. |
| M6 | teilweise | `tfMinutes` dient transparentem Stundenreporting. Der Autobot übersetzt `stagnationHours` korrekt in `ceil(hours/tfHours)` Bars; Indikatorperioden bleiben unverändert. |
| M7 | Modellwahl | K=4 bleibt unverändert; keine adaptive K-Formel. |

## Code-Belege

- `Symbiose_Dashboard.html:1728-1818` — anchored t1 Walk-Forward, Mindest-Trainingsdaten,
  expliziter Evidenzstatus und DSR über effektive Trials.
- `Symbiose_Dashboard.html:1769-1779` — Train-Signalende `testStart-2`, Exit-Grenze
  `testStart-1`, Auswahl nur aus `exitBar < testStart`.
- `Symbiose_Dashboard.html:1797-1807` — OOS-Signale nur bis `testEnd-1`; Entry liegt damit
  maximal auf `testEnd`; `purgedByT1` und `censoredTest` werden je Fold berichtet.
- `Symbiose_Dashboard.html:1812-1817` — `totalTrials = 18 × trialMultiplier`, DSR auf dem
  aggregierten OOS-Ergebnis, `evidenceStatus: 'OOS'`.
- `Symbiose_Dashboard.html:6107-6174` — TimeStop-Sweep nutzt reale Kandidatenanzahl und
  sortiert DSR-first, danach Expectancy.
- `Symbiose_Dashboard.html:6731-6743` — Autobot-Evidenz ist fail-closed: vollständiges
  OOS-WF-Objekt, mindestens 15 geschlossene Trades, positive Expectancy und DSR ≥ 0.5.
- `Symbiose_Dashboard.html:7117-7142` — Autobot revalidiert den frischen Timeframe direkt
  über `classifyRadarTf()` und wertet danach frisches Walk-Forward aus.
- `Symbiose_Dashboard.html:7164-7173` — `stagnationHours` wird timeframe-korrekt in Bars
  übersetzt; 12h sind 48 Bars auf 15m und 3 Bars auf 4h.

## Reproduzierbare Vorher/Nachher-Messung

Messaufbau: unverändertes `HEAD`-Dashboard gegen aktuellen uncommitted Diff. Gleiche fünf
Golden-Fixtures, jeweils letzte 1500 Bars, `makerFee=0.0002`, `takerFee=0.0006`,
`slippage=0.0005`, `timeStopBars=15`. Die Messung zeigt die methodische Wirkung der
Grenz- und Accounting-Korrektur. Sie ist keine Performance- oder Live-Edge-Behauptung.

Dashboard-Hashes:

- Vorher (`HEAD`): `0e380f19dc447fed9981da9d14aa293f90ae41108088eee5284d1aab19458eaf`
- Nachher (aktueller Diff): `8a05272afc988b57f53f5fa37a402cc5caa0f545e874cc9c2c43b36e9c4ddd35`

| Fixture | OOS geschlossen vorher → nachher | Expectancy R vorher → nachher | Profit Factor vorher → nachher | DSR vorher → nachher |
|---|---:|---:|---:|---:|
| BTCUSDT 1h | 32 → 33 | 0.027151 → -0.117960 | 1.028238 → 0.874305 | 0.032350 → 0.029272 |
| ETHUSDT 1h | 32 → 34 | 0.225515 → 0.208129 | 1.325370 → 1.291319 | 0.038026 → 0.037745 |
| SOLUSDT 1h | 21 → 35 | -0.207655 → -0.035923 | 0.742583 → 0.951561 | 0.017767 → 0.030458 |
| XRPUSDT 4h | 33 → 32 | 0.038386 → -0.035505 | 1.058976 → 0.947023 | 0.037476 → 0.027871 |
| DOGEUSDT 4h | 41 → 32 | -0.289921 → 0.082976 | 0.593317 → 1.138075 | 0.006210 → 0.050018 |

Fold-Geometrie vorher → nachher:

- 1h-Fixtures Trainingsstunden: `[126, 404, 680, 956]` → `[300, 540, 780, 1020]`
- 1h-Fixtures Teststunden: `[278, 278, 278, 280]` → `[240, 240, 240, 243]`
- 4h-Fixtures Trainingsstunden: `[504, 1616, 2720, 3824]` → `[1200, 2160, 3120, 4080]`
- 4h-Fixtures Teststunden: `[1112, 1112, 1112, 1120]` → `[960, 960, 960, 972]`

Sichtbare Grenzereignisse nachher:

- `purgedByT1`: BTC `[0,1,1,1]`, ETH `[0,1,0,1]`, SOL `[1,1,1,0]`, XRP `[1,1,1,0]`, DOGE `[1,0,1,1]`
- `censoredTest`: BTC `[1,1,1,1]`, ETH `[1,0,1,0]`, SOL `[1,1,1,1]`, XRP `[1,1,0,0]`, DOGE `[0,1,1,1]`

Reproduktion:

```bash
git show HEAD:Symbiose_Dashboard.html > /tmp/aura_dashboard_before.html
node .hermes/audit/aura_pwf_snapshot.js /tmp/aura_dashboard_before.html > .hermes/audit/pwf_before.json
node .hermes/audit/aura_pwf_snapshot.js Symbiose_Dashboard.html > .hermes/audit/pwf_after.json
```

Artefakte:

- `.hermes/audit/aura_pwf_snapshot.js` — SHA256 `b4d4163ab5996c991c2c98711d6de4d9baca1e2412a3ef48495481b0a5f6315a`
- `.hermes/audit/pwf_before.json` — SHA256 `6fd89583185f7c67e5ebae7bb2f7a58d67d44c5879ae40cd6048b1b0e8ee1037`
- `.hermes/audit/pwf_after.json` — SHA256 `87c93dd4b6b766c8610ee7864346a416168807b06ef94882869e017d688a083c`

## Verifizierte aktuelle Baseline

Die lokale unabhängige Oracle-Referenz bestätigt Accounting und Fold-Geometrie für n=1000.
Die Geometrie beginnt mit Train `[235,534]`, Test `[536,650]`, 300/115 Stunden bei
60-Minuten-Bars und 18 Grid-Trials. Diese Werte sind Geometrie-/Fixturewerte, keine
Performance-Behauptungen.

Der aktuelle reale lokale Sensitivitätslauf auf dem **synthetischen Fixture** ist
`PAPER_CANDIDATE`: 33 OOS-Trades, Median-Expectancy `1.241176305240437 R` und
95%-CI `[0.772705700169848, 1.709646910311026]`. Dies ist keine Live-Edge- oder
Profitabilitätsbehauptung. Fail-closed Zustände (`NO_EVIDENCE`, neutraler DSR 0.5,
`INSUFFICIENT_DATA`) bleiben unverändert nicht akzeptierend.

## Test- und Release-Belege

Alle folgenden Kommandos wurden auf dem finalen Diff ausgeführt:

| Prüfung | Ergebnis |
|---|---|
| `python3 tests/reference_backtest.py` | PASS |
| `node tests/test_lookahead_metamorphic.js` | PASS, 3/3 |
| `node tests/test_engine_full.js` | PASS, 121/121 |
| `node tests/test_autobot_statistical_edge.js` | PASS |
| `node tests/test_timestop_timeframe_scaling.js` | PASS |
| `node tests/test_live_trade_tracker.js` | PASS, inklusive echtem Autobot-Scan-Verhalten |
| `node tests/test_autobot_entry_gate.js` | PASS |
| `node tests/sensitivity_release_gates.js` | `PAPER_CANDIDATE` auf synthetischem Fixture |
| `pytest -q` | 145 passed, 53 subtests passed |
| `python3 tests/browser_research_harness.py` | PASS, 10 identische Läufe, 0 Seitenfehler, 0 Konsolenfehler |
| `python3 scripts/release_check.py` | alle Gates PASS (inkl. Version-Progression auf v1.0.8) |
| `git diff --check` | PASS |

Spezifische Regressionstests:

- `tests/test_engine_full.js:1087-1137` — exakter t1-Vertrag mit explizitem Grenzereignis.
- `tests/test_engine_full.js:1139-1169` — OOS-Entry darf nicht außerhalb des Testbereichs liegen.
- `tests/test_engine_full.js:1175-1189` — DSR/Trials steigen mit der effektiven
  Selektionsfamilie und fallen bei ungültigen Multipliern fail-closed auf 18 zurück.
- `tests/test_autobot_statistical_edge.js:33-51` — Autobot akzeptiert nur ausreichende,
  positive OOS-Evidenz mit DSR ≥ 0.5.
- `tests/test_timestop_timeframe_scaling.js:57-68` — 12h entsprechen exakt 3 Bars auf 4h
  und 48 Bars auf 15m.
- `tests/test_live_trade_tracker.js:601-613` — der reale 15m-Fallback erscheint im Sweep;
  der Trial-Multiplikator entspricht der tatsächlichen Kandidatenanzahl.
- `tests/test_live_trade_tracker.js:683-687` — frisches vollständiges WF-Objekt wird
  weitergereicht, abgelehnte Evidenz erzeugt keinen Trade, akzeptierte Evidenz persistiert
  effektive Trials.

## Unabhängige Abschlussprüfung

Ein frischer unabhängiger Reviewer hat den finalen Diff für den PWF-Scope freigegeben.
Geprüft wurden Quant-Logik, Leakage-Grenzen, Trial-Accounting, Testqualität, Scope und
Release-Vertrag. Keine realen Blocker gefunden.

Hinweis des Reviewers: `window.__SYM_TEST` existiert weiterhin im Produktions-Dashboard,
ist aber bereits in `HEAD` vorhanden und wird durch diesen Diff weder eingeführt noch
verändert. Das ist ein vorbestehender Scopepunkt außerhalb dieser PWF-Korrektur.

## Restrisiken und Grenzen

- `PAPER_CANDIDATE` stammt aus einem deterministischen synthetischen Fixture. Es ist kein
  Live-GO und keine Profitabilitätsgarantie.
- Die Vorher/Nachher-Werte zeigen geänderte Messlogik und Fold-Geometrie. Sie dürfen nicht
  als verbesserte Trading-Performance interpretiert werden; BTC und XRP verschlechtern sich
  unter der korrigierten Messung sogar.
- Die Golden-Master-Parität bleibt ein separater externer Evidenzpfad. Der aktuelle
  Release-Check besteht die vorhandene Authentizitätsprüfung, ersetzt aber keine neuen
  echten TradingView-Exporte.
- Es wurde nicht committet, nicht gepusht und kein Versionsbump durchgeführt.
