# AURA Sync-Migration — Fehlerpfade wirklich fail-closed

Workspace: `/mnt/c/Users/Ivo/Desktop/AURA_Webhook_Setup/`

## Parent-Review: zwei blockierende Bash-Fehler

### 1. Manuelles `on_error` verliert Exitcode

Aktuell:

```bash
if ! verify_live_contract aura-terminal; then
    echo "..."
    on_error
fi
```

`on_error()` liest `$?`. Nach dem erfolgreichen `echo` ist das 0. Ein erfolgreiches Rollback kann dadurch die fehlgeschlagene Migration mit Exit 0 beenden.

### 2. Funktionsfehler können in `if verify_live_contract` verschluckt werden

Bash deaktiviert `errexit` in Funktionen, die als Bedingung eines `if`/`!` aufgerufen werden. Aktuell besteht `verify_live_contract()` aus mehreren nackten Befehlen. Scheitert z. B. Containervertrag oder JSON-Validierung, kann ein späteres Cleanup erfolgreich sein und die Funktion 0 zurückgeben.

Außerdem prüft `rollback_after_rename()` aktuell den vollständigen migrierten Sync-Vertrag. Der alte Rollback-Container hat absichtlich noch nicht die Sync-Env und würde daher trotz gesundem v1.0.7-Service als kaputt gelten.

## Auftrag

Striktes TDD. Ändere ausschließlich:

- `enable_cross_device_sync_v107.sh`
- `test_enable_cross_device_sync_static.py`
- optional neue lokale Testdatei für Bash-Verhalten

Keine echten Remote-/Docker-/VM-Aktionen. Keine Secrets. Keine Git-Side-Effects.

### Produktionsfix

1. Trenne Verifikation:
   - `verify_basic_v107(name)`: Containervertrag (running, healthy, Port, RW-Volume) + `/serving` exakt v1.0.7.
   - `verify_live_sync_contract(name)`: Basic + exakt normalisierte Sync-Env + LAN-Host `/api/state` 200/valide JSON.
2. Jede mehrstufige Funktion muss Fehler explizit propagieren, z. B. `command || return 1`; nicht auf `set -e` innerhalb einer `if`-Bedingung verlassen.
3. `guest_api_state_lan_ok()`:
   - JSON-Validierungsfehler müssen nach bestmöglichem Temp-Cleanup mit Return 1 enden.
   - HTTP != 200 ebenfalls Cleanup + Return 1.
   - erfolgreicher Cleanup darf früheren Fehler nie in Erfolg verwandeln.
   - State-Inhalt nie ausgeben.
4. Kandidat/Poll/Endprüfung verwendet `verify_live_sync_contract`.
5. Rollbackprüfung verwendet nur `verify_basic_v107`, weil alter Container erwartbar die neue Sync-Env noch nicht hat.
6. Fehler nach 90 Sekunden löst Rollback mit einem expliziten Nichtnullcode aus, z. B. `on_error 1` oder separater Handler mit Parameter. Trap-Aufruf muss echten `$?` weiterhin übernehmen.
7. Erfolg darf erst nach vollständig bestandenem Sync-Vertrag Rollback-Container entfernen.
8. Kein `|| true`, kein `2>/dev/null`, kein generisches `docker inspect`, keine State-/Volume-Löschung.

### RED-Tests

Mindestens statisch/dynamisch beweisen:

- `verify_live_sync_contract` nutzt explizite `|| return 1`-Verkettung für Basic, Env und API.
- `verify_basic_v107` propagiert Container- und Serving-Fehler.
- Rollback ruft nur Basic auf, nicht Sync/API.
- Timeout-Pfad übergibt explizit Exit 1 an Fehlerhandler; kein abhängig von vorherigem `echo` gewordenes `$?`.
- API-JSON-Validierungsfehler bleibt Return 1 trotz Cleanup.
- Bestehende Vertrags-/Sicherheitschecks bleiben grün.

## Verifikation

- alle Desktop-Tests
- py_compile
- bash -n
- weiterhin keine kritische Fehlerunterdrückung/destruktive State-Aktion
- Bericht mit RED/GREEN.
