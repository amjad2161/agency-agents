# JARVIS watchdog - keeps JARVIS_BRAINIAC.py alive forever
$Root = "C:\Users\User\JARVIS_SINGULARITY"
$pyw = Join-Path $Root '.venv\Scripts\pythonw.exe'
$py  = Join-Path $Root '.venv\Scripts\python.exe'
$exe = if (Test-Path -LiteralPath $pyw) { $pyw } else { $py }
$script = Join-Path $Root 'JARVIS_BRAINIAC.py'

while ($true) {
    # Check if JARVIS already running
    $running = $false
    Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
        ForEach-Object { if ($_.CommandLine -like "*JARVIS_BRAINIAC*") { $running = $true } }

    if (-not $running) {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] JARVIS not running - starting..."
        Start-Process -FilePath $exe -ArgumentList "`"$script`"" -WorkingDirectory $Root -WindowStyle Hidden
        Start-Sleep 8
    }
    Start-Sleep 15
}
