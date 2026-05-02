Set-Location C:\Users\User\agency
python -m pytest runtime/tests/test_jarvis_pass22.py -v --tb=short
if ($LASTEXITCODE -ne 0) { Write-Error "Tests failed"; exit 1 }
git add -A
git commit -m "Pass 22: face recognition, gesture control, Telegram bot, neural TTS, joint planner"
git push
Write-Host "Pass 22 pushed OK"
