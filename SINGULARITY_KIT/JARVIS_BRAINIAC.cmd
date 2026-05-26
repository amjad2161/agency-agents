@echo off
title JARVIS BRAINIAC
cd /d "%~dp0"
set ROOT=%~dp0
if exist "%ROOT%.venv\Scripts\pythonw.exe" (
    start "" /B "%ROOT%.venv\Scripts\pythonw.exe" "%ROOT%JARVIS_BRAINIAC.py"
) else if exist "%ROOT%.venv\Scripts\python.exe" (
    start "" /B "%ROOT%.venv\Scripts\python.exe" "%ROOT%JARVIS_BRAINIAC.py"
) else (
    echo Venv not found - run LAUNCH_POST_MERGE_SETUP.cmd first
    pause
    exit /b 1
)
