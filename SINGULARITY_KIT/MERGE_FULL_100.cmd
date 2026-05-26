@echo off
title MERGE FULL 100% - Zero Exclusions
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0MERGE_FULL_100.ps1"
echo.
pause
