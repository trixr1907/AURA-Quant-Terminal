# AURA v1.7.1 — Receiver-Bootstrap, Docs-Wahrheit & P4-Startup-Grace

**Release-Typ:** PATCH (`1.7.1`, Bugfix)  
**Datum:** 14. September 2026  
**Status:** Canonical Release · Production Ready

---

## 🎯 Zusammenfassung (Runde 29)

AURA v1.7.1 behebt drei in realen Clean-Slate-Inbetriebnahmen aufgedeckte Schwachstellen in Receiver, Dokumentation und Alarmierung:

1. **Receiver-Bootstrap-Pfad (Frischinstallations-Lücke):**
   Der Deploy-Receiver (`scripts/ops/aura_webhook_receiver.reference.py`) scheiterte bei Clean-Slate-Installationen ohne Vorcontainer am `docker inspect`-Befehl. Er verfügt nun über einen kanonischen Bootstrap-Pfad, der bei nicht vorhandenem Container diesen aus der Compose-Spezifikation (`--restart unless-stopped`, `--read-only`, `--security-opt no-new-privileges:true`, `--cap-drop ALL`, tmpfs `/tmp`, Port 8787, Volume `aura-state`, `--env-file /var/lib/aura/aura_bot.env`) instanziiert.

2. **Docs-Wahrheit (Server-Bot Persistenz):**
   Korrektur von `SERVER_BOT_GUIDE.md`: Beseitigung der phantomartigen `read_persistent_bot_env()`-Referenz. Die Dokumentation beschreibt nun exakt das echte Verhalten der nativen Docker `--env-file`-Übergabe beim Container-Start/Recycle.

3. **P4-Startup-Grace (Runner-Dead Fehlalarm-Schutz):**
   Die Runner-Dead-Erkennung im Relay (`runner_dead_transition`) löst bei neu gestarteten Containern erst dann Alarm aus, wenn der Runner mindestens einen vollständigen Zyklus abgeschlossen hat (`cycle_count >= 1`) bzw. die 120s-Gnadenfrist abgelaufen ist.

---

## 📦 Umgesetzte Fixes (A–C)

### Befund 1 / Block A — Receiver-Bootstrap-Referenz & Deployment-Guide
- Neue Referenz-Implementierung: `scripts/ops/aura_webhook_receiver.reference.py`.
- `current_container_config()` fängt fehlende Container sauber ab (`check=False`, Rückgabe `None`).
- `bootstrap_arguments()` erzeugt vollständigen `docker run`-Befehl nach Compose-Spezifikation inklusive `--env-file` (falls `/var/lib/aura/aura_bot.env` vorhanden).
- `_ntfy_notify()` sendet Deploy-Erfolgs- (P3) und Fehler-Pushes (P4).
- `docs/deployment/DOCKER_GUIDE.md` und `docs/deployment/SERVER_BOT_GUIDE.md` um vollständige Anleitung für schlüsselfertige Fremd- und Frischinstallationen (systemd-Unit, Environment, GitHub-Webhook) erweitert.

### Befund 2 / Block B — Docs-Wahrheit
- `docs/deployment/SERVER_BOT_GUIDE.md` vollständig bereinigt und an den echten Code angeglichen.
- Transparente Darstellung: Docker wendet `--env-file /var/lib/aura/aura_bot.env` nativ an; der Receiver liest keine Variablen selbst via Python-Parsing ein.

### Befund 3 / Block C — P4-Startup-Grace im Relay
- `bitget_relay.py`: `RELAY_START_TIME` und `runner_dead_transition` erweitert um `startup_grace_sec` (120s) und `cycle_count < 1`-Prüfung.
- Beseitigung von Fehlalarmen während des legitimen Boot- und ersten Scan-Fensters.
- `tests/test_pf67_server_mode.py` erweitert um 3 gezielte Testfälle (Startup-Grace, Sofort-Alarm bei Tod nach Zyklus 1, Timeout nach Ablauf der Gnadenfrist).

---

## 🧪 Test-Zahlen & Baseline
- **pytest:** 294 passed, 57 subtests passed (+9 Tests gegenüber v1.7.0 Baseline 285/57)
- **Node JS Suite:** 83/83 Testdateien bestanden
- **Symbiose_Dashboard.html innerHTML Count:** 66 unverändert
- **Trials-Ledger:** EXP-032 unverändert
- **Verdict:** SOFTWARE_GO / MODEL_NO_EVIDENCE (real)
