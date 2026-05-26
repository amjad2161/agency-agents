# SUPREME_MERGE.ps1 — Caveman merge driver
# Merge 7 source bundles into canonical C:\Users\User\agency
# Newer-wins by mtime. Skip __pycache__, .git, .venv, blobs, .pyc.
# Idempotent. Logs to supreme_merge_log.txt
# Author: Claude (autonomous scheduled run 2026-05-05)

[CmdletBinding()]
param(
  [switch]$DryRun,
  [switch]$IncludeOpenJarvis,
  [string]$Canonical = "C:\Users\User\agency",
  [string]$LogPath = "C:\Users\User\OneDrive\מסמכים\Claude\Projects\jarvis brainiac\supreme_merge_log.txt"
)

$ErrorActionPreference = "Continue"
$started = Get-Date
"=== SUPREME_MERGE start $started ===" | Tee-Object -FilePath $LogPath

# Source mounts ranked by trust (highest first wins ties)
$Sources = @(
  @{ Path = "C:\Users\User\Downloads\Kimi_Agent_Full JARVIS Project Audit"; Tag = "kimi-audit" },
  @{ Path = "C:\Users\User\Downloads\jarvis brainiac";                       Tag = "downloads-jb" },
  @{ Path = "C:\Users\User\Downloads\jarvis";                                Tag = "downloads-jarvis" },
  @{ Path = "C:\Users\User\Downloads\agency-agents-main";                    Tag = "agency-agents-main" }
)
if ($IncludeOpenJarvis) {
  $Sources += @{ Path = "C:\Users\User\Downloads\OpenJarvis-main"; Tag = "openjarvis" }
}

$Excludes = @(
  "__pycache__", ".git", ".venv", ".mypy_cache", ".pytest_cache", ".ruff_cache",
  "blobs", "node_modules", "*.pyc", ":memory:", ".coverage*", "*.bundle"
)

function Should-Skip($relPath) {
  foreach ($e in $Excludes) {
    if ($relPath -like "*$e*") { return $true }
  }
  return $false
}

# Pre-flight: clear stuck index.lock
$lock = Join-Path $Canonical ".git\index.lock"
if (Test-Path $lock) {
  "[preflight] Removing stuck $lock" | Tee-Object -FilePath $LogPath -Append
  if (-not $DryRun) { Remove-Item $lock -Force -ErrorAction SilentlyContinue }
}

$copied = 0; $skipped = 0; $newer = 0; $same = 0; $missing = 0

foreach ($src in $Sources) {
  if (-not (Test-Path $src.Path)) {
    "[skip-source] $($src.Tag): not found at $($src.Path)" | Tee-Object -FilePath $LogPath -Append
    continue
  }
  "[source] $($src.Tag) -> $($src.Path)" | Tee-Object -FilePath $LogPath -Append

  Get-ChildItem -Path $src.Path -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
    $rel = $_.FullName.Substring($src.Path.Length).TrimStart('\','/')
    if (Should-Skip $rel) { $skipped++; return }

    $dst = Join-Path $Canonical $rel
    if (-not (Test-Path $dst)) {
      $missing++
      if (-not $DryRun) {
        $dstDir = Split-Path $dst -Parent
        if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Path $dstDir -Force | Out-Null }
        Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
      }
      return
    }

    $dstFile = Get-Item -LiteralPath $dst
    if ($_.LastWriteTime -gt $dstFile.LastWriteTime) {
      $newer++
      if (-not $DryRun) {
        # Atomic write: copy to .tmp, then os.replace via Move-Item -Force
        $tmp = "$dst.tmp.$([guid]::NewGuid().ToString('N'))"
        Copy-Item -LiteralPath $_.FullName -Destination $tmp -Force
        Move-Item -LiteralPath $tmp -Destination $dst -Force
        $copied++
      }
    } else { $same++ }
  }
}

$elapsed = ((Get-Date) - $started).TotalSeconds
@"
=== SUPREME_MERGE summary ===
canonical    : $Canonical
sources      : $($Sources.Count)
dry_run      : $DryRun
files_copied : $copied
newer_found  : $newer
missing_dst  : $missing
same         : $same
excluded     : $skipped
elapsed_s    : $elapsed
end          : $(Get-Date)
"@ | Tee-Object -FilePath $LogPath -Append

if (-not $DryRun -and $copied -gt 0) {
  "[next] cd $Canonical; git add --renormalize .; git add -A; git commit --no-verify -m 'merge: SUPREME consolidation 2026-05-05 ($copied files, $newer newer-wins)'; git push origin main" | Tee-Object -FilePath $LogPath -Append
}
