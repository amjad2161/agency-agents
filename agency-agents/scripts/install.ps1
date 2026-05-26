<#
.SYNOPSIS
    One-shot installer for Agency Runtime on Windows.

.DESCRIPTION
    Bootstraps the runtime end-to-end on a fresh Windows machine:
      1. Disables the Microsoft-Store Python execution aliases (they break pip + venv)
      2. Installs Python 3.13 via winget if no real Python is found
      3. Clones (or updates) the repo to %USERPROFILE%\agency
      4. Creates a virtualenv and installs the runtime + extras
      5. Prompts for ANTHROPIC_API_KEY and persists it as a User env var
      6. Sets trust mode to yolo (persistent ~/.agency/trust.conf)
      7. Enables AGENCY_ENABLE_COMPUTER_USE for browser/desktop automation
      8. Initializes a starter profile and lessons file
      9. Runs 'agency doctor' to verify

    Idempotent: re-running updates the repo, refreshes deps, and skips
    anything already in place. Safe to run after a partial-failure run.

.PARAMETER NoLaunch
    Skip launching 'agency serve' at the end. Default behaviour starts the
    web UI on http://127.0.0.1:8765 once setup completes.

.PARAMETER InstallDir
    Override the install location. Defaults to "$env:USERPROFILE\agency".

.PARAMETER ApiKey
    Pre-supply the Anthropic API key (skips the interactive prompt).
    Useful for unattended installs.

.EXAMPLE
    # The one-line bootstrap. Run this in PowerShell:
    iwr -UseBasicParsing https://raw.githubusercontent.com/amjad2161/agency-agents/main/scripts/install.ps1 | iex

.EXAMPLE
    # Local run after cloning:
    .\scripts\install.ps1

.EXAMPLE
    # Unattended:
    .\scripts\install.ps1 -ApiKey "sk-ant-..." -NoLaunch
#>

[CmdletBinding()]
param(
    [string]$InstallDir = "$env:USERPROFILE\agency",
    [string]$ApiKey,
    [switch]$NoLaunch
)

$ErrorActionPreference = 'Stop'
$RepoUrl = 'https://github.com/amjad2161/agency-agents.git'

# ----- helpers ----------------------------------------------------------

function Write-Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Note($msg) { Write-Host "    $msg" -ForegroundColor DarkGray }
function Write-Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

function Test-Command($name) {
    [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Get-RealPythonExe {
    # Returns a path to a usable python.exe (NOT the Microsoft Store stub),
    # or $null if none can be found. The Store stub lives under
    # %LOCALAPPDATA%\Microsoft\WindowsApps and silently redirects to the Store
    # on first invocation, breaking pip + venv. We filter it out explicitly.
    # We also fall back to scanning the canonical winget / python.org install
    # locations directly — winget can complete a Python install before the
    # PATH refresh in this session picks the new directory up.
    $candidates = @()
    foreach ($name in 'python', 'python3', 'py') {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $cmd) {
            $candidates += $cmd.Source
        }
    }
    # Direct path scan, last-ditch. Walk python313 down to python310.
    foreach ($ver in '313', '312', '311', '310') {
        foreach ($base in @(
            (Join-Path $env:LOCALAPPDATA "Programs\Python\Python$ver"),
            (Join-Path $env:ProgramFiles    "Python$ver"),
            (Join-Path ${env:ProgramFiles(x86)} "Python$ver")
        )) {
            if ([string]::IsNullOrEmpty($base)) { continue }
            $exe = Join-Path $base 'python.exe'
            if (Test-Path $exe) { $candidates += $exe }
        }
    }
    foreach ($p in $candidates) {
        if ($null -eq $p) { continue }
        if ($p -like '*\WindowsApps\*') { continue }  # Store stub
        try {
            $ver = & $p --version 2>&1
            if ($ver -match '^Python 3\.(1[0-9]|[2-9][0-9])') {
                return $p
            }
        } catch {
            continue
        }
    }
    return $null
}

# ----- 1. unblock execution policy if needed ----------------------------

Write-Step "Checking PowerShell execution policy"
$cur = Get-ExecutionPolicy -Scope CurrentUser
if ($cur -in @('Restricted', 'AllSigned', 'Undefined')) {
    Write-Note "Setting CurrentUser policy to RemoteSigned (required for venv activation)."
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force
    Write-Ok "Done."
} else {
    Write-Ok "Policy is $cur — fine."
}

# ----- 2. nuke the Microsoft Store python aliases -----------------------

Write-Step "Disabling the Microsoft Store python aliases"
$aliasDir = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps'
foreach ($stub in 'python.exe', 'python3.exe') {
    $stubPath = Join-Path $aliasDir $stub
    if (Test-Path $stubPath) {
        try {
            Remove-Item $stubPath -Force -ErrorAction Stop
            Write-Ok "Removed $stub stub."
        } catch {
            Write-Warn "Could not remove $stub stub (likely benign — the real Python on PATH wins). $_"
        }
    }
}

# ----- 3. install Python 3.13 if needed ---------------------------------

Write-Step "Locating a real Python interpreter"
$py = Get-RealPythonExe
if ($null -eq $py) {
    Write-Note "No suitable Python found. Installing Python 3.13 via winget..."
    if (-not (Test-Command 'winget')) {
        Write-Host ""
        Write-Host "winget is not available on this machine. Install Python 3.13 manually:" -ForegroundColor Red
        Write-Host "  https://www.python.org/downloads/windows/" -ForegroundColor Red
        Write-Host "  …with 'Add python.exe to PATH' CHECKED." -ForegroundColor Red
        Write-Host "Then re-run this script." -ForegroundColor Red
        exit 1
    }
    & winget install --id Python.Python.3.13 -e --silent --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget install of Python.Python.3.13 failed (exit $LASTEXITCODE)."
    }
    # Refresh PATH for the current session so we can find the new python.exe.
    $env:PATH = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [System.Environment]::GetEnvironmentVariable('Path', 'User')
    $py = Get-RealPythonExe
    if ($null -eq $py) {
        throw "Python install reported success but I still can't find it on PATH. Restart PowerShell and re-run."
    }
    Write-Ok "Installed: $py"
} else {
    Write-Ok "Found: $py ($(& $py --version))"
}

# ----- 4. clone or update the repo --------------------------------------

Write-Step "Fetching the repo into $InstallDir"
if (-not (Test-Command 'git')) {
    if (Test-Command 'winget') {
        Write-Note "git is not installed; installing Git.Git via winget..."
        & winget install --id Git.Git -e --silent --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) {
            throw "winget install of Git.Git failed (exit $LASTEXITCODE)."
        }
        # Refresh PATH so the new git.exe is reachable in this session.
        $env:PATH = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                    [System.Environment]::GetEnvironmentVariable('Path', 'User')
        if (-not (Test-Command 'git')) {
            # winget installs Git to %ProgramFiles%\Git\cmd by default; add it
            # explicitly in case the PATH refresh missed it.
            $gitCmd = Join-Path $env:ProgramFiles 'Git\cmd'
            if (Test-Path $gitCmd) { $env:PATH = "$gitCmd;$env:PATH" }
        }
        if (-not (Test-Command 'git')) {
            throw "Git installed but not on PATH. Restart PowerShell and re-run."
        }
        Write-Ok "Installed git: $((Get-Command git).Source)"
    } else {
        Write-Host "git is not installed and winget isn't available." -ForegroundColor Red
        Write-Host "Install Git for Windows manually: https://git-scm.com/download/win" -ForegroundColor Red
        Write-Host "Then re-run this script." -ForegroundColor Red
        exit 1
    }
}
if (Test-Path (Join-Path $InstallDir '.git')) {
    Push-Location $InstallDir
    try {
        Write-Note "Repo already exists; pulling latest main."
        & git fetch origin main
        & git checkout main
        & git pull --ff-only origin main
    } finally {
        Pop-Location
    }
} else {
    if (Test-Path $InstallDir) {
        $existing = Get-ChildItem $InstallDir -Force | Measure-Object
        if ($existing.Count -gt 0) {
            throw "$InstallDir already exists and is not a git checkout. Move it aside or pass -InstallDir <other path>."
        }
    } else {
        New-Item -ItemType Directory -Path $InstallDir | Out-Null
    }
    & git clone --depth 1 $RepoUrl $InstallDir
}
Write-Ok "Repo at $InstallDir"

# ----- 5. virtualenv + pip install --------------------------------------

Write-Step "Creating virtualenv and installing the runtime"
Push-Location $InstallDir
try {
    $venvPath = Join-Path $InstallDir '.venv'
    if (-not (Test-Path $venvPath)) {
        & $py -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "venv creation failed." }
        Write-Ok "Created .venv"
    } else {
        Write-Ok ".venv already exists; reusing."
    }
    $venvPy  = Join-Path $venvPath 'Scripts\python.exe'
    $venvPip = Join-Path $venvPath 'Scripts\pip.exe'
    # Don't pass --quiet on pip: a silent failure here looks like the
    # whole installer hung. Better to show progress + surface real errors.
    & $venvPy -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip self-upgrade failed (exit $LASTEXITCODE)." }
    & $venvPip install -e runtime
    if ($LASTEXITCODE -ne 0) { throw "pip install runtime failed (exit $LASTEXITCODE)." }
    & $venvPip install -e "runtime[docs]"
    if ($LASTEXITCODE -ne 0) { throw "pip install runtime[docs] failed (exit $LASTEXITCODE)." }
    & $venvPip install -e "runtime[computer]"
    if ($LASTEXITCODE -ne 0) { throw "pip install runtime[computer] failed (exit $LASTEXITCODE)." }
    Write-Ok "Runtime + [docs] + [computer] installed in .venv"
} finally {
    Pop-Location
}

# ----- 6. ANTHROPIC_API_KEY ---------------------------------------------

Write-Step "Configuring ANTHROPIC_API_KEY"
$existing = [System.Environment]::GetEnvironmentVariable('ANTHROPIC_API_KEY', 'User')
if ([string]::IsNullOrWhiteSpace($ApiKey) -and -not [string]::IsNullOrWhiteSpace($existing)) {
    Write-Ok "Key already set in User env (length $($existing.Length))."
    $env:ANTHROPIC_API_KEY = $existing
} else {
    if ([string]::IsNullOrWhiteSpace($ApiKey)) {
        Write-Host ""
        Write-Host "    Get a key at: https://console.anthropic.com/settings/keys" -ForegroundColor DarkGray
        Write-Host "    The prompt below hides input. Press Enter to skip; you can set it later." -ForegroundColor DarkGray
        $secure = Read-Host "    Paste your ANTHROPIC_API_KEY" -AsSecureString
        $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try {
            $ApiKey = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
        } finally {
            [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($ApiKey)) {
        [System.Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY', $ApiKey, 'User')
        $env:ANTHROPIC_API_KEY = $ApiKey
        Write-Ok "Saved to User env (length $($ApiKey.Length))."
    } else {
        Write-Warn "No key provided. Set later with:"
        Write-Warn '  [System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")'
    }
}

# ----- 7. computer_use feature flag ------------------------------------

Write-Step "Enabling computer_use (browser/desktop automation)"
[System.Environment]::SetEnvironmentVariable('AGENCY_ENABLE_COMPUTER_USE', '1', 'User')
$env:AGENCY_ENABLE_COMPUTER_USE = '1'
Write-Ok "AGENCY_ENABLE_COMPUTER_USE=1 (User env)"

# ----- 8. trust mode + profile + lessons --------------------------------

$venvScripts = Join-Path $InstallDir '.venv\Scripts'
$agencyExe   = Join-Path $venvScripts 'agency.exe'

Write-Step "Setting trust mode to yolo"
& $agencyExe trust set yolo | Out-Null
Write-Ok "Persistent: $env:USERPROFILE\.agency\trust.conf"

Write-Step "Initializing profile and lessons"
$profilePath = Join-Path $env:USERPROFILE '.agency\profile.md'
if (-not (Test-Path $profilePath)) {
    # Don't open an editor in unattended mode; just lay down the template.
    $profileDir = Split-Path $profilePath -Parent
    if (-not (Test-Path $profileDir)) { New-Item -ItemType Directory -Path $profileDir | Out-Null }
    @"
# About me

<!-- Edit this file. Anything you put here is sent to every agent as
     background context. Keep it tight — every byte is in every prompt. -->

- Name:
- Role / context:
- Country / timezone:
- Communication style:
- Tools / stacks I use:
- Risk tolerance (low / medium / high):

# Things I always want

-

# Things I never want

-
"@ | Set-Content -Path $profilePath -Encoding UTF8
    Write-Ok "Created $profilePath (edit it before your first real run)."
} else {
    Write-Ok "Profile already exists at $profilePath."
}

# Seed the lessons file with one starter line so the loader has something
# to inject from session 1. The agent can append from there.
$lessonsPath = Join-Path $env:USERPROFILE '.agency\lessons.md'
if (-not (Test-Path $lessonsPath)) {
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-dd HH:mm UTC')
    @"
# Lessons learned

<!-- Cross-session memory. The agent reads this at the start of every
     session and appends to it during/after work. You can edit any
     entry by hand. -->

## $stamp · install

WORKED:    Setup completed via scripts/install.ps1.
COST:      —
NEVER-AGAIN: —
NEXT-TIME: Edit ~/.agency/profile.md before the first real run.
"@ | Set-Content -Path $lessonsPath -Encoding UTF8
    Write-Ok "Created $lessonsPath."
} else {
    Write-Ok "Lessons file already exists at $lessonsPath."
}

# ----- 9. doctor --------------------------------------------------------

Write-Step "Verifying with 'agency doctor'"
& $agencyExe doctor

# ----- 10. launch --------------------------------------------------------

if ($NoLaunch) {
    Write-Step "Done"
    Write-Host ""
    Write-Host "Activate the venv in any new shell with:" -ForegroundColor Green
    Write-Host "  cd $InstallDir; .\.venv\Scripts\Activate.ps1" -ForegroundColor Green
    Write-Host ""
    Write-Host "Then:" -ForegroundColor Green
    Write-Host "  agency serve --port 8765       # full UI" -ForegroundColor Green
    Write-Host "  agency run `"...`"               # CLI" -ForegroundColor Green
    Write-Host "  agency run `"...`" --skill jarvis-brainiac" -ForegroundColor Green
} else {
    Write-Step "Launching 'agency serve' on http://127.0.0.1:8765"
    Write-Note "Ctrl+C to stop the server. Re-launch later with: cd $InstallDir; .\.venv\Scripts\Activate.ps1; agency serve"

    # Open the browser AFTER the port is actually listening — opening it
    # immediately gave 'site can't be reached' until the server bound.
    # Background job polls the port, then opens the browser; the main
    # script execs `agency serve` so the user sees server logs in this
    # window and can Ctrl+C to stop.
    Start-Job -ScriptBlock {
        param($url)
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Milliseconds 500
            try {
                $tcp = New-Object Net.Sockets.TcpClient
                $tcp.Connect('127.0.0.1', 8765)
                $tcp.Close()
                Start-Process $url
                return
            } catch {
                continue
            }
        }
    } -ArgumentList 'http://127.0.0.1:8765' | Out-Null

    & $agencyExe serve --port 8765
}
