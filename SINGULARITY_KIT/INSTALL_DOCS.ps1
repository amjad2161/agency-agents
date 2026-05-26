# Copy SINGULARITY.md, ROADMAP.md, INDEX.md, DELIVERY.md from kit -> destination
$kit = 'C:\Users\User\OneDrive\מסמכים\Claude\Projects\jarvis brainiac\SINGULARITY_KIT'
$dst = 'C:\Users\User\JARVIS_SINGULARITY'
if (-not (Test-Path -LiteralPath $dst)) { New-Item -ItemType Directory -Path $dst -Force | Out-Null }
$files = @{
    'SINGULARITY.md' = 'SINGULARITY.md'
    'ROADMAP.md'     = 'ROADMAP.md'
    'INDEX.md'       = 'INDEX.md'
    'DELIVERY.md'    = 'DELIVERY.md'
    'README.md'      = 'SINGULARITY_KIT_README.md'
}
foreach ($k in $files.Keys) {
    $src = Join-Path $kit $k
    $tgt = Join-Path $dst $files[$k]
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination $tgt -Force
        Write-Host ('Copied ' + $k + ' -> ' + $files[$k]) -ForegroundColor Green
    } else {
        Write-Warning ('Missing source: ' + $src)
    }
}
Write-Host ''
Write-Host 'Verification in destination:' -ForegroundColor Cyan
Get-ChildItem -LiteralPath $dst -File | Where-Object { $_.Name -in 'SINGULARITY.md','ROADMAP.md','INDEX.md','DELIVERY.md','SINGULARITY_KIT_README.md' } | Sort-Object Name | Format-Table Name, Length, LastWriteTime -AutoSize
