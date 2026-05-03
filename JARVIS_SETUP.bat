@echo off
setlocal enabledelayedexpansion

:: ============================================================
:: JARVIS_SETUP.bat — One-click setup for JARVIS Supreme Brainiac
:: Run once after cloning or pulling. Re-run to upgrade deps.
:: ============================================================

set ROOT=%~dp0
set RUNTIME=%ROOT%runtime

echo.
echo  [JARVIS] Supreme Brainiac — Setup
echo  ===================================
echo.

:: --- Locate Python (prefer py launcher, fall back to python) ---
where py >nul 2>&1
if %errorlevel%==0 (
    set PYTHON=py
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        set PYTHON=python
    ) else (
        echo [ERROR] Python not found. Install Python 3.10+ from https://python.org
        exit /b 1
    )
)

%PYTHON% --version
echo.

:: --- Check Python version >= 3.10 ---
for /f "tokens=2 delims= " %%v in ('%PYTHON% --version 2^>^&1') do set PYVER=%%v
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    set PYMAJ=%%a
    set PYMIN=%%b
)
if %PYMAJ% LSS 3 (
    echo [ERROR] Python 3.10+ required. Found %PYVER%
    exit /b 1
)
if %PYMAJ%==3 if %PYMIN% LSS 10 (
    echo [ERROR] Python 3.10+ required. Found %PYVER%
    exit /b 1
)

:: --- Create virtual environment ---
if not exist "%ROOT%.venv" (
    echo [SETUP] Creating virtual environment...
    %PYTHON% -m venv "%ROOT%.venv"
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        exit /b 1
    )
    echo [OK] Virtual environment created at .venv
) else (
    echo [OK] Virtual environment already exists.
)

set VENV_PYTHON=%ROOT%.venv\Scripts\python.exe
set VENV_PIP=%ROOT%.venv\Scripts\pip.exe

:: --- Upgrade pip ---
echo.
echo [SETUP] Upgrading pip...
"%VENV_PYTHON%" -m pip install --upgrade pip --quiet

:: --- Install runtime package with dev extras ---
echo [SETUP] Installing agency runtime (pip install -e runtime[dev])...
"%VENV_PIP%" install -e "%RUNTIME%[dev]" --quiet
if %errorlevel% neq 0 (
    echo [ERROR] Installation failed.
    exit /b 1
)
echo [OK] Runtime installed.

:: --- Check for ANTHROPIC_API_KEY ---
echo.
if "%ANTHROPIC_API_KEY%"=="" (
    echo [WARN] ANTHROPIC_API_KEY is not set.
    echo        Set it in your environment or create a .env file:
    echo        ANTHROPIC_API_KEY=sk-ant-...
    echo.
    echo        To set permanently on Windows:
    echo        setx ANTHROPIC_API_KEY "sk-ant-your-key-here"
) else (
    echo [OK] ANTHROPIC_API_KEY is set.
)

:: --- Smoke test ---
echo.
echo [SETUP] Running smoke tests...
"%VENV_PYTHON%" -m agency.cli list --category engineering >nul 2>&1
if %errorlevel% neq 0 (
    :: Try alternate entry point
    "%ROOT%.venv\Scripts\agency.exe" list --category engineering >nul 2>&1
    if %errorlevel% neq 0 (
        echo [WARN] CLI smoke test did not pass. Check ANTHROPIC_API_KEY and reinstall.
    ) else (
        echo [OK] CLI smoke test passed.
    )
) else (
    echo [OK] CLI smoke test passed.
)

echo.
echo  ===================================
echo  [JARVIS] Setup complete.
echo  Run JARVIS_START.bat to launch.
echo  ===================================
echo.

endlocal
