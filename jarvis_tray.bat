@echo off
setlocal
if not defined AGENCY_ROOT set "AGENCY_ROOT=%USERPROFILE%\agency"
set "PYW=%AGENCY_ROOT%\.venv\Scripts\pythonw.exe"
set "TRAY=%AGENCY_ROOT%\jarvis_os\tray.py"
set "HOTKEY=%AGENCY_ROOT%\jarvis_os\hotkey_listener.py"
if not exist "%PYW%" (
    echo [JARVIS] pythonw.exe missing at %PYW%
    echo [JARVIS] Run INSTALL_AUTOSTART.cmd to set up the venv.
    pause
    exit /b 1
)
if not exist "%TRAY%" (
    echo [JARVIS] tray.py missing at %TRAY%
    pause
    exit /b 1
)
cd /d "%AGENCY_ROOT%"
start "" "%PYW%" "%TRAY%"
if exist "%HOTKEY%" (
    start "" "%PYW%" "%HOTKEY%"
)
