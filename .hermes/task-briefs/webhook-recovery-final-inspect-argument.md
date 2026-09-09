# AURA Recovery — finalem Docker-Inspect fehlt Containername

Workspace: `/mnt/c/Users/Ivo/Desktop/AURA_Webhook_Setup/`

## Produktionsbeleg

Zweiter Recovery-Lauf war funktional bis zum finalen Bericht erfolgreich:

- Container korrekt als fehlend erkannt.
- Image `aura-terminal:latest` vorhanden.
- Volume `aura-state` vorhanden.
- Container mit bekanntem Vertrag gestartet, ID `38bd975...`.
- Health-Poll erkannte erst `running starting`, danach wurde `/serving` erfolgreich; extern bestätigt Parent: `http://192.168.8.115:8787/serving` liefert HTTP 200 v1.0.6.
- Danach scheiterte ausschließlich finale Ausgabe mit:
  `docker: 'docker container inspect' requires at least 1 argument`

Root Cause: In `repair_webhook_deployment_v107.sh` finaler Befehl Zeile 124 enthält Format, aber kein abschließendes `aura-terminal`-Argument.

## Auftrag

Striktes TDD. Ändere nur:

- `repair_webhook_deployment_v107.sh`
- `test_repair_webhook_deployment_static.py`

1. Regressionstest zuerst rot: finaler Status-Inspect muss nach geschlossenem Format-String exakt das Containerargument `aura-terminal` enthalten.
2. Minimaler Fix: `aura-terminal` an finalen `docker container inspect --format '...'`-Befehl anhängen.
3. Keine anderen Verhaltensänderungen.
4. Keine Remote-/Docker-/VM-Aktionen, keine Secrets, keine Git-Side-Effects.

## Verifikation

- alle Desktop-Tests grün
- `bash -n`
- `py_compile`
- weiterhin kein generisches `docker inspect`, kein `|| true`, kein `2>/dev/null`
- Bericht RED/GREEN.
