@echo off
REM Dry-run wrapper — extracts, merges, tests, commits, but does NOT push.
setlocal
cd /d "%~dp0"
echo.
echo === DRY-RUN MODE — no GitHub push ===
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\JARVIS_SINGULARITY_DRIVER.ps1" -NoPush
set RC=%ERRORLEVEL%
echo.
echo Exit code: %RC%
pause
exit /b %RC%
