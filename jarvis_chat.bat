@echo off
cd /d "%USERPROFILE%\agency"
start "" "%USERPROFILE%\agency\.venv\Scripts\pythonw.exe" "%USERPROFILE%\agency\jarvis_os\native_chat.py"
