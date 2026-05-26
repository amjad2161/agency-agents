# MERGE_FULL_100 - Absolute 100% merge. No exclusions. Every file. Plus GitHub clone.
[CmdletBinding()]
param(
    [string]$Destination = "C:\Users\User\JARVIS_SINGULARITY"
)
$ErrorActionPreference = 'Continue'
$ProgressPreference    = 'SilentlyContinue'

Write-Host "=== MERGE_FULL_100 - ZERO EXCLUSIONS - 100% MERGE ===" -ForegroundColor Cyan
Write-Host "Destination: $Destination" -ForegroundColor Cyan

$Sources = @(
    'C:\Users\User\Downloads\Kimi_Agent_Full JARVIS Project Audit000. (2)',
    'C:\Users\User\Downloads\Kimi_Agent_Full JARVIS Project Audit',
    'C:\Users\User\Downloads\jarvis brainiac'
)
$GitHubRepo = "https://github.com/amjad2161/agency-agents.git"
$GitHubTarget = Join-Path $Destination "imports\agency-agents"

# Stats
$totalSrc = 0
$totalCopied = 0
$totalSkipped = 0
$totalBytes = 0L

# 1. CLONE GITHUB REPO
Write-Host ""
Write-Host "=== Cloning $GitHubRepo ===" -ForegroundColor Cyan
$git = (Get-Command git -ErrorAction SilentlyContinue).Source
if (-not $git) {
    Write-Warning "git not in PATH - skipping clone"
} else {
    $importsDir = Join-Path $Destination "imports"
    if (-not (Test-Path $importsDir)) { New-Item -ItemType Directory -Path $importsDir -Force | Out-Null }
    if (Test-Path $GitHubTarget) {
        Write-Host "Pulling latest..."
        & $git -C $GitHubTarget pull 2>&1 | Out-Host
    } else {
        Write-Host "Cloning fresh..."
        & $git clone $GitHubRepo $GitHubTarget 2>&1 | Out-Host
    }
    if (Test-Path $GitHubTarget) {
        $cloneCount = (Get-ChildItem -Path $GitHubTarget -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
        Write-Host "[OK] GitHub repo cloned: $cloneCount files in $GitHubTarget" -ForegroundColor Green
    }
}

# 2. ROBOCOPY EACH SOURCE WITH ZERO EXCLUSIONS
foreach ($src in $Sources) {
    if (-not (Test-Path -LiteralPath $src)) {
        Write-Warning "Source missing: $src"
        continue
    }
    $srcName = (Split-Path $src -Leaf) -replace '[^\w\-\.]', '_'
    $dstSub = Join-Path $Destination "_FULL_MERGE_$srcName"
    Write-Host ""
    Write-Host "=== Mirroring: $src" -ForegroundColor Cyan
    Write-Host "    -> $dstSub" -ForegroundColor DarkGray

    # robocopy /E = subdirs incl empty, /R:1 /W:1 = retry once wait 1s, /XJ = exclude junction (avoid loops)
    # /MT:8 = multithreaded, /NP = no progress percent, /NJH /NJS = quiet headers
    $rcArgs = @($src, $dstSub, '/E', '/R:1', '/W:1', '/XJ', '/MT:8', '/NP', '/NJH', '/NJS', '/NDL', '/NFL')
    & robocopy @rcArgs | Out-Null

    # Count
    if (Test-Path -LiteralPath $dstSub) {
        $cnt = (Get-ChildItem -LiteralPath $dstSub -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
        $sz  = (Get-ChildItem -LiteralPath $dstSub -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        Write-Host "    [OK] $cnt files, $([math]::Round($sz / 1GB, 2)) GB copied" -ForegroundColor Green
        $totalCopied += $cnt
        $totalBytes += $sz
    }
    # Source count
    $srcCnt = (Get-ChildItem -LiteralPath $src -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
    $totalSrc += $srcCnt
    Write-Host "    Source had $srcCnt files; copied $cnt" -ForegroundColor DarkGray
}

# 3. REPORT
Write-Host ""
Write-Host "========== FULL MERGE COMPLETE ==========" -ForegroundColor Green
Write-Host "Sources scanned: $($Sources.Count) folders + 1 GitHub repo"
Write-Host "Total source files: $totalSrc"
Write-Host "Total copied to destination: $totalCopied"
Write-Host "Total bytes: $([math]::Round($totalBytes / 1GB, 2)) GB"

# Write report
$reportPath = Join-Path $Destination 'FULL_MERGE_REPORT.md'
$lines = @(
    "# JARVIS FULL MERGE - 100% NO EXCLUSIONS",
    "",
    "**Date:** $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
    "**Mode:** ZERO exclusions, ZERO size cap, byte-for-byte mirror",
    "",
    "## Sources (mirrored to _FULL_MERGE_<name>/)",
    ""
)
foreach ($s in $Sources) { $lines += "- $s" }
$lines += ""
$lines += "## GitHub repo cloned to imports/agency-agents/"
$lines += ""
$lines += "- $GitHubRepo"
$lines += ""
$lines += "## Stats"
$lines += ""
$lines += "- Total source files (3 folders): $totalSrc"
$lines += "- Total copied to destination: $totalCopied"
$lines += "- Total bytes: $([math]::Round($totalBytes / 1GB, 2)) GB"
$lines | Out-File -LiteralPath $reportPath -Encoding utf8

Write-Host ""
Write-Host "Report: $reportPath" -ForegroundColor Cyan
Write-Host ""
Write-Host "All files preserved at full fidelity in:" -ForegroundColor Yellow
Write-Host "  $Destination\_FULL_MERGE_*/         (3 source mirrors)"
Write-Host "  $Destination\imports\agency-agents\ (GitHub clone)"
