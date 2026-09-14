# AURA Server-Bot Guide — 24/7 Signale ohne offenen Browser

Dieses Dokument beschreibt die Inbetriebnahme, Persistenz und den 24/7-Betrieb des **Headless Paper-Autobots (Server-Modus)** in AURA v1.8.1.

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
     "last_heartbeat_age_sec": 14.2,
     "paused": false,
     "paused_by": null,
     "cycle_count": 1,
     "trade_count": 0,
     "equity": 10000,
     "runner_restart_count": 0
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


## Runner-Selbstheilung und Netzwerkgrenzen

Das Relay überwacht im Signal-Center-Thread ausschließlich die Freshness erfolgreich abgeschlossener Runner-Zyklen. Das Feld `running` ist nur sichtbar und kein Stall-Kriterium. Vor dem ersten Zyklus bleibt die bestehende Startup-Gnadenfrist von 120 Sekunden aktiv.

Ablauf eines Stall-Ereignisses:

1. Fehlt nach der Startup-Gnadenfrist ein Zyklus-Timestamp oder überschreitet `last_cycle_age_sec` die Schwelle, markiert das Relay genau ein Stall-Ereignis.
2. Vor dem Stop schreibt `RUNNER_STALL_STACK_DUMP` einmalig einen `faulthandler`-Dump aller Relay-Threads nach stderr für die Container-Logs.
3. Der Manager sendet `terminate()`, wartet höchstens fünf Sekunden, nutzt nötigenfalls `kill()` und wartet nochmals begrenzt.
4. Der Ersatzprozess startet ausschließlich über `_start_runner_if_enabled()` und lädt Trading-State, Positionen und Equity wieder über den bestehenden Relay-State.
5. Die P4-Meldung enthält `Selbstheilung ausgelöst`. Erst ein höherer erfolgreicher `cycle_count` des Ersatzprozesses erzeugt P3 `Selbstheilung erfolgreich — Runner wieder aktiv`.

Die Standardschwelle lautet:

```text
max(3 * AURA_BOT_SCAN_SEC, 180.0)
```

Ein positiver und endlicher `AURA_RUNNER_STALE_SEC`-Wert überschreibt die Formel. Ungültige, nicht-endliche oder nicht-positive Werte fallen ohne Startfehler auf die berechnete Schwelle zurück. Alle ausgehenden Relay- und Runner-Netzwerkaufrufe sind auf 10 Sekunden begrenzt; ein Timeout beendet nur den aktuellen Scan sauber, gibt den Scan-Guard frei und lässt den nächsten Turn zu.

### Betriebs-ENV

| Variable | Standard | Bedeutung |
|---|---:|---|
| `AURA_BOT_MODE` | aus | `server` aktiviert den Headless Paper-Autobot. |
| `AURA_BOT_SCAN_SEC` | `60` | Scanintervall; bestimmt auch die berechnete Stall-Schwelle. |
| `AURA_RUNNER_STALE_SEC` | berechnet | Optionaler positiver, endlicher Override der Stall-Schwelle. |
| `AURA_BOT_EQUITY` | `10000` | Start- und Digest-Fallback-Equity, falls der kanonische Server-State ungültig ist. |
| `AURA_NTFY_ERRORS` | `1` | Aktiviert P4-Selbstheilungs- und P3-Recovery-Meldungen über den bestehenden Relay-Pfad. |
| `AURA_NTFY_DIGEST` | `1` | Aktiviert den Tages-Digest inklusive Selbstheilungen der letzten 24 Stunden. |

---

## 🔄 Persistenz-Mechanismus (Release-fester Receiver)

### Das Problem
Der automatische GitHub Deploy-Receiver baut bei jedem neuen Release (`symbiose.zip`) den Docker-Container neu. Ein einmaliges `docker run -e AURA_BOT_MODE=server` ginge beim nächsten Release verloren.

### Die Lösung
Die Konfiguration liegt in `/var/lib/aura/aura_bot.env` auf dem persistenten Volume `aura-state`. Der Receiver (`scripts/ops/aura_webhook_receiver.reference.py`) wendet diese Datei beim Container-Bootstrap sowie bei jedem Container-Recreate über den nativen Docker-Parameter `--env-file /var/lib/aura/aura_bot.env` an (sofern vorhanden). Der Receiver liest oder parst die Datei nicht selbst, sondern übergibt den Pfad direkt an `docker run`.

#### Receiver-Referenz-Muster (`scripts/ops/aura_webhook_receiver.reference.py`):
```python
def resolve_bot_env_file() -> Path | None:
    """Locate the persistent bot env file on host if present."""
    custom_path = os.environ.get("AURA_BOT_ENV_FILE", "/var/lib/aura/aura_bot.env")
    for candidate_str in (custom_path, "/var/lib/docker/volumes/aura-state/_data/aura_bot.env"):
        try:
            candidate = Path(candidate_str)
            if candidate.is_file():
                return candidate
        except (PermissionError, OSError):
            continue
    return None


def bootstrap_arguments(image: str) -> list[str]:
    """Build canonical docker run arguments for fresh installation (no prior container)."""
    args = [
        "docker", "run", "-d",
        "--name", CONTAINER_NAME,
        "--restart", "unless-stopped",
        "--read-only",
        "--security-opt", "no-new-privileges:true",
        "--cap-drop", "ALL",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "-p", os.environ.get("AURA_PORT_BINDING", "127.0.0.1:8787:8787"),
        "-v", f"{os.environ.get('AURA_STATE_VOLUME', 'aura-state')}:/var/lib/aura",
        "-e", "SYM_PORT=8787",
        "-e", "SYM_HOST=0.0.0.0",
        "-e", f"AURA_ALLOWED_HOSTS={os.environ.get('AURA_ALLOWED_HOSTS', '127.0.0.1')}",
        "-e", "AURA_STATE_DIR=/var/lib/aura",
        "-e", "AURA_NTFY_BTC=1",
        "-e", "AURA_NTFY_BTC_COOLDOWN_MIN=30",
        "-e", "AURA_NTFY_DIGEST=1",
        "-e", "AURA_NTFY_DIGEST_UTC=7",
        "-e", "AURA_NTFY_ERRORS=1",
    ]
    
    ntfy_url = os.environ.get("AURA_NTFY_URL", "").strip()
    if ntfy_url:
        args.extend(["-e", f"AURA_NTFY_URL={ntfy_url}"])

    bot_mode = os.environ.get("AURA_BOT_MODE", "").strip()
    if bot_mode:
        args.extend(["-e", f"AURA_BOT_MODE={bot_mode}"])

    bot_env = resolve_bot_env_file()
    if bot_env is not None:
        args.extend(["--env-file", str(bot_env)])

    args.append(image)
    return args


def recreate_arguments(config: dict[str, Any], image: str) -> list[str]:
    """Build docker run arguments from the existing container configuration."""
    host_config = config.get("HostConfig") or {}
    args = ["docker", "run", "-d", "--name", CONTAINER_NAME]

    restart_name = ((host_config.get("RestartPolicy") or {}).get("Name") or "unless-stopped")
    args.extend(["--restart", restart_name])

    if host_config.get("ReadonlyRootfs"):
        args.append("--read-only")

    for sec_opt in host_config.get("SecurityOpt") or []:
        args.extend(["--security-opt", sec_opt])

    for cap in host_config.get("CapDrop") or []:
        args.extend(["--cap-drop", cap])

    for tmpfs_path, tmpfs_opts in (host_config.get("Tmpfs") or {}).items():
        opt_str = f":{tmpfs_opts}" if tmpfs_opts else ""
        args.extend(["--tmpfs", f"{tmpfs_path}{opt_str}"])

    for env_value in (config.get("Config") or {}).get("Env") or []:
        args.extend(["-e", env_value])

    bot_env = resolve_bot_env_file()
    if bot_env is not None:
        args.extend(["--env-file", str(bot_env)])

    for mount in config.get("Mounts") or []:
        mount_type = mount.get("Type")
        source = mount.get("Name") if mount_type == "volume" else mount.get("Source")
        destination = mount.get("Destination")
        if mount_type in {"volume", "bind"} and source and destination:
            value = f"{source}:{destination}"
            if not mount.get("RW", True):
                value += ":ro"
            args.extend(["-v", value])

    for container_port, bindings in (host_config.get("PortBindings") or {}).items():
        for binding in bindings or []:
            host_port = binding.get("HostPort")
            if not host_port:
                continue
            host_ip = binding.get("HostIp") or ""
            published = f"{host_ip}:{host_port}:{container_port}" if host_ip else f"{host_port}:{container_port}"
            args.extend(["-p", published])

    args.append(image)
    return args
```

---

## 👥 Fremdinstallation / Installation für Dritte

Möchte ein Freund oder Teampartner eine eigene AURA-Instanz mit 24/7 Server-Bot betreiben:

1. **Eigener Server / VM:** Eigene Docker-VM oder Proxmox-Node.
2. **Eigenes Topic:** Ein völlig eigenständiges, geheimes ntfy-Topic wählen (niemals Topics teilen!).
3. **Eigener Receiver:** Den Webhook-Receiver auf seiner VM mit `scripts/ops/aura_webhook_receiver.reference.py` einrichten (siehe [DOCKER_GUIDE.md](DOCKER_GUIDE.md#--frischinstallation-receiver-einrichten-automatischer-github-deploy-receiver)).
4. **Gleiche 3 Aktivierungsschritte:** `enable_server_bot.sh` mit seinem Topic ausführen.

---

## 🎛️ Bedienung & Betriebsmodi

### Betriebsmodi

1. **Tab geschlossen (Standard 24/7-Betrieb):**
   - Der Server-Runner führt jede Minute autonom den Scan durch, überwacht Take-Profits / Stop-Losses und sendet Signale via ntfy.
   - `/ready` zeigt `paused: false` und `paused_by: null`.
2. **Tab als Fernglas (Beobachtung):**
   - Das Dashboard ist geöffnet, der lokale Browser-Autobot ist inaktiv/pausiert.
   - Das blaue Banner `🌐 SERVER-BOT AKTIV (24/7)` signalisiert, dass der Server-Bot die Positionen managed.
   - Der Server-Runner läuft unterbrechungsfrei weiter (`paused: false`).
3. **Tab mit aktivem Browser-Autobot (Lokaler Test/Handel):**
   - Wird der Browser-Autobot im Dashboard manuell gestartet (`enabled: true`, `mode != 'server'`), greift der v1.7.0 Anti-Doppel-Handel-Schutz.
   - Der Server-Runner pausiert seinen Scan-Zyklus („Browser bot is active — server bot paused this cycle").
   - `/ready` meldet `paused: true` und `paused_by: "browser"`.
   - **Wichtig:** Browser-Paper-Positionen leben im `localStorage` des jeweiligen Browsers und frieren beim Schließen des Browser-Tabs ein (by design). Nur der Server-Bot führt Trades 24/7 persistent im Relay/Container weiter.

### Watchdog-Pause-Semantik & `/ready` Status

- `paused`: `true` | `false` — Zeigt an, ob der Server-Runner wegen aktivem Browser-Bot pausiert ist.
- `paused_by`: `"browser"` | `null` — Ursache der Pause.
- `last_cycle_age_sec`: Alter des letzten vollständigen Handelszyklus (bleibt während Pause auf dem letzten Scan-Zeitpunkt stehen).
- `last_heartbeat_age_sec`: Alter des letzten Heartbeats des Runners (wird auch bei Pausen-Zyklen minütlich aktualisiert).
- **Watchdog-Regel:** Solange der Runner im Pausen-Zustand seinen Heartbeat aktualisiert, gilt er als lebendig. Der Watchdog löst keinen Stall-Alarm (P4) und keinen unnötigen Selbstheilungs-Neustart aus. Stirbt der Runner-Prozess jedoch auch während einer Pause (Heartbeat älter als Stall-Schwelle), greift die Selbstheilung weiterhin zuverlässig.

### Update-Kadenz

- **5 Sekunden:** Live-Preise für manuelle und Bot-Trade-Karten (`refreshTradePrices` aktualisiert PnL, R-Multiple, Mark-Preise).
- **60 Sekunden:** Vollständiger Signal- und Positions-Scan des Server-Runners (`AURA_BOT_SCAN_SEC=60`).
- **Chart:** Interaktives TradingView-Widget wie gewohnt.

---

## 🛡️ Sicherheit & Guardrails

- **Paper-Only:** Der Autobot führt ausschließlich simulierte Paper-Trades aus. Es werden zu keinem Zeitpunkt echte API-Orders an Börsen geschickt.
- **Fail-Close:** Bei Marktdaten-Ausfällen oder unvollständigen Kerzen bricht der Zyklus ab — es wird kein Trade ohne nachgewiesene positive OOS-Evidenz eröffnet.
- **Restart-Sicherheit:** Alle Trades, Once-Flags und Cooldowns überleben Container-Restarts unter `/var/lib/aura`.
