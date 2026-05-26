@echo off
title JARVIS BRAINIAC - Deploy + Launch
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0DEPLOY_BRAINIAC.ps1"
echo.
pause
