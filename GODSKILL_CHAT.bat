@echo off
cd /d "C:\Users\User\agency"
set PYTHONPATH=C:\Users\User\agency\runtime;C:\Users\User\agency
set JARVIS_URL=http://127.0.0.1:8765
"C:\Users\User\agency\.venv\Scripts\python.exe" "C:\Users\User\agency\jarvis_os\native_chat.py"
