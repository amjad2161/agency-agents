# Post-merge verifier: structural sanity checks on JARVIS_SINGULARITY
[CmdletBinding()]
param([string]$Root = "C:\Users\User\JARVIS_SINGULARITY")

$ErrorActionPreference = 'Continue'
$pass = 0; $fail = 0; $warn = 0
$results = @()

function Check {
    param([string]$Name, [scriptblock]$Test, [string]$Severity='fail')
    try {
        $ok = & $Test
        if ($ok) {
            $script:pass++
            $script:results += [pscustomobject]@{ Status='PASS'; Name=$Name; Detail='' }
        } else {
            if ($Severity -eq 'warn') { $script:warn++; $stat='WARN' } else { $script:fail++; $stat='FAIL' }
            $script:results += [pscustomobject]@{ Status=$stat; Name=$Name; Detail='' }
        }
    } catch {
        $script:fail++
        $script:results += [pscustomobject]@{ Status='FAIL'; Name=$Name; Detail=$_.Exception.Message }
    }
}

Write-Host "=== Verifying $Root ===" -ForegroundColor Cyan

Check 'destination exists'           { Test-Path $Root }
Check 'agents dir present'           { Test-Path (Join-Path $Root 'agents') }
Check 'runtime dir present'          { Test-Path (Join-Path $Root 'runtime') }
Check 'jarvis_brainiac module'       { Test-Path (Join-Path $Root 'jarvis_brainiac\__init__.py') }
Check 'jarvis_os module'             { Test-Path (Join-Path $Root 'jarvis_os\__init__.py') }
Check 'godskill_server present'      { Test-Path (Join-Path $Root 'godskill_server\server.py') }
Check 'JARVIS_OMEGA package'         { Test-Path (Join-Path $Root 'JARVIS_OMEGA\omega.py') }
Check 'README.md present'            { Test-Path (Join-Path $Root 'README.md') }
Check 'merge report generated'      { Test-Path (Join-Path $Root 'MERGE_REPORT.md') }
Check 'manifest CSV generated'      { Test-Path (Join-Path $Root '_MANIFEST.csv') }
Check 'git initialized'              { Test-Path (Join-Path $Root '.git') }
Check '.gitignore present'           { Test-Path (Join-Path $Root '.gitignore') }
Check 'no >100MB files'              { (Get-ChildItem -Path $Root -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Length -gt 100MB } | Measure-Object).Count -eq 0 }
Check 'no __pycache__ leaked'        -Severity warn { (Get-ChildItem -Path $Root -Recurse -Directory -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq '__pycache__' } | Measure-Object).Count -eq 0 }
Check 'no .venv leaked'              { (Get-ChildItem -Path $Root -Recurse -Directory -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -in '.venv','venv' } | Measure-Object).Count -eq 0 }
Check 'no node_modules leaked'       { (Get-ChildItem -Path $Root -Recurse -Directory -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq 'node_modules' } | Measure-Object).Count -eq 0 }
Check 'no Ollama blob dirs'          { (Get-ChildItem -Path $Root -Recurse -Directory -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq 'blobs' } | Measure-Object).Count -eq 0 }

# Stats
$allFiles = Get-ChildItem -Path $Root -Recurse -File -ErrorAction SilentlyContinue
$totalSize = ($allFiles | Measure-Object -Property Length -Sum).Sum
$totalCount = $allFiles.Count
Write-Host ""
$results | Format-Table -AutoSize | Out-String | Write-Host

$human = if ($totalSize -ge 1GB) {"{0:N2} GB" -f ($totalSize/1GB)} elseif ($totalSize -ge 1MB) {"{0:N2} MB" -f ($totalSize/1MB)} else {"$totalSize B"}
Write-Host "Total files: $totalCount   Total size: $human" -ForegroundColor Cyan
Write-Host "PASS=$pass  FAIL=$fail  WARN=$warn" -ForegroundColor $(if($fail -eq 0){'Green'}else{'Red'})

# Try import smoke test
Write-Host "`n=== Python smoke test ===" -ForegroundColor Cyan
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command python3 -ErrorAction SilentlyContinue).Source }
if ($py) {
    Push-Location $Root
    try {
        $env:PYTHONPATH = "$Root;$Root\runtime;$env:PYTHONPATH"
        $smoke = @'
import importlib, sys
mods = ["jarvis_brainiac", "jarvis_os"]
ok=0; fail=0
for m in mods:
    try:
        importlib.import_module(m); ok+=1; print(f"[OK]   import {m}")
    except Exception as e:
        fail+=1; print(f"[FAIL] import {m}: {e}")
print(f"smoke: ok={ok} fail={fail}")
sys.exit(0 if fail==0 else 1)
'@
        $smoke | & $py -
    } finally { Pop-Location }
} else {
    Write-Host "Python not in PATH — skipping smoke test." -ForegroundColor Yellow
}

if ($fail -gt 0) { exit 1 } else { exit 0 }
