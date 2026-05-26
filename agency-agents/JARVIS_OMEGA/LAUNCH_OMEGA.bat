@echo off
REM Ω-SINGULARITY launcher — Windows
setlocal
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.11+ required & exit /b 1)
if "%~1"=="" ( python omega.py stats ) else ( python omega.py %* )
endlocal
