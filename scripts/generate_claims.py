import csv

CLAIMS = [
    # --- Ebene 1: Herleitung (Derivation) ---
    {
        "ID": "CLM-01",
        "Quelle": "Symbiose_Dashboard.html:1019",
        "Wortlaut": "Score = 0.30 * Trend + 0.25 * Mom + 0.25 * Vol + 0.20 * Struct, clamp(0, 100)",
        "Typ": "Formel",
        "Ebene_Querschnitt": "Ebene 1",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "Symbiose_Dashboard.html:1019, Symbiose_Signal_System_v1.pine:487, test_engine_full.js:770; Gewichte summieren exakt zu 1.0; 100% Parität mit Pine.",
        "Empfehlung_Fix": "Keine Änderung nötig. Mathematisch und implementierungsseitig verifiziert."
    },
    {
        "ID": "CLM-02",
        "Quelle": "Symbiose_Dashboard.html:1085",
        "Wortlaut": "calcDSR: Deflated Sharpe Ratio nach Bailey & López de Prado (2014) mit Skew/Kurtosis-Korrektur und Euler-Mascheroni-Erwartungswert",
        "Typ": "Formel",
        "Ebene_Querschnitt": "Ebene 1",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "Symbiose_Dashboard.html:1085-1112, tests/reference_backtest.py:75-110; Python-Oracle und JS-Engine stimmen überein (EPS < 1e-6).",
        "Empfehlung_Fix": "Keine Änderung nötig. Formel entspricht exakt der publizierten Literatur."
    },
    {
        "ID": "CLM-03",
        "Quelle": "Symbiose_Dashboard.html:1182",
        "Wortlaut": "calcKelly: f* = (p*(b+1)-1)/b, Half-Kelly = 0.5*f*, Sample-Ramp (5-14 Trades), Hard-Cap min(0.25, riskPct/100)",
        "Typ": "Formel",
        "Ebene_Querschnitt": "Ebene 1",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "Symbiose_Dashboard.html:1182-1209, test_engine_full.js:330-360; 5000 randomisierte Property-Tests halten alle Invarianten ein.",
        "Empfehlung_Fix": "Keine Änderung nötig. Konservatives Kapitalerhaltungs-Design verifiziert."
    },
    {
        "ID": "CLM-04",
        "Quelle": "Symbiose_Dashboard.html:1118",
        "Wortlaut": "calibrateProbabilities: PAVA-Isotonische Regression mit Sigmoid-Prior (P(Long=50)=0.5000), monoton nicht-fallend [0.05, 0.95]",
        "Typ": "Formel",
        "Ebene_Querschnitt": "Ebene 1",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "Symbiose_Dashboard.html:1118-1175, tests/reference_backtest.py:116-160; Monotonie und Randwerte in Unit- und Oracle-Tests belegt.",
        "Empfehlung_Fix": "Keine Änderung nötig. PAVA-Monotonie verifiziert."
    },
    {
        "ID": "CLM-05",
        "Quelle": "Symbiose_Dashboard.html:1516",
        "Wortlaut": "dynamicTp1At: Arbitragefreie dynTP1-Preissetzung über EQH/EQL und gegnerische FVG in [1R, 2R), Fallback 2R, ohne Look-ahead",
        "Typ": "Formel",
        "Ebene_Querschnitt": "Ebene 1",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "Symbiose_Dashboard.html:1516-1534, Symbiose_Signal_System_v1.pine:285-320, test_engine_full.js:370-420.",
        "Empfehlung_Fix": "Keine Änderung nötig. Kausale Struktur-Levels ohne Zukunftsbezug verifiziert."
    },
    {
        "ID": "CLM-06",
        "Quelle": "Symbiose_Dashboard.html:1627",
        "Wortlaut": "SuperTrend-Trailing: Neuer Trailing-Stop gilt erst ab Folgekerze; kein Intra-Bar-Look-ahead auf High/Low der aktuellen Kerze",
        "Typ": "Verhalten",
        "Ebene_Querschnitt": "Ebene 1",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "Symbiose_Dashboard.html:1627-1639, test_engine_full.js:900-915, tests/test_lookahead_metamorphic.js:60-80.",
        "Empfehlung_Fix": "Keine Änderung nötig. Metamorphisch und temporal geprüft."
    },
    {
        "ID": "CLM-07",
        "Quelle": "Symbiose_Dashboard.html:1304",
        "Wortlaut": "regimeOf: ADX >= 20 Trendschwelle, EMA50/EMA200 Orientierung, Bollinger/Keltner-Squeeze-Filter",
        "Typ": "Formel",
        "Ebene_Querschnitt": "Ebene 1",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "Symbiose_Dashboard.html:1304-1344, test_engine_full.js:680-720.",
        "Empfehlung_Fix": "Keine Änderung nötig. Technische Definition vollständig konsistent."
    },
    {
        "ID": "CLM-08",
        "Quelle": "Symbiose_Dashboard.html:1536",
        "Wortlaut": "macroAdjust: Sättigungskappen fgAdj +-4, fundAdj +-10/25, oiAdj +-10/25, basisAdj +-3, macroCap +-25, Makro-Veto bei schwacher Technik",
        "Typ": "Formel",
        "Ebene_Querschnitt": "Ebene 1",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "Symbiose_Dashboard.html:1536-1547, test_engine_full.js:280-320.",
        "Empfehlung_Fix": "Keine Änderung nötig. Veto- und Kappendefinitionen verifiziert."
    },
    {
        "ID": "CLM-09",
        "Quelle": "Symbiose_Dashboard.html:1789",
        "Wortlaut": "Selection Objective in Walk-Forward: exp * sqrt(n) * (1 - 1/(1+n)) mit n >= 2 Train-Trades (EXP-024)",
        "Typ": "Formel",
        "Ebene_Querschnitt": "Ebene 1",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "Symbiose_Dashboard.html:1789; obj = stats.total >= minTrainTrades ? stats.exp * Math.sqrt(stats.total) * (1 - 1 / (1 + stats.total)) : -Infinity.",
        "Empfehlung_Fix": "Keine Änderung nötig. Regularisierte Selektion verifiziert."
    },

    # --- Ebene 2: Implementierung (Correctness) ---
    {
        "ID": "CLM-10",
        "Quelle": "tests/reference_backtest.py:280",
        "Wortlaut": "Oracle-Parität JS <-> Python: Identische Trades, Accounting, Folds, DSR und PAVA-Kalibrierung",
        "Typ": "Verhalten",
        "Ebene_Querschnitt": "Ebene 2",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "python3 tests/reference_backtest.py -> REFERENCE BACKTEST: ALL ASSERTIONS PASSED.",
        "Empfehlung_Fix": "Keine Änderung nötig. Vollständige Parität belegt."
    },
    {
        "ID": "CLM-11",
        "Quelle": "tests/compare_pine_js_golden.js:144",
        "Wortlaut": "Golden-Master-Parität Pine v6 <-> JS Engine auf 5 Symbolen (BTC, ETH, SOL 1h; XRP, DOGE 4h)",
        "Typ": "Verhalten",
        "Ebene_Querschnitt": "Ebene 2",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "node tests/compare_pine_js_golden.js: 58.859 Bars verglichen, 20 Soft-Mismatch-Bars = 0,034% (BTC: 0/13573 ~4,7e-12, ETH: 2/13573 max Δ20, SOL: 10/13573 max Δ8, XRP: 6/9070 max Δ20, DOGE: 2/9070 max Δ20). Ursache: Kumulative Indikatoren (OBV/CVD, EMA aus Listing-Historie); Pine akkumuliert ab Listing (2017+), JS ab Exportfenster (15.000 Bars). PASS gerechtfertigt (0,034% << 0,1% Limit, max Δ <= 25 Soft-Ceiling).",
        "Empfehlung_Fix": "Keine Änderung nötig. Empirische Diskrepanzen und Konvergenzverhalten im Bericht und Doku vollständig offengelegt."
    },
    {
        "ID": "CLM-12",
        "Quelle": "Symbiose_Dashboard.html:1769",
        "Wortlaut": "Exakte t1-Grenzen im Walk-Forward: trainEnd = testStart - 2, trainExitBoundary = testStart - 1, Auswahl nur exitBar < testStart",
        "Typ": "Verhalten",
        "Ebene_Querschnitt": "Ebene 2",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "Symbiose_Dashboard.html:1769-1779, test_engine_full.js:1088-1130, tests/test_lookahead_metamorphic.js:90-115.",
        "Empfehlung_Fix": "Keine Änderung nötig. t1-Purging verhindert Leakage von Train in Test."
    },
    {
        "ID": "CLM-13",
        "Quelle": "Symbiose_Dashboard.html:1797",
        "Wortlaut": "OOS-Signale nur bis testEnd - 1; Entry liegt maximal auf testEnd",
        "Typ": "Verhalten",
        "Ebene_Querschnitt": "Ebene 2",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "Symbiose_Dashboard.html:1797, test_engine_full.js:1140-1170.",
        "Empfehlung_Fix": "Keine Änderung nötig. Out-of-Bounds Test-Entries ausgeschlossen."
    },
    {
        "ID": "CLM-14",
        "Quelle": "Symbiose_Dashboard.html:7164",
        "Wortlaut": "Stagnation Hours werden timeframe-korrekt in Bars umgerechnet (12h = 48 Bars auf 15m, 3 Bars auf 4h)",
        "Typ": "Verhalten",
        "Ebene_Querschnitt": "Ebene 2",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "Symbiose_Dashboard.html:7164-7173, tests/test_timestop_timeframe_scaling.js; alle Timeframes verifiziert.",
        "Empfehlung_Fix": "Keine Änderung nötig. Timeframe-Skalierung verifiziert."
    },
    {
        "ID": "CLM-15",
        "Quelle": "bitget_relay.py:120",
        "Wortlaut": "Relay arbeitet strikt read-only: keine Authentifizierung, keine Order-Endpunkte, nur GET / und POST /api/public",
        "Typ": "Sicherheit",
        "Ebene_Querschnitt": "Ebene 2",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "bitget_relay.py, tests/test_relay_full.py (61 Tests OK), pytest.",
        "Empfehlung_Fix": "Keine Änderung nötig. Keine unbefugten Routen oder Credentials."
    },

    # --- Ebene 3: Darstellung (Provenance & Verbraucherschutz) ---
    {
        "ID": "CLM-16",
        "Quelle": "PWF_FIX_REPORT.md:50",
        "Wortlaut": "Dashboard-Hash '8a05272afc988b57f53f5fa37a402cc5caa0f545e874cc9c2c43b36e9c4ddd35' für v1.0.8 Release",
        "Typ": "Zahl",
        "Ebene_Querschnitt": "Ebene 3",
        "Status": "FALSCH",
        "Schweregrad": "NIEDRIG",
        "Beleg_Repro": "Tatsächlicher v1.0.8 SHA-256 ist 0dea7c77ed4f571d8eb41f2c82354cbbcaeb9a34e52f37e46e55c1367c1cd98b. Der Hash '8a05272a...' stammte aus dem uncommitted Draft-Stand vor Versions-Finalisierung. Alle Backtest-Zahlen stimmen exakt überein.",
        "Empfehlung_Fix": "PWF_FIX_REPORT.md aktualisieren, um den finalen Release-Hash 0dea7c77... auszuweisen und die Pre-Commit-Provenance transparent festzuhalten."
    },
    {
        "ID": "CLM-17",
        "Quelle": "SYMBIOSE_Model_Validation.md:156",
        "Wortlaut": "Test commands referenzieren 'node test_symbiose.js' und '118/118' Tests in test_engine_full.js",
        "Typ": "Verhalten",
        "Ebene_Querschnitt": "Ebene 3",
        "Status": "FALSCH",
        "Schweregrad": "NIEDRIG",
        "Beleg_Repro": "test_engine_full.js enthält aktuell 121 Tests; test_symbiose.js existiert nicht mehr im Workspace (durch neuere Test-Dateien ersetzt).",
        "Empfehlung_Fix": "SYMBIOSE_Model_Validation.md aktualisieren: Testbefehle und Testanzahl (121/121) auf aktuellen Stand bringen."
    },
    {
        "ID": "CLM-18",
        "Quelle": "SYMBIOSE_Model_Validation.md:168",
        "Wortlaut": "Section 7 behauptet 'External evidence still open: Five golden-master CSV exports'",
        "Typ": "Verhalten",
        "Ebene_Querschnitt": "Ebene 3",
        "Status": "FALSCH",
        "Schweregrad": "NIEDRIG",
        "Beleg_Repro": "Alle fünf Golden-Master CSV-Dateien liegen vor in tests/fixtures/golden/ mit vollständiger provenance.json und werden in release_check.py kontinuierlich getestet.",
        "Empfehlung_Fix": "SYMBIOSE_Model_Validation.md Section 7 als erledigt/integriert dokumentieren."
    },
    {
        "ID": "CLM-19",
        "Quelle": "VERSION:1, README.md:1, Symbiose_Dashboard.html:719, SYMBIOSE_Tutorial.html:6, bitget_relay.py:38",
        "Wortlaut": "Version 1.1.4 einheitlich in allen Systemkomponenten",
        "Typ": "Zahl",
        "Ebene_Querschnitt": "Ebene 3",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "scripts/release_check.py Gate 'version consistency' PASS; alle 9 Vorkommen matchen exakt '1.1.4'.",
        "Empfehlung_Fix": "Keine Änderung nötig. Versionierung ist strikt konsistent."
    },
    {
        "ID": "CLM-20",
        "Quelle": "Symbiose_Dashboard.html:6731",
        "Wortlaut": "Autobot-Evidenz ist fail-closed: OOS-Status, >=15 geschlossene Trades, positive Expectancy, DSR >= 0.5; keine Trading-Garantie",
        "Typ": "Verhalten",
        "Ebene_Querschnitt": "Ebene 3",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "Symbiose_Dashboard.html:6731-6760, tests/test_autobot_statistical_edge.js, tests/test_autobot_entry_gate.js.",
        "Empfehlung_Fix": "Keine Änderung nötig. Autobot verweigert Ausführung bei fehlender OOS-Evidenz."
    },
    {
        "ID": "CLM-21",
        "Quelle": "tests/sensitivity_release_gates.js:135",
        "Wortlaut": "PAPER_CANDIDATE resultiert aus synthetischem Test-Fixture (deterministische Sinuswelle) und stellt keinen Live-Edge dar",
        "Typ": "Verhalten",
        "Ebene_Querschnitt": "Ebene 3",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "SYMBIOSE_Model_Validation.md:135, tests/sensitivity_release_gates.js:10-30; synthetischer Charakter klar ausgewiesen.",
        "Empfehlung_Fix": "Keine Änderung nötig. Keine irreführenden Gewinnversprechen vorhanden."
    },

    # --- Ebene 4: Statistische Validität ---
    {
        "ID": "CLM-22",
        "Quelle": "Symbiose_Dashboard.html:1005",
        "Wortlaut": "Look-ahead-Invarianz: effWarmup = min(warmup, max(14, n - 60)) verhindert Repainting historischer Scores bei Kerzen-Anhängen",
        "Typ": "Verhalten",
        "Ebene_Querschnitt": "Ebene 4",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "tests/test_lookahead_metamorphic.js: 3/3 metamorphic tests PASS.",
        "Empfehlung_Fix": "Keine Änderung nötig. Kausale Barrieren verhindern Leaks."
    },
    {
        "ID": "CLM-23",
        "Quelle": "Symbiose_Dashboard.html:1813",
        "Wortlaut": "DSR Multiplicity: totalTrials = paramGrid.length * trialMultiplier (18 * Multiplier) deckt den gesamten effektiven Suchraum ab",
        "Typ": "Formel",
        "Ebene_Querschnitt": "Ebene 4",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "Symbiose_Dashboard.html:1735, 1813; TimeStop-Sweep übergibt reale Kandidatenanzahl, Autobot übergibt Kandidatenanzahl.",
        "Empfehlung_Fix": "Keine Änderung nötig. Multiplicity-Korrektur ist mathematisch konservativ."
    },
    {
        "ID": "CLM-24",
        "Quelle": "tests/fixtures/golden/provenance.json:1",
        "Wortlaut": "Fixture-Integrität: Golden Master Fixtures stammen aus unabhängigen TradingView-Exporten mit verifizierter Provenienz",
        "Typ": "Architektur",
        "Ebene_Querschnitt": "Ebene 4",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "scripts/release_check.py Gate 'golden master authenticity' PASS; keine selbsterzeugten zirkulären Fixtures.",
        "Empfehlung_Fix": "Keine Änderung nötig. Provenienz ist maschinenlesbar verifiziert."
    },

    # --- Querschnitt A: End-to-End-Signalkette ---
    {
        "ID": "CLM-25",
        "Quelle": "Symbiose_Dashboard.html:1347",
        "Wortlaut": "End-to-End Signalkette: Daten -> Indikatoren -> Core-Score -> 5 Gates -> Radar -> Autobot Edge-Gate -> Tracker",
        "Typ": "Architektur",
        "Ebene_Querschnitt": "Querschnitt A",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "test_engine_full.js Section 10 & 13; test_live_trade_tracker.js; test_autobot_entry_gate.js; alle Stufen deterministisch getestet.",
        "Empfehlung_Fix": "Keine Änderung nötig. Vollständige Kette verifiziert."
    },

    # --- Querschnitt B: Doku <-> Code ---
    {
        "ID": "CLM-26",
        "Quelle": "README.md:85, SYMBIOSE_Tutorial.html:217",
        "Wortlaut": "Dokumentierte Schwellenwerte (Score 75/25, MTF 3/4, ADX 20, Squeeze, Makro-Veto, TimeStop 15 Bars) entsprechen exakt dem Code",
        "Typ": "Verhalten",
        "Ebene_Querschnitt": "Querschnitt B",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "Symbiose_Dashboard.html:720 (SYM-Konstanten); alle Werte stimmen 1:1 überein.",
        "Empfehlung_Fix": "Keine Änderung nötig. Doku und Code sind synchron."
    },

    # --- Querschnitt C: Daten-Lineage & Betrieb ---
    {
        "ID": "CLM-27",
        "Quelle": "Symbiose_Dashboard.html:1855",
        "Wortlaut": "window.__SYM_TEST exponiert reine Rechenfunktionen (analyze, simulateRange, etc.) im Browser-Kontext für Unit-Tests",
        "Typ": "Architektur",
        "Ebene_Querschnitt": "Querschnitt C",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "Symbiose_Dashboard.html:1855; keine Execution- oder Credential-Funktionen enthalten. Notwendig für In-Browser-Testing & Playwright.",
        "Empfehlung_Fix": "Bewusst als Test-/Audit-Schnittstelle belassen und in Doku festhalten."
    },
    {
        "ID": "CLM-28",
        "Quelle": "git ls-files .hermes",
        "Wortlaut": "Repo-Hygiene: .hermes/ Ordner (34 Dateien, interne Arbeitsdokumente) war im öffentlichen Git-Repository getrackt",
        "Typ": "Architektur",
        "Ebene_Querschnitt": "Querschnitt C",
        "Status": "FALSCH",
        "Schweregrad": "MITTEL",
        "Beleg_Repro": "git ls-files .hermes liefert 34 Dateien. Zwar keine Secrets und aus symbiose.zip exkludiert, aber interne Agent-Dateien gehören nicht in das öffentliche Git-Tracking.",
        "Empfehlung_Fix": ".gitignore um '.hermes/' ergänzen und 'git rm -r --cached .hermes' ausführen."
    },

    # --- Querschnitt D: Release- & Testintegrität ---
    {
        "ID": "CLM-29",
        "Quelle": "scripts/release_check.py:46",
        "Wortlaut": "Release-Gates: release_check.py validiert alle 10 Software-, Engine-, Paritäts- und Sicherheitsgates fail-closed",
        "Typ": "Verhalten",
        "Ebene_Querschnitt": "Querschnitt D",
        "Status": "WAHR",
        "Schweregrad": "INFO",
        "Beleg_Repro": "python3 scripts/release_check.py; prüft Engine (121 Tests), Radar, Autobot, Sync, Golden Master Parität, E2E Browser, Secrets.",
        "Empfehlung_Fix": "Keine Änderung nötig. Release-Pipeline arbeitet strikt fail-closed."
    }
]

with open("/home/ivo/projects/AURA_Quant_Terminal/claims.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "ID", "Quelle", "Wortlaut", "Typ", "Ebene_Querschnitt", "Status", "Schweregrad", "Beleg_Repro", "Empfehlung_Fix"
    ], lineterminator="\n")
    writer.writeheader()
    for row in CLAIMS:
        cleaned_row = {k: v.strip() if isinstance(v, str) else v for k, v in row.items()}
        writer.writerow(cleaned_row)

print(f"Generated claims.csv with {len(CLAIMS)} entries.")
