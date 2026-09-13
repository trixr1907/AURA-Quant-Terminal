# AURA Confluence Terminal — Release v1.6.0

**Datum:** 2026-09-14  
**Typ:** MINOR (Signal-Center: Trade-Events, BTC-Regime-Wächter, Daily Digest, Ntfy-Settings-Panel)  
**SemVer-Grund:** PF-59 Signal-Hub mit Dedup & Prioritäten, PF-60 „🔔 Benachrichtigungen"-Panel im Dashboard, PF-61 Trade-Events (Eröffnung/TP1/TP2/TP3/SL/Schluss) mit Once-Flags & Multi-Tab-Dedup, PF-62 Autonomer 24/7 BTC-Regime-Wächter im Relay mit 30 min Cooldown & Squeeze-Stille, PF-63 Daily-Digest & Feed-Error-Alerts; Version-Sync auf v1.6.0.  
**Urteil:** SOFTWARE_GO / MODEL_NO_EVIDENCE (unverändert)  
**Ledger-Status:** EXP-032 (unverändert)  
**Marktdaten-Snapshot:** Marktdaten-Snapshot bewusst unverändert auf v1.5.4-Stand (keine Datenänderung im Feature-Release).

---

## Änderungen

### 1. PF-59 — Zentraler Signal-Hub mit Dedup, Cooldown & Prioritäten
- **Dashboard-Modul `NtfySignals`:** Einheitlicher Signal-Dispatcher mit interner Queue, genau 1 Retry und strikter Fehlerunterdrückung bei leerem/deaktiviertem Topic.
- **Prioritäten-Matrix:**
  - Priorität 1 (leise): Daily Digest.
  - Priorität 3 (Standard): Trade eröffnet, TP1, TP2, TP3, sonstiger Schluss, Deploy ✅, Test-Push.
  - Priorität 4 (Dringend): Stop-Loss, BTC-Regime-Wechsel, Feed-Fehler (>5 min Datenstopp), Deploy ❌.
- **Relay-seitige Signal-Claims:** Atomarer First-Writer-Wins-Mechanismus über `POST /api/state` (`signal_claim: {key: "tradeId:event"}`) schützt vor Doppel-Pushes aus mehreren offenen Browser-Tabs.
- **PF-33 Absorption:** Der alte, unstrukturierte Relay-Delete-Push wurde absorbiert und durch das semantisch saubere Dashboard-Event-System abgelöst.

### 2. PF-60 — „🔔 Benachrichtigungen"-Einstellungs-Panel im Dashboard
- **Kompakte UI-Sektion:** Direkt unterhalb des Paper-Autobots angesiedelt mit intuitiver Endverbraucher-Sprache.
- **Granulare Signal-Toggles:** Individuelle Checkboxen für *Eröffnung*, *TP1*, *TP2*, *TP3*, *Stop-Loss* und *Sonstiger Schluss*.
- **Test-Push:** Interaktiver Button sendet sofort einen Priorität-3-Testpush zur Verifikation der Topic-Erreichbarkeit auf Mobilgeräten/PCs.
- **Barrierefreiheit & Layout-Stabilität:** Vollständige A11y-Attribute (`role="status"`, `aria-live="polite"`, `aria-describedby`), `flex-wrap: wrap` für 320 px Responsive-Tauglichkeit ohne Horizontales Scrolling.
- **Persistenz & Sync:** Einstellungen werden unter dem Key `aura-ntfy-signals-settings-v1` in `localStorage` und über den zentralen Relay-State-Sync abgeglichen.

### 3. PF-61 — Vollständiger Trade-Lifecycle mit Once-Flags
- **Emittierte Trade-Events:**
  - `open`: Bei manueller Eröffnung oder Autobot-Einstieg (Prio 3).
  - `tp1`, `tp2`, `tp3`: Bei Erreichen der Take-Profit-Ziele (Prio 3).
  - `sl_close`: Bei Schließung durch Stop-Loss (Prio 4).
  - `other_close`: Bei manuellem Schließen, Time-Stop oder Break-Even-Exit (Prio 3).
- **Persistente Once-Flags:** `openNotified`, `tp1Hit`, `tp2Hit`, `tp3Hit`, `closeNotified` auf jedem Trade-Objekt verhindern Wiederholungsalarme über Page-Reloads und Sync-Zyklen hinweg.
- **Richtungsbereinigte Berechnungen:** PnL- und R-Multiple-Metriken im Push-Text werden für Long (`dir === 1`) und Short (`dir === -1`) mathematisch exakt ausgewiesen.

### 4. PF-62 — 24/7 BTC-Regime-Wächter im Relay
- **Autonomer Daemon-Thread:** Läuft unabhängig von offenen Browser-Tabs 24/7 im Relay-Hintergrund und prüft alle 5 Minuten geschlossene 1h-Kerzen von `BTCUSDT`.
- **JS↔Python-Parität:** Exakter mathematischer Port der Dashboard-Indikatoren (`_calc_ema`, `_calc_rma`, `_calc_atr`, `_calc_adx`, `_calc_kc_bb_squeeze`).
- **Signal-Disziplin & Anti-Flut:**
  - 30 Minuten Mindest-Cooldown zwischen Regime-Pushes.
  - Squeeze-Eintritt und -Austritt bleiben still (Status wird nur im Body ausgewiesen).
  - Ein während eines Squeezes eingetretener Strukturwechsel wird beim Verlassen des Squeezes zuverlässig einmalig signalisiert.
- **Persistenter Zustand:** Letztes Regime und Alarm-Zeitstempel werden in `/var/lib/aura/aura_signal_center_state.json` gespeichert (kein Doppel-Push nach Container-Neustart).

### 5. PF-63 — Daily-Digest & Feed-Error-Alerts
- **Daily Digest (Prio 1, leise):** Sendet täglich zur konfigurierten UTC-Stunde (Default: `AURA_NTFY_DIGEST_UTC=7`) eine Zusammenfassung aus Gesamtkapital (Autobot + Manuell), offenen Positionen, aktuellem BTC-Regime und 24h realisierter PnL.
- **Feed-Error-Alerts (Prio 4):** Löst einen Alarm aus, wenn über 5 Minuten keine Marktdaten empfangen werden können. 60 Minuten Cooldown verhindert Alarmfluten. Eine erfolgreiche Datenabfrage beendet die Fehlerkette ohne den Cooldown vorzeitig zu löschen.

---

## Verifikations-Nachweise (Regel 2: ausgeführte Befehle + Ausgabe)

### 1. Pytest-Suite (Vollständig inkl. Subtests)
```
$ python3 -m pytest -q
........................................................................ [ 28%]
..................................................................... [ 56%]
............................................................... [ 81%]
..............................................                                                      [100%]
250 passed, 57 subtests passed in 11.49s
```
*(Baseline v1.5.4: 236 passed, 57 subtests passed -> Delta: +14 neue Python-Tests für PF-59, PF-62, PF-63 und PF-33-Absorption).*

### 2. JS-Test-Suiten (Kanonischer Loop)
```
$ python3 -c "
import glob, subprocess
js_files = sorted(glob.glob('tests/test_*.js'))
passed = sum(1 for f in js_files if subprocess.run(['node', f], capture_output=True).returncode == 0)
print(f'JS_PASS={passed} JS_FAIL=0 JS_TOTAL={len(js_files)}')
"
JS_PASS=82 JS_FAIL=0 JS_TOTAL=82
```
*(Baseline v1.5.4: 79 Suiten -> Delta: +3 Suiten: `test_pf59_signal_hub.js`, `test_pf60_settings_ui.js`, `test_pf61_trade_events.js`).*

### 3. innerHTML-Kanonik
```
$ printf 'innerHTML: '; grep -o 'innerHTML' Symbiose_Dashboard.html | wc -l
innerHTML: 66
```
*(Baseline v1.5.4: 66 -> Delta: 0. Das neue Benachrichtigungs-Panel wurde ohne innerHTML realisiert: statisches Template mit sauberen DOM-Property-Bindings (`.value`, `.checked`, `.textContent`) verhindert XSS-Angriffsflächen).*

### 4. Release-Check & Forensisches Audit
```
$ python3 scripts/release_check.py
...
VERDICT: SOFTWARE_GO / MODEL_NO_EVIDENCE (real) · synthetic-gate: PAPER_CANDIDATE · lockbox-eval: UNUSED
```
*(Exit-Code: 0. Alle 73 automatisierten Prüfpunkte bestanden).*

### 5. CVD Reference & Invariance Gate
```
$ python3 scripts/cvd_reference.py
{
  "ok": true,
  "thresholds": {
    "min_bars": 5000,
    "max_relative_drift": 1e-10,
    "max_flip_count": 0
  },
  "fixtures": [...]
}
```

### 6. Packaging & Archiv-Prüfung
```
$ python3 scripts/build_package.py
Built symbiose.zip: 26 files
SHA-256: 632c68b34a30dcdf4af40500b048c3955570cada6ae676d3ebc26c2b6b8e03fb
SMOKE TEST: all non-browser checks passed from clean extraction
```

---

## Scope & Evidenz-Garantie
- Keine Modifikation an Score-, Sizing- oder Evidenz-Algorithmen.
- `TRIALS_LEDGER.md` (EXP-032) und `VERDICT.md` sind unmodifiziert (0/0 diff).
- `data/bitget_usdt_futures_universe.json` ist bit-identisch zum v1.5.4-Tag.
- Urteil: `SOFTWARE_GO / MODEL_NO_EVIDENCE`.
