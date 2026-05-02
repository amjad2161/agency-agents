@echo off
REM ============================================================
REM RUN_FIX_AND_PUSH.cmd — full sequence:
REM   1. Apply known-bug fixes to agency repo
REM   2. Re-run driver in PUSH mode (real commit + push)
REM ============================================================
setlocal
cd /d "%~dp0"
echo.
echo === STEP A: applying known-bug fixes ===
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\FIX_KNOWN_BUGS.ps1"
if errorlevel 1 (
    echo Fix script reported errors — review FIX_KNOWN_BUGS output above.
    pause
    exit /b 1
)
echo.
echo === STEP B: running full driver (with push) ===
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\JARVIS_SINGULARITY_DRIVER.ps1"
set RC=%ERRORLEVEL%
echo.
echo === DONE — exit code: %RC% ===
echo Logs:
echo   - FIX_KNOWN_BUGS:    (above)
echo   - JARVIS_DRIVER:     %CD%\jarvis_driver_log.txt
echo.
pause
exit /b %RC%
