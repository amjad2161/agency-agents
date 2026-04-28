Get-Process -Name "git" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500
Remove-Item ".git\index.lock" -Force -ErrorAction SilentlyContinue
git add -A
git commit -m "feat(jarvis): Pass 4 -- audit autonomous_loop/capability_evolver/knowledge_expansion/meta_reasoner/orchestrator, new tests, all green"
git push origin HEAD:main --force-with-lease
