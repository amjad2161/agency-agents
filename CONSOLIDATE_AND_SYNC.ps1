# CONSOLIDATE_AND_SYNC.ps1
# Operator-runnable Windows-host cleanup + satellite-repo sync.
# Performs the cleanup that the sandbox bash mount cannot do
# (.git/index.lock removal, file moves, satellite-repo sync).
#
# Idempotent: safe to re-run.
#
# Run from:  C:\Users\User\agency
# Command:   powershell -ExecutionPolicy Bypass -File .\CONSOLIDATE_AND_SYNC.ps1

$ErrorActionPreference = "Continue"
$root = "C:\Users\User\agency"
Set-Location $root

Write-Host "===== JARVIS CONSOLIDATE + SYNC =====" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# 1. Remove stale CANARY + lock files
# ---------------------------------------------------------------------------
Write-Host "`n[1/6] Removing stale CANARY + git locks..." -ForegroundColor Yellow
$stale = @(
    ".jarvis_brainiac\CANARY.txt",
    ".git\index.lock",
    ".git\HEAD.lock"
)
foreach ($f in $stale) {
    $p = Join-Path $root $f
    if (Test-Path $p) {
        Remove-Item $p -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path $p)) { Write-Host "  removed: $f" -ForegroundColor Green }
    }
}

# ---------------------------------------------------------------------------
# 2. Archive historical JARVIS_PUSH_P*.ps1 + FINAL_PUSH_V*.ps1
# ---------------------------------------------------------------------------
Write-Host "`n[2/6] Archiving 23 historical push scripts..." -ForegroundColor Yellow
$archive = Join-Path $root "archive\push_scripts"
New-Item -ItemType Directory -Path $archive -Force | Out-Null

$pattern = @("JARVIS_PUSH_P*.ps1", "FINAL_PUSH_V*.ps1")
$moved = 0
foreach ($pat in $pattern) {
    Get-ChildItem -Path $root -Filter $pat -File -ErrorAction SilentlyContinue | ForEach-Object {
        Move-Item $_.FullName -Destination $archive -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path $_.FullName)) { $moved++ }
    }
}
Write-Host "  moved $moved files to archive\push_scripts\" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 3. Archive duplicate launchers
# ---------------------------------------------------------------------------
Write-Host "`n[3/6] Consolidating duplicate launchers..." -ForegroundColor Yellow
$launcherArchive = Join-Path $root "archive\launchers"
New-Item -ItemType Directory -Path $launcherArchive -Force | Out-Null

# Keep canonical: JARVIS_LAUNCH.ps1 + LAUNCH_V27.cmd
# Archive everything else with similar names
$keep = @("JARVIS_LAUNCH.ps1", "LAUNCH_V27.cmd", "JARVIS_OPEN.bat", "JARVIS_SETUP.bat", "JARVIS_START.bat")
$candidates = Get-ChildItem -Path $root -File -Filter "*LAUNCH*" -ErrorAction SilentlyContinue
$candidates += Get-ChildItem -Path $root -File -Filter "JARVIS_*.bat" -ErrorAction SilentlyContinue
$archivedLaunchers = 0
foreach ($f in $candidates) {
    if ($keep -notcontains $f.Name) {
        Move-Item $f.FullName -Destination $launcherArchive -Force -ErrorAction SilentlyContinue
        if (-not (Test-Path $f.FullName)) { $archivedLaunchers++ }
    }
}
Write-Host "  archived $archivedLaunchers redundant launchers" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 4. Sync 5 satellite repos
# ---------------------------------------------------------------------------
Write-Host "`n[4/6] Syncing 5 satellite repos..." -ForegroundColor Yellow
$syncScript = Join-Path $root "integrations\external_repos\SYNC_SATELLITES.ps1"
if (Test-Path $syncScript) {
    & $syncScript
} else {
    Write-Warning "  SYNC_SATELLITES.ps1 not found at $syncScript"
}

# ---------------------------------------------------------------------------
# 5. Update .gitignore for jarvis_brainiac runtime artifacts
# ---------------------------------------------------------------------------
Write-Host "`n[5/6] Hardening .gitignore..." -ForegroundColor Yellow
$gi = Join-Path $root ".gitignore"
$additions = @(
    ".jarvis_brainiac/CANARY.txt",
    ".jarvis_brainiac/improvement_log.jsonl",
    ".jarvis_brainiac/last_run_report.md",
    ".jarvis_brainiac/memory/",
    ".jarvis_brainiac/proposed/",
    "archive/",
    "*.zip",
    "*.bundle"
)
$existing = if (Test-Path $gi) { Get-Content $gi } else { @() }
$added = 0
foreach ($a in $additions) {
    if ($existing -notcontains $a) {
        Add-Content -Path $gi -Value $a
        $added++
    }
}
Write-Host "  added $added new entries to .gitignore" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 6. Run pytest sanity check
# ---------------------------------------------------------------------------
Write-Host "`n[6/6] Running pytest --collect-only..." -ForegroundColor Yellow
$venv = Join-Path $root ".venv\Scripts\python.exe"
$py = if (Test-Path $venv) { $venv } else { "python" }
& $py -m pytest runtime/tests --collect-only -q 2>&1 | Select-Object -Last 5

Write-Host "`n===== CONSOLIDATE COMPLETE =====" -ForegroundColor Cyan
Write-Host "Next: review changes -> git add -A -> git commit -> git push" -ForegroundColor White
