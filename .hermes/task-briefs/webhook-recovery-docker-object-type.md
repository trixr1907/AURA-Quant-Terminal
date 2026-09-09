# AURA Recovery — Docker-Objekttyp eindeutig prüfen

Workspace: `/mnt/c/Users/Ivo/Desktop/AURA_Webhook_Setup/`

## Exakte neue Produktionsdiagnose

Recovery-Ausgabe:

- `docker inspect --format '{{.Id}}' aura-terminal` lieferte `sha256:1baa49...`.
- Direkt danach scheiterte `docker inspect --format '{{.State.Status}} ...' aura-terminal` mit `map has no entry for key "State"`.
- Frühere Diagnose zeigte bei `docker ps -a --filter name=aura-terminal` keinen Container, aber Image `aura-terminal:latest` existiert.

Root Cause: Generisches `docker inspect aura-terminal` kann bei fehlendem Container das gleichnamige Image `aura-terminal:latest` auflösen. Das Image hat `.Id`, aber keinen `.State`. Recovery interpretierte deshalb das Image irrtümlich als vorhandenen Container.

Nicht Proxmox, SSH, Passwort oder Auth. Docker-Objekttyp-Ambiguität im Skript.

## Auftrag

Striktes TDD. Ändere ausschließlich:

- `aura_webhook_receiver.py`
- `repair_webhook_deployment_v107.sh`
- `test_aura_webhook_receiver.py`
- `test_repair_webhook_deployment_static.py`

### Fix

1. Alle Container-Inspektionen müssen explizit `docker container inspect` verwenden:
   - Receiver `current_container_config()`
   - Recovery Existenzcheck
   - Recovery Healthpoll
   - finale Recovery-Statusausgabe
2. Image-Inspektion bleibt explizit `docker image inspect`.
3. Volume-Inspektion bleibt explizit `docker volume inspect`.
4. Wenn kein Container existiert, muss Recovery nun korrekt in den Restore-Zweig gehen, vorhandenes Image und Volume prüfen und `aura-terminal` starten.
5. Keine Änderung am State-Volume; keine State-Inhalte lesen/ausgeben.
6. Keine Fehlerunterdrückung `|| true` oder `2>/dev/null`.
7. Keine echten Docker-/VM-/Remote-Aktionen; keine Secrets; keine Git-Side-Effects.

### Tests

RED zuerst:

- Statischer Test verwirft jedes generische `docker inspect` im Recovery-Skript.
- Erwartet explizites `docker container inspect` an Existenz-, Health- und Finalstellen.
- Receiver-Test erwartet `current_container_config()` ruft exakt `docker container inspect aura-terminal` auf und akzeptiert realistische JSON-Liste.
- Bestehende 8 Tests bleiben grün.

## Verifikation

- `python3 -m pytest -q test_aura_webhook_receiver.py test_repair_webhook_deployment_static.py`
- `python3 -m py_compile ...`
- `bash -n repair_webhook_deployment_v107.sh`
- kein generisches `docker inspect`, kein `|| true`, kein `2>/dev/null`
- Bericht mit RED/GREEN.
