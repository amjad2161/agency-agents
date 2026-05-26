@echo off
title JARVIS SINGULARITY VERIFY
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0VERIFY_SINGULARITY.ps1" %*
echo.
echo ===== Exit code: %ERRORLEVEL% =====
pause
