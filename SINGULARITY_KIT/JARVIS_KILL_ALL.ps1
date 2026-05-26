# Kill EVERY JARVIS instance no matter what version
Write-Host "=== KILLING ALL JARVIS / Python instances ===" -ForegroundColor Red

# 1. Kill by venv path
Get-Process | Where-Object { $_.Path -like "*JARVIS*" -or $_.Path -like "*\.venv\Scripts\*" } |
    ForEach-Object { Write-Host "Killing: $($_.ProcessName) PID $($_.Id) -> $($_.Path)"; Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }

# 2. Kill all pythonw and python with JARVIS in cmdline
$wmis = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue
foreach ($p in $wmis) {
    if ($p.CommandLine -like "*JARVIS_BRAINIAC*" -or $p.CommandLine -like "*JARVIS_SINGULARITY*") {
        Write-Host "Killing python PID $($p.ProcessId) -> $($p.CommandLine)"
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

# 3. Kill any lingering JARVIS BRAINIAC v25 windows
Get-Process | Where-Object { $_.MainWindowTitle -like "*JARVIS BRAINIAC*" } |
    ForEach-Object { Write-Host "Killing window: $($_.MainWindowTitle) PID $($_.Id)"; Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }

Start-Sleep 2
Write-Host "[OK] All killed" -ForegroundColor Green
