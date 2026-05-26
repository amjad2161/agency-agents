# JARVIS SINGULARITY MERGE ENGINE v1.2
# Unifies AGENCY + KIMI AGENT + JARVIS forks into one folder.
# Policy: newest-wins, content-hash dedup, skip files >100MB,
#         exclude noise dirs, init fresh git locally (no push).

[CmdletBinding()]
param(
    [string]$Destination = "C:\Users\User\JARVIS_SINGULARITY",
    [int]$MaxFileSizeMB  = 100,
    [switch]$DryRun
)

$ErrorActionPreference = 'Continue'
$ProgressPreference    = 'SilentlyContinue'

# Source priority (highest wins on collision)
$Sources = @(
    [pscustomobject]@{ Name='agency';                 Path='C:\Users\User\agency';                                                  Priority=1 }
    [pscustomobject]@{ Name='kimi-audit';             Path='C:\Users\User\Downloads\Kimi_Agent_Full JARVIS Project Audit';          Priority=2 }
    [pscustomobject]@{ Name='downloads-jarvis-brain'; Path='C:\Users\User\Downloads\jarvis brainiac';                               Priority=3 }
    [pscustomobject]@{ Name='agency-agents-main';     Path='C:\Users\User\Downloads\agency-agents-main';                            Priority=4 }
    [pscustomobject]@{ Name='jarvis';                 Path='C:\Users\User\Downloads\jarvis';                                        Priority=5 }
    [pscustomobject]@{ Name='kimi-audit-2';           Path='C:\Users\User\Downloads\Kimi_Agent_Full JARVIS Project Audit000. (2)';  Priority=6 }
)

$ExcludeDirs = @(
    '.git','.venv','venv','env','.env','node_modules','__pycache__',
    '.pytest_cache','.mypy_cache','.ruff_cache','.tox','.cache',
    'dist','build','blobs','.next','.nuxt','.svelte-kit','target',
    'bin','obj','.idea','.vscode-test','coverage','.coverage'
)
$ExcludeFilePatterns = @(
    '*.pyc','*.pyo','*.pyd','*.so','*.dylib',
    '*.bundle','*.gguf','*.bin','*.pt','*.pth','*.safetensors','*.onnx',
    '*.iso','*.dmg','*.exe','*.msi','sha256-*'
)

$MaxBytes = $MaxFileSizeMB * 1MB

if (-not $DryRun) {
    if (-not (Test-Path $Destination)) {
        New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    }
}

$LogPath     = Join-Path $Destination '_MERGE.log'
$ReportPath  = Join-Path $Destination 'MERGE_REPORT.md'
$ManifestCsv = Join-Path $Destination '_MANIFEST.csv'

if (-not $DryRun) {
    "[$(Get-Date -Format o)] MERGE START -> $Destination" | Out-File $LogPath -Encoding utf8
    'src_priority,src_name,rel_path,size_bytes,sha256,action,reason' | Out-File $ManifestCsv -Encoding utf8
}

function Test-Excluded {
    param($File, [string]$Root)
    $rel = $File.FullName.Substring($Root.Length).TrimStart('\','/')
    foreach ($d in $ExcludeDirs) {
        if ($rel -like "*\$d\*" -or $rel -like "$d\*" -or $rel -like "*/$d/*" -or $rel -like "$d/*") { return $true }
    }
    if ($rel -like "*.egg-info\*" -or $rel -like "*.egg-info/*") { return $true }
    foreach ($p in $ExcludeFilePatterns) {
        if ($File.Name -like $p) { return $true }
    }
    if ($File.Length -gt $MaxBytes) { return $true }
    return $false
}

function Get-Sha {
    param([string]$Path)
    try { return (Get-FileHash -Path $Path -Algorithm SHA256 -ErrorAction Stop).Hash } catch { return '' }
}

function Format-Bytes {
    param([long]$b)
    if ($b -ge 1GB) { return ('{0:N2} GB' -f ($b / 1GB)) }
    if ($b -ge 1MB) { return ('{0:N2} MB' -f ($b / 1MB)) }
    if ($b -ge 1KB) { return ('{0:N2} KB' -f ($b / 1KB)) }
    return "$b B"
}

$Stats = [ordered]@{
    Sources             = 0
    FilesScanned        = 0
    FilesCopied         = 0
    FilesSkippedSize    = 0
    FilesSkippedExclude = 0
    FilesSkippedDup     = 0
    FilesOverwriteNewer = 0
    BytesCopied         = 0L
}

$DestIndex = @{}
if (Test-Path $Destination) {
    Get-ChildItem -Path $Destination -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
        $rel = $_.FullName.Substring($Destination.Length).TrimStart('\','/')
        if ($rel -notmatch '^(_MERGE\.log|_MANIFEST\.csv|MERGE_REPORT\.md)$') {
            $DestIndex[$rel] = [ordered]@{
                Hash    = ''
                Mtime   = $_.LastWriteTimeUtc
                SrcPri  = 999
                SrcName = '<existing>'
                Size    = $_.Length
            }
        }
    }
}

foreach ($src in ($Sources | Sort-Object Priority)) {
    if (-not (Test-Path $src.Path)) {
        Write-Warning "Source missing: $($src.Path)"
        continue
    }
    $Stats.Sources++
    Write-Host ("=== [{0}] {1} :: {2} ===" -f $src.Priority, $src.Name, $src.Path) -ForegroundColor Cyan
    $rootLen = $src.Path.Length

    Get-ChildItem -Path $src.Path -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
        $Stats.FilesScanned++
        $f = $_
        if (Test-Excluded -File $f -Root $src.Path) {
            if ($f.Length -gt $MaxBytes) { $Stats.FilesSkippedSize++ } else { $Stats.FilesSkippedExclude++ }
            return
        }
        $rel = $f.FullName.Substring($rootLen).TrimStart('\','/')
        $destPath = Join-Path $Destination $rel
        $action = ''
        $reason = ''
        $hash = ''

        if ($DestIndex.ContainsKey($rel)) {
            $existing = $DestIndex[$rel]
            if (-not $existing.Hash) { $existing.Hash = Get-Sha (Join-Path $Destination $rel) }
            $hash = Get-Sha $f.FullName
            if ($hash -and $hash -eq $existing.Hash) {
                $Stats.FilesSkippedDup++
                $action = 'skip-duplicate'
                $reason = 'hash-equal'
            } elseif ($f.LastWriteTimeUtc -gt $existing.Mtime) {
                if (-not $DryRun) {
                    $parent = Split-Path $destPath -Parent
                    if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
                    Copy-Item -Path $f.FullName -Destination $destPath -Force
                }
                $Stats.FilesOverwriteNewer++
                $Stats.BytesCopied += $f.Length
                $DestIndex[$rel] = [ordered]@{ Hash=$hash; Mtime=$f.LastWriteTimeUtc; SrcPri=$src.Priority; SrcName=$src.Name; Size=$f.Length }
                $action = 'overwrite-newer'
                $reason = "from $($src.Name)"
            } else {
                $Stats.FilesSkippedDup++
                $action = 'skip-older'
                $reason = "kept newer from $($existing.SrcName)"
            }
        } else {
            $hash = Get-Sha $f.FullName
            if (-not $DryRun) {
                $parent = Split-Path $destPath -Parent
                if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
                Copy-Item -Path $f.FullName -Destination $destPath -Force
            }
            $Stats.FilesCopied++
            $Stats.BytesCopied += $f.Length
            $DestIndex[$rel] = [ordered]@{ Hash=$hash; Mtime=$f.LastWriteTimeUtc; SrcPri=$src.Priority; SrcName=$src.Name; Size=$f.Length }
            $action = 'copy-new'
            $reason = "from $($src.Name)"
        }

        if (-not $DryRun) {
            $relCsv = $rel -replace '"','""'
            $reasonCsv = $reason -replace '"','""'
            $line = '"{0}","{1}","{2}",{3},"{4}","{5}","{6}"' -f $src.Priority, $src.Name, $relCsv, $f.Length, $hash, $action, $reasonCsv
            Add-Content -Path $ManifestCsv -Value $line -Encoding utf8
        }

        if (($Stats.FilesScanned % 1000) -eq 0) {
            Write-Host ("  scanned={0} copied={1} dup={2} >cap={3} excl={4}" -f $Stats.FilesScanned, $Stats.FilesCopied, $Stats.FilesSkippedDup, $Stats.FilesSkippedSize, $Stats.FilesSkippedExclude) -ForegroundColor DarkGray
        }
    }
}

$rl = New-Object System.Collections.Generic.List[string]
$rl.Add('# JARVIS SINGULARITY - Merge Report')
$rl.Add('')
$rl.Add('Date: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
$rl.Add('Destination: ' + $Destination)
if ($DryRun) { $rl.Add('Mode: DRY RUN') } else { $rl.Add('Mode: LIVE') }
$rl.Add('')
$rl.Add('## Stats')
$rl.Add('')
$rl.Add('| Metric | Value |')
$rl.Add('|---|---|')
$rl.Add('| Sources processed | ' + $Stats.Sources + ' |')
$rl.Add('| Files scanned | ' + $Stats.FilesScanned + ' |')
$rl.Add('| Files copied (new) | ' + $Stats.FilesCopied + ' |')
$rl.Add('| Files overwritten (newer) | ' + $Stats.FilesOverwriteNewer + ' |')
$rl.Add('| Files skipped (duplicate hash) | ' + $Stats.FilesSkippedDup + ' |')
$rl.Add('| Files skipped (over cap) | ' + $Stats.FilesSkippedSize + ' |')
$rl.Add('| Files skipped (excluded) | ' + $Stats.FilesSkippedExclude + ' |')
$rl.Add('| Total bytes copied | ' + (Format-Bytes $Stats.BytesCopied) + ' |')
$rl.Add('')
$rl.Add('## Source priority')
$rl.Add('')
foreach ($s in ($Sources | Sort-Object Priority)) {
    $rl.Add(('{0}. **{1}** -- {2}' -f $s.Priority, $s.Name, $s.Path))
}
$rl.Add('')
$rl.Add('## Exclusions')
$rl.Add('')
$rl.Add('Dirs: ' + ($ExcludeDirs -join ', '))
$rl.Add('File patterns: ' + ($ExcludeFilePatterns -join ', '))
$rl.Add('Size cap MB: ' + $MaxFileSizeMB)
$rl.Add('')
$rl.Add('Manifest CSV: _MANIFEST.csv')
$rl.Add('Run log: _MERGE.log')

if (-not $DryRun) {
    $rl -join "`r`n" | Out-File $ReportPath -Encoding utf8
    "[$(Get-Date -Format o)] MERGE END scanned=$($Stats.FilesScanned) copied=$($Stats.FilesCopied) overwrite=$($Stats.FilesOverwriteNewer) skipdup=$($Stats.FilesSkippedDup) skipsize=$($Stats.FilesSkippedSize) skipexc=$($Stats.FilesSkippedExclude) bytes=$($Stats.BytesCopied)" | Add-Content $LogPath -Encoding utf8
}

Write-Host ''
Write-Host '========== MERGE COMPLETE ==========' -ForegroundColor Green
Write-Host ('Sources processed: ' + $Stats.Sources)
Write-Host ('Files scanned:     ' + $Stats.FilesScanned)
Write-Host ('Copied new:        ' + $Stats.FilesCopied)
Write-Host ('Overwrote newer:   ' + $Stats.FilesOverwriteNewer)
Write-Host ('Skipped duplicate: ' + $Stats.FilesSkippedDup)
Write-Host ('Skipped >cap:      ' + $Stats.FilesSkippedSize)
Write-Host ('Skipped excluded:  ' + $Stats.FilesSkippedExclude)
Write-Host ('Bytes copied:      ' + (Format-Bytes $Stats.BytesCopied))
Write-Host ('Report:            ' + $ReportPath)

if (-not $DryRun) {
    Push-Location $Destination
    try {
        $gitExe = (Get-Command git -ErrorAction SilentlyContinue).Source
        if (-not $gitExe) {
            Write-Warning 'git not in PATH - skipping repo init'
        } elseif (-not (Test-Path '.git')) {
            git init -b main 2>&1 | Out-Null
            $gi = @(
                '# JARVIS SINGULARITY .gitignore',
                '__pycache__/',
                '*.py[cod]',
                '*.so',
                '*.dylib',
                '.venv/',
                'venv/',
                'env/',
                '.env',
                'node_modules/',
                '.pytest_cache/',
                '.mypy_cache/',
                '.ruff_cache/',
                '.tox/',
                '.cache/',
                'dist/',
                'build/',
                '*.egg-info/',
                '.coverage',
                'coverage/',
                '.idea/',
                '.vscode/',
                '.DS_Store',
                '*.gguf',
                '*.bin',
                '*.pt',
                '*.pth',
                '*.safetensors',
                '*.onnx',
                '*.bundle',
                'blobs/',
                'sha256-*',
                '_MERGE.log',
                '_MANIFEST.csv'
            )
            $gi -join "`r`n" | Out-File '.gitignore' -Encoding utf8
            git add -A 2>&1 | Out-Null
            git -c user.email='singularity@jarvis.local' -c user.name='JARVIS Singularity' commit -m 'feat: unified singularity merge - agency + kimi + jarvis forks' 2>&1 | Out-Null
            Write-Host ''
            Write-Host 'Git initialized + committed (local main, no remote).' -ForegroundColor Yellow
        } else {
            Write-Host ''
            Write-Host 'Git already initialized. Skipping init.' -ForegroundColor Yellow
        }
    } catch {
        Write-Warning ('Git step failed: ' + $_.Exception.Message)
    } finally {
        Pop-Location
    }
}
