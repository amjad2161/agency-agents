@echo off
echo ============================================
echo   JARVIS BRAINIAC — Installation
echo ============================================
cd /d "%~dp0"
python -m pip install --upgrade pip
pip install -e runtime
pip install numpy pytest pytest-asyncio ezdxf pypdf python-docx openpyxl flask requests
echo.
echo Installation complete!
echo Run: python -m agency.main
pause
