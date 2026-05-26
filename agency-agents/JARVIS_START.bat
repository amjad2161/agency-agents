@echo off
setlocal enabledelayedexpansion

:: ============================================================
:: JARVIS_START.bat — Launch JARVIS Supreme Brainiac interactive mode
:: Requires JARVIS_SETUP.bat to have been run first.
:: ============================================================

set ROOT=%~dp0
set VENV_PYTHON=%ROOT%.venv\Scripts\python.exe
set VENV_AGENCY=%ROOT%.venv\Scripts\agency.exe

:: --- Check setup was done ---
if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment not found. Run JARVIS_SETUP.bat first.
    exit /b 1
)

:: --- Load .env if present (basic key=value parsing) ---
if exist "%ROOT%.env" (
    for /f "usebackq tokens=1,* delims==" %%a in ("%ROOT%.env") do (
        if not "%%a"=="" if not "%%b"=="" (
            set "%%a=%%b"
        )
    )
)

:: --- Check API key ---
if "%ANTHROPIC_API_KEY%"=="" (
    echo.
    echo [ERROR] ANTHROPIC_API_KEY not set.
    echo         Set it in environment or create a .env file at repo root:
    echo         ANTHROPIC_API_KEY=sk-ant-your-key-here
    echo.
    exit /b 1
)

:: --- Print banner ---
echo.
echo  ============================================================
echo    J.A.R.V.I.S  —  Supreme Brainiac Agent
echo    Owner: Amjad Mobarsham  ^|  mobarsham@gmail.com
echo  ============================================================
echo.

:: --- Parse optional argument for command ---
set CMD=%~1

if "%CMD%"=="" (
    :: Interactive mode — show what's available
    echo  Usage:
    echo    JARVIS_START.bat list                     - List all 323 skills
    echo    JARVIS_START.bat list --category X        - Filter by category
    echo    JARVIS_START.bat plan "your task here"    - Route task to best skill
    echo    JARVIS_START.bat run "your task here"     - Execute task
    echo    JARVIS_START.bat doctor                   - System health check
    echo.
    echo  Starting interactive shell with agency activated...
    echo  Type 'agency --help' for full command list.
    echo  Type 'exit' to quit.
    echo.
    cmd /k "set PATH=%ROOT%.venv\Scripts;%PATH% && echo [JARVIS] Ready. && agency doctor"
) else (
    :: Run specific command
    if exist "%VENV_AGENCY%" (
        "%VENV_AGENCY%" %*
    ) else (
        "%VENV_PYTHON%" -m agency.cli %*
    )
)

endlocal
