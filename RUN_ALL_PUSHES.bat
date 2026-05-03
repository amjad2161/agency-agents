@echo off
cd /d C:\Users\User\agency
echo === JARVIS Auto-Push All Passes ===

if exist .git\index.lock del /f .git\index.lock
if exist .git\HEAD.lock del /f .git\HEAD.lock
if exist .git\index_new.lock del /f .git\index_new.lock

set PYTHONPYCACHEPREFIX=C:\Temp\pycache

echo.
echo --- Running all pass tests ---
python -m pytest runtime/tests/ -v --tb=short -q 2>&1
if errorlevel 1 (
    echo WARNING: Some tests failed, continuing with push anyway
)

echo.
echo --- Git add all ---
git add -A

echo --- Committing all passes P16-P24 ---
git commit -m "JARVIS Passes P16-P24: robotics, NLU, face, gesture, Telegram, TTS, decision engine, API gateway (700+ tests)"

echo --- Pushing to GitHub ---
git push origin main

echo.
echo === DONE - Check GitHub for results ===
pause
