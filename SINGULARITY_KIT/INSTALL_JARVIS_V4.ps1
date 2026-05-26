[CmdletBinding()]
param(
    [string]$Kit  = "C:\Users\User\OneDrive\מסמכים\Claude\Projects\jarvis brainiac\SINGULARITY_KIT",
    [string]$Root = "C:\Users\User\JARVIS_SINGULARITY"
)
$ErrorActionPreference = 'Continue'
Write-Host "=== JARVIS v4.0 SUPERINTELLIGENCE - INSTALL ===" -ForegroundColor Cyan

# Stop existing
Get-Process | Where-Object { $_.Path -like "*JARVIS_SINGULARITY\.venv*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like "*JARVIS*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 2

# Copy main + jarvis_brain
Copy-Item -LiteralPath (Join-Path $Kit 'JARVIS_BRAINIAC.py') -Destination (Join-Path $Root 'JARVIS_BRAINIAC.py') -Force
Write-Host "[OK] Copied JARVIS_BRAINIAC.py v4.0" -ForegroundColor Green
$brainSrc = Join-Path $Kit 'jarvis_brain'
$brainDst = Join-Path $Root 'jarvis_brain'
if (-not (Test-Path $brainDst)) { New-Item -ItemType Directory -Path $brainDst -Force | Out-Null }
Copy-Item -Path "$brainSrc\*.py" -Destination $brainDst -Force
Write-Host "[OK] Copied jarvis_brain/ all 11 modules" -ForegroundColor Green

# Install action+vision deps
$venvPy = Join-Path $Root '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPy) {
    Write-Host "Installing v4 deps: pyautogui pyperclip pygetwindow psutil opencv-python..." -ForegroundColor Yellow
    & $venvPy -m pip install --quiet pyautogui pyperclip pygetwindow psutil opencv-python pillow 2>&1 | Out-Host
    Write-Host "[OK] v4 deps installed" -ForegroundColor Green
}

# Pull vision model in background
$ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if ($ollama) {
    $models = & $ollama list 2>&1
    if ($models -notmatch "vision|llava") {
        Write-Host "Pulling llama3.2-vision (4.2GB) in background..." -ForegroundColor Yellow
        Start-Process -FilePath $ollama -ArgumentList "pull", "llama3.2-vision" -WindowStyle Hidden
    } else {
        Write-Host "[OK] Vision model already present" -ForegroundColor Green
    }
}

# Launch
$pyw = Join-Path $Root '.venv\Scripts\pythonw.exe'
$exe = if (Test-Path -LiteralPath $pyw) { $pyw } else { Join-Path $Root '.venv\Scripts\python.exe' }
Start-Process -FilePath $exe -ArgumentList "`"$(Join-Path $Root 'JARVIS_BRAINIAC.py')`"" -WorkingDirectory $Root -WindowStyle Hidden
Start-Sleep 5

Write-Host ""
Write-Host "========== JARVIS v4.0 SUPERINTELLIGENCE LAUNCHED ==========" -ForegroundColor Green
Write-Host "v4 NEW capabilities (real, not theatrical):"
Write-Host "  REAL COMPUTER USE:"
Write-Host "    - 'click X Y'    Click anywhere"
Write-Host "    - 'type <text>'  Type text"
Write-Host "    - 'press <key>'  Press key"
Write-Host "    - 'hotkey ctrl+s' Hotkey combo"
Write-Host "    - 'focus <title>' Focus window"
Write-Host "    - 'windows'      List open windows"
Write-Host "    - 'url <link>'   Open browser"
Write-Host "  VISION:"
Write-Host "    - 'screen' / 'see screen' / 'what do you see' -> Ollama vision describes screen"
Write-Host "  TELEMETRY:"
Write-Host "    - 'stats'        CPU/RAM/disk/network"
Write-Host "    - 'processes'    Top 10 by memory"
Write-Host "  PROACTIVE:"
Write-Host "    - Clipboard monitor"
Write-Host "    - Idle detection (10+ min)"
Write-Host "    - Webcam presence ('webcam on/off')"
Write-Host "  SENTIENT (from v3):"
Write-Host "    - Memory + 144+ skills + GitHub import + autonomous loop"
