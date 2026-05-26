@echo off
title JARVIS — Starting...
cd /d "%~dp0"
set ROOT=%~dp0
set "PY=%ROOT%.venv\Scripts\python.exe"
set "PYW=%ROOT%.venv\Scripts\pythonw.exe"
set "SERVER=%ROOT%godskill_server\server.py"
set "CHAT=%ROOT%jarvis_os\native_chat.py"
set "JARVIS_URL=http://127.0.0.1:8765"
set "PYTHONPATH=%ROOT%runtime;%ROOT%"
set "AGENCY_ROOT=%ROOT%"

:: ── Auto-create desktop shortcut on first run ─────────────────────────────────
set "LNK=%USERPROFILE%\Desktop\JARVIS.lnk"
if not exist "%LNK%" (
    powershell -NoProfile -NonInteractive -Command "$s=$env:USERPROFILE+'\Desktop\JARVIS.lnk';$ws=New-Object -ComObject WScript.Shell;$sc=$ws.CreateShortcut($s);$sc.TargetPath='%ROOT%JARVIS_OPEN.bat';$sc.WorkingDirectory='%ROOT%';$sc.Description='JARVIS GODSKILL Navigation System';$sc.IconLocation='%ROOT%.venv\Scripts\python.exe,0';$sc.Save();Write-Host 'Shortcut created.'" 2>nul
)

:: ── Sanity checks ─────────────────────────────────────────────────────────────
if not exist "%PY%" (
    echo.
    echo [ERROR] Python venv not found at:
    echo   %PY%
    echo Run JARVIS_SETUP.bat first to create the virtual environment.
    pause
    exit /b 1
)
if not exist "%CHAT%" (
    echo.
    echo [ERROR] native_chat.py not found at:
    echo   %CHAT%
    pause
    exit /b 1
)

:: ── Start server if not already running ───────────────────────────────────────
"%PY%" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=2)" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [JARVIS] Starting server...
    start "" /B "%PYW%" "%SERVER%"
    set /A _t=0
    :WAIT_LOOP
    timeout /t 1 /nobreak >nul
    "%PY%" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=1)" >nul 2>&1
    if %ERRORLEVEL% EQU 0 goto SERVER_UP
    set /A _t+=1
    if %_t% LSS 6 goto WAIT_LOOP
    echo [WARNING] Server slow to start — opening chat anyway.
)
:SERVER_UP

:: ── Open chat window ──────────────────────────────────────────────────────────
title JARVIS
"%PY%" "%CHAT%"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Chat failed ^(exit code %ERRORLEVEL%^). Details:
    echo ───────────────────────────────────────────────────
    "%PY%" "%CHAT%" 2>&1
    pause
)
