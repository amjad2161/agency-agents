@echo off
title JARVIS SINGULARITY - FULL PIPELINE
echo ============================================================
echo   JARVIS SINGULARITY - FULL PIPELINE
echo   1. MERGE  (agency + kimi + jarvis forks -> singularity)
echo   2. VERIFY (structure + smoke imports)
echo   3. SETUP  (venv + runtime install + smoke test)
echo ============================================================
echo.

call "%~dp0LAUNCH_MERGE.cmd"
if errorlevel 1 (echo MERGE FAILED & exit /b 1)

echo.
echo === VERIFY ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0VERIFY_SINGULARITY.ps1"
if errorlevel 1 (echo VERIFY FAILED & pause & exit /b 2)

echo.
echo === POST-MERGE SETUP ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0POST_MERGE_SETUP.ps1"

echo.
echo === ALL DONE ===
pause
