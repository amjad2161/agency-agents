# INSTALL_AUTOSTART.ps1 — register JARVIS as Windows OS-level service
# Adds tray + hotkey to startup; installs deps into venv

$AgencyRoot = "$env:USERPROFILE\agency"
$JarvisOS   = Join-Path $AgencyRoot "jarvis_os"
$Venv       = Join-Path $AgencyRoot ".venv"
$Pip        = Join-Path $Venv "Scripts\pip.exe"
$Python     = Join-Path $Venv "Scripts\python.exe"
$PythonW    = Join-Path $Venv "Scripts\pythonw.exe"

function Step($t) { Write-Host "`n========== $t ==========" -ForegroundColor Cyan }
function W($m,$c="White") { Write-Host "  $m" -ForegroundColor $c }

Step "STEP 1 — Verify agency repo + venv"
if (!(Test-Path $AgencyRoot)) { W "agency missing at $AgencyRoot" Red; exit 1 }
if (!(Test-Path $Venv))       { W "Creating venv..." Yellow; python -m venv $Venv }
W "agency: $AgencyRoot" Green
W "venv:   $Venv" Green

Step "STEP 2 — Copy jarvis_os/ into agency repo"
$srcOS = Join-Path $PSScriptRoot "jarvis_os"
$dstOS = Join-Path $AgencyRoot "jarvis_os"
if (Test-Path $dstOS) { Remove-Item $dstOS -Recurse -Force }
Copy-Item $srcOS $dstOS -Recurse -Force
W "Copied jarvis_os/ → $dstOS" Green

Step "STEP 3 — Install Python deps (pystray, Pillow, keyboard)"
& $Pip install pystray Pillow keyboard --quiet 2>&1 | Where-Object { $_ -match "error|installed|Successfully" } | ForEach-Object { W $_ }

Step "STEP 4 — Create launcher batch files"
$trayBat = Join-Path $AgencyRoot "jarvis_tray.bat"
@"
@echo off
cd /d "$AgencyRoot"
start "" "$PythonW" "$dstOS\tray.py"
start "" "$PythonW" "$dstOS\hotkey_listener.py"
"@ | Out-File $trayBat -Encoding ascii
W "Wrote: $trayBat" Green

$chatBat = Join-Path $AgencyRoot "jarvis_chat.bat"
@"
@echo off
cd /d "$AgencyRoot"
start "" "$PythonW" "$dstOS\native_chat.py"
"@ | Out-File $chatBat -Encoding ascii
W "Wrote: $chatBat" Green

Step "STEP 5 — Add to Windows startup folder"
$startup = [Environment]::GetFolderPath("Startup")
$shortcut = Join-Path $startup "JARVIS.lnk"
$wsh = New-Object -ComObject WScript.Shell
$lnk = $wsh.CreateShortcut($shortcut)
$lnk.TargetPath = $trayBat
$lnk.WorkingDirectory = $AgencyRoot
$lnk.Description = "JARVIS BRAINIAC v25 — system tray + hotkey"
$lnk.IconLocation = "$Python,0"
$lnk.WindowStyle = 7  # minimized
$lnk.Save()
W "Startup shortcut: $shortcut" Green

Step "STEP 6 — Add Start Menu shortcut"
$startMenu = [Environment]::GetFolderPath("StartMenu")
$smShortcut = Join-Path $startMenu "Programs\JARVIS BRAINIAC.lnk"
$lnk2 = $wsh.CreateShortcut($smShortcut)
$lnk2.TargetPath = $chatBat
$lnk2.WorkingDirectory = $AgencyRoot
$lnk2.Description = "Open JARVIS native chat window"
$lnk2.IconLocation = "$Python,0"
$lnk2.Save()
W "Start Menu: $smShortcut" Green

Step "STEP 7 — Start now (no reboot needed)"
Start-Process $trayBat -WindowStyle Hidden
W "Tray + hotkey running. Look for J icon in notification area." Green
W "Press Win+J to open chat window from anywhere." Cyan

Write-Host "`n=============================================================" -ForegroundColor Green
Write-Host "  JARVIS INSTALLED AS WINDOWS OS COMPONENT" -ForegroundColor Green
Write-Host "=============================================================" -ForegroundColor Green
Write-Host "  • Tray icon: notification area (right-click for menu)"
Write-Host "  • Global hotkey: Win+J → opens chat"
Write-Host "  • Auto-starts on every Windows boot"
Write-Host "  • Server runs in background"
Write-Host "  • No browser required"
Write-Host ""
Read-Host "Press Enter to close"
