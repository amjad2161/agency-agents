@echo off
title Generate AGENT_INDEX.md
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0GENERATE_AGENT_INDEX.ps1"
echo.
echo Done.
pause
