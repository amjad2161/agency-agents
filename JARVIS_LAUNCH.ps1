# ============================================================
#  JARVIS_LAUNCH.ps1 — Master launcher for all JARVIS services
#  Pass 20 | Starts: REST API + Dashboard + Scheduler + Robot
# ============================================================

param(
    [int]$ApiPort       = 8765,
    [int]$DashboardPort = 8081,
    [switch]$NoRobot,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root  = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv  = Join-Path $Root "runtime\.venv\Scripts\python.exe"
$PyCmd = if (Test-Path $Venv) { $Venv } else { "python" }

function Write-Step([string]$icon, [string]$msg, [string]$colour = "Cyan") {
    Write-Host "  $icon  $msg" -ForegroundColor $colour
}

function Write-Banner {
    Clear-Host
    Write-Host ""
    Write-Host "  ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗" -ForegroundColor Cyan
    Write-Host "  ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝" -ForegroundColor Cyan
    Write-Host "  ██║███████║██████╔╝██║   ██║██║███████╗" -ForegroundColor Cyan
    Write-Host "  ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║" -ForegroundColor Cyan
    Write-Host "  ██║██║  ██║██║  ██║ ╚████╔╝ ██║███████║" -ForegroundColor Cyan
    Write-Host "  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  JARVIS — Humanoid Robot Brain  |  Pass 20" -ForegroundColor White
    Write-Host "  ─────────────────────────────────────────" -ForegroundColor DarkGray
    Write-Host ""
}

Write-Banner

# ────────────────────────────────────────────
#  1. Environment check
# ────────────────────────────────────────────
Write-Host "[ STARTUP CHECKLIST ]" -ForegroundColor Yellow
Write-Host ""

# Python
try {
    $pyVer = & $PyCmd --version 2>&1
    Write-Step "✅" "Python    : $pyVer"
} catch {
    Write-Step "❌" "Python not found — install Python 3.11+" "Red"
    exit 1
}

# API Key
if ($env:ANTHROPIC_API_KEY) {
    Write-Step "✅" "API Key   : set (${($env:ANTHROPIC_API_KEY).Substring(0,8)}...)"
} else {
    Write-Step "⚠️" "API Key   : ANTHROPIC_API_KEY not set (mock LLM will be used)" "Yellow"
}

# agency package
try {
    & $PyCmd -c "import agency" 2>$null
    Write-Step "✅" "agency    : package importable"
} catch {
    Write-Step "⚠️" "agency    : installing runtime..." "Yellow"
    Push-Location (Join-Path $Root "runtime")
    & $PyCmd -m pip install -e . -q
    Pop-Location
    Write-Step "✅" "agency    : installed"
}

# Flask (dashboard)
try {
    & $PyCmd -c "import flask" 2>$null
    Write-Step "✅" "Flask     : available"
} catch {
    Write-Step "⚠️" "Flask     : installing..." "Yellow"
    & $PyCmd -m pip install flask -q
    Write-Step "✅" "Flask     : installed"
}

Write-Host ""
Write-Host "[ LAUNCHING SERVICES ]" -ForegroundColor Yellow
Write-Host ""

$jobs = @()

# ────────────────────────────────────────────
#  2. REST API server (FastAPI / Pass 14)
# ────────────────────────────────────────────
$apiScript = @"
import sys, os
sys.path.insert(0, r'$Root\runtime')
os.chdir(r'$Root\runtime')
import uvicorn
from agency.server import build_app
app = build_app()
uvicorn.run(app, host='0.0.0.0', port=$ApiPort, log_level='warning')
"@

$apiJob = Start-Job -ScriptBlock {
    param($py, $script)
    & $py -c $script
} -ArgumentList $PyCmd, $apiScript

$jobs += $apiJob
Write-Step "🚀" "REST API  : http://localhost:$ApiPort  (job $($apiJob.Id))"

# ────────────────────────────────────────────
#  3. Dashboard (Flask / Pass 20)
# ────────────────────────────────────────────
$dashScript = @"
import sys
sys.path.insert(0, r'$Root\runtime')
from agency.dashboard import run_dashboard
run_dashboard(port=$DashboardPort)
"@

$dashJob = Start-Job -ScriptBlock {
    param($py, $script)
    & $py -c $script
} -ArgumentList $PyCmd, $dashScript

$jobs += $dashJob
Write-Step "🖥️" "Dashboard : http://localhost:$DashboardPort  (job $($dashJob.Id))"

# ────────────────────────────────────────────
#  4. Scheduler (Pass 13)
# ────────────────────────────────────────────
$schedScript = @"
import sys, time
sys.path.insert(0, r'$Root\runtime')
from agency.scheduler import Scheduler
s = Scheduler()
s.start()
print('[JARVIS Scheduler] running')
try:
    while True:
        time.sleep(30)
except KeyboardInterrupt:
    s.stop()
"@

$schedJob = Start-Job -ScriptBlock {
    param($py, $script)
    & $py -c $script
} -ArgumentList $PyCmd, $schedScript

$jobs += $schedJob
Write-Step "⏰" "Scheduler : background cron runner (job $($schedJob.Id))"

# ────────────────────────────────────────────
#  5. Robot simulation (optional)
# ────────────────────────────────────────────
if (-not $NoRobot) {
    $robotScript = @"
import sys, time
sys.path.insert(0, r'$Root\runtime')
try:
    from agency.robotics.robot_brain import RobotBrain
    from agency.robotics.simulation import SimulationBackend
    from agency.robotics.stt import STTBackend
    brain = RobotBrain(sim_backend=SimulationBackend.MOCK,
                       stt_backend=STTBackend.MOCK, use_vision=False)
    brain.start()
    print('[JARVIS Robot] simulation active')
    while True:
        time.sleep(10)
except Exception as e:
    print(f'[JARVIS Robot] unavailable: {e}')
"@

    $robotJob = Start-Job -ScriptBlock {
        param($py, $script)
        & $py -c $script
    } -ArgumentList $PyCmd, $robotScript

    $jobs += $robotJob
    Write-Step "🤖" "Robot     : mock simulation (job $($robotJob.Id))"
}

# ────────────────────────────────────────────
#  6. Wait for services to initialise
# ────────────────────────────────────────────
Write-Host ""
Write-Host "  Waiting for services to start..." -ForegroundColor DarkGray
Start-Sleep -Seconds 3

# ────────────────────────────────────────────
#  7. Open browser
# ────────────────────────────────────────────
if (-not $NoBrowser) {
    try {
        Start-Process "http://localhost:$DashboardPort"
        Write-Step "🌐" "Browser   : opened dashboard"
    } catch {
        Write-Step "ℹ️" "Browser   : open http://localhost:$DashboardPort manually"
    }
}

# ────────────────────────────────────────────
#  8. Status summary
# ────────────────────────────────────────────
Write-Host ""
Write-Host "  ─────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host "  JARVIS is ONLINE" -ForegroundColor Green
Write-Host ""
Write-Host "  REST API  →  http://localhost:$ApiPort"      -ForegroundColor White
Write-Host "  Dashboard →  http://localhost:$DashboardPort" -ForegroundColor White
Write-Host ""
Write-Host "  Press Ctrl-C to shut down all services." -ForegroundColor DarkGray
Write-Host "  ─────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host ""

# ────────────────────────────────────────────
#  9. Keep alive / Ctrl-C handler
# ────────────────────────────────────────────
try {
    while ($true) {
        # Show any new job output
        foreach ($j in $jobs) {
            $out = Receive-Job -Job $j -ErrorAction SilentlyContinue
            if ($out) { Write-Host "  [job $($j.Id)] $out" -ForegroundColor DarkGray }
        }
        Start-Sleep -Seconds 5
    }
} finally {
    Write-Host ""
    Write-Host "  Shutting down JARVIS..." -ForegroundColor Yellow
    foreach ($j in $jobs) {
        Stop-Job  -Job $j -ErrorAction SilentlyContinue
        Remove-Job -Job $j -ErrorAction SilentlyContinue
    }
    Write-Host "  All services stopped. Goodbye." -ForegroundColor Cyan
}
