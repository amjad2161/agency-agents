@echo off
setlocal
if not defined AGENCY_ROOT set "AGENCY_ROOT=%USERPROFILE%\agency"
set "PYW=%AGENCY_ROOT%\.venv\Scripts\pythonw.exe"
set "CHAT=%AGENCY_ROOT%\jarvis_os\native_chat.py"
if not exist "%PYW%" (
    echo [JARVIS] pythonw.exe missing at %PYW%
    echo [JARVIS] Run INSTALL_AUTOSTART.cmd to set up the venv.
    pause
    exit /b 1
)
if not exist "%CHAT%" (
    echo [JARVIS] native_chat.py missing at %CHAT%
    pause
    exit /b 1
)
cd /d "%AGENCY_ROOT%"
start "" "%PYW%" "%CHAT%"
