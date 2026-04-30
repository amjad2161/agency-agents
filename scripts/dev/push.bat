@echo off
title JARVIS — GitHub Push
color 0A
echo.
echo ============================================
echo  J.A.R.V.I.S — Pushing to GitHub
echo ============================================
echo.

cd /d "C:\Users\User\agency"

echo [1/5] Removing stale lock files...
if exist ".git\index.lock" del /f ".git\index.lock" && echo   Deleted index.lock
if exist ".git\HEAD.lock" del /f ".git\HEAD.lock" && echo   Deleted HEAD.lock
if exist ".git\refs\heads\main.lock" del /f ".git\refs\heads\main.lock" && echo   Deleted main.lock
echo   Done.
echo.

echo [2/5] Current git status...
git log --oneline -5
echo.

echo [3/5] Fetching origin...
git fetch origin
echo.

echo [4/5] Rebasing onto origin/main...
git pull --rebase origin main
if errorlevel 1 (
    echo.
    echo WARNING: Rebase had issues. Trying merge...
    git rebase --abort 2>nul
    git merge origin/main -m "merge: sync with origin"
)
echo.

echo [5/5] Pushing to GitHub...
git push origin HEAD:main
if errorlevel 1 (
    echo.
    echo Trying force-with-lease...
    git push --force-with-lease origin HEAD:main
)

echo.
echo ============================================
echo  DONE. Check above for push confirmation.
echo ============================================
echo.
git log --oneline -5
echo.
pause
