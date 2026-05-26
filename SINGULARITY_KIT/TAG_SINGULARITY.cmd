@echo off
title Tag JARVIS Singularity baseline
chcp 65001 >nul
cd /d "%~dp0"
git tag -a v0.1.0-singularity -m "Post-merge unified baseline (2026-05-03)"
echo.
echo Current tags:
git tag --list
pause
