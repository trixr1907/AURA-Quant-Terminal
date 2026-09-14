# AURA Server-Bot Guide — 24/7 Signale ohne offenen Browser

Dieses Dokument beschreibt die Inbetriebnahme, Persistenz und den 24/7-Betrieb des **Headless Paper-Autobots (Server-Modus)** in AURA v1.7.0.

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

## 🚀 Aktivierung in 3 Schritten (generisch)

Dieses Verfahren funktioniert auf jeder AURA-Installation (Homelab, VPS, Fremdinstallation).

### Schritt 1: Aktivierungs-Skript ausführen

Auf dem Host (Docker-VM / Proxmox-Node):

```bash
# Interaktiv (fragt nach ntfy-URL):
sudo ./scripts/ops/enable_server_bot.sh

# Oder parametrisiert in einem Schritt:
sudo ./scripts/ops/enable_server_bot.sh \
  --ntfy-url "https://ntfy.sh/<DEIN-GEHEIMER-TOPIC>" \
  --scan-sec 60 \
  --equity 10000
```

Das Skript:
1. Validiert die ntfy-URL und Parameter.
2. Schreibt die Konfiguration persistent nach `/var/lib/aura/aura_bot.env`.
3. Startet den Container `aura-terminal` sauber mit der neuen Umgebung neu.

*Manuelle Alternative ohne Skript:*
Erstelle `/var/lib/aura/aura_bot.env` direkt auf dem Host:
```env
AURA_BOT_MODE=server
AURA_BOT_SCAN_SEC=60
AURA_BOT_EQUITY=10000
AURA_NTFY_URL=https://ntfy.sh/<DEIN-GEHEIMER-TOPIC>
```

### Schritt 2: Geräte abonnieren

Abonniere dein ntfy-Topic auf dem Smartphone (ntfy-App) und/oder PC (Browser):
👉 Detaillierte Schritt-für-Schritt Anleitung: [NTFY_GUIDE.md](NTFY_GUIDE.md).

### Schritt 3: Verifizieren & Test-Push

1. **Runner-Status prüfen:**
   ```bash
   curl -s http://localhost:8787/ready | jq .runner
   ```
   Erwartetes Ergebnis:
   ```json
   {
     "running": true,
     "last_cycle_age_sec": 14.2,
     "cycle_count": 1,
     "trade_count": 0,
     "equity": 10000
   }
   ```

2. **Test-Signal emittieren:**
   ```bash
   curl -s -X POST http://localhost:8787/api/signals \
     -H "Content-Type: application/json" \
     -d '{"title":"AURA Server-Bot Test","body":"Signal-Pfad 24/7 verifiziert","priority":3}'
   ```
   Ergebnis: `{"ok": true}` und sofortiger Push-Eingang auf allen abonnierten Geräten.

---

## 🔄 Persistenz-Mechanismus (Release-fester Receiver)

### Das Problem
Der automatische GitHub Deploy-Receiver baut bei jedem neuen Release (`symbiose.zip`) den Docker-Container neu. Ein einmaliges `docker run -e AURA_BOT_MODE=server` ginge beim nächsten Release verloren.

### Die Lösung
Die Konfiguration liegt in `/var/lib/aura/aura_bot.env` auf dem persistenten Volume `aura-state`. Der Receiver liest diese Datei bei jedem Container-Start/Rebuild automatisch ein und merged sie in die `docker run`-Parameter.

#### Receiver-Referenz-Muster (für eigene Deploy-Receiver / Fremd-Installationen):
```python
def read_persistent_bot_env() -> dict[str, str]:
    """Read /var/lib/aura/aura_bot.env if present to persist bot env across releases."""
    env_file = Path(DEPLOY_STATE_DIR) / "aura_bot.env"
    if not env_file.exists():
        env_file = Path("/var/lib/docker/volumes/aura-state/_data/aura_bot.env")
    if not env_file.exists():
        return {}
    res = {}
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if k:
                res[k] = v
    except Exception as exc:
        log.warning("Failed to read persistent bot env file %s: %s", env_file, exc)
    return res


def recreate_arguments(config: dict[str, Any], image: str) -> list[str]:
    host_config = config.get("HostConfig") or {}
    args = ["docker", "run", "-d", "--name", CONTAINER_NAME]
    
    restart_name = ((host_config.get("RestartPolicy") or {}).get("Name") or "unless-stopped")
    args.extend(["--restart", restart_name])

    env_map = {}
    for env_value in (config.get("Config") or {}).get("Env") or []:
        key, _, val = env_value.partition("=")
        if key not in {"AURA_ALLOWED_HOSTS", "AURA_STATE_DIR"}:
            env_map[key] = val

    # Persistent bot env file wins
    persistent_bot_env = read_persistent_bot_env()
    env_map.update(persistent_bot_env)

    # Core deployment parameters
    env_map["AURA_ALLOWED_HOSTS"] = DEPLOY_ALLOWED_HOSTS
    env_map["AURA_STATE_DIR"] = DEPLOY_STATE_DIR

    for k, v in env_map.items():
        args.extend(["-e", f"{k}={v}"])
    ...
```

---

## 👥 Fremdinstallation / Installation für Dritte

Möchte ein Freund oder Teampartner eine eigene AURA-Instanz mit 24/7 Server-Bot betreiben:

1. **Eigener Server / VM:** Eigene Docker-VM oder Proxmox-Node.
2. **Eigenes Topic:** Ein völlig eigenständiges, geheimes ntfy-Topic wählen (niemals Topics teilen!).
3. **Eigener Receiver:** Den Webhook-Receiver auf seiner VM mit eigenem `AURA_WEBHOOK_SECRET` und eigenem Topic einrichten (Timeout: 300 s, Version-Polling auf `/serving`).
4. **Gleiche 3 Aktivierungsschritte:** `enable_server_bot.sh` mit seinem Topic ausführen.

---

## 🎛️ Bedienung über das Dashboard

Das Dashboard fungiert im Server-Modus als **Fernglas** und Fernbedienung:

1. **Status-Badge:** Im Autobot-Bereich erscheint das blaue Banner `🌐 SERVER-BOT AKTIV (24/7)`.
2. **Doppel-Handel-Schutz:** Der Browser-Autobot pausiert seinen lokalen Scan automatisch (Start-Button ist gesperrt, verhindert doppelte Orders).
3. **Parameter ändern:** Klicke auf `⚙ Parameter`, passe Profil/Schwellen/Hebel an und klicke `✓ Speichern & Anwenden`. Die Parameter werden im nächsten Scan-Zyklus (~60s) vom Server-Runner übernommen.
4. **Trade-Karten:** Offene Positionen tragen das Badge `🌐 SERVER`.

---

## 🛡️ Sicherheit & Guardrails

- **Paper-Only:** Der Autobot führt ausschließlich simulierte Paper-Trades aus. Es werden zu keinem Zeitpunkt echte API-Orders an Börsen geschickt.
- **Fail-Close:** Bei Marktdaten-Ausfällen oder unvollständigen Kerzen bricht der Zyklus ab — es wird kein Trade ohne nachgewiesene positive OOS-Evidenz eröffnet.
- **Restart-Sicherheit:** Alle Trades, Once-Flags und Cooldowns überleben Container-Restarts unter `/var/lib/aura`.
