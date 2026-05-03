# SYNC_SATELLITES.ps1 — mirror 5 satellite repos from local v26 build
# Idempotent: safe to re-run. Uses robocopy /MIR (mirrors source -> dest).
$ErrorActionPreference = "Stop"

$src = "C:\Users\User\Downloads\jarvis brainiac\integrations\external_repos"
$dst = "C:\Users\User\agency\integrations\external_repos"
$repos = @("decepticon", "docker-android", "gane", "paper2code", "saymotion")

if (-not (Test-Path $src)) {
    Write-Error "Source not found: $src"
    exit 1
}

New-Item -ItemType Directory -Path $dst -Force | Out-Null

foreach ($r in $repos) {
    $s = Join-Path $src $r
    $d = Join-Path $dst $r
    if (-not (Test-Path $s)) {
        Write-Warning "Skip $r (source missing)"
        continue
    }
    Write-Host "==> Mirroring $r" -ForegroundColor Cyan
    robocopy $s $d /MIR /NFL /NDL /NP /R:1 /W:1 /XD ".git" "node_modules" "__pycache__" | Out-Null
    if ($LASTEXITCODE -ge 8) {
        Write-Warning "robocopy failed for $r (exit=$LASTEXITCODE)"
    }
}

Write-Host "`n[OK] Sync complete." -ForegroundColor Green
Write-Host "Total files at $dst :"
(Get-ChildItem -Path $dst -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
