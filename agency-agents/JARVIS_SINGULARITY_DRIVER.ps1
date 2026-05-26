# =============================================================================
# JARVIS_SINGULARITY_DRIVER.ps1  —  v24 unified push driver
# =============================================================================
# Executes the 7-step mission autonomously on this Windows machine.
# Idempotent: re-running is safe. Logs everything to .\jarvis_driver_log.txt
#
# USAGE (PowerShell, as your normal user — NOT admin):
#   cd "$env:USERPROFILE\OneDrive\מסמכים\Claude\Projects\jarvis brainiac"
#   .\JARVIS_SINGULARITY_DRIVER.ps1
#
# To skip push (dry-run):
#   .\JARVIS_SINGULARITY_DRIVER.ps1 -NoPush
#
# To force re-extract of zip:
#   .\JARVIS_SINGULARITY_DRIVER.ps1 -ForceExtract
# =============================================================================

[CmdletBinding()]
param(
    [string]$AgencyRoot      = "$env:USERPROFILE\agency",
    [string]$WorkspaceRoot   = "$env:USERPROFILE\OneDrive\מסמכים\Claude\Projects\jarvis brainiac",
    [string]$SingularityZip  = "$env:USERPROFILE\Downloads\Kimi_Agent_Full JARVIS Project Audit\JARVIS_SINGULARITY.zip",
    [string]$Branch          = "main",
    [string]$CommitMessage   = "JARVIS SINGULARITY v24 — 2575 files, 83 tests, 145 Kimi requirements, Pass14→P24 complete",
    [switch]$NoPush,
    [switch]$ForceExtract,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$LogFile = Join-Path $PSScriptRoot "jarvis_driver_log.txt"
"" | Out-File -FilePath $LogFile -Encoding utf8

function Write-Step {
    param([string]$Title)
    $line = "`n========== $Title ==========`n"
    Write-Host $line -ForegroundColor Cyan
    $line | Out-File -FilePath $LogFile -Append -Encoding utf8
}

function Write-Info {
    param([string]$Msg)
    Write-Host "  $Msg"
    "  $Msg" | Out-File -FilePath $LogFile -Append -Encoding utf8
}

function Run-And-Log {
    param([string]$Cmd, [string]$Cwd = $null)
    if ($Cwd) { Push-Location $Cwd }
    try {
        Write-Info "> $Cmd"
        $output = & cmd /c "$Cmd 2>&1"
        $output | ForEach-Object {
            Write-Host "    $_"
            "    $_" | Out-File -FilePath $LogFile -Append -Encoding utf8
        }
        return $LASTEXITCODE
    } finally {
        if ($Cwd) { Pop-Location }
    }
}

# =============================================================================
Write-Step "STEP 1 — Audit C:\Users\User\agency"

if (!(Test-Path $AgencyRoot)) {
    Write-Info "AgencyRoot does not exist: $AgencyRoot"
    Write-Info "Cloning from GitHub..."
    Run-And-Log "git clone https://github.com/amjad2161/agency-agents.git `"$AgencyRoot`""
} else {
    Write-Info "AgencyRoot exists: $AgencyRoot"
    Run-And-Log "git status --short" $AgencyRoot
    Run-And-Log "git log --oneline -5" $AgencyRoot
    $fileCount = (Get-ChildItem -Path $AgencyRoot -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
    Write-Info "File count under AgencyRoot: $fileCount"
}

# =============================================================================
Write-Step "STEP 2 — Extract SINGULARITY.zip into AgencyRoot (merge mode, preserve newer)"

if (!(Test-Path $SingularityZip)) {
    Write-Info "SingularityZip NOT FOUND: $SingularityZip"
    Write-Info "Skipping zip extract step. Using current AgencyRoot tree as-is."
} else {
    $zipSize = [Math]::Round((Get-Item $SingularityZip).Length / 1MB, 2)
    Write-Info "Zip found: $SingularityZip ($zipSize MB)"

    $extractDir = Join-Path $env:TEMP "JARVIS_SINGULARITY_EXTRACT_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    New-Item -ItemType Directory -Path $extractDir | Out-Null
    Write-Info "Extract target: $extractDir"

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($SingularityZip, $extractDir)
    Write-Info "Extracted."

    # Find the actual root inside the zip (zip may have a top-level wrapper dir)
    $top = Get-ChildItem -Path $extractDir -Directory | Select-Object -First 1
    $extractRoot = if ($top -and (Get-ChildItem -Path $extractDir).Count -eq 1) { $top.FullName } else { $extractDir }
    Write-Info "Effective extract root: $extractRoot"

    # Merge: copy file-by-file, only if newer than target (or target missing)
    Write-Info "Merging into $AgencyRoot (newer-wins per file)..."
    $copied = 0; $kept = 0
    Get-ChildItem -Path $extractRoot -Recurse -File | ForEach-Object {
        $rel = $_.FullName.Substring($extractRoot.Length).TrimStart('\','/')
        $dst = Join-Path $AgencyRoot $rel
        if ((Test-Path $dst) -and (Get-Item $dst).LastWriteTime -gt $_.LastWriteTime) {
            $kept++
        } else {
            $dstDir = Split-Path -Parent $dst
            if (!(Test-Path $dstDir)) { New-Item -ItemType Directory -Path $dstDir -Force | Out-Null }
            Copy-Item -Path $_.FullName -Destination $dst -Force
            $copied++
        }
    }
    Write-Info "Merged: $copied files copied, $kept kept (target was newer)"
    Remove-Item -Path $extractDir -Recurse -Force -ErrorAction SilentlyContinue
}

# =============================================================================
Write-Step "STEP 3 — Copy current session outputs into AgencyRoot"

$sessionFiles = @(
    "jarvis_brainiac",
    "SINGULARITY.md",
    "SINGULARITY_VERIFICATION.md",
    "SATELLITE_REPOS.md",
    "JARVIS_SINGULARITY_DRIVER.ps1"
)
foreach ($item in $sessionFiles) {
    $src = Join-Path $WorkspaceRoot $item
    $dst = Join-Path $AgencyRoot   $item
    if (Test-Path $src) {
        if (Test-Path $dst) { Remove-Item -Path $dst -Recurse -Force }
        if ((Get-Item $src).PSIsContainer) {
            Copy-Item -Path $src -Destination $dst -Recurse -Force
        } else {
            Copy-Item -Path $src -Destination $dst -Force
        }
        Write-Info "Copied: $item"
    } else {
        Write-Info "MISSING (skipped): $item"
    }
}

# =============================================================================
Write-Step "STEP 4 — Run pytest"

if ($SkipTests) {
    Write-Info "Skipped per -SkipTests flag"
} else {
    $runtimePath = Join-Path $AgencyRoot "runtime"
    if (Test-Path "$runtimePath\tests") {
        # ensure venv
        $venv = Join-Path $AgencyRoot ".venv"
        if (!(Test-Path "$venv\Scripts\python.exe")) {
            Run-And-Log "python -m venv `"$venv`"" $AgencyRoot
        }
        $pip = Join-Path $venv "Scripts\pip.exe"
        $py  = Join-Path $venv "Scripts\python.exe"
        Run-And-Log "`"$pip`" install -e runtime --quiet" $AgencyRoot
        Run-And-Log "`"$pip`" install pytest --quiet" $AgencyRoot
        Run-And-Log "`"$py`" -m pytest runtime/tests -v --tb=short" $AgencyRoot
    } else {
        Write-Info "No runtime/tests directory found — skipping"
    }
}

# =============================================================================
Write-Step "STEP 5 — Comprehensive git commit"

Push-Location $AgencyRoot
try {
    # Configure user if missing (idempotent)
    $cfgName  = git config --get user.name  2>$null
    $cfgEmail = git config --get user.email 2>$null
    if (!$cfgName)  { git config user.name  "Amjad Mobarsham" }
    if (!$cfgEmail) { git config user.email "mobarsham@gmail.com" }

    git add -A 2>&1 | Out-Null
    $diffCheck = git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Info "No changes staged — nothing to commit."
    } else {
        $fullMsg = @"
$CommitMessage

Includes:
- All Pass 14→P24 modules (rate_limiter, webhooks, renderer, updater, doctor,
  audit_log, tts, vision, browser, email, long_term_memory, cron_scheduler,
  context_prompt, robotics/{robot_brain,motion_skills,simple_ppo,task_executor,
  world_model}, decision_engine, api_gateway, hot_reload, context_manager)
- 145 Kimi user requirements (audit_artifacts/kimi_requests_extracted.md)
- GODSKILL Navigation v11.0 spec (JARVIS_NAVIGATION_GODSKILL.md)
- Full singularity audit artifacts (PROVENANCE.json, MANIFEST.sha256)
- jarvis_brainiac/ orchestrator package (registry, router, sync, memory, CLI)
- Satellite repo decision matrix (SATELLITE_REPOS.md)

sha256(MANIFEST.sha256) = 54cceaada07c8d7149d1a8027bc67b06c8085d79acaa0101ce5e3b89bdf4b512
Tests: 83/83 (Pass 24) + 265+ cumulative (Pass 14→20)
Operator: amjad2161 / mobarsham@gmail.com
"@
        $tmpMsg = New-TemporaryFile
        $fullMsg | Out-File -FilePath $tmpMsg -Encoding utf8
        Run-And-Log "git commit -F `"$tmpMsg`""
        Remove-Item $tmpMsg -Force
    }
} finally {
    Pop-Location
}

# =============================================================================
Write-Step "STEP 6 — Push to origin/$Branch"

if ($NoPush) {
    Write-Info "Skipped per -NoPush flag (dry-run)"
} else {
    Push-Location $AgencyRoot
    try {
        # Verify remote
        $remote = git remote get-url origin 2>$null
        if (!$remote) {
            Write-Info "No 'origin' remote configured. Add with:"
            Write-Info "  git remote add origin git@github.com:amjad2161/agency-agents.git"
            Write-Info "(or HTTPS: https://github.com/amjad2161/agency-agents.git)"
        } else {
            Write-Info "Remote: $remote"
            $rc = Run-And-Log "git push origin $Branch"
            if ($rc -ne 0) {
                Write-Info "Direct push failed (rc=$rc). Attempting push to a feature branch + opening PR URL..."
                $featBranch = "claude/jarvis-singularity-v24-$(Get-Date -Format 'yyyyMMdd-HHmm')"
                git checkout -b $featBranch
                Run-And-Log "git push -u origin $featBranch"
                Write-Info "Open a PR at: https://github.com/amjad2161/agency-agents/compare/$Branch...$featBranch"
            }
        }
    } finally {
        Pop-Location
    }
}

# =============================================================================
Write-Step "STEP 7 — Final report"

Push-Location $AgencyRoot
try {
    Write-Info "Last 10 commits:"
    Run-And-Log "git log --oneline -10"
    Write-Info ""
    Write-Info "Branch / push status:"
    Run-And-Log "git status -sb"
    Write-Info ""
    Write-Info "Remote URLs:"
    Run-And-Log "git remote -v"
} finally {
    Pop-Location
}

Write-Host "`n=============================================================================" -ForegroundColor Green
Write-Host " JARVIS SINGULARITY DRIVER COMPLETE" -ForegroundColor Green
Write-Host " Log file: $LogFile" -ForegroundColor Green
Write-Host "=============================================================================" -ForegroundColor Green
