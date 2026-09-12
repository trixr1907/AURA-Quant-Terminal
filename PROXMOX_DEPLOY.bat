@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title AURA Quant Terminal - Deep Proxmox ^& Homelab Auto-Deployer

echo ===================================================================
echo   AURA QUANT TERMINAL - DEEP PROXMOX ^& HOMELAB SCANNER
echo ===================================================================
echo.
echo Dieses Tool scannt dein gesamtes Proxmox VE System (Host, LXCs, VMs)
echo nach Docker-Umgebungen und waehlt das optimale Setup.
echo.

set /p REMOTE_HOST="Proxmox Server IP / Hostname (z.B. 192.168.178.50): "
if "%REMOTE_HOST%"=="" (
    echo [FEHLER] Keine IP/Hostname angegeben!
    pause
    exit /b 1
)

set /p REMOTE_USER="SSH User [Standard: root]: "
if "%REMOTE_USER%"=="" set REMOTE_USER=root

echo.
echo ===================================================================
echo   HINWEIS ZUR PASSWORT-EINGABE:
echo   OpenSSH verlangt das Passwort 1x fuer die Dateiuebertragung (SCP)
echo   und 1x fuer den interaktiven Scanner (SSH).
echo ===================================================================
echo.

echo [1/2] Uebertrage AURA Bundle als komprimiertes Paket nach %REMOTE_USER%@%REMOTE_HOST%...
echo Bitte gib jetzt das SSH-Passwort ein:
ssh %REMOTE_USER%@%REMOTE_HOST% "mkdir -p /root/aura_deploy"
if errorlevel 1 (
    echo [FEHLER] Das Zielverzeichnis auf Proxmox konnte nicht vorbereitet werden.
    pause
    exit /b 1
)

scp deep_infrastructure_scanner.sh smart_homelab_installer.sh proxmox_lxc_install.sh Dockerfile docker-compose.yml bitget_relay.py Symbiose_Dashboard.html SYMBIOSE_Tutorial.html VERSION %REMOTE_USER%@%REMOTE_HOST%:/root/aura_deploy/
if errorlevel 1 (
    echo [FEHLER] Die AURA-Dateien konnten nicht vollstaendig uebertragen werden.
    echo Starte diese BAT direkt aus dem entpackten AURA-Projektordner.
    pause
    exit /b 1
)

if exist "data" (
    scp -r data %REMOTE_USER%@%REMOTE_HOST%:/root/aura_deploy/
    if errorlevel 1 (
        echo [WARNUNG] Datendateien konnten nicht uebertragen werden.
    )
)

echo.
echo [2/2] Starte interaktiven Tiefenscan auf dem Proxmox-Server...
echo (Bitte ggf. noch 1x das SSH-Passwort eingeben)
echo.
ssh -t %REMOTE_USER%@%REMOTE_HOST% "cd /root/aura_deploy && chmod +x deep_infrastructure_scanner.sh smart_homelab_installer.sh proxmox_lxc_install.sh && bash deep_infrastructure_scanner.sh"
if errorlevel 1 (
    echo.
    echo [FEHLER] Der Proxmox-Scanner oder das Deployment ist fehlgeschlagen.
    pause
    exit /b 1
)

echo.
echo ===================================================================
echo   PROXMOX SCAN ^& DEPLOYMENT ABGESCHLOSSEN!
echo ===================================================================
echo.
pause
