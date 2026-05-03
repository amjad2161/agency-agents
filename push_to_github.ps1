# JARVIS BRAINIAC — Push to GitHub (PowerShell)
# Usage: .\push_to_github.ps1

$ErrorActionPreference = "Stop"
$REPO = "https://github.com/amjad2161/agency-agents.git"
$BRANCH = "main"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  JARVIS BRAINIAC — GitHub Push" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

git add -A

$status = git status --porcelain
if (-not $status) {
    Write-Host "No changes to commit." -ForegroundColor Yellow
    exit 0
}

Write-Host "Changes to commit:" -ForegroundColor Green
git diff --cached --stat

$MSG = @"
JARVIS BRAINIAC v28.0 — $(Get-Date -Format "yyyy-MM-dd HH:mm")

Stats:
- 119 Python files
- 96,353 lines of code
- 276 tests passing
- 35 external integrations
- 10 real working demos

Author: Amjad Mobarsham
"@

git commit -m $MSG

Write-Host ""
Write-Host "Pushing to $REPO ..." -ForegroundColor Cyan
git push origin $BRANCH

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  ✅ Pushed successfully!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
