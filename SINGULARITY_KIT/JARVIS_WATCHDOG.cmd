@echo off
title JARVIS Watchdog (keep alive)
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0JARVIS_WATCHDOG.ps1"
