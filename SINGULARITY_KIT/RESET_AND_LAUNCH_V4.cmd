@echo off
title JARVIS RESET + V4 RELAUNCH
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0RESET_AND_LAUNCH_V4.ps1"
pause
