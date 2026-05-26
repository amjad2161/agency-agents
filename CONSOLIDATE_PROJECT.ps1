# CONSOLIDATE_PROJECT.ps1
# Script to organize, clean, and migrate the JARVIS BRAINIAC project files.

$ErrorActionPreference = "Continue"

# Define paths
$source = "C:\Users\Mobar\OneDrive\Desktop\jarvis brainiac"
$dest = "C:\Users\Mobar\jarvis-brainiac"

Write-Host "===== JARVIS SYSTEM CONSOLIDATION & MIGRATION =====" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# 1. Internal Organization (Clean up ZIPs and Logs in source)
# ---------------------------------------------------------------------------
Write-Host "`n[1/4] Organizing backups and logs in source folder..." -ForegroundColor Yellow

$zipArchive = Join-Path $source "archive\zip_backups"
$logArchive = Join-Path $source "archive\logs"

New-Item -ItemType Directory -Path $zipArchive -Force | Out-Null
New-Item -ItemType Directory -Path $logArchive -Force | Out-Null

# Move ZIPs
$zips = Get-ChildItem -Path $source -Filter "*.zip" -File -ErrorAction SilentlyContinue
$zipCount = 0
foreach ($z in $zips) {
    Move-Item $z.FullName -Destination $zipArchive -Force -ErrorAction SilentlyContinue
    $zipCount++
}
Write-Host "  Moved $zipCount ZIP backup(s) to archive\zip_backups\" -ForegroundColor Green

# Move root logs
$logs = @("install_supreme_log.txt", "one_click_log.txt", "jarvis_supreme.log")
$logCount = 0
foreach ($l in $logs) {
    $p = Join-Path $source $l
    if (Test-Path $p) {
        Move-Item $p -Destination $logArchive -Force -ErrorAction SilentlyContinue
        $logCount++
    }
}

# Move external logs if existing
$extLogsDir = "C:\Users\Mobar\agency\logs"
if (Test-Path $extLogsDir) {
    $extLogs = Get-ChildItem -Path $extLogsDir -File -ErrorAction SilentlyContinue
    foreach ($el in $extLogs) {
        Move-Item $el.FullName -Destination $logArchive -Force -ErrorAction SilentlyContinue
        $logCount++
    }
}
Write-Host "  Consolidated $logCount log file(s) into archive\logs\" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 2. Prepare Migration Destination
# ---------------------------------------------------------------------------
Write-Host "`n[2/4] Preparing destination folder: $dest..." -ForegroundColor Yellow
if (-not (Test-Path $dest)) {
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    Write-Host "  Created target folder: $dest" -ForegroundColor Green
} else {
    Write-Host "  Target folder already exists." -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# 3. Copying Workspace Contents (Safe Migration)
# ---------------------------------------------------------------------------
Write-Host "`n[3/4] Copying files to new location (this may take a minute)..." -ForegroundColor Yellow

# Using Robocopy for fast, reliable copy including security attributes and metadata
# Excluding .venv, node_modules, and cache directories to keep it clean and fast
robocopy "$source" "$dest" /E /COPY:DAT /R:3 /W:2 /XD .git .venv node_modules .pytest_cache __pycache__ /NDL /NFL /NJH /NJS

# Copy .git metadata to preserve repository settings
Write-Host "  Copying repository metadata (.git)..." -ForegroundColor Yellow
robocopy (Join-Path $source ".git") (Join-Path $dest ".git") /E /COPY:DAT /R:3 /W:2 /NDL /NFL /NJH /NJS

# Copy .venv environment to keep dependencies
if (Test-Path (Join-Path $source ".venv")) {
    Write-Host "  Copying virtual environment (.venv)..." -ForegroundColor Yellow
    robocopy (Join-Path $source ".venv") (Join-Path $dest ".venv") /E /COPY:DAT /R:3 /W:2 /NDL /NFL /NJH /NJS
}

Write-Host "  Workspace copy complete." -ForegroundColor Green

# ---------------------------------------------------------------------------
# 4. Clean up Legacy Folders
# ---------------------------------------------------------------------------
Write-Host "`n[4/4] Cleaning up legacy folders..." -ForegroundColor Yellow

$legacyFolders = @(
    "C:\Users\Mobar\.jarvis",
    "C:\Users\Mobar\agency"
)
foreach ($lf in $legacyFolders) {
    if (Test-Path $lf) {
        Remove-Item $lf -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  Removed legacy folder: $lf" -ForegroundColor Green
    }
}

Write-Host "`n===== CONSOLIDATION & COPY COMPLETE =====" -ForegroundColor Cyan
Write-Host "`nNext Steps to Complete Migration:" -ForegroundColor Yellow
Write-Host "1. Close this terminal, VS Code, and any other programs using the old directory." -ForegroundColor White
Write-Host "2. Delete the old directory manually to complete the 'Move':" -ForegroundColor White
Write-Host "   -> C:\Users\Mobar\OneDrive\Desktop\jarvis brainiac" -ForegroundColor Red
Write-Host "3. Open your IDE/Terminal in the new directory:" -ForegroundColor White
Write-Host "   -> C:\Users\Mobar\jarvis-brainiac" -ForegroundColor Green
Write-Host "4. Set C:\Users\Mobar\jarvis-brainiac as your active Antigravity IDE workspace." -ForegroundColor White
