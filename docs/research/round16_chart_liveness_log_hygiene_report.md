# Runde 16 — Chart-Liveness und Log-Hygiene (v1.3.2)

Datum: 2026-09-13  
Status: ABGESCHLOSSEN  
Release: https://github.com/trixr1907/AURA-Quant-Terminal/releases/tag/v1.3.2

## Ergebnis

Runde 16 behebt ausschließlich Feed-/Anzeigeprobleme. Score-, Sizing- und Signalregeln blieben unverändert.

- PF-24: Der bestehende Sticky-Bitget-Socket abonniert für das fokussierte Symbol Candle- und Ticker-Kanal gemeinsam. `lastPr` aktualisiert Schlusskurs, High und Low der laufenden Kerze ohne deren Zeitstempel zu verändern. Beim Kerzenwechsel bleibt die bestehende `t > last.t`-Logik erhalten; der Regressionstest belegt, dass keine Duplikate entstehen. `tradePrices[App.symbol]` wird mitgeführt, Quelle und Pill bleiben `bitget-ws`/grün.
- PF-24 Redraw: Der Dirty-Key enthält nun Close, High und Low der unmittelbar in `App.data.candles` aktualisierten Live-Kerze. Canvas-Redraws werden per RAF auf höchstens einen Lauf je 250 ms begrenzt; der 4-s-Reanalyse-Debounce blieb unverändert. Es entstanden keine zusätzlichen REST-Aufrufe.
- PF-25: `fmtPx` formatiert Preise ab 1 mit zwei Stellen, Preise unter 1 gemäß Eigentümerentscheidung überwiegend mit sechs und Kleinstpreise mit acht Stellen. Damit lautet der ALCH-Beleg exakt `Entry: 0.042820 | SL: 0.040493 | TP2: 0.045850`.
- PF-26: Die Entry-Zeile wird durch `formatAutobotEntryLog` als reine Funktion aufgebaut. Die doppelte Time-Stop-Dauer entfällt; sehr kleine Uni-DSR-Werte erscheinen als `<0.01`, Trial-Zahlen mit deutschen Tausenderpunkten.

## Produkt-PR und Merge

Produkt-PR: https://github.com/trixr1907/AURA-Quant-Terminal/pull/19  
Merge-Methode: Merge-Commit, kein Squash  
Produkt-Merge-Commit: `5fc429decef2d02ee81bfae79a4add42eb53d7fa`

Der Merge-Commit hat exakt zwei Parents:

1. `2c7e96660915b1eaf726a5c2b5fdfd234f6a8474` — vorheriger `main`
2. `b0cdfefa0a7625491546d40b38c87cea4de6cd6c` — Produktbranch

## Annotierter Tag

Tag: `v1.3.2`  
Tag-Objekt: `67f610a910fb04d07862af95dac91ab56de6dd7f`  
Peel (`v1.3.2^{commit}`): `5fc429decef2d02ee81bfae79a4add42eb53d7fa`  
Botschaft: `AURA v1.3.2 — Confluence Terminal (read-only research)`

Der Peel entspricht exakt dem Produkt-Merge-Commit.

## Verifikation

### Pytest

Befehl:

    python3 -m pytest -q

Ergebnis: `224 passed, 57 subtests passed`, Exit 0.

### Vollständige Node-Suiten

Befehl:

    for f in tests/test_*.js; do node "$f" >/dev/null || exit 10; echo "$f: PASS"; done

Zählung:

    wc -l </tmp/round16-js.txt

Ergebnis: `57` — 57/57 Suiten PASS, Exit 0.

Neue Suiten:

- `tests/test_chart_liveness_ticker.js`
- `tests/test_price_formatting.js`
- `tests/test_autobot_entry_log_hygiene.js`

Zusätzlich wurde `tests/test_live_trade_current_price_render.js` um die reale `fmtPx`-Abhängigkeit ergänzt, nachdem der unabhängige Pre-Commit-Review diesen fehlenden Testkontext gefunden hatte.

### innerHTML-Budget

Befehl:

    grep -c "innerHTML" Symbiose_Dashboard.html

Ergebnis: `51` — unverändert.

### CVD und Release Gate

`cvd independent reference parity`: PASS, darunter für alle Fixtures `max_flip_count = 0`.  
Befehl: `python3 scripts/release_check.py`  
Exit: `0`  
Verdict: `SOFTWARE_GO / MODEL_NO_EVIDENCE (real)`; Synthetic Gate `PAPER_CANDIDATE`; Lockbox `UNUSED`.

Das Software-Gate ist grün. Die unveränderte Aussage `MODEL_NO_EVIDENCE` wird ausdrücklich nicht als Trading-Edge interpretiert.

## Ledger

Runde 16 wurde nach Ledger-Regeln als Prozess-Fix klassifiziert: Ticker-Nutzung und Canvas-Redraw ändern nur die Aktualität/Anzeige des letzten Marktpreises; adaptive Formatierung und Log-Hygiene verändern ausschließlich Darstellung. Keine Signal-, Score-, Sizing-, Parameter- oder Universumslogik wurde geändert.

Verifier-Ergebnis:

- Letzter Eintrag: `EXP-032`
- Einträge: `7`
- Chain-Head: `ac6132270659130165f84c6ca1b7a04b04fc4af6fbed0dbb0b63ba13adfb116b`
- `total_model_experiments`: `10` — unverändert

## Check-Runs

Auf Produkt-Merge-Commit `5fc429decef2d02ee81bfae79a4add42eb53d7fa`:

- `Test Suite & Quality Gates`: `completed / success`
- `Socket Security: Project Report`: `completed / success`
- `publish`: `completed / success`
- `SonarCloud Code Analysis`: `completed / neutral`

Auf PR #19 schlug das SonarCloud Quality Gate fehl. Konkreter Blocker waren drei neue `javascript:S1523`-Vulnerabilities (dynamische Codeausführung) in den hermetischen Node-Tests:

- `tests/test_autobot_entry_log_hygiene.js:25`
- `tests/test_chart_liveness_ticker.js:109`
- `tests/test_price_formatting.js:18`

Diese wurden bewusst akzeptiert: Alle drei Tests laden ausschließlich den eingecheckten, repository-eigenen Inhalt von `Symbiose_Dashboard.html`, extrahieren daraus Funktionen und führen sie in einem isolierten `node:vm`-Kontext aus. Es existiert kein externer oder nutzergesteuerter Input in diesem Pfad. Kommentare dokumentieren diese Vertrauensgrenze. SonarCloud meldete zusätzlich nicht-blockierende Code-Smells; zwei Produktstellen (`fmtTrials`-Regex und überflüssiger Fallback beim Object-Spread) wurden bereinigt. Der ausdrücklich aus Runde 16 ausgeschlossene S3776-Refactor von `connectWS` wurde nicht vorgenommen.

## GitHub Release und heruntergeladenes Asset

Workflow: `Publish GitHub Release`, Run `34725808769`, Conclusion `success`.  
Release ist weder Draft noch Prerelease.  
Asset: `symbiose.zip`

Das Asset wurde nach dem Upload erneut mit `gh release download v1.3.2` heruntergeladen und unabhängig geprüft:

- Größe: `230905` Bytes
- Dateien: `26`
- SHA-256: `5c9ecf9735b6d7623503ad8131bd708c864d6a9c362ed5a76ea14b87f92cb576`
- `VERSION`: `1.3.2`
- Pflichtdateien vorhanden: `LICENSE`, `RELEASE_v1.3.2.md`, `VERSION`, `Dockerfile`
- Download: https://github.com/trixr1907/AURA-Quant-Terminal/releases/download/v1.3.2/symbiose.zip

Der Hash stammt ausdrücklich vom nach dem GitHub-Upload heruntergeladenen Asset, nicht vom lokalen Vorab-Build.

## Docs-Merge

Der Docs-Bericht wird nach dem Release über einen separaten docs-only PR gemergt. Der tatsächliche Docs-Merge-Hash wird nach dem Merge direkt aus Git/API ermittelt und in der abschließenden Antwort ausgewiesen; er wird nicht vorab rekonstruiert oder in diesen getaggten Produktstand zurückgeschrieben.
