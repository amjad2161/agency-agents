@echo off
cd /d "%~dp0"
set ROOT=%~dp0
set PYTHONPATH=%ROOT%runtime;%ROOT%
set JARVIS_URL=http://127.0.0.1:8765
"%ROOT%.venv\Scripts\python.exe" "%ROOT%jarvis_os\native_chat.py"
