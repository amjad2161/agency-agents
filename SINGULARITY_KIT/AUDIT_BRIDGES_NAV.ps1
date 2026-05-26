# Audit bridges/ + godskill_nav_v11/ structural completeness
[CmdletBinding()]
param(
    [string]$Root = "C:\Users\User\JARVIS_SINGULARITY"
)

$ErrorActionPreference = 'Continue'
Write-Host "=== JARVIS SINGULARITY - Bridges + Nav Audit ===" -ForegroundColor Cyan
Write-Host "Root: $Root"
Write-Host ""

# Bridges expected
$expectedBridges = @(
    'blender','dobot','instagram','lyra2','gitnexus','metaverse','neural_avatar',
    'rtk_ai','scifi_ui','cubesandbox','cadam','jarvs','matrix_wallpaper',
    'personas','working_demos'
)

$bridgesPath = Join-Path $Root 'jarvis_brainiac\bridges'
if (-not (Test-Path -LiteralPath $bridgesPath)) {
    $bridgesPath = Join-Path $Root 'bridges'
}

Write-Host "## Bridges audit ($bridgesPath)" -ForegroundColor Cyan
if (-not (Test-Path -LiteralPath $bridgesPath)) {
    Write-Warning "bridges/ folder not found"
} else {
    $present = Get-ChildItem -LiteralPath $bridgesPath -File -Filter '*.py' -ErrorAction SilentlyContinue | ForEach-Object { $_.BaseName }
    $present = $present | Where-Object { $_ -ne '__init__' }
    foreach ($b in $expectedBridges) {
        if ($present -contains $b) {
            Write-Host "  [OK]   $b.py" -ForegroundColor Green
        } else {
            Write-Host "  [MISS] $b.py" -ForegroundColor Yellow
        }
    }
    $extra = $present | Where-Object { $_ -notin $expectedBridges }
    if ($extra.Count -gt 0) {
        Write-Host "  Extras (not in expected list):"
        foreach ($e in $extra) { Write-Host "    + $e.py" -ForegroundColor DarkGray }
    }
}
Write-Host ""

# godskill_nav_v11 tiers
$tiers = @{
    'tier1_satellite'   = 'GPS/GLONASS/Galileo/BeiDou/QZSS/NavIC + RTK'
    'tier2_indoor'      = 'Visual SLAM/VIO + WiFi RTT + BLE + UWB + magnetic + PDR'
    'tier3_underwater'  = 'INS + DVL + LBL/SBL/USBL + sonar SLAM + bathymetric'
    'tier4_denied'      = 'TRN + LiDAR SLAM + radar + celestial + radio + gravity + magnetic anomaly'
    'tier5_fusion'      = 'EKF/UKF/PF + graph SLAM + data assoc + outlier reject + time sync'
    'tier6_ai'          = 'Deep learning radio maps + ResNet/ViT + Neural SLAM + LSTM + uncertainty'
    'tier7_offline_data'= 'Vector maps + sat imagery + DEM + bathymetry + radio fingerprint + cell + BLE'
}
$navRoots = @(
    (Join-Path $Root 'JARVIS_OMEGA\godskill_navigation'),
    (Join-Path $Root 'godskill_nav_v11')
)
$navRoot = $navRoots | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

Write-Host "## Godskill Navigation audit ($navRoot)" -ForegroundColor Cyan
if (-not $navRoot) {
    Write-Warning "godskill nav root not found"
} else {
    foreach ($t in $tiers.Keys) {
        $tierPath = Join-Path $navRoot $t
        if (Test-Path -LiteralPath $tierPath) {
            $files = Get-ChildItem -LiteralPath $tierPath -File -Recurse -ErrorAction SilentlyContinue
            $count = $files.Count
            $hasReadme = ($files | Where-Object { $_.Name -ieq 'README.md' }).Count -gt 0
            if ($hasReadme) {
                Write-Host ("  [OK]   {0,-22} {1,3} files  ({2})" -f $t, $count, $tiers[$t]) -ForegroundColor Green
            } else {
                Write-Host ("  [WARN] {0,-22} {1,3} files  no README  ({2})" -f $t, $count, $tiers[$t]) -ForegroundColor Yellow
            }
        } else {
            Write-Host ("  [MISS] {0,-22} folder absent  ({1})" -f $t, $tiers[$t]) -ForegroundColor Red
        }
    }
}
Write-Host ""

# Module imports check (quick)
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command python3 -ErrorAction SilentlyContinue).Source }
if ($py) {
    Write-Host "## Python import smoke" -ForegroundColor Cyan
    $env:PYTHONPATH = "$Root;$Root\runtime;$env:PYTHONPATH"
    $smoke = @"
import importlib, sys
mods = ['jarvis_brainiac', 'jarvis_os']
for m in mods:
    try:
        importlib.import_module(m)
        print('  [OK]   ' + m)
    except Exception as e:
        print('  [FAIL] ' + m + ': ' + str(e))
try:
    import jarvis_brainiac.bridges
    print('  [OK]   jarvis_brainiac.bridges')
except Exception as e:
    print('  [FAIL] jarvis_brainiac.bridges: ' + str(e))
"@
    $smokeFile = Join-Path $env:TEMP "_jarvis_audit_smoke.py"
    $smoke | Out-File -LiteralPath $smokeFile -Encoding utf8
    & $py $smokeFile
    Remove-Item -LiteralPath $smokeFile -ErrorAction SilentlyContinue
} else {
    Write-Host "Python not in PATH — skipping import smoke." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Audit complete ===" -ForegroundColor Green
