# AURA Server-Bot Guide — 24/7 Signale ohne offenen Browser

Dieses Dokument beschreibt die Inbetriebnahme und den Betrieb des **Headless Paper-Autobots (Server-Modus)** in AURA v1.7.0.

---

## 🎯 Überblick & Eigentümer-Szenario

**Szenario:** Du bist unterwegs, hast nur dein Smartphone dabei; dein Heim-PC ist **ausgeschaltet**.  
Dein Homelab (z. B. Proxmox-Server → Docker-VM → AURA-Container) läuft 24/7.

**Ergebnis:** Du erhältst Push-Benachrichtigungen über:
- Trade eröffnet (`AURA · Trade-Signal: XPNUSDT SHORT 3x — Trade eröffnet [Server-Bot]`)
- Take-Profit Ziele getroffen (`TP1 (+1.0R)`, `TP2`, `TP3`)
- Stop-Loss (`AURA · Risiko-Alarm: Stop-Loss getroffen`)
- BTC-Regime-Wechsel (`BULL / BEAR / SIDEWAYS`)
- Täglicher Stiller Digest (7:00 UTC)

**Alles ohne dass ein Browser geöffnet sein muss.**

---

## 🚀 Server-Modus aktivieren

### 1. In `docker-compose.yml` oder `.env`

Füge die Umgebungsvariablen hinzu:

```env
# Server-Modus aktivieren (Default ist leer/aus)
AURA_BOT_MODE=server

# Scan-Intervall in Sekunden (Default 60)
AURA_BOT_SCAN_SEC=60

# Start-Simulationskapital in USDT (Default 10000)
AURA_BOT_EQUITY=10000

# ntfy Push-URL für Signale
AURA_NTFY_URL=https://ntfy.sh/<DEIN-GEHEIMER-TOPIC>
```

### 2. Container starten

```bash
docker compose up -d --build
```

Beim Start loggt das Relay:
```
[Runner] AURA Headless Paper Autobot starting (v1.7.0)
[Runner] Engine loaded OK
[Runner] Mode flag written to relay state
[Runner] Cycle #1 done. Open=0 Equity=10000 Funnel={} (142ms)
```

---

## 🎛️ Bedienung über das Dashboard

Das Dashboard fungiert im Server-Modus als **Fernglas** und Fernbedienung:

1. **Status-Badge:** Im Autobot-Bereich erscheint das blaue Badge `🌐 SERVER-BOT AKTIV (24/7)`.
2. **Doppel-Handel-Schutz:** Der Browser-Autobot pausiert seinen lokalen Scan automatisch (der Start-Button ist gesperrt).
3. **Parameter ändern:** Klicke auf `⚙ Parameter`, passe Profil/Schwellen/Hebel an und klicke `✓ Speichern & Anwenden`. Die Parameter werden im nächsten Scan-Zyklus (~60s) vom Server-Runner übernommen.
4. **Trade-Karten:** Offene Positionen tragen das Badge `🌐 SERVER`.

---

## 🛡️ Sicherheit & Grenzen

- **Paper-Only:** Der Autobot führt ausschließlich simulierte Paper-Trades aus. Es werden zu keinem Zeitpunkt echte API-Orders an Börsen geschickt.
- **Fail-Close:** Bei Marktdaten-Ausfällen oder unvollständigen Kerzen bricht der Zyklus ab — es wird kein Trade ohne nachgewiesene positive OOS-Evidenz eröffnet.
- **Restart-Sicherheit:** Alle Trades, Once-Flags und Cooldowns überleben Container-Restarts unter `/var/lib/aura`.
