@echo off
title JARVIS SINGULARITY POST-MERGE SETUP
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0POST_MERGE_SETUP.ps1" %*
echo.
echo ===== Exit code: %ERRORLEVEL% =====
pause
