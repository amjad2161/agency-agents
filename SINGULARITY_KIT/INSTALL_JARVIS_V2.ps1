[CmdletBinding()]
param(
    [string]$Kit  = "C:\Users\User\OneDrive\מסמכים\Claude\Projects\jarvis brainiac\SINGULARITY_KIT",
    [string]$Root = "C:\Users\User\JARVIS_SINGULARITY"
)
$ErrorActionPreference = 'Continue'
Write-Host "=== JARVIS v2.0 - Iron Man Edition - INSTALL ===" -ForegroundColor Cyan

# Stop existing
Write-Host "Stopping existing JARVIS instances..." -ForegroundColor Yellow
Get-Process | Where-Object { $_.Path -like "*JARVIS_SINGULARITY\.venv*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like "*JARVIS*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Copy
Copy-Item -LiteralPath (Join-Path $Kit 'JARVIS_BRAINIAC.py') -Destination (Join-Path $Root 'JARVIS_BRAINIAC.py') -Force
Write-Host "[OK] Copied JARVIS_BRAINIAC.py v2.0" -ForegroundColor Green

# Voice deps
$venvPy = Join-Path $Root '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPy) {
    Write-Host "Installing voice deps (pyttsx3, sounddevice)..." -ForegroundColor Yellow
    & $venvPy -m pip install --quiet pyttsx3 sounddevice 2>&1 | Out-Host
}

# Check if Ollama is installed and start it
Write-Host ""
Write-Host "=== Checking Ollama (local AI brain) ===" -ForegroundColor Cyan
$ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if ($ollama) {
    Write-Host "[OK] Ollama found: $ollama" -ForegroundColor Green
    # Ensure ollama service is running
    if (-not (Get-Process ollama -ErrorAction SilentlyContinue)) {
        Write-Host "Starting Ollama service..."
        Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 3
    }
    # List models
    Write-Host "Available models:"
    & $ollama list 2>&1 | Out-Host
    # Try pulling a small model if none
    $models = & $ollama list 2>&1
    if ($models -notmatch "llama|qwen|mistral|phi|gemma") {
        Write-Host "No chat model found. Pulling llama3.2 (small, fast, multilingual)..." -ForegroundColor Yellow
        Start-Process -FilePath $ollama -ArgumentList "pull", "llama3.2" -WindowStyle Hidden
        Write-Host "(Pull running in background - JARVIS will detect it once complete)" -ForegroundColor Yellow
    }
} else {
    Write-Host "[WARN] Ollama not in PATH. JARVIS will use local fallback." -ForegroundColor Yellow
    Write-Host "       To install Ollama: https://ollama.com/download" -ForegroundColor DarkGray
}

# Autostart
$startup = [Environment]::GetFolderPath('Startup')
$lnkPath = Join-Path $startup 'JARVIS BRAINIAC.lnk'
$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnkPath)
$sc.TargetPath = (Join-Path $Root '.venv\Scripts\pythonw.exe')
$sc.Arguments = "`"" + (Join-Path $Root 'JARVIS_BRAINIAC.py') + "`""
$sc.WorkingDirectory = $Root
$sc.WindowStyle = 7
$sc.IconLocation = "$env:SystemRoot\System32\imageres.dll, 109"
$sc.Description = "JARVIS BRAINIAC v2.0"
$sc.Save()
Write-Host "[OK] Autostart on login installed" -ForegroundColor Green

# Launch
$pyw = Join-Path $Root '.venv\Scripts\pythonw.exe'
$py  = Join-Path $Root '.venv\Scripts\python.exe'
$exe = if (Test-Path -LiteralPath $pyw) { $pyw } else { $py }
$script = Join-Path $Root 'JARVIS_BRAINIAC.py'
Write-Host ""
Write-Host "Launching JARVIS v2.0..." -ForegroundColor Green
Start-Process -FilePath $exe -ArgumentList "`"$script`"" -WorkingDirectory $Root -WindowStyle Hidden
Start-Sleep -Seconds 4

Write-Host ""
Write-Host "========== JARVIS v2.0 LAUNCHED ==========" -ForegroundColor Green
Write-Host "Brain: Ollama local (no API key needed)" -ForegroundColor Cyan
Write-Host "Always-on mic | Wake word | Double-clap | Tray | Multi-lang | God-mode"
