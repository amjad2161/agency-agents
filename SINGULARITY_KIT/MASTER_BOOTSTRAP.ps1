# JARVIS SINGULARITY - MASTER BOOTSTRAP
# Runs all post-merge ops end-to-end, writes BOOTSTRAP_REPORT.md
# Steps:
#   1. POST_MERGE_SETUP   (venv + pip install runtime)
#   2. VERIFY             (structural checks + Python smoke)
#   3. GENERATE_AGENT_INDEX
#   4. AUDIT              (bridges + nav tier check)
#   5. TAG                (git tag baseline)
#   6. Write BOOTSTRAP_REPORT.md inside destination

[CmdletBinding()]
param(
    [string]$Root = "C:\Users\User\JARVIS_SINGULARITY",
    [string]$Kit  = "C:\Users\User\OneDrive\מסמכים\Claude\Projects\jarvis brainiac\SINGULARITY_KIT"
)

$ErrorActionPreference = 'Continue'
$report = New-Object System.Collections.Generic.List[string]
$report.Add('# JARVIS SINGULARITY - Bootstrap Report')
$report.Add('')
$report.Add('**Started:** ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
$report.Add('')

function Step {
    param([string]$Title, [scriptblock]$Body)
    Write-Host ''
    Write-Host ('================ ' + $Title + ' ================') -ForegroundColor Cyan
    $report.Add('## ' + $Title)
    $report.Add('')
    try {
        & $Body
        $report.Add('Status: PASS')
    } catch {
        Write-Warning ($Title + ' failed: ' + $_.Exception.Message)
        $report.Add('Status: FAIL - ' + $_.Exception.Message)
    }
    $report.Add('')
}

# Step 1: POST_MERGE_SETUP
Step 'POST_MERGE_SETUP' {
    & (Join-Path $Kit 'POST_MERGE_SETUP.ps1') -Root $Root
}

# Step 2: VERIFY
Step 'VERIFY' {
    & (Join-Path $Kit 'VERIFY_SINGULARITY.ps1') -Root $Root
}

# Step 3: AGENT_INDEX
Step 'GENERATE_AGENT_INDEX' {
    & (Join-Path $Kit 'GENERATE_AGENT_INDEX.ps1') -Root $Root
}

# Step 4: AUDIT
Step 'AUDIT bridges + nav' {
    & (Join-Path $Kit 'AUDIT_BRIDGES_NAV.ps1') -Root $Root
}

# Step 5: TAG
Step 'TAG v0.1.0-singularity' {
    Push-Location $Root
    try {
        $existing = (git tag --list 'v0.1.0-singularity' 2>&1) -as [string]
        if ([string]::IsNullOrWhiteSpace($existing)) {
            git tag -a v0.1.0-singularity -m 'Post-merge unified baseline (2026-05-03)' 2>&1 | Out-Host
            Write-Host 'Tagged v0.1.0-singularity' -ForegroundColor Green
        } else {
            Write-Host 'Tag v0.1.0-singularity already exists, skipping' -ForegroundColor Yellow
        }
    } finally { Pop-Location }
}

# Step 6: write report
$report.Add('---')
$report.Add('**Finished:** ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
$report.Add('')
$report.Add('## Quick start')
$report.Add('')
$report.Add('```')
$report.Add('cd ' + $Root)
$report.Add('.\.venv\Scripts\Activate.ps1')
$report.Add('agency list')
$report.Add('agency serve')
$report.Add('python -m jarvis_brainiac')
$report.Add('```')

$reportPath = Join-Path $Root 'BOOTSTRAP_REPORT.md'
$report -join "`r`n" | Out-File -LiteralPath $reportPath -Encoding utf8

Write-Host ''
Write-Host '================ ALL STEPS COMPLETE ================' -ForegroundColor Green
Write-Host ('Report: ' + $reportPath) -ForegroundColor Cyan
Write-Host ''
Write-Host 'Press any key to close...'
[void][System.Console]::ReadKey($true)
