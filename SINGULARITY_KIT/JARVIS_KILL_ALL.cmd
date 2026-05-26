@echo off
title KILL ALL JARVIS
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0JARVIS_KILL_ALL.ps1"
