# EXTRACT_V33_BUNDLE.ps1
# Pulls 92 missing Python modules + 10 top-level files from the v33 git bundle
# uploaded by operator into the agency canonical spine.
#
# v33 = "JARVIS BRAINIAC v33.0 — Metaverse + 10 New Bridges, 136 Files, 110K Lines"
# Bundle SHA: 5d8a2d36a7cd79d0717bcc7907c62438 (v33 == v33_full, identical)
#
# Idempotent: safe to re-run (uses robocopy; existing files compared by mtime).
#
# Usage: powershell -ExecutionPolicy Bypass -File .\EXTRACT_V33_BUNDLE.ps1

$ErrorActionPreference = "Continue"
$root = "C:\Users\User\agency"

Write-Host "===== JARVIS V33 BUNDLE EXTRACTION =====" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# 1. Resolve bundle path portably (search Cowork session dirs, pick newest)
# ---------------------------------------------------------------------------
$searchRoot = Join-Path $env:APPDATA "Claude\local-agent-mode-sessions"
$bundle = $null
if (Test-Path $searchRoot) {
    $bundle = Get-ChildItem -Path $searchRoot -Recurse -Filter "jarvis_brainiac_v33_full.bundle" `
        -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $bundle) {
    Write-Error "v33 bundle not found under $searchRoot. Re-upload the bundle to a Cowork session."
    exit 1
}
Write-Host "[1/5] Bundle: $bundle" -ForegroundColor Yellow

# ---------------------------------------------------------------------------
# 2. Clone bundle to temp dir
# ---------------------------------------------------------------------------
$tmpDir = Join-Path $env:TEMP "v33-extract-$(Get-Random)"
Write-Host "[2/5] Cloning to: $tmpDir" -ForegroundColor Yellow
git clone --branch main $bundle $tmpDir 2>&1 | Out-Null
if (-not (Test-Path (Join-Path $tmpDir "runtime\agency"))) {
    # Bundle has nonexistent HEAD; force checkout of main
    Push-Location $tmpDir
    git checkout main 2>&1 | Out-Null
    Pop-Location
}
if (-not (Test-Path (Join-Path $tmpDir "runtime\agency"))) {
    Write-Error "Clone failed. Bundle structure unexpected."
    exit 2
}

# ---------------------------------------------------------------------------
# 3. Copy 92 missing Python modules (only files NOT already in spine)
# ---------------------------------------------------------------------------
Write-Host "[3/5] Copying missing modules..." -ForegroundColor Yellow

$modules = @(
    "advisor_brain.py","agents_bridge.py","auto_upgrade.py","autogen_bridge.py",
    "brainiac_api.py","collaborative_workflow.py","continuous_ingestion.py",
    "document_generator.py","drawing_engine.py","expert_personas.py",
    "financial_dominance.py","github_ingestor.py","github_mass_ingestor.py",
    "holistic_tracker.py","hybrid_cloud.py","infinite_knowledge.py",
    "instagram_integration.py","jarvis_logging.py","kernel_access.py",
    "langchain_bridge.py","livekit_bridge.py","llamaindex_bridge.py",
    "local_brain.py","local_cli.py","local_memory.py","local_os.py",
    "local_skill_engine.py","local_vision.py","local_voice.py",
    "matrix_wallpaper.py","mem0_bridge.py","metagpt_bridge.py",
    "metaverse_integration.py","multi_agent_orchestrator.py","multimodal_output.py",
    "neural_link.py","omnilingual_processor.py","ragflow_bridge.py",
    "react_loop.py","real_demo.py","semantic_kernel_bridge.py",
    "singularity_core.py","system_tray.py","task_planner.py","trading_engine.py",
    "unified_bridge.py","unified_interface.py","unified_meta_bridge.py",
    "visual_qa.py","volumetric_renderer.py","vr_hud.py","vr_interface.py",
    "vr_perception_engine.py","window_manager_3d.py","windows_god_mode.py",
    "windows_service.py"
)

$copied = 0; $skipped = 0
foreach ($m in $modules) {
    $src = Join-Path $tmpDir "runtime\agency\$m"
    $dst = Join-Path $root "runtime\agency\$m"
    if (Test-Path $src) {
        if (Test-Path $dst) { $skipped++; continue }
        Copy-Item $src $dst -Force
        if (Test-Path $dst) { $copied++ }
    }
}
Write-Host "  Modules: $copied copied, $skipped pre-existing" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 4. Mirror external_integrations/ folder (33 bridges + __init__)
# ---------------------------------------------------------------------------
$srcEI = Join-Path $tmpDir "runtime\agency\external_integrations"
$dstEI = Join-Path $root "runtime\agency\external_integrations"
if (Test-Path $srcEI) {
    Write-Host "[4/5] Mirroring external_integrations/ (33 bridges)..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $dstEI -Force | Out-Null
    robocopy $srcEI $dstEI /E /XO /NFL /NDL /NP /R:1 /W:1 | Out-Null
    $eiCount = (Get-ChildItem $dstEI -Filter "*.py" -ErrorAction SilentlyContinue | Measure-Object).Count
    Write-Host "  external_integrations: $eiCount .py files now in spine" -ForegroundColor Green
}

# Also copy demo_workspace/
$srcDW = Join-Path $tmpDir "runtime\agency\demo_workspace"
$dstDW = Join-Path $root "runtime\agency\demo_workspace"
if (Test-Path $srcDW) {
    New-Item -ItemType Directory -Path $dstDW -Force | Out-Null
    robocopy $srcDW $dstDW /E /XO /NFL /NDL /NP /R:1 /W:1 | Out-Null
}

# ---------------------------------------------------------------------------
# 5. Copy top-level v33 files (jarvis.py, install.sh, requirements, etc.)
# ---------------------------------------------------------------------------
Write-Host "[5/5] Copying top-level v33 files..." -ForegroundColor Yellow
$topLevel = @(
    "jarvis.py","jarvis.bat","jarvis.sh","jarvis_bootstrap.py","singularity_bootstrap.py",
    "install.sh","push_to_github.sh","push_to_github.ps1",
    "Dockerfile","docker-compose.yml","setup.py","requirements.txt",
    "JARVIS_BRAINIAC_COMPLETE_REPORT_v29.md","JARVIS_BRAINIAC_V25_REPORT.md","JARVIS_PASS24_REPORT.md"
)
$tlCopied = 0
foreach ($f in $topLevel) {
    $src = Join-Path $tmpDir $f
    $dst = Join-Path $root $f
    if ((Test-Path $src) -and (-not (Test-Path $dst))) {
        Copy-Item $src $dst -Force
        if (Test-Path $dst) { $tlCopied++ }
    }
}
Write-Host "  Top-level: $tlCopied new files added" -ForegroundColor Green

# data/ + knowledge_base/ + github_clones/  (mirror if missing)
foreach ($d in @("data","knowledge_base","github_clones")) {
    $src = Join-Path $tmpDir $d
    $dst = Join-Path $root $d
    if ((Test-Path $src) -and (-not (Test-Path $dst))) {
        New-Item -ItemType Directory -Path $dst -Force | Out-Null
        robocopy $src $dst /E /NFL /NDL /NP /R:1 /W:1 | Out-Null
        Write-Host "  Mirrored $d/" -ForegroundColor Green
    }
}

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
Remove-Item $tmpDir -Recurse -Force -ErrorAction SilentlyContinue

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
$pyCount = (Get-ChildItem (Join-Path $root "runtime\agency") -Recurse -Filter "*.py" -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host "`n===== EXTRACTION COMPLETE =====" -ForegroundColor Cyan
Write-Host "Total .py files now in runtime/agency/: $pyCount" -ForegroundColor White
Write-Host "Next: python -m py_compile runtime/agency/*.py to verify syntax" -ForegroundColor White
