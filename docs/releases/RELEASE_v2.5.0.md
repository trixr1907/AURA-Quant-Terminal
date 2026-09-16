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

Die finalen lokalen und Remote-Evidenzen werden vor Veröffentlichung ergänzt:

- Pytest: ausstehend
- JavaScript-Subtests: ausstehend
- Release-Check: ausstehend
- Ledger-Verifikation: ausstehend
- `innerHTML`: ausstehend
- PR / Merge-Commit / Tag: ausstehend
- Release-Asset SHA-256: ausstehend
- Auto-Deploy und ntfy-Server-ID: ausstehend
