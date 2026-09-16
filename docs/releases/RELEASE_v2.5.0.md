# AURA v2.5.0 — Confluence Terminal (read-only research)
## Release-Bericht: Server-Only Live (Runde 39)

**Datum:** 2026-09-16  
**Branch:** `feat/round39-v2.5.0-server-only-live`  
**Tag-Botschaft:** `AURA v2.5.0 — Confluence Terminal (read-only research)`  
**Ausgangsbasis:** `bf6119bd5c9f07d99b948eb1ad360768e4235e08`  
**Release-Wahrheit:** `SOFTWARE_GO / MODEL_NO_EVIDENCE`

## Ziel

Im Server-Modus ist der Docker-Runner die einzige Quelle für Paper-Trades. Er läuft ohne Browser-Abhängigkeit durchgehend; das Dashboard beobachtet Server-State und ändert die zentrale Bot-Konfiguration.

## Verhaltensänderung

- `headless_autobot.js` ignoriert alte Browser-Ownership-Flags und setzt Runner-State, Payload und Health immer auf `paused:false`, `pausedBy:null`.
- `Symbiose_Dashboard.html` eröffnet, verwaltet oder schließt keine Browser-Trades mehr. `Autobot.tick()` kehrt im Server-Modus vor jeder lokalen Simulation zurück.
- Dashboard-Trades und Historie werden auf Datensätze mit `source="server"` begrenzt.
- Profil, Equity, Risiko, Slots, MinScore, MTF, Volumen, OOS, DSR und Time-Stop gehen über `POST /api/bot-config` in `aura-server-bot-config-v1`; der Runner liest den Key in jedem 15-Sekunden-Zyklus neu.
- `/status` kennzeichnet „Server-Only Live seit v2.5.0“, `Bot Aktiv: Ja` und `Pausiert: Nein`.
- Der Tages-Digest bleibt unverändert und liest Equity, offene Trades und Abschlüsse ausschließlich aus dem Server-Bot-State.

## Gewollter Breaking Change

Die alte Doppel-Bot-Logik ist beendet: Der Browser-Autobot tradet nicht mehr und kann den Server-Bot nicht pausieren. API- und Laufzeit-State-Schemas bleiben kompatibel; betroffen ist ausschließlich die frühere Ownership-Semantik.

## Migration

1. Deployment mit `AURA_BOT_MODE=server` starten bzw. beibehalten.
2. Dashboard einmal öffnen und „Server-Bot Config deaktivieren“ wählen, wenn ein historisches Browser-`enabled`-Flag gelöscht werden soll.
3. Danach gewünschte Parameter speichern. Sie wirken spätestens im nächsten Runner-Zyklus.
4. Das alte Flag ist für die Runner-Verfügbarkeit nicht mehr relevant: Der Server läuft auch ohne geöffnetes Dashboard weiter.

## Unveränderte Invarianten

- Globale Modellwahrheit bleibt `MODEL_NO_EVIDENCE`; diese Version erhebt keinen Profitabilitätsanspruch.
- Ledger-Head bleibt EXP-032 (`ac6132270659130165f84c6ca1b7a04b04fc4af6fbed0dbb0b63ba13adfb116b`).
- Lockbox bleibt `UNUSED`.
- Radar-Profilgrenzen 58/65/75 und der Nullvarianz-Guard bleiben aktiv.
- Kein Echtgeld-Orderpfad wird eingeführt.

## Abnahme-Evidenz

| Kriterium | Status | Beleg |
|---|---|---|
| Pause-Block entfernt, kein `Browser bot is active` im Code | PASS | `grep -F "Browser bot is active" headless_autobot.js` → kein Match |
| `runner_health.json` immer `paused:false` im Server-Modus | PASS | `exposeHealth()` und `toServerPayload()` forcieren `false/null` |
| Dashboard öffnet keine Trades wenn Server aktiv | PASS | `Autobot.tick()` early-return + `scanAndExecuteOpportunities()` loggt statt zu traden |
| Dashboard Config-Änderungen wirken per `/api/bot-config` | PASS | `pushServerConfig()` + `save_server_bot_config()` + Runner liest `KEY_SRV_CFG` |
| `test_server_only_live.js` | PASS | Browser-enabled blockiert Server nicht; configMinScore 77 korrekt |
| `test_r39_release.py` | PASS | 2 passed |
| `test_pf66_headless_runner.js` | PASS | 35/35 (mode-flag-Tests auf Server-Only umgestellt) |
| `test_relay_status.py` | PASS | Banner + `Nein (Server-Only Live)` + `bot_active=Ja` verifiziert |
| `test_relay_full.py` | PASS | `/api/bot-config` Endpoint-Test neu + bestehende |
| Vollständige Suites / Release-Gate / Ledger | PASS | pytest: **508 passed, 69 subtests**; release_check: **SOFTWARE_GO / MODEL_NO_EVIDENCE** Exit 0; verify_ledger: EXP-032 `ac6132270659130165f84c6ca1b7a04b04fc4af6fbed0dbb0b63ba13adfb116b` |
| `innerHTML` | PASS | **63** (unverändert); Banner in `bitget_relay.py` Python-String, kein neuer JS-innerHTML-Sink |
| PR / Merge-Commit / Tag / Release / Asset | PASS | PR #53 merged, Commit `22396e1` (2 Parents: `bf6119b` + `a45b921`), Tag `v2.5.0` gepusht (`9a6968c8...`), Publish workflow run `35141290694` → success, Asset SHA-256 `9fc9cf1ae7ea0e094605ee4048b5fbd3b211e64c1c6b8063b444c6fe802194d7` (322 691 Bytes) |
| CI grün (main) | PASS | Run `35141266167` → `Test Suite & Quality Gates`: success |
| Auto-Deploy und ntfy-Server-ID | PENDING — VMs sind nicht lokal erreichbar; Webhook-Delivery-ID und ntfy-Push-ID werden nach realem Auto-Deploy vom Betreiber nachgetragen |

