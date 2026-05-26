[CmdletBinding()]
param(
    [string]$Kit  = "C:\Users\User\OneDrive\מסמכים\Claude\Projects\jarvis brainiac\SINGULARITY_KIT",
    [string]$Root = "C:\Users\User\JARVIS_SINGULARITY"
)
$ErrorActionPreference = 'Continue'
Write-Host "=== JARVIS RESET + V4 RELAUNCH ===" -ForegroundColor Cyan

# 1. Kill EVERY JARVIS instance
Write-Host "[1/5] Killing every JARVIS instance..." -ForegroundColor Yellow
& "$Kit\JARVIS_KILL_ALL.ps1"

# 2. Copy fresh v4.0 files
Write-Host "[2/5] Deploying fresh v4.0..." -ForegroundColor Yellow
Copy-Item -LiteralPath (Join-Path $Kit 'JARVIS_BRAINIAC.py') -Destination (Join-Path $Root 'JARVIS_BRAINIAC.py') -Force
$brainSrc = Join-Path $Kit 'jarvis_brain'
$brainDst = Join-Path $Root 'jarvis_brain'
if (-not (Test-Path $brainDst)) { New-Item -ItemType Directory -Path $brainDst -Force | Out-Null }
Copy-Item -Path "$brainSrc\*.py" -Destination $brainDst -Force
Write-Host "    [OK]" -ForegroundColor Green

# 3. Replace autostart shortcut to use watchdog instead of plain python
Write-Host "[3/5] Installing watchdog as autostart..." -ForegroundColor Yellow
$startup = [Environment]::GetFolderPath('Startup')
$lnkPath = Join-Path $startup 'JARVIS BRAINIAC.lnk'
$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnkPath)
$sc.TargetPath = (Join-Path $Kit 'JARVIS_WATCHDOG.cmd')
$sc.WorkingDirectory = $Kit
$sc.WindowStyle = 7
$sc.IconLocation = "$env:SystemRoot\System32\imageres.dll, 109"
$sc.Description = "JARVIS BRAINIAC watchdog - keeps alive"
$sc.Save()
Write-Host "    [OK] Autostart now points to watchdog" -ForegroundColor Green

# 4. Start watchdog in background NOW (will auto-launch JARVIS)
Write-Host "[4/5] Starting watchdog now..." -ForegroundColor Yellow
Start-Process -FilePath "powershell" -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", "`"$Kit\JARVIS_WATCHDOG.ps1`"" -WindowStyle Hidden
Start-Sleep 10
Write-Host "    [OK] Watchdog running. JARVIS should appear within 8 seconds." -ForegroundColor Green

# 5. Verify JARVIS launched
Write-Host "[5/5] Verifying JARVIS launched..." -ForegroundColor Yellow
$found = $false
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
    ForEach-Object { if ($_.CommandLine -like "*JARVIS_BRAINIAC*") { $found = $true; Write-Host "    [OK] PID $($_.ProcessId) running" -ForegroundColor Green } }
if (-not $found) {
    Write-Host "    [WARN] JARVIS not yet detected - watchdog will retry every 15s" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========== JARVIS V4 RESET COMPLETE ==========" -ForegroundColor Green
Write-Host "  - All zombie versions killed"
Write-Host "  - Fresh v4.0 deployed (BrainOrb + Neuralink + StatsPanel)"
Write-Host "  - Single-instance lock active (port 47291)"
Write-Host "  - Watchdog running (auto-restart if killed)"
Write-Host "  - Autostart on login: WATCHDOG (not plain python)"
Write-Host ""
Write-Host "Test: close JARVIS window. Watchdog will revive it within 15s."
Write-Host "Test: say 'Jarvis' or double-clap. Window summons + speaks 'Yes sir?'"
