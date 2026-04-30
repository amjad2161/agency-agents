@echo off
title JARVIS — Push to main
color 0A
echo.
echo ============================================
echo  J.A.R.V.I.S — Push to main
echo ============================================
echo.

cd /d "C:\Users\User\agency"

echo [0] Removing stale lock files...
if exist ".git\index.lock" del /f ".git\index.lock" && echo   Deleted index.lock
if exist ".git\HEAD.lock" del /f ".git\HEAD.lock" && echo   Deleted HEAD.lock
if exist ".git\refs\heads\main.lock" del /f ".git\refs\heads\main.lock" && echo   Deleted main.lock
echo   Done.
echo.

echo [1] Current status...
git log --oneline -3
echo.

echo [2] Pushing commit ca313b5 to GitHub...
git push origin HEAD:main
if errorlevel 1 (
    echo.
    echo [WARN] Normal push failed. Trying force-with-lease...
    git push --force-with-lease origin HEAD:main
    if errorlevel 1 (
        echo [ERROR] Push failed. Ensure git credentials are configured:
        echo   git config --global credential.helper manager
        echo   Then run: git push origin HEAD:main
        pause
        exit /b 1
    )
)

echo.
echo ============================================
echo  DONE. Commit ca313b5 pushed to main.
echo  feat(jarvis): SupremeJarvisBrain routing + React fix + setup scripts
echo ============================================
echo.
git log --oneline -5
echo.
pause
