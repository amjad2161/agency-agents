@echo off
title JARVIS v2.0 INSTALL
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL_JARVIS_V2.ps1"
pause
