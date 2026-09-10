@echo off
setlocal EnableDelayedExpansion
title AURA Quant Terminal - Docker Starter

echo =======================================================
echo   AURA QUANT TERMINAL - DOCKER ONE-CLICK LAUNCHER
echo =======================================================
echo.

if "%AURA_PORT%"=="" set "AURA_PORT=8787"
if "%AURA_ALLOWED_HOSTS%"=="" set "AURA_ALLOWED_HOSTS=127.0.0.1"

echo LAN-Konfiguration:
echo   AURA_ALLOWED_HOSTS=%AURA_ALLOWED_HOSTS%
echo   (Fuer LAN-Zugriff AURA_ALLOWED_HOSTS mit Hostnamen/IPs setzen;
echo    Loopback 127.0.0.1 und localhost bleiben immer erlaubt).
echo.

where docker >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [FEHLER] Docker Desktop ist nicht installiert oder nicht im PATH gefunden!
    echo Bitte installiere Docker Desktop: https://www.docker.com/products/docker-desktop/
    echo.
    pause
    exit /b 1
)

echo [1/4] Pruefe Docker Daemon Status...
docker info >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [FEHLER] Docker Daemon laeuft nicht!
    echo Bitte starte Docker Desktop und fuehre dieses Skript erneut aus.
    echo.
    pause
    exit /b 1
)

echo [2/4] Baue AURA Terminal Docker Image...
docker build -t aura-quant-terminal:latest .
if %ERRORLEVEL% NEQ 0 (
    echo [FEHLER] Docker Build fehlgeschlagen!
    pause
    exit /b 1
)

:: Beende eventuell alte Container-Instanzen
docker stop aura-terminal >nul 2>nul
docker rm aura-terminal >nul 2>nul

echo [3/4] Starte Container im Hintergrund auf Port %AURA_PORT%...
docker run -d --name aura-terminal --restart unless-stopped -p %AURA_PORT%:8787 -e "AURA_ALLOWED_HOSTS=%AURA_ALLOWED_HOSTS%" -e AURA_STATE_DIR=/var/lib/aura -v aura-state:/var/lib/aura aura-quant-terminal:latest
if %ERRORLEVEL% NEQ 0 (
    echo [FEHLER] Docker Run fehlgeschlagen!
    pause
    exit /b 1
)

echo [4/4] Verifiziere Bereitschaft und Endpunkte (Bounded Readiness Poll)...
set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%POWERSHELL%" set "POWERSHELL=powershell.exe"

"%POWERSHELL%" -NoLogo -NoProfile -Command "$port = '%AURA_PORT%'; $deadline = (Get-Date).AddSeconds(45); $ready = $false; while ((Get-Date) -lt $deadline) { $running = (docker inspect aura-terminal --format '{{.State.Running}}' 2>$null); if ($running -ne 'true') { Start-Sleep -Milliseconds 1000; continue }; try { $s = Invoke-RestMethod -Uri \"http://127.0.0.1:$port/serving\" -TimeoutSec 3 -ErrorAction Stop; if (-not $s.ok) { Start-Sleep -Milliseconds 1000; continue }; $b = '{\"path\":\"/api/v2/mix/market/ticker\",\"params\":{\"symbol\":\"BTCUSDT\",\"productType\":\"USDT-FUTURES\"}}'; $p = Invoke-RestMethod -Uri \"http://127.0.0.1:$port/api/public\" -Method Post -ContentType 'application/json' -Body $b -TimeoutSec 5 -ErrorAction Stop; if (-not $p) { Start-Sleep -Milliseconds 1000; continue }; $r = Invoke-RestMethod -Uri \"http://127.0.0.1:$port/ready\" -TimeoutSec 3 -ErrorAction Stop; if (-not $r.ok) { Start-Sleep -Milliseconds 1000; continue }; $st = Invoke-RestMethod -Uri \"http://127.0.0.1:$port/api/state\" -Headers @{Host=\"127.0.0.1:$port\"} -TimeoutSec 3 -ErrorAction Stop; if (-not $st.ok) { Start-Sleep -Milliseconds 1000; continue }; $ready = $true; break } catch { Start-Sleep -Milliseconds 1000 } }; if (-not $ready) { exit 1 } else { exit 0 }"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [FEHLER] Bereitschafts-Pruefung nach 45s fehlgeschlagen!
    echo Letzte Container-Logs von aura-terminal:
    docker logs --tail 50 aura-terminal
    echo.
    pause
    exit /b 1
)

echo.
echo =======================================================
echo   ERFOLGREICH GESTARTET!
echo   Web-Dashboard:  http://localhost:%AURA_PORT%/
echo   Tutorial:       http://localhost:%AURA_PORT%/tutorial
echo   Serving Status: http://localhost:%AURA_PORT%/serving
echo   Readiness:      http://localhost:%AURA_PORT%/ready
echo   Shared State:   http://localhost:%AURA_PORT%/api/state
echo =======================================================
echo.
echo Oeffne Browser...
start http://localhost:%AURA_PORT%/

echo.
echo Der Container laeuft nun dauerhaft im Hintergrund (auch fuer Homelab/Server geeignet).
echo Um ihn zu stoppen: fuehre 'DOCKER_STOP.bat' aus oder 'docker stop aura-terminal'.
echo.
pause
