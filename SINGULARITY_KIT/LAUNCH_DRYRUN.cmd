@echo off
setlocal
title JARVIS SINGULARITY MERGE - DRY RUN
echo Dry-run: NO files will be written. Reports stats only.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0MERGE_SINGULARITY.ps1" -DryRun
pause
