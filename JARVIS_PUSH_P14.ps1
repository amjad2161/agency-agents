# JARVIS Pass 14 — plugin system, REST API, client rate limiter
# Run from repo root: .\JARVIS_PUSH_P14.ps1

Set-Location C:\Users\User\agency

git add `
  runtime/agency/plugins.py `
  runtime/agency/rate_limiter.py `
  runtime/agency/simple_server.py `
  runtime/agency/cli.py `
  runtime/tests/test_jarvis_pass14.py

git commit -m "feat(jarvis): Pass 14 — plugin system, REST API, client rate limiter"

git push
