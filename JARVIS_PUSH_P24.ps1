Set-Location C:\Users\User\agency
if (Test-Path .git\index.lock)     { Remove-Item .git\index.lock -Force }
if (Test-Path .git\HEAD.lock)      { Remove-Item .git\HEAD.lock -Force }
if (Test-Path .git\index_new.lock) { Remove-Item .git\index_new.lock -Force }
$env:PYTHONPYCACHEPREFIX = "C:\Temp\pycache"
Write-Host "Running Pass 24 tests..."
python -m pytest runtime/tests/test_jarvis_pass24.py -v --tb=short
if ($LASTEXITCODE -ne 0) { Write-Error "Tests failed — aborting push"; exit 1 }
Write-Host "Adding all files..."
git add -A
git commit -m "Pass 24: decision engine, API gateway, hot-reload, task executor, context manager, world model (83 tests)"
git push
Write-Host "Pass 24 pushed OK"
