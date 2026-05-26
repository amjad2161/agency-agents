@echo off
title JARVIS SINGULARITY - MASTER BOOTSTRAP
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0MASTER_BOOTSTRAP.ps1"
