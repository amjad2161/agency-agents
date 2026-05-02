@echo off
REM ============================================================
REM RUN_JARVIS_SINGULARITY.cmd — double-click launcher
REM Bypasses ExecutionPolicy so the .ps1 driver runs even if
REM PowerShell policy is Restricted.
REM ============================================================
setlocal
cd /d "%~dp0"
echo.
echo ============================================================
echo  JARVIS SINGULARITY DRIVER — launching...
echo  Working dir: %CD%
echo ============================================================
echo.

REM Run the driver with full bypass and verbose output
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\JARVIS_SINGULARITY_DRIVER.ps1"

set RC=%ERRORLEVEL%
echo.
echo ============================================================
echo  Driver finished with exit code: %RC%
echo  Full log: %CD%\jarvis_driver_log.txt
echo ============================================================
echo.
pause
exit /b %RC%
