@echo off
REM ====================================================================
REM Agency Runtime — one-shot installer (double-click on Windows)
REM
REM Hand this file to a non-technical user. They double-click it; it
REM elevates if needed, runs the PowerShell installer, opens the agent
REM web UI in their browser, and they're done.
REM ====================================================================

setlocal

REM Find a real PowerShell (prefer pwsh.exe v7+, fall back to Windows
REM PowerShell 5.1 which ships with every modern Windows).
set "PS_EXE=powershell.exe"
where pwsh.exe >nul 2>&1 && set "PS_EXE=pwsh.exe"

REM Pass-through any args the user might've added (e.g. -NoLaunch).
"%PS_EXE%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo ============================================================
    echo  Installer exited with code %RC%.
    echo  Read the messages above; fix the reported issue; re-run.
    echo ============================================================
    pause
)

exit /b %RC%
