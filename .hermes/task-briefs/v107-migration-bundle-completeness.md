# AURA Sync-Migration — Bundle-Vollständigkeit (fehlende BAT remote)

Workspace ausschließlich: `/mnt/c/Users/Ivo/Desktop/AURA_Webhook_Setup/`

## Befund

Erster Live-Lauf brach korrekt fail-closed ab (kein Container angefasst, Altcontainer unverändert):

```
FileNotFoundError: '/root/aura_webhook/ENABLE_CROSS_DEVICE_SYNC_V107.bat'
  test_enable_cross_device_sync_static.py:19 setUpClass -> BAT.read_text
```

Ursache: `test_enable_cross_device_sync_static.py` liest in `setUpClass` die BAT aus `Path(__file__).parent`. Die Migrations-BAT überträgt per `scp` nur 4 Dateien, nicht sich selbst. Remote fehlt damit die BAT und der Selbsttest-Gate schlägt fehl.

## Auftrag

Striktes TDD, minimal. Keine echten Remote-/Docker-/VM-/SSH-/Git-Aktionen.

Ändere nur:

- `ENABLE_CROSS_DEVICE_SYNC_V107.bat`
- `enable_cross_device_sync_v107.sh`
- `test_enable_cross_device_sync_static.py`

### 1. Bundle vollständig übertragen

Die Migrations-BAT muss zusätzlich `ENABLE_CROSS_DEVICE_SYNC_V107.bat` selbst per `scp` übertragen, damit alle 5 Bundle-Dateien remote vorhanden sind. Vorhandene Existenz-Checks am BAT-Anfang entsprechend um die BAT selbst ergänzen (oder klar abdecken).

### 2. Klarer Pre-Flight-Check im Shell-Skript

In `enable_cross_device_sync_v107.sh` vor dem lokalen Test-Gate (Schritt [2/10]) explizit prüfen, dass `ENABLE_CROSS_DEVICE_SYNC_V107.bat` im `BUNDLE_DIR` existiert. Bei Fehlen eindeutige, sofort verständliche Fehlermeldung auf stderr und `exit` mit definiertem Nichtnullcode — noch vor `python3 -m unittest`. Kein `|| true`, kein `2>/dev/null`.

Der bestehende Test-Gate-Block bleibt unverändert und muss weiterhin alle Tests ausführen.

### 3. Regressionstest

Mindestens:

- Statisch belegen, dass die BAT sich selbst in den `scp`-Aufruf aufnimmt (Bündelvertrag = BAT + SH + receiver.py + beide Tests).
- Statisch belegen, dass das SH vor dem unittest-Gate einen expliziten BAT-Existenz-Check mit klarer Fehlermeldung enthält und dieser vor dem ersten `python3 -m unittest` steht.
- Bestehende Tests bleiben grün.

## Verifikation

- vollständige Desktop-Pytest-Suite
- `python3 -m py_compile *.py`
- `bash -n enable_cross_device_sync_v107.sh`
- Bericht mit RED/GREEN und geänderten Dateien
