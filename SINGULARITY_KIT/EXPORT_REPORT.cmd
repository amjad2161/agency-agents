@echo off
title Export merge artifacts to kit folder for inspection
chcp 65001 >nul
copy /Y "%~dp0..\MERGE_REPORT.md" "%~dp0_REPORT_SNAPSHOT.md"
copy /Y "%~dp0..\_MERGE.log"      "%~dp0_RUNLOG_SNAPSHOT.txt"
echo.
echo Snapshots saved to KIT folder. Done.
pause
