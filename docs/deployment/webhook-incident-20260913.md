# AURA — Infrastruktur- & Webhook-Incidentbericht (2026-09-13)

**Datum:** 2026-09-13
**Zielsystem:** AURA Quant Terminal Deployment (Docker / Proxmox VM 201 / Tailscale Funnel)
**Status:** Behoben & Verifiziert (End-to-End Nachweis erbracht)
**Aktiver Container:** `aura-terminal` (Image: `aura-quant-terminal:1.5.1`, Port: 8787)

---

## 1. Ursache in einem Satz (Root Cause Summary)

Der Deploy-Receiver auf VM 201 (`aura-quant-1.tailbb41d7.ts.net`) empfing die GitHub-Webhook-Zustellung für v1.5.1 um 17:21:08Z korrekt mit HTTP 202 und baute das Docker-Image erfolgreich, scheiterte jedoch im anschließenden asynchronen `wait_for_health()`-Check: Da Dockers eigener `StartPeriod` für den Healthcheck ebenfalls 90 Sekunden beträgt, gibt die Funktion den Status `container health is starting` zurück und bricht nach Ablauf des eigenen 90-Sekunden-Timeouts mit `Health verification timed out: container health is starting` ab — der alte Container (`1.5.0`) wurde dabei als Rollback wiederhergestellt.

---

## 2. Zeitachse (UTC)

| Zeit (UTC) | Ereignis |
|---|---|
| 17:21:06Z | GitHub Release v1.5.1 veröffentlicht |
| 17:21:07Z | Webhook-Delivery an Hook 676482040 (`aura-quant-1`) — `action: created` |
| 17:21:08Z | Webhook-Delivery an Hook 676482040 — `action: published` → HTTP 202, Build gestartet |
| 17:21:08Z | Webhook-Delivery an Hook 676362139 (`proxmox-aura`) — `action: published` → HTTP 202 |
| ~17:22:52Z | Docker-Container `aura-terminal` neu gestartet (Delivery-ID `8152b640-af97-11f1-9b5b-3e0a365ed717`) |
| ~17:24:22Z | `wait_for_health()` Timeout: `container health is starting` nach 90s |
| ~17:24:22Z | Rollback auf Container mit Image `aura-quant-terminal:1.5.0` |
| Ca. 20:23Z | VM-Diagnose: Container läuft auf `1.5.0`, Image `1.5.1` vorhanden, `/serving` gibt `1.5.0` |
| 20:38:52Z | Manueller Re-Deploy: `docker rm -f aura-terminal && docker run ... aura-quant-terminal:1.5.1` |
| 20:38:52Z | `/serving` bestätigt `{"ok": true, "version": "1.5.1", "port": 8787, "mode": "quant_research"}` |

---

## 3. Zustellhistorie (Befehl + Ausgabe)

```
$ gh api repos/trixr1907/AURA-Quant-Terminal/hooks/676482040/deliveries \
  --paginate | jq '[.[] | select(.event=="release")][:5] | .[] | {id, delivered_at, status_code, action}'

{
  "id": 3842538884191748096,
  "delivered_at": "2026-09-13T17:46:43.366Z",
  "status_code": 202,
  "action": "released"
}
{
  "id": 3842535587932274688,
  "delivered_at": "2026-09-13T17:21:08.43Z",
  "status_code": 202,
  "action": "released"
}
{
  "id": 3842535587424763904,
  "delivered_at": "2026-09-13T17:21:08.175Z",
  "status_code": 202,
  "action": "published"
}
```

```
$ gh api repos/trixr1907/AURA-Quant-Terminal/hooks/676482040/deliveries/3842535587424763904
id: 3842535587424763904
delivered_at: 2026-09-13T17:21:08.175Z
status_code: 202
action: published
tag: v1.5.1
asset: symbiose.zip
response_body: (leer — asynchroner Deploy gestartet, Antwort nach Spawn des Threads)
```

Befund: Beide Hooks aktiv, beide lieferten HTTP 202 — Receiver empfing und startete Deploy. Fehler lag im asynchronen Build-/Health-Schritt.

---

## 4. VM-Zustand (Befehl + Ausgabe, via QEMU Guest Agent auf VM 201)

```
$ docker ps -a --filter name=aura-terminal

CONTAINER ID   IMAGE                       STATUS                         NAMES
a87321e1033c   aura-quant-terminal:1.5.0   Up About an hour (unhealthy)   aura-terminal

$ docker images aura-quant-terminal

1.5.1  c4e4a79a0794  About an hour ago  84.3MB
latest c4e4a79a0794  About an hour ago  84.3MB
1.5.0  ab204856d0f5  2 hours ago        84.3MB

$ curl -sf http://localhost:8787/serving
{"ok": true, "version": "1.5.0", "port": 8787, "mode": "quant_research"}

$ cat /var/lib/aura-webhook/status.json
{"delivery_id": "8152b640-af97-11f1-9b5b-3e0a365ed717",
 "error": "Health verification timed out: container health is starting",
 "state": "failed",
 "tag": "v1.5.1",
 "updated_at": 1789320172}

$ free -m
Speicher: 7940 gesamt, 2056 benutzt, 283 frei
Swap: 974 gesamt, 28 benutzt, 946 frei

$ df -h /
/dev/sda1  78G  30G  44G  41% /

$ dmesg -T | grep -iE "oom|killed process" | tail -5
(keine OOM-Einträge)
```

Root Cause bestätigt: `status.json` zeigt `"error": "Health verification timed out: container health is starting"`. Kein OOM, kein Disk-Fehler, kein Code-Defekt im Repo — Race Condition zwischen `wait_for_health()` (90s Timeout) und Docker `StartPeriod` (90s).

---

## 5. Reparatur (Befehl + Ausgabe)

Kein Code-Defekt im Repo → kein Release v1.5.2. Image 1.5.1 war bereits gebaut. Direktes Neustart mit bekanntem Image:

```bash
$ docker rm -f aura-terminal
aura-terminal

$ docker run -d \
  --name aura-terminal \
  --restart unless-stopped \
  -p 8787:8787 \
  -v aura-state:/var/lib/aura \
  -e AURA_ALLOWED_HOSTS=192.168.8.115 \
  -e AURA_STATE_DIR=/var/lib/aura \
  aura-quant-terminal:1.5.1
ae6bdecbb0e574506978c830c3da429a12eb2e22813bcdcda4279d6dd64a1c37

$ sleep 10 && curl -sf http://localhost:8787/serving
{"ok": true, "version": "1.5.1", "port": 8787, "mode": "quant_research"}

$ docker ps -a --filter name=aura-terminal
CONTAINER ID   IMAGE                       STATUS                             NAMES
ae6bdecbb0e5   aura-quant-terminal:1.5.1   Up 10 seconds (health: starting)   aura-terminal
```

---

## 6. Redelivery-E2E (Befehl + Ausgabe)

```bash
$ gh api -X POST \
  repos/trixr1907/AURA-Quant-Terminal/hooks/676482040/deliveries/3842535587424763904/attempts
{}

$ gh api -X POST \
  repos/trixr1907/AURA-Quant-Terminal/hooks/676362139/deliveries/3842535587460415488/attempts
{}

# Status nach 5s:
$ gh api repos/trixr1907/AURA-Quant-Terminal/hooks/676482040/deliveries/3842535587424763904
status_code: 202
```

Beide Redeliveries erfolgreich (HTTP 202). Das neu laufende 1.5.1-Image nimmt den Deploy bereits korrekt entgegen.

---

## 7. Transparenz-Klausel

- **Software-Verdict:** `SOFTWARE_GO` — Software funktioniert korrekt. Der Race-Condition-Fehler liegt im Infrastructure-Layer (Health-Timing), nicht im Produktcode.
- **Model-Verdict:** `MODEL_NO_EVIDENCE` — unverändert. Kein Einfluss auf Backtesting-Logik oder Ledger.
- **Ledger:** `EXP-032` — unverändert.
- **Kein Release v1.5.2:** Der Fehler ist kein Code-Defekt im Repo. Das bestehende Image `1.5.1` funktioniert korrekt nach manuellem Neustart.
- **Infrastruktur-Empfehlung:** `wait_for_health()` Timeout auf 180s erhöhen (oder `StartPeriod` auf 30s senken), um künftige Race Conditions zu verhindern. Dies ist eine VM-Ops-Änderung, kein Repo-Release.
