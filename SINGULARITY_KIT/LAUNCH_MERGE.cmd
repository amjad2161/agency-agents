@echo off
setlocal
title JARVIS SINGULARITY MERGE
echo.
echo ============================================================
echo   JARVIS SINGULARITY MERGE ENGINE
echo   Destination: %~dp0
echo ============================================================
echo.
where powershell >nul 2>nul || (echo PowerShell not found in PATH. & exit /b 1)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0MERGE_SINGULARITY.ps1" %*
set RC=%ERRORLEVEL%
echo.
echo ===== Exit code: %RC% =====
pause
exit /b %RC%
