@echo off
title JARVIS OS Install
echo Installing JARVIS as Windows OS component...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL_AUTOSTART.ps1"
