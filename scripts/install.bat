@echo off
REM ====================================================================
REM Agency Runtime — standalone installer for Windows.
REM
REM HOW TO USE:
REM   1. Download THIS file to your Desktop (or anywhere).
REM   2. Double-click it.
REM   3. Wait. The installer handles Python, the repo, the venv, the
REM      API key prompt, the trust mode, the launch — everything.
REM
REM This .bat is self-bootstrapping: it downloads the latest installer
REM script directly from GitHub on every run (with a cache-bust query
REM string so you always get the newest version, no GitHub-CDN
REM staleness). The .bat itself is tiny and stable; the heavy logic
REM lives in scripts/install.ps1 in the repo.
REM ====================================================================

setlocal EnableDelayedExpansion

set "SCRIPT_URL=https://raw.githubusercontent.com/amjad2161/agency-agents/main/scripts/install.ps1?t=%RANDOM%%RANDOM%"
set "PSFILE=%TEMP%\agency-install-%RANDOM%.ps1"
set "PS_EXE=powershell.exe"
where pwsh.exe >nul 2>&1 && set "PS_EXE=pwsh.exe"

echo.
echo  Agency Runtime installer
echo  ========================
echo.
echo  Downloading the latest installer script...

REM Prefer curl (built into Windows 10/11). Fallback to PowerShell's iwr.
where curl.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    curl.exe -fsSL "%SCRIPT_URL%" -o "%PSFILE%"
) else (
    "%PS_EXE%" -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; iwr -UseBasicParsing '%SCRIPT_URL%' -OutFile '%PSFILE%'"
)

if not exist "%PSFILE%" (
    echo.
    echo  ERROR: could not download the installer script.
    echo  Check your internet connection and try again.
    echo.
    pause
    exit /b 1
)

echo  Running the installer ^(this can take 5-10 minutes the first time^)...
echo.

REM Pass through any args ^(-NoLaunch, -ApiKey, etc.^).
"%PS_EXE%" -NoProfile -ExecutionPolicy Bypass -File "%PSFILE%" %*
set "RC=%ERRORLEVEL%"

del "%PSFILE%" 2>nul

if not "%RC%"=="0" (
    echo.
    echo  ============================================================
    echo   Installer exited with code %RC%.
    echo   Read the messages above; fix the reported issue; re-run
    echo   ^(double-click this same file again^).
    echo  ============================================================
    pause
    exit /b %RC%
)

echo.
echo  ============================================================
echo   Done. The agent web UI is running at http://127.0.0.1:8765
echo  ============================================================
echo.
pause
