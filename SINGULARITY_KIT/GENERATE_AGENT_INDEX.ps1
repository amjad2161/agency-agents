# Auto-generate AGENT_INDEX.md from the agents/ tree
[CmdletBinding()]
param(
    [string]$Root = "C:\Users\User\JARVIS_SINGULARITY",
    [string]$Output = $null
)

$ErrorActionPreference = 'Continue'
$agents = Join-Path $Root 'agents'
if (-not $Output) { $Output = Join-Path $Root 'AGENT_INDEX.md' }

if (-not (Test-Path -LiteralPath $agents)) {
    Write-Error "agents/ folder not found at $agents"
    exit 1
}

$divisions = @(
    'design','engineering','marketing','sales','support','testing',
    'product','project-management','strategy','spatial-computing',
    'academic','science','specialized','finance','game-development','paid-media'
)

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('# JARVIS SINGULARITY - Agent Index')
$lines.Add('')
$lines.Add('Auto-generated from `agents/` tree on ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
$lines.Add('')
$totalAgents = 0
$divisionCounts = @{}

foreach ($d in $divisions) {
    $path = Join-Path $agents $d
    if (-not (Test-Path -LiteralPath $path)) { continue }
    $files = Get-ChildItem -LiteralPath $path -File -Filter '*.md' -ErrorAction SilentlyContinue | Sort-Object Name
    if ($files.Count -eq 0) { continue }
    $divisionCounts[$d] = $files.Count
    $totalAgents += $files.Count
}

$lines.Add('## Summary')
$lines.Add('')
$lines.Add("Total agent personas: **$totalAgents**")
$lines.Add('')
$lines.Add('| Division | Count |')
$lines.Add('|---|---|')
foreach ($d in $divisions) {
    if ($divisionCounts.ContainsKey($d)) {
        $lines.Add("| $d | $($divisionCounts[$d]) |")
    }
}
$lines.Add('')

foreach ($d in $divisions) {
    $path = Join-Path $agents $d
    if (-not (Test-Path -LiteralPath $path)) { continue }
    $files = Get-ChildItem -LiteralPath $path -File -Filter '*.md' -ErrorAction SilentlyContinue | Sort-Object Name
    if ($files.Count -eq 0) { continue }
    $lines.Add("## $d ($($files.Count))")
    $lines.Add('')
    foreach ($f in $files) {
        $name = $f.BaseName
        $rel = "agents/$d/$($f.Name)"
        $lines.Add("- [$name]($rel)")
    }
    $lines.Add('')
}

# Also list any agents in unexpected dirs
$other = Get-ChildItem -LiteralPath $agents -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -notin $divisions } | Sort-Object Name
if ($other.Count -gt 0) {
    $lines.Add('## Other / unclassified')
    $lines.Add('')
    foreach ($o in $other) {
        $files = Get-ChildItem -LiteralPath $o.FullName -File -Filter '*.md' -ErrorAction SilentlyContinue | Sort-Object Name
        if ($files.Count -gt 0) {
            $lines.Add("### $($o.Name) ($($files.Count))")
            $lines.Add('')
            foreach ($f in $files) {
                $name = $f.BaseName
                $rel = "agents/$($o.Name)/$($f.Name)"
                $lines.Add("- [$name]($rel)")
            }
            $lines.Add('')
        }
    }
}

$lines -join "`r`n" | Out-File -LiteralPath $Output -Encoding utf8
Write-Host ("AGENT_INDEX.md written to $Output") -ForegroundColor Green
Write-Host ("Total agents: $totalAgents across $($divisionCounts.Count) divisions")
