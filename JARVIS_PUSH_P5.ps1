# JARVIS Pass 5 — push to main
Get-Process -Name "git" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500
Remove-Item ".git\index.lock" -Force -ErrorAction SilentlyContinue
git add -A
git commit -m "feat(jarvis): Pass 5 — fix ComplexityClassifier thresholds, add SupremeJarvisBrain.skills, doctor AGENCY_BACKEND flag, 45 new tests (749 total)"
git push origin HEAD:main --force-with-lease
