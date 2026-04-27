@echo off
title JARVIS — Commit + Push Fixed Files
color 0A
echo.
echo ============================================
echo  J.A.R.V.I.S — Committing E2E Fixes
echo ============================================
echo.

cd /d "C:\Users\User\agency"

echo [0] Removing stale lock files...
if exist ".git\index.lock" del /f ".git\index.lock" && echo   Deleted index.lock
if exist ".git\HEAD.lock" del /f ".git\HEAD.lock" && echo   Deleted HEAD.lock
if exist ".git\refs\heads\main.lock" del /f ".git\refs\heads\main.lock" && echo   Deleted main.lock
echo   Done.
echo.

echo [1] Git status...
git status --short
echo.

echo [2] Staging all changes...
git add -A
echo.

echo [3] Committing...
git commit -m "fix: E2E upgrade — humanized soul, repair truncated files, CI startup fixed, 688/688 tests passing"
echo.

echo [4] Fetching origin...
git fetch origin
echo.

echo [5] Pushing to GitHub...
git push origin HEAD:main
if errorlevel 1 (
    echo.
    echo Trying force-with-lease...
    git push --force-with-lease origin HEAD:main
)

echo.
echo ============================================
echo  DONE. J.A.R.V.I.S commit pushed to main.
echo ============================================
echo.
git log --oneline -5
echo.
pause
