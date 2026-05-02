# =============================================================================
# FIX_KNOWN_BUGS.ps1  —  applies fixes for the 3 test collection errors
# discovered by the dry-run of JARVIS_SINGULARITY_DRIVER.
# =============================================================================
# Bugs:
#   1. runtime/agency/context_manager.py — missing ContextEntry dataclass
#      (imported by test_context_manager.py + test_new_modules.py)
#   2. runtime/tests/test_shell_skill.py:255 — truncated function name
#      "    ilure(self) -> None:" → "    def test_failure(self) -> None:"
# =============================================================================

[CmdletBinding()]
param(
    [string]$AgencyRoot = "$env:USERPROFILE\agency"
)
$ErrorActionPreference = "Stop"

function Write-Step { param([string]$Title) Write-Host "`n========== $Title ==========`n" -ForegroundColor Cyan }
function Write-Info { param([string]$Msg) Write-Host "  $Msg" }

Write-Step "BUG 1 — Add ContextEntry to context_manager.py"

$cmPath = Join-Path $AgencyRoot "runtime\agency\context_manager.py"
if (!(Test-Path $cmPath)) {
    Write-Info "MISSING: $cmPath — skipping"
} else {
    $content = Get-Content $cmPath -Raw
    if ($content -match "class\s+ContextEntry") {
        Write-Info "ContextEntry already exists — no fix needed"
    } else {
        $patch = @"

# ============================================================================
# ContextEntry — added by FIX_KNOWN_BUGS.ps1 (Pass 25 hotfix)
# Required by test_context_manager.py and test_new_modules.py
# ============================================================================
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class ContextEntry:
    """A single entry in the agent's working context.

    Attributes:
        content: The textual content of the entry.
        kind: Category (e.g. 'message', 'tool_result', 'observation').
        ts: ISO-8601 UTC timestamp of when the entry was created.
        tags: Optional labels for filtering/retrieval.
        metadata: Arbitrary extra data.
    """
    content: str
    kind: str = "message"
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "kind": self.kind,
            "ts": self.ts,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContextEntry":
        return cls(
            content=data.get("content", ""),
            kind=data.get("kind", "message"),
            ts=data.get("ts", datetime.now(timezone.utc).isoformat()),
            tags=list(data.get("tags", [])),
            metadata=dict(data.get("metadata", {})),
        )

"@
        # Append the patch
        Add-Content -Path $cmPath -Value $patch -Encoding utf8
        Write-Info "Appended ContextEntry to $cmPath"
    }
}

Write-Step "BUG 2 — Fix test_shell_skill.py:255 truncated function name"

$tsPath = Join-Path $AgencyRoot "runtime\tests\test_shell_skill.py"
if (!(Test-Path $tsPath)) {
    Write-Info "MISSING: $tsPath — skipping"
} else {
    $lines = Get-Content $tsPath
    $line255 = $lines[254]    # 0-indexed
    Write-Info "Current line 255: '$line255'"

    if ($line255 -match "^\s*ilure\(self\)") {
        # Replace the broken line with a proper definition.
        # Best guess: was "def test_failure(self)" before truncation.
        $lines[254] = $line255 -replace "^(\s*)ilure\(self\)", "`$1def test_failure(self)"
        Set-Content -Path $tsPath -Value $lines -Encoding utf8
        Write-Info "Patched line 255 to: '$($lines[254])'"
    } elseif ($line255 -match "^\s*def\s+test_") {
        Write-Info "Already patched — no fix needed"
    } else {
        Write-Info "Line 255 doesn't match expected pattern. Manual review:"
        Write-Info "  $line255"
        Write-Info "  Adjacent context (lines 252-258):"
        for ($i = 251; $i -lt 258 -and $i -lt $lines.Length; $i++) {
            Write-Info "    [$($i+1)]: $($lines[$i])"
        }
    }
}

Write-Step "VERIFY — re-run pytest collection"

$venv = Join-Path $AgencyRoot ".venv\Scripts\python.exe"
if (Test-Path $venv) {
    Push-Location $AgencyRoot
    try {
        & $venv -m pytest runtime/tests --collect-only -q 2>&1 | Select-Object -Last 30 | ForEach-Object {
            Write-Host "  $_"
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Info "venv not found at $venv — skipping verification"
}

Write-Host "`n=== FIX_KNOWN_BUGS done ===" -ForegroundColor Green
