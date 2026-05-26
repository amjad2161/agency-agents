# DEPLOY_BRAINIAC.ps1
# 1. Copy JARVIS_BRAINIAC.py from kit -> destination
# 2. Copy launcher .cmd
# 3. Create desktop shortcut
# 4. Kill any running agency serve / uvicorn on :8765
# 5. Launch JARVIS BRAINIAC native app

[CmdletBinding()]
param(
    [string]$Kit  = "C:\Users\User\OneDrive\מסמכים\Claude\Projects\jarvis brainiac\SINGULARITY_KIT",
    [string]$Root = "C:\Users\User\JARVIS_SINGULARITY"
)

$ErrorActionPreference = 'Continue'
Write-Host "=== JARVIS BRAINIAC - DEPLOY + LAUNCH ===" -ForegroundColor Cyan

# Step 1: copy files
$srcPy  = Join-Path $Kit 'JARVIS_BRAINIAC.py'
$srcCmd = Join-Path $Kit 'JARVIS_BRAINIAC.cmd'
$dstPy  = Join-Path $Root 'JARVIS_BRAINIAC.py'
$dstCmd = Join-Path $Root 'JARVIS_BRAINIAC.cmd'

if (Test-Path -LiteralPath $srcPy) {
    Copy-Item -LiteralPath $srcPy -Destination $dstPy -Force
    Write-Host "[OK] Copied JARVIS_BRAINIAC.py to $dstPy" -ForegroundColor Green
} else {
    Write-Warning "Missing: $srcPy"
}
if (Test-Path -LiteralPath $srcCmd) {
    Copy-Item -LiteralPath $srcCmd -Destination $dstCmd -Force
    Write-Host "[OK] Copied JARVIS_BRAINIAC.cmd to $dstCmd" -ForegroundColor Green
}

# Step 2: kill agency serve / uvicorn on :8765
Write-Host ""
Write-Host "=== Stopping any agency serve on :8765 ===" -ForegroundColor Cyan
$pids = @()
try {
    $conns = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
    if ($conns) { $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique }
} catch {}
foreach ($pid_ in $pids) {
    try {
        $proc = Get-Process -Id $pid_ -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "  Stopping PID $pid_ ($($proc.ProcessName))" -ForegroundColor Yellow
            Stop-Process -Id $pid_ -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}
if (-not $pids) { Write-Host "  No process listening on :8765" }

# Step 3: desktop shortcut
Write-Host ""
Write-Host "=== Creating desktop shortcut ===" -ForegroundColor Cyan
$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop 'JARVIS BRAINIAC.lnk'
try {
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($lnkPath)
    $sc.TargetPath = $dstCmd
    $sc.WorkingDirectory = $Root
    $sc.IconLocation = "$env:SystemRoot\System32\imageres.dll, 109"
    $sc.Description = "JARVIS BRAINIAC v0.1.0-singularity"
    $sc.Save()
    Write-Host "[OK] Shortcut created: $lnkPath" -ForegroundColor Green
} catch {
    Write-Warning "Shortcut creation failed: $_"
}

# Start Menu entry
$startMenu = [Environment]::GetFolderPath('StartMenu')
$progDir = Join-Path $startMenu 'Programs\JARVIS BRAINIAC'
if (-not (Test-Path -LiteralPath $progDir)) { New-Item -ItemType Directory -Path $progDir -Force | Out-Null }
$smLnk = Join-Path $progDir 'JARVIS BRAINIAC.lnk'
try {
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($smLnk)
    $sc.TargetPath = $dstCmd
    $sc.WorkingDirectory = $Root
    $sc.IconLocation = "$env:SystemRoot\System32\imageres.dll, 109"
    $sc.Description = "JARVIS BRAINIAC v0.1.0-singularity"
    $sc.Save()
    Write-Host "[OK] Start Menu entry: $smLnk" -ForegroundColor Green
} catch {}

# Step 4: launch JARVIS BRAINIAC
Write-Host ""
Write-Host "=== Launching JARVIS BRAINIAC ===" -ForegroundColor Cyan
$pyw = Join-Path $Root '.venv\Scripts\pythonw.exe'
$py  = Join-Path $Root '.venv\Scripts\python.exe'
$exe = if (Test-Path -LiteralPath $pyw) { $pyw } elseif (Test-Path -LiteralPath $py) { $py } else { $null }
if (-not $exe) {
    Write-Error 'Venv python not found - run LAUNCH_POST_MERGE_SETUP.cmd first'
    exit 1
}
Write-Host ("Launching: " + $exe + " " + $dstPy) -ForegroundColor Green
Start-Process -FilePath $exe -ArgumentList "`"$dstPy`"" -WorkingDirectory $Root -WindowStyle Hidden
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "========== JARVIS BRAINIAC LAUNCHED ==========" -ForegroundColor Green
Write-Host "Window should appear within seconds. Check system tray for the cyan orb icon."
Write-Host "Single-click tray = toggle visibility."
Write-Host "Right-click tray = Show/Quit menu."
Write-Host ""
