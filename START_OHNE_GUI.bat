@echo off
setlocal
cd /d "%~dp0"
title AURA v1.0.4 - Zuverlaessiger CLI-Modus
set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%POWERSHELL%" (
    echo [FEHLER] Windows PowerShell wurde unter dem Systempfad nicht gefunden:
    echo %POWERSHELL%
    pause
    exit /b 9009
)
"%POWERSHELL%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap.ps1" -NoGui
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" pause
exit /b %RC%
