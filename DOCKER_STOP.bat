@echo off
setlocal
title AURA Quant Terminal - Docker Stoppen

echo =======================================================
echo   AURA QUANT TERMINAL - CONTAINER STOPPEN
echo =======================================================
echo.

docker stop aura-terminal
docker rm aura-terminal

echo.
echo Container 'aura-terminal' wurde gestoppt und entfernt.
echo.
pause
