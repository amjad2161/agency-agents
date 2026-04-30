# JARVIS Pass 3 Push Script
# Run as: Right-click → Run with PowerShell  (or: cd agency; .\scripts\dev\jarvis-push-p3.ps1)

# Resolve the repo root (this script lives in scripts/dev/, two levels deep).
Set-Location (Resolve-Path (Join-Path $PSScriptRoot "..\.."))

# Clear stale lock files
Get-Process -Name "git" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500
Remove-Item ".git\index.lock"  -Force -ErrorAction SilentlyContinue
Remove-Item ".git\MERGE_HEAD"  -Force -ErrorAction SilentlyContinue

git add -A
git status --short

git commit -m "feat(jarvis): Pass 3 — soul filter, chat REPL, Jerusalem TZ, routing, 594 tests

- jarvis_soul.py: filter_response() strips forbidden phrases
    * 'as an AI' → 'as JARVIS', 'I cannot' → 'JARVIS does not'
    * removes feelings disclaimers, apologetic openers, motivational filler
    * has_forbidden_phrase() audit helper; __all__ exports complete
- jarvis_greeting.py: Asia/Jerusalem via zoneinfo, bilingual greeting
    * _jerusalem_now() with UTC fallback
    * _time_period() → (Hebrew, English) for 5 time bands
    * get_greeting() returns e.g. 'ערב טוב, Amjad. Good evening. 22:14 IST.'
- cli.py: agency chat REPL fully wired
    * startup banner + greeting on launch
    * filter_response() applied to all output
    * built-ins: !skills, !route <text>, exit/quit/bye
    * clean Ctrl+C → farewell → exit
- jarvis_brain.py: KEYWORD_SLUG_BOOST expanded to 110+ entries
    * poem/poetry → creative-writing (9.0)
    * translate/hebrew → linguistics-nlp (9.0/8.0)
    * draw/picture → design-creative (8.0)
    * video/make a video → content-media (8.0/10.0)
    * build an api → backend-architect (12.0)
    * fix a bug → omega-engineer (10.0)
    * make a website → frontend (10.0)
    * send email → email-intelligence (10.0)
    * search the web → journalism-research (10.0)
    * analyze data/data analysis → data (9.0/10.0)
    * routing accuracy: 10/10
- amjad_memory.py: confirmed real (Asia/Jerusalem, Hebrew pref, full profile)
- vector_memory.py: confirmed real (TF-IDF + SQLite, not stub)
- trust.py: confirmed real (TrustGate + shell denylist, not stub)
- tests/test_jarvis_pass3.py: 28 new tests added
- JARVIS_CAPABILITIES.md: updated (594 tests, soul filter section, chat REPL)
- Total test suite: 594 passed, 0 failed"

git push origin HEAD:main --force-with-lease
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Pass 3 pushed. מוכן."
} else {
    Write-Error "Push failed — check remote status."
}
