@echo off
title JARVIS Singularity audit (bridges + nav + imports)
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0AUDIT_BRIDGES_NAV.ps1"
echo.
pause
