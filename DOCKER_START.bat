@echo off
setlocal
title AURA Quant Terminal - Docker Starter

echo =======================================================
echo   AURA QUANT TERMINAL - DOCKER ONE-CLICK LAUNCHER
echo =======================================================
echo.

where docker >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [FEHLER] Docker Desktop ist nicht installiert oder nicht im PATH gefunden!
    echo Bitte installiere Docker Desktop: https://www.docker.com/products/docker-desktop/
    echo.
    pause
    exit /b 1
)

echo [1/3] Pruefe Docker Daemon Status...
docker info >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [FEHLER] Docker Daemon laeuft nicht!
    echo Bitte starte Docker Desktop und fuehre dieses Skript erneut aus.
    echo.
    pause
    exit /b 1
)

echo [2/3] Baue und starte AURA Terminal Docker Container...
docker build -t aura-quant-terminal:latest .
if %ERRORLEVEL% NEQ 0 (
    echo [FEHLER] Docker Build fehlgeschlagen!
    pause
    exit /b 1
)

:: Beende eventuell alte Container-Instanzen
docker stop aura-terminal >nul 2>nul
docker rm aura-terminal >nul 2>nul

echo [3/3] Starte Container im Hintergrund auf Port 8787...
docker run -d --name aura-terminal --restart unless-stopped -p 8787:8787 -e AURA_ALLOWED_HOSTS=127.0.0.1 -e AURA_STATE_DIR=/var/lib/aura -v aura-state:/var/lib/aura aura-quant-terminal:latest
if %ERRORLEVEL% NEQ 0 (
    echo [FEHLER] Docker Run fehlgeschlagen!
    pause
    exit /b 1
)

echo.
echo =======================================================
echo   ERFOLGREICH GESTARTET!
echo   Web-Dashboard: http://localhost:8787/
echo   Tutorial:      http://localhost:8787/tutorial
echo =======================================================
echo.
echo Oeffne Browser...
start http://localhost:8787/

echo.
echo Der Container laeuft nun dauerhaft im Hintergrund (auch fuer Homelab/Server geeignet).
echo Um ihn zu stoppen: fuehre 'DOCKER_STOP.bat' aus oder 'docker stop aura-terminal'.
echo.
pause
