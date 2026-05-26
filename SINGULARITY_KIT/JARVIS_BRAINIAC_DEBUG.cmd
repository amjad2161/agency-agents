@echo off
title JARVIS BRAINIAC (DEBUG mode - shows errors)
cd /d "%~dp0"
set ROOT=%~dp0
echo Activating venv...
call "%ROOT%.venv\Scripts\activate.bat"
echo.
echo Running JARVIS BRAINIAC with visible output...
echo.
python "%ROOT%JARVIS_BRAINIAC.py"
echo.
echo === Exit code: %ERRORLEVEL% ===
pause
