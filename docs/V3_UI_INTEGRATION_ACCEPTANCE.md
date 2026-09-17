# AURA v3 — UI- & Control-Plane-Integrationsabnahme

**Datum:** 2026-09-17  
**Workspace:** `/home/ivo/projects/AURA_v2`  
**Branch:** `audit/r40-baseline`  
**Paketstatus:** `UI_INTEGRATION: PASS`  
*(Hinweis: Dieser Paketstatus ist eine komponentenbezogene Abnahme der UI-/Control-Plane-Integration und stellt ausdrücklich KEINE Gesamtproduktfreigabe dar. Modell-Evidenz, Funding-Kosten, TP3 und Soak-Test bleiben separaten Paketen vorbehalten).*

---

## 1. Ausgangslage & Klärende Befunde

### Testzahlen-Diskrepanz
Im Übergabebericht bestand eine rechnerische Abweichung zwischen 99 genannten v3-Tests und einer tabellarischen Aufschlüsselung von 100. Die tatsächliche Pytest-Collection und Ausführung ergab:
- **v3-Pytest-Suite (`tests/test_v3_*.py`):** 115 Tests gesammelt, **115 passed** in 35.72s.
- **Gesamte Python-Testsuite (`pytest -ra`):** 623 Tests gesammelt, **623 passed** in 51.01s (0 Fehler).
- **JavaScript-Suite (`node tests/test_*.js`):** 98 Testdateien ausgeführt, **98 passed**, 0 failed (100% grün).

### Bereinigung der JavaScript-Regression (`tests/test_cross_device_sync.js`)
- **Ursache:** Bei der Härtung der v3-API lieferte `/api/v3/state` das Statuswörterbuch direkt als Root-Objekt, während die Legacy-Relay-Schnittstelle Payloads in `{ ok: true, data: { ... } }` einbettete. In `Symbiose_Dashboard.html` führte dies dazu, dass verschachtelte Mocks in `SyncEngine.pull()` nicht mehr in den Shadow-Store synchronisiert wurden, wodurch ein History-Delete-Diff fehlschlug.
- **Lösung:** Defensives Entpacken `const remote = (s.data && typeof s.data === 'object') ? s.data : s;` in `Symbiose_Dashboard.html`. Dadurch werden sowohl v3-Root-Antworten als auch gekapselte Legacy-Payloads korrekt verarbeitet, ohne Testverträge abzuwerten.

### Behebung der Duplikation geschlossener Positionen (`PaperTradingEngine`)
- **Ursache:** In `PaperTradingEngine._load_state_from_db_if_available()` wurde `self.closed_positions` bei wiederholten API-Aufrufen nicht geleert, sondern mit `append()` kontinuierlich vergrößert.
- **Lösung:** `self.open_positions.clear()` und `self.closed_positions.clear()` vor jedem Einlesen aus SQLite hinzugefügt.

---

## 2. Startbefehle & Systemzugriff

### Umgebungsvariablen & Secrets
Das System liest den Operator-Token aus der Umgebungsvariable `AURA_RELAY_TOKEN`. Es befinden sich keine Tokens im Code, im HTML, in Logdateien oder in URL-Parametern.

```bash
# Optional: Setzen eines individuellen Tokens (Standard-Fallback ist vorhanden)
export AURA_RELAY_TOKEN="<GEHEIMER_OPERATOR_TOKEN>"
```

### Start der Dienste
Die Weboberfläche, die FastAPI v3 API und der autonome Worker-Dienst laufen entkoppelt:

```bash
# 1. API-Server starten (FastAPI + Static Files):
python3 -m uvicorn aura.api.app:app --host 127.0.0.1 --port 8000

# 2. Separaten Worker-Dienst starten (in zweitem Terminal):
python3 -m aura.runner.worker --symbols BTCUSDT,ETHUSDT --poll-interval 1.0
```

### Browser-Zugriff
- **Dashboard-URL:** `http://127.0.0.1:8000/`
- **Swagger / OpenAPI-Spezifikation:** `http://127.0.0.1:8000/docs`
- **Health-Check:** `http://127.0.0.1:8000/api/v3/health`

---

## 3. Sicherheits- & Authentifizierungskonzept

1. **Session-Handling via Same-Origin HttpOnly Cookie:**
   - Beim Login über das UI-Modal (`POST /api/v3/auth/login`) mit dem Operator-Token erzeugt der Server eine kryptografisch sichere Zufallssitzung (`secrets.token_hex(32)`).
   - Das Cookie `aura_session` wird mit `HttpOnly=True`, `SameSite=Lax` und `max_age=86400` (24h) gesetzt. Unter HTTPS bzw. hinter `X-Forwarded-Proto: https` wird automatisch `Secure=True` aktiviert.
2. **CSRF-Schutz für schreibende Aktionen:**
   - Bei allen mutierenden Anfragen (`POST`, `PUT`, `DELETE`, `PATCH`), die über ein Session-Cookie authentifiziert sind, erzwingt `verify_auth_token` einen Abgleich der `Origin`- bzw. `Referer`-Header gegen den Server-`Host`. Abweichende Fremd-Origins werden mit HTTP 403 Forbidden abgewiesen.
3. **Login Rate-Limiting:**
   - Zum Schutz gegen Brute-Force-Angriffe blockiert die API einen Client nach 5 aufeinanderfolgenden fehlerhaften Login-Versuchen für 60 Sekunden mit HTTP 429 (Too Many Requests).
4. **Schutz des Status-Endpunkts:**
   - Auch `/api/v3/state` ist auth-geschützt. Anonyme Zugriffe erhalten HTTP 401 Unauthorized; sensible Serverdaten leaken nicht an Unbefugte.
5. **Konsequenzen der In-Memory Session-Speicherung:**
   - Sessions liegen im Hauptspeicher des API-Prozesses. Bei einem Neustart des API-Servers müssen sich aktive Browser neu authentifizieren. Bei Multi-Worker-Deployments (z.B. Uvicorn mit `--workers > 1`) muss Sticky-Session-Routing konfiguriert werden oder ein Single-Process-Modell gefahren werden.

---

## 4. Control-Plane & Halt-Semantik

### Latenz & Ausführungsgarantie
- **Latenz:** Die Quittierungslatenz für Not-Halt und Konfigurationsänderungen ist begrenzt durch:
  $$t_{\text{latency}} \le t_{\text{poll}} + \sum t_{\text{network\_timeout}}$$
  Unter Standardeinstellung (`poll_interval = 1.0s`, Fast-/Mock-Feeds) quittiert der Worker Befehle in $< 1.0\,\text{s}$. Bei laufendem Netzwerk-Request kann sich die Quittierung um den konfigurierten Feed-Timeout (Standard: 5.0s) verzögern.
- **Race-Condition-Schutz:** Der Worker verarbeitet Kontrollbefehle (`_apply_control_plane_commands`) am Anfang jedes Zyklus, **bevor** Marktdaten ausgewertet oder Einstiegssignale geprüft werden. Bei aktiviertem Halt setzt die FSM `is_halted = True`, sodass in demselben Zyklus kein Einstieg mehr committed werden kann.
- **Transaktionale Not-Halt-Policy:**
  - Neue Signale werden strikt abgewiesen (`REJECTED: Not-Halt aktiv` im `shadow_log`).
  - Bestehende Positionen werden weiter gegen jeden Bar überwacht: TP1/TP2, Stop-Loss und Time-Stop bleiben aktiv.
- **Preis-Breakeven vs. Netto-Verlustfreiheit:**
  - Nach Erreichen von TP1 wird der Stop-Loss auf den tatsächlichen Ausführungspreis (`entry_price`, inkl. Slippage) nachgezogen.
  - **Klarstellung:** Dies ist ein *Preis-Breakeven*, keine absolute *Netto-Verlustfreiheit*, da bei einem späteren Stop-Exit für die verbleibende Restmenge weiterhin Taker-Gebühren (0.06%) und Ausführungsslippage anfallen.
- **UI-Zustandsdifferenzierung:**
  Das Dashboard unterscheidet explizit vier Befehlszustände:
  - *Angefordert:* Banner zeigt `⌛ Angefordert: halt — Warte auf Quittung durch Worker...`
  - *Quittiert:* Badge schaltet auf `⏹ NOT-HALT (Einstiege gesperrt)`, Banner erlischt.
  - *Fehlgeschlagen:* Banner zeigt `❌ Fehlgeschlagen: {type} ({result})`.
  - *Unbekannt/Stale:* Wenn der Worker-Heartbeat $> 120\,\text{s}$ ausbleibt, schaltet das Badge auf `⚠️ WORKER STALE`. Es wird kein erfolgreicher Halt vorgetäuscht.

---

## 5. Anforderung → Test → Artefakt-Matrix (E2E-Playwright)

Alle Tests laufen gegen echte Uvicorn- und Worker-Prozesse mit isolierter Testdatenbank:

| Anforderung | E2E-Testfall | Verifizierter Nachweis & Assertions | Artefakt / Screenshot |
|---|---|---|---|
| **A. Unauthenticated Access** | `test_scenario_a_unauthenticated_access_denied` | Nicht authentifizierter Aufruf liefert 401; UI zeigt "ANMELDUNG"; Klick auf Steuerung blockiert. | `01_scenario_a_unauthenticated.png` |
| **B. Login & State** | `test_scenario_b_login_and_load_authoritative_state` | Token-Eingabe schließt Modal, setzt HttpOnly Cookie; Pill wird grün (`OPERATOR (Live)`); Server-Equity geladen. | `02_scenario_b_authenticated_state.png` |
| **C. Config Revision Ack** | `test_scenario_c_config_request_and_worker_ack` | Risk geändert -> API erhöht `requested_config_rev` -> Worker quittiert `active_config_rev` -> UI rendert neue Rev. | `03_scenario_c_config_applied.png` |
| **D. Concurrent Conflict (Req 2.B)** | `test_scenario_d_concurrent_config_conflict_409` | Zwei Browserkontexte öffnen Config; Client 1 speichert Rev 2; Client 2 (stale) erhält 409 Konflikt-Alert; re-synced auf Rev 2. | `11_req2b_concurrent_conflict_resolved.png` |
| **E. Emergency Halt** | `test_scenario_e_halt_and_prevent_new_entries` | Not-Halt-Klick schreibt Command; Worker setzt FSM auf `HALTED`; UI-Badge zeigt `⏹ NOT-HALT`. | `04_scenario_e_halt_confirmed.png` |
| **F. Position Monitored (Req 2.E)** | `test_scenario_f_position_monitored_during_halt` | Im Halt: Valid-Signal für ETHUSDT wird abgewiesen; bestehende BTCUSDT-Position löst TP1 aus, SL auf Breakeven gesetzt. | Code-Assertion (`shadow_log`) |
| **G. Resume & Recovering** | `test_scenario_g_resume_and_resumption` | Wiederaufnahme quittiert; Status verlässt NOT-HALT (`RECOVERING`/`RUNNING`); Button wechselt zurück. | `05_scenario_g_resumed_running.png` |
| **H. Browser Closed (Req 2.C)** | `test_scenario_h_browser_close_and_reopen_persists_state` | Alle Browser schließen; Worker verarbeitet im Hintergrund Trade-Event in SQLite; neuer Browser öffnet und zeigt exakte Änderung. | `12_req2c_state_changed_while_browser_closed.png` |
| **I. Stale Detection (Req 2.D)** | `test_scenario_i_worker_stale_detection_and_recovery` | Worker gestoppt -> Heartbeat veraltet -> UI meldet `⚠️ WORKER STALE`; Worker startet neu -> Idempotenz verifiziert -> Recovery. | `06_scenario_i_stale_detected.png` |
| **J. Mobile Viewport** | `test_scenario_j_mobile_viewport_and_trade_rendering` | iPhone 13/14 Emulation (390x844, Touch): Login, Responsive Autobot-Sektion und Evidence-Banner geprüft. | `08_mobile_unauthenticated.png`, `09_mobile_authenticated_dashboard.png` |
| **K. Paper Trade Lifecycle (Req 2.A)** | `test_scenario_k_deterministic_paper_trade_production_lifecycle_in_ui` | Synthetischer Breakout -> Worker öffnet Trade mit Slippage & Fee -> Erscheint in UI -> Bar erreicht TP1 -> UI zeigt TP1 & PnL. | `10_req2a_trade_lifecycle_ui.png` |

---

## 6. Verbleibende Einschränkungen & Abgrenzung

Folgende Aspekte sind in diesem Arbeitspaket **nicht** enthalten und bleiben gesonderten Runden vorbehalten:
1. **Modell-Evidenz:** Das System bleibt im Zustand `MODEL_NO_EVIDENCE`. Alle Trades sind rein simulierte Paper-Trades.
2. **Kostenstellen-Vollständigkeit:** 8-stündige Funding-Raten auf Perpetual-Futures und die dritte Ausstiegstranche (TP3) sind im Ausführungs-Accounting noch nicht aktiv. Das Evidence-Banner weist dauerhaft darauf hin.
3. **Soak-Test & Container-Betrieb:** Die Docker-/Proxmox-Langzeitverifikation erfolgt in einem nachfolgenden Infrastruktur-Paket.
