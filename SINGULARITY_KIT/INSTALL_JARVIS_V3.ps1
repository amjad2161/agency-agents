[CmdletBinding()]
param(
    [string]$Kit  = "C:\Users\User\OneDrive\מסמכים\Claude\Projects\jarvis brainiac\SINGULARITY_KIT",
    [string]$Root = "C:\Users\User\JARVIS_SINGULARITY"
)
$ErrorActionPreference = 'Continue'
Write-Host "=== JARVIS v3.0 SENTIENT - INSTALL ===" -ForegroundColor Cyan

# Stop existing
Get-Process | Where-Object { $_.Path -like "*JARVIS_SINGULARITY\.venv*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like "*JARVIS*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 2

# Copy main + sentient layer
Copy-Item -LiteralPath (Join-Path $Kit 'JARVIS_BRAINIAC.py') -Destination (Join-Path $Root 'JARVIS_BRAINIAC.py') -Force
Write-Host "[OK] Copied JARVIS_BRAINIAC.py v3.0" -ForegroundColor Green

$brainSrc = Join-Path $Kit 'jarvis_brain'
$brainDst = Join-Path $Root 'jarvis_brain'
if (Test-Path $brainSrc) {
    if (-not (Test-Path $brainDst)) { New-Item -ItemType Directory -Path $brainDst -Force | Out-Null }
    Copy-Item -Path "$brainSrc\*" -Destination $brainDst -Force -Recurse
    Write-Host "[OK] Copied jarvis_brain/ sentient modules" -ForegroundColor Green
}

# Ensure deps
$venvPy = Join-Path $Root '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPy) {
    & $venvPy -m pip install --quiet pyttsx3 sounddevice chromadb 2>&1 | Out-Host
}

# Launch
$pyw = Join-Path $Root '.venv\Scripts\pythonw.exe'
$exe = if (Test-Path -LiteralPath $pyw) { $pyw } else { Join-Path $Root '.venv\Scripts\python.exe' }
Start-Process -FilePath $exe -ArgumentList "`"$(Join-Path $Root 'JARVIS_BRAINIAC.py')`"" -WorkingDirectory $Root -WindowStyle Hidden
Start-Sleep 4

Write-Host ""
Write-Host "========== JARVIS v3.0 SENTIENT LAUNCHED ==========" -ForegroundColor Green
Write-Host "New capabilities:" -ForegroundColor Cyan
Write-Host "  - Persistent memory (SQLite + ChromaDB vector store)"
Write-Host "  - 144+ agency agents auto-registered as skills"
Write-Host "  - GitHub import + integrate: 'github https://github.com/owner/repo'"
Write-Host "  - Remember facts: 'remember name=Amjad'"
Write-Host "  - Recall: 'recall name'"
Write-Host "  - Find agents: 'find skill SQL' or 'which agent for python testing'"
Write-Host "  - Search 33,784 indexed files: 'search files routing'"
Write-Host "  - Autonomous background loop"
