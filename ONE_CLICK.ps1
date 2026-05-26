# ONE_CLICK.ps1 — Master driver for JARVIS_SUPREME.
# Single command: merge → install → boot → selftest → run → report.
# OFFLINE-FIRST · NO API KEYS · OPEN-SOURCE · ALL-PERMS · IDEMPOTENT
# Author: Claude (autonomous build 2026-05-05)
[CmdletBinding()]
param(
  [string]$Canonical = "",
  [string]$Workspace = "",
  [string]$OllamaModel = "llama3",
  [switch]$SkipMerge,
  [switch]$SkipInstall,
  [switch]$SkipCommit,
  [switch]$SkipRun,
  [switch]$NoOllama
)

if ([string]::IsNullOrEmpty($Canonical)) { $Canonical = $PSScriptRoot }
if ([string]::IsNullOrEmpty($Workspace)) { $Workspace = $PSScriptRoot }
if ([string]::IsNullOrEmpty($Canonical)) { $Canonical = Get-Location }
if ([string]::IsNullOrEmpty($Workspace)) { $Workspace = Get-Location }

$ErrorActionPreference = "Continue"
$started = Get-Date
$logPath = Join-Path $Workspace "one_click_log.txt"
"=== ONE_CLICK start $started ===" | Out-File -FilePath $logPath
function L([string]$m, [string]$color = "Gray") {
  $m | Tee-Object -FilePath $logPath -Append
  Write-Host $m -ForegroundColor $color
}
function Step([int]$n, [int]$total, [string]$title) {
  Write-Host ""
  Write-Host "════════════════════════════════════════" -ForegroundColor Cyan
  Write-Host "  STEP $n/$total : $title" -ForegroundColor Cyan
  Write-Host "════════════════════════════════════════" -ForegroundColor Cyan
  "[$n/$total] $title" | Out-File -FilePath $logPath -Append
}

$total = 7
$exitCodes = @{}

# ── Step 1: Pre-flight + index.lock cleanup ──────────────────────────────────
Step 1 $total "Pre-flight"
if (-not (Test-Path $Canonical)) { L "FATAL: canonical missing $Canonical" "Red"; exit 1 }
if (-not (Test-Path $Workspace)) { L "FATAL: workspace missing $Workspace" "Red"; exit 1 }
$lock = Join-Path $Canonical ".git\index.lock"
if (Test-Path $lock) { Remove-Item $lock -Force -EA SilentlyContinue; L "  cleared .git\index.lock" "Yellow" }

$python = Get-Command python -EA SilentlyContinue
if (-not $python) {
    $localPy = Join-Path $env:LOCALAPPDATA "Programs\Python"
    if (Test-Path $localPy) {
        $exe = Get-ChildItem -Path $localPy -Filter "python.exe" -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($exe) {
            $pyDir = Split-Path $exe.FullName
            $env:PATH = "$pyDir;$pyDir\Scripts;$env:PATH"
            $python = Get-Command python -EA SilentlyContinue
            L "  auto-detected python at $($exe.FullName)" "Green"
        }
    }
}

if (-not $python) { L "FATAL: python not on PATH" "Red"; exit 2 }
L "  python: $($python.Source)" "Green"

# ── Step 2: Merge bundles (newer-wins) ───────────────────────────────────────
Step 2 $total "Merge source bundles"
if (-not $SkipMerge) {
  $merge = Join-Path $Workspace "SUPREME_MERGE.ps1"
  if (Test-Path $merge) {
    & $merge -Canonical $Canonical
    $exitCodes["merge"] = $LASTEXITCODE
    L "  merge exit_code=$($exitCodes['merge'])"
  } else { L "  SUPREME_MERGE.ps1 not found, skipping" "Yellow" }
} else { L "  skipped" "DarkGray" }

# ── Step 3: Install (deps + venv + ollama + autostart + perms config) ────────
Step 3 $total "Install"
if (-not $SkipInstall) {
  $install = Join-Path $Workspace "INSTALL_SUPREME.ps1"
  if (Test-Path $install) {
    $instParams = @{
      Canonical = $Canonical
      Workspace = $Workspace
      OllamaModel = $OllamaModel
    }
    if ($NoOllama) { $instParams["SkipOllama"] = $true }
    & $install @instParams
    $exitCodes["install"] = $LASTEXITCODE
    L "  install exit_code=$($exitCodes['install'])"
  } else { L "  INSTALL_SUPREME.ps1 not found" "Red"; exit 3 }
} else { L "  skipped" "DarkGray" }

# ── Step 4: Selftest ─────────────────────────────────────────────────────────
Step 4 $total "Selftest"
$env:AGENCY_ROOT = $Canonical
$env:OFFLINE_MODE = "1"
$env:ALLOW_ALL = "1"
$env:JARVIS_PERM_LEVEL = "GOD"
$env:JARVIS_REQUIRE_API_KEYS = "0"
$env:PYTHONUTF8 = "1"
$selftest = Join-Path $Workspace "supreme_selftest.py"
if (Test-Path $selftest) {
  python $selftest 2>&1 | Tee-Object -FilePath $logPath -Append
  $exitCodes["selftest"] = $LASTEXITCODE
  L "  selftest exit_code=$($exitCodes['selftest']) (0=all green)" $(if($exitCodes['selftest'] -eq 0){"Green"}else{"Yellow"})
} else { L "  supreme_selftest.py not found" "Yellow" }

# ── Step 5: Health (boot via supreme) ────────────────────────────────────────
Step 5 $total "Health snapshot"
$supreme = Join-Path $Workspace "JARVIS_SUPREME.py"
if (Test-Path $supreme) {
  python $supreme boot 2>&1 | Tee-Object -FilePath $logPath -Append | Out-Null
  $exitCodes["boot"] = $LASTEXITCODE
  L "  boot exit_code=$($exitCodes['boot']) (0=healthy, 1=degraded, 2=failed)"
} else { L "  JARVIS_SUPREME.py not found" "Red"; exit 4 }

# ── Step 6: Commit + push ────────────────────────────────────────────────────
Step 6 $total "Commit + push"
if (-not $SkipCommit) {
  Push-Location $Canonical
  try {
    $cfgName  = git config --get user.name  2>$null
    $cfgEmail = git config --get user.email 2>$null
    if (!$cfgName)  { git config user.name  "Amjad Mobarsham" }
    if (!$cfgEmail) { git config user.email "mobarsham@gmail.com" }
    git add --renormalize . 2>&1 | Out-Null
    git add -A 2>&1 | Out-Null
    $changes = git status --porcelain
    if ($changes) {
      $msg = "supreme: ONE_CLICK consolidation 2026-05-05 + offline + all-perms + selftest"
      git commit --no-verify -m $msg 2>&1 | Tee-Object -FilePath $logPath -Append
      git push origin main 2>&1 | Tee-Object -FilePath $logPath -Append
      $exitCodes["push"] = $LASTEXITCODE
      L "  push exit_code=$($exitCodes['push'])"
    } else {
      L "  nothing to commit" "DarkGray"
      $exitCodes["push"] = 0
    }
  } finally { Pop-Location }
} else { L "  skipped" "DarkGray" }

# ── Step 7: Run (background daemons) ─────────────────────────────────────────
Step 7 $total "Run supreme (background)"
if (-not $SkipRun) {
  $launcher = Join-Path $Workspace "JARVIS_SUPREME.ps1"
  if (Test-Path $launcher) {
    Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -WindowStyle Minimized -File `"$launcher`" -Cmd run" -WorkingDirectory $Workspace
    L "  launched JARVIS_SUPREME run in background" "Green"
    Start-Sleep -Seconds 3
  } else { L "  launcher not found" "Yellow" }
} else { L "  skipped" "DarkGray" }

# ── Final summary ────────────────────────────────────────────────────────────
$elapsed = ((Get-Date) - $started).TotalSeconds
Write-Host ""
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  ONE_CLICK SUMMARY                                     " -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════" -ForegroundColor Cyan
foreach ($k in $exitCodes.Keys) {
  $v = $exitCodes[$k]
  $c = if ($v -eq 0) { "Green" } else { "Yellow" }
  Write-Host ("  {0,-12}: exit_code={1}" -f $k, $v) -ForegroundColor $c
}
Write-Host ("  elapsed_s   : {0:N1}" -f $elapsed)
Write-Host "  log         : $logPath"
Write-Host ""
$anyFail = ($exitCodes.Values | Where-Object { $_ -ne 0 }).Count
if ($anyFail -eq 0) {
  Write-Host "✅ ONE_CLICK COMPLETE — supreme online" -ForegroundColor Green
  Write-Host "   chat:    .\JARVIS_SUPREME.ps1 -Cmd chat" -ForegroundColor Green
  Write-Host "   route:   .\JARVIS_SUPREME.ps1 -Cmd route -Query 'your task'" -ForegroundColor Green
  exit 0
} else {
  Write-Host "⚠️  ONE_CLICK partial — $anyFail step(s) non-zero. See $logPath" -ForegroundColor Yellow
  exit $anyFail
}
