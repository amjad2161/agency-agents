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
git commit -m "feat(jarvis): SupremeJarvisBrain routing + React fix + setup scripts

- jarvis_brain.py: add React/frontend keyword boosts to KEYWORD_SLUG_BOOST
  (react, vue, angular, svelte, typescript, component, tailwind, vite, etc.)
- planner.py: wire SupremeJarvisBrain.top_k() as primary skill router
  (replaces naive registry.search; falls back on error)
- amjad_memory.py: remove duplicate _singleton declaration (line 184)
- JARVIS_SETUP.bat: one-click venv + pip install -e runtime[dev] + smoke test
- JARVIS_START.bat: one-click