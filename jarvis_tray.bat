@echo off
cd /d "%USERPROFILE%\agency"
start "" "%USERPROFILE%\agency\.venv\Scripts\pythonw.exe" "%USERPROFILE%\agency\jarvis_os\tray.py"
start "" "%USERPROFILE%\agency\.venv\Scripts\pythonw.exe" "%USERPROFILE%\agency\jarvis_os\hotkey_listener.py"
