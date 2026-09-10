@echo off
setlocal
cd /d "%~dp0"
title AURA v1.1.0 - Smart Start
color 0A

echo ========================================================
echo        AURA v1.1.0 - Smart Start
echo ========================================================
echo Pruefe und installiere fehlende Abhaengigkeiten sicher ...
echo.

set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%POWERSHELL%" (
    echo [FEHLER] Windows PowerShell wurde unter dem Systempfad nicht gefunden:
    echo %POWERSHELL%
    echo Bitte die Windows-Systemdateien mit "sfc /scannow" pruefen.
    pause
    exit /b 9009
)

"%POWERSHELL%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo AURA konnte nicht vollstaendig gestartet werden. Exit-Code: %RC%
    pause
)
exit /b %RC%
