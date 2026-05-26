@echo off
title Install JARVIS Singularity docs
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL_DOCS.ps1"
echo.
echo Done.
pause
