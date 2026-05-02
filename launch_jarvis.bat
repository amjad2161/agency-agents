@echo off
echo ============================================
echo   JARVIS BRAINIAC — Launching...
echo ============================================
cd /d "%~dp0"
set PYTHONPATH=%~dp0;%~dp0runtime
python -m agency.main
pause
