Set-Location C:\Users\User\agency

# Remove stale git lock if present
$lockFile = ".git\index.lock"
if (Test-Path $lockFile) {
    Remove-Item $lockFile -Force
    Write-Host "Removed stale git lock"
}

# Run tests with fresh bytecode cache
Write-Host "Running Pass 23 tests..."
$env:PYTHONPYCACHEPREFIX = "$env:TEMP\p23cache"
python -m pytest runtime/tests/test_jarvis_pass23.py -v --tb=short
if ($LASTEXITCODE -ne 0) {
    Write-Error "Tests failed — aborting push"
    exit 1
}
Write-Host "All tests passed."

git add runtime/agency/nlu_engine.py `
         runtime/agency/vad_engine.py `
         runtime/agency/robotics/camera_tracker.py `
         runtime/agency/secure_config.py `
         runtime/agency/network_monitor.py `
         runtime/agency/robotics/object_memory.py `
         runtime/agency/cli.py `
         runtime/tests/test_jarvis_pass23.py `
         JARVIS_PUSH_P23.ps1

git commit -m "Pass 23: NLU engine, VAD, camera tracking, secure config, network monitor, object memory"
git push

Write-Host "Pass 23 pushed OK"
