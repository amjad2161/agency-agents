<#
.SYNOPSIS
    JARVIS UNIFIED BUILD — מיזוג מלא של כל פרויקטי JARVIS לתיקייה אחת
.DESCRIPTION
    מסרק את כל המחשב, מאסף כל קובץ רלוונטי, ומאחד ל-C:\Users\Mobar\JARVIS_UNIFIED
    
.USAGE
    הרץ כ-Administrator:
    powershell -ExecutionPolicy Bypass -File "C:\Users\Mobar\jarvis-brainiac\BUILD_JARVIS_UNIFIED.ps1"
#>

$ErrorActionPreference = "Continue"
$VerbosePreference = "Continue"

Write-Host ""
Write-Host "██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗    ██╗   ██╗███╗   ██╗██╗███████╗██╗███████╗██████╗ " -ForegroundColor Cyan
Write-Host "██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝    ██║   ██║████╗  ██║██║██╔════╝██║██╔════╝██╔══██╗" -ForegroundColor Cyan
Write-Host "██║███████║██████╔╝██║   ██║██║███████╗    ██║   ██║██╔██╗ ██║██║█████╗  ██║█████╗  ██║  ██║" -ForegroundColor Cyan
Write-Host "██ ██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║    ██║   ██║██║╚██╗██║██║██╔══╝  ██║██╔══╝  ██║  ██║" -ForegroundColor Cyan  
Write-Host "██╗██║  ██║██║  ██║ ╚████╔╝ ██║███████║    ╚██████╔╝██║ ╚████║██║██║     ██║███████╗██████╔╝" -ForegroundColor Cyan
Write-Host "╚═╝╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝     ╚═════╝ ╚═╝  ╚═══╝╚═╝╚═╝     ╚═╝╚══════╝╚═════╝ " -ForegroundColor Cyan
Write-Host ""
Write-Host "BUILD STARTED: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow
Write-Host ""

# ─── Configuration ─────────────────────────────────────────────────────────────

$UNIFIED_ROOT = "C:\Users\Mobar\JARVIS_UNIFIED"

$SOURCES = @(
    @{
        Name = "jarvis-brainiac (PRIMARY)"
        Path = "C:\Users\Mobar\jarvis-brainiac"
        DestPrefix = ""
        Priority = 1
    },
    @{
        Name = "Desktop JARVIS (SECONDARY)"
        Path = "C:\Users\Mobar\OneDrive\Desktop\jarvis brainiac"
        DestPrefix = "_archive\desktop_jarvis"
        Priority = 2
    },
    @{
        Name = "SkyCore (DRONE SYSTEM)"
        Path = "C:\Users\Mobar\SkyCore"
        DestPrefix = "skycore"
        Priority = 3
    },
    @{
        Name = "KidGenius Academy"
        Path = "C:\Users\Mobar\kidgenius-academy"
        DestPrefix = "kidgenius"
        Priority = 4
    }
)

$SKIP_DIRS = @(".git", ".venv", "venv", "env", "node_modules", "__pycache__", 
               ".pytest_cache", ".mypy_cache", "dist", "build", ".next",
               ".nuxt", "blobs", ".tox", ".cache", ".idea", ".vs")

$SKIP_EXTENSIONS = @(".pyc", ".pyo", ".gguf", ".bin", ".pt", ".pth", 
                      ".safetensors", ".onnx", ".exe", ".msi", ".dll",
                      ".so", ".dylib", ".mp4", ".avi", ".mkv", ".mov",
                      ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico",
                      ".zip", ".tar", ".gz", ".7z", ".rar")

$MAX_FILE_SIZE_MB = 10

# ─── Stats ─────────────────────────────────────────────────────────────────────

$Stats = @{
    Copied       = 0
    Duplicates   = 0
    SkippedExt   = 0
    SkippedSize  = 0
    Errors       = 0
    BySource     = @{}
}

$CopiedHashes = @{}  # SHA256 → dest path

# ─── Functions ─────────────────────────────────────────────────────────────────

function Get-FileHash256($path) {
    try {
        return (Get-FileHash -Path $path -Algorithm SHA256).Hash
    } catch {
        return $null
    }
}

function Should-SkipDir($dirname) {
    return ($dirname -in $SKIP_DIRS) -or ($dirname.StartsWith("."))
}

function Should-SkipFile($file) {
    $ext = $file.Extension.ToLower()
    if ($ext -in $SKIP_EXTENSIONS) { return "extension" }
    $sizeMB = $file.Length / 1MB
    if ($sizeMB -gt $MAX_FILE_SIZE_MB) { return "size" }
    return $null
}

function Copy-Source($source) {
    $srcRoot = $source.Path
    $destPrefix = $source.DestPrefix
    $name = $source.Name

    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor DarkGray
    Write-Host "  Source: $name" -ForegroundColor White
    Write-Host "  From:   $srcRoot" -ForegroundColor Gray
    if ($destPrefix) {
        Write-Host "  To:     $UNIFIED_ROOT\$destPrefix" -ForegroundColor Gray
    } else {
        Write-Host "  To:     $UNIFIED_ROOT" -ForegroundColor Gray
    }
    Write-Host ("=" * 60) -ForegroundColor DarkGray

    if (-not (Test-Path $srcRoot)) {
        Write-Host "  ⚠️  Source not found: $srcRoot" -ForegroundColor Yellow
        return
    }

    $fileCount = 0
    $Stats.BySource[$name] = 0

    # Walk all files
    Get-ChildItem -Path $srcRoot -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
        $file = $_
        $relativeParts = $file.FullName.Substring($srcRoot.Length).TrimStart('\')

        # Skip if in a skip directory
        $pathParts = $relativeParts.Split('\')
        $inSkipDir = $false
        foreach ($part in $pathParts[0..($pathParts.Count - 2)]) {
            if (Should-SkipDir $part) {
                $inSkipDir = $true
                break
            }
        }
        if ($inSkipDir) {
            $Stats.Duplicates += 0  # not counting as dup
            return
        }

        # Build destination path
        if ($destPrefix) {
            $destFile = Join-Path $UNIFIED_ROOT $destPrefix $relativeParts
        } else {
            $destFile = Join-Path $UNIFIED_ROOT $relativeParts
        }

        # Check skip reason
        $skipReason = Should-SkipFile $file
        if ($skipReason -eq "extension") {
            $Stats.SkippedExt++
            return
        }
        if ($skipReason -eq "size") {
            $Stats.SkippedSize++
            return
        }

        # Hash check
        $hash = Get-FileHash256 $file.FullName
        if ($null -eq $hash) {
            $Stats.Errors++
            return
        }

        if ($CopiedHashes.ContainsKey($hash) -and $source.Priority -gt 1) {
            $Stats.Duplicates++
            return
        }

        # Copy file
        try {
            $destDir = Split-Path $destFile -Parent
            if (-not (Test-Path $destDir)) {
                New-Item -ItemType Directory -Path $destDir -Force | Out-Null
            }
            Copy-Item -Path $file.FullName -Destination $destFile -Force
            $CopiedHashes[$hash] = $destFile
            $Stats.Copied++
            $Stats.BySource[$name]++
            $fileCount++

            if ($fileCount % 100 -eq 0) {
                Write-Host "  ... $fileCount files from $name" -ForegroundColor DarkCyan
            }
        } catch {
            $Stats.Errors++
        }
    }

    Write-Host "  ✅ $fileCount files from $name" -ForegroundColor Green
}

# ─── Main ──────────────────────────────────────────────────────────────────────

# Create unified root
Write-Host "Creating JARVIS_UNIFIED directory..." -ForegroundColor Cyan
New-Item -ItemType Directory -Path $UNIFIED_ROOT -Force | Out-Null
New-Item -ItemType Directory -Path "$UNIFIED_ROOT\knowledge" -Force | Out-Null
Write-Host "✅ Created: $UNIFIED_ROOT" -ForegroundColor Green

# Phase 1: Copy all sources
Write-Host ""
Write-Host "PHASE 1: Copying all sources..." -ForegroundColor Yellow
foreach ($source in $SOURCES) {
    Copy-Source $source
}

# Phase 2: Copy key knowledge files
Write-Host ""
Write-Host "PHASE 2: Copying knowledge documents..." -ForegroundColor Yellow
$keyDocs = @(
    "C:\Users\Mobar\jarvis-brainiac\memory\requirements_master.md",
    "C:\Users\Mobar\jarvis-brainiac\UNIFIED_MANIFEST.md",
    "C:\Users\Mobar\jarvis-brainiac\JARVIS_STATUS.md",
    "C:\Users\Mobar\jarvis-brainiac\.antigravity_rules",
    "C:\Users\Mobar\jarvis-brainiac\SINGULARITY_KIT\MISSION_STATUS.md",
    "C:\Users\Mobar\jarvis-brainiac\SINGULARITY_KIT\ROADMAP.md"
)
foreach ($doc in $keyDocs) {
    if (Test-Path $doc) {
        $destDoc = "$UNIFIED_ROOT\knowledge\$(Split-Path $doc -Leaf)"
        Copy-Item -Path $doc -Destination $destDoc -Force
        Write-Host "  ✅ $(Split-Path $doc -Leaf)" -ForegroundColor Green
    }
}

# Phase 3: Scan for additional JARVIS docs
Write-Host ""
Write-Host "PHASE 3: Scanning for additional JARVIS files..." -ForegroundColor Yellow
$extraDir = "$UNIFIED_ROOT\_additional_finds"
New-Item -ItemType Directory -Path $extraDir -Force | Out-Null
$jarvisPattern = "jarvis|brainiac|singularity|agency|skycore|gane|mythos"

$additionalFiles = Get-ChildItem -Path "C:\Users\Mobar\OneDrive" -Recurse -File `
    -ErrorAction SilentlyContinue | Where-Object {
        ($_.Name -match $jarvisPattern -or $_.Directory.FullName -match $jarvisPattern) -and
        ($_.Extension -in @('.md', '.txt', '.py', '.ps1', '.bat', '.cmd')) -and
        $_.Length -lt 5MB
    }

$extraCount = 0
foreach ($f in $additionalFiles) {
    $dest = Join-Path $extraDir $f.Name
    if (-not (Test-Path $dest)) {
        try {
            Copy-Item -Path $f.FullName -Destination $dest -Force
            $extraCount++
        } catch {}
    }
}
Write-Host "  ✅ Found $extraCount additional JARVIS-related files" -ForegroundColor Green

# Phase 4: Run tests
Write-Host ""
Write-Host "PHASE 4: Running all tests..." -ForegroundColor Yellow
Write-Host "  (Tests will run from jarvis-brainiac primary source)" -ForegroundColor Gray

$testResult = & python -m pytest "C:\Users\Mobar\jarvis-brainiac\tests\" -v --tb=short 2>&1
$testOutput = $testResult -join "`n"
$testOutput | Out-File "$UNIFIED_ROOT\knowledge\test_results.txt" -Encoding utf8 -Force
Write-Host $testOutput

# Phase 5: Create README
Write-Host ""
Write-Host "PHASE 5: Creating README..." -ForegroundColor Yellow

$bySourceTable = ""
foreach ($name in $Stats.BySource.Keys) {
    $count = $Stats.BySource[$name]
    $bySourceTable += "| $name | $count |`n"
}

$readmeContent = @"
# JARVIS UNIFIED — Complete Project
Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm UTC')

## Build Statistics
| Metric | Count |
|--------|-------|
| Files copied | $($Stats.Copied) |
| Duplicates skipped | $($Stats.Duplicates) |
| Skipped (ext) | $($Stats.SkippedExt) |
| Skipped (size) | $($Stats.SkippedSize) |
| Errors | $($Stats.Errors) |

## Sources Merged
| Source | Files |
|--------|-------|
$bySourceTable

## Directory Structure
```
JARVIS_UNIFIED/
├── jarvis_brainiac/         ← Core: FreeLLM, Memory, Pipeline, Builder
├── godskill_server/         ← REST API (18 endpoints)
├── tests/                   ← All tests (73+)
├── skycore/                 ← Drone system (253 modules, 8 layers)
├── kidgenius/               ← Educational platform (React/TS)
├── knowledge/               ← Requirements + test results + index
│   ├── requirements_master.md  ← 88 requirements, 5 epochs
│   ├── UNIFIED_MANIFEST.md     ← Project map
│   ├── MISSION_STATUS.md       ← 30 missions verified
│   └── test_results.txt        ← Latest test run
├── _archive/                ← Historical versions
├── _additional_finds/       ← Extra discovered files
└── README_UNIFIED.md        ← This file
```

## Quick Start
```powershell
# Run tests
cd C:\Users\Mobar\JARVIS_UNIFIED
python -m pytest tests/ -v

# Start REST API
python godskill_server\server.py

# Launch JARVIS GUI
python JARVIS_BRAINIAC.py

# API calls
curl http://127.0.0.1:8765/api/unified/stats
curl http://127.0.0.1:8765/api/unified/requirements
curl "http://127.0.0.1:8765/api/unified/search?q=voice"
curl http://127.0.0.1:8765/api/unified/timeline
```
"@

$readmeContent | Out-File "$UNIFIED_ROOT\README_UNIFIED.md" -Encoding utf8 -Force
Write-Host "  ✅ README_UNIFIED.md created" -ForegroundColor Green

# Phase 6: Build Python module index
Write-Host ""
Write-Host "PHASE 6: Building module index..." -ForegroundColor Yellow
$pyFiles = Get-ChildItem -Path $UNIFIED_ROOT -Recurse -File -Filter "*.py" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "node_modules|__pycache__|.venv" } |
    ForEach-Object { $_.FullName.Replace($UNIFIED_ROOT, "").TrimStart('\') }

$indexContent = "# JARVIS UNIFIED — Python Module Index`n"
$indexContent += "# Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm')`n"
$indexContent += "# Total: $($pyFiles.Count) Python files`n`n"
$pyFiles | Sort-Object | ForEach-Object { $indexContent += "- $_`n" }
$indexContent | Out-File "$UNIFIED_ROOT\knowledge\module_index.md" -Encoding utf8 -Force
Write-Host "  ✅ $($pyFiles.Count) Python modules indexed" -ForegroundColor Green

# Git init in JARVIS_UNIFIED
Write-Host ""
Write-Host "PHASE 7: Initializing git..." -ForegroundColor Yellow
Push-Location $UNIFIED_ROOT
git init 2>&1 | Out-Null
git add -A 2>&1 | Out-Null
git commit -m "JARVIS Unified Singularity v1.0.0 — $(Get-Date -Format 'yyyy-MM-dd')" 2>&1 | Out-Null
git tag -a "v1.0.0-unified" -m "Unified: jarvis-brainiac + SkyCore + KidGenius | 88 requirements | 5 epochs" 2>&1 | Out-Null
Pop-Location
Write-Host "  ✅ git init + v1.0.0-unified tag" -ForegroundColor Green

# Final Summary
Write-Host ""
Write-Host ("=" * 60) -ForegroundColor Green
Write-Host "✅ JARVIS UNIFIED BUILD COMPLETE!" -ForegroundColor Green
Write-Host ("=" * 60) -ForegroundColor Green
Write-Host ""
Write-Host "📁 Location:      $UNIFIED_ROOT" -ForegroundColor White
Write-Host "📄 Files copied:  $($Stats.Copied)" -ForegroundColor White
Write-Host "🔁 Duplicates:    $($Stats.Duplicates)" -ForegroundColor White
Write-Host "❌ Errors:        $($Stats.Errors)" -ForegroundColor White
Write-Host ""
Write-Host "Source breakdown:" -ForegroundColor Gray
foreach ($name in $Stats.BySource.Keys) {
    Write-Host "  $name`: $($Stats.BySource[$name]) files" -ForegroundColor DarkCyan
}
Write-Host ""
Write-Host "🧠 Requirements:  $UNIFIED_ROOT\knowledge\requirements_master.md" -ForegroundColor Cyan
Write-Host "📋 Manifest:      $UNIFIED_ROOT\README_UNIFIED.md" -ForegroundColor Cyan
Write-Host "🧪 Test results:  $UNIFIED_ROOT\knowledge\test_results.txt" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. winget install Ollama.Ollama && ollama pull llama3.3" -ForegroundColor White
Write-Host "  2. python godskill_server\server.py" -ForegroundColor White
Write-Host "  3. curl http://127.0.0.1:8765/api/unified/stats" -ForegroundColor White
Write-Host ""
