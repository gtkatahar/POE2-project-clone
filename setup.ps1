#Requires -Version 5.1
<#
.SYNOPSIS
    First-time setup for POE2 Crafting Helper.
    Installs Python if missing, creates a venv, and installs all dependencies.
#>

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# --- helpers -----------------------------------------------------------------

function Write-Step { param($msg) Write-Host ""; Write-Host ">>> $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "    OK   $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "    WARN $msg" -ForegroundColor Yellow }
function Write-Err  { param($msg) Write-Host "    ERR  $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "================================================" -ForegroundColor Magenta
Write-Host "  POE2 Crafting Helper - First-time setup       " -ForegroundColor Magenta
Write-Host "================================================" -ForegroundColor Magenta

# --- 1. Locate or install Python 3.11+ ---------------------------------------

Write-Step "Checking for Python 3.11+..."

$PythonExe = $null

foreach ($cmd in @('py', 'python', 'python3')) {
    try {
        $raw = & $cmd --version 2>&1
        if ("$raw" -match 'Python (\d+)\.(\d+)') {
            if ([int]$Matches[1] -ge 3 -and [int]$Matches[2] -ge 11) {
                $PythonExe = $cmd
                Write-Ok "Found $raw  ($cmd)"
                break
            }
            Write-Warn "Found $raw but need 3.11+ -- will install a newer version."
        }
    } catch {
        # command not found, try next
    }
}

if (-not $PythonExe) {
    Write-Step "Python not found -- attempting automatic install..."

    $wingetCmd = Get-Command winget -ErrorAction SilentlyContinue
    if ($wingetCmd) {
        Write-Host "    Using winget to install Python 3.13..." -ForegroundColor Cyan
        winget install --id Python.Python.3.13 --source winget --accept-package-agreements --accept-source-agreements
    } else {
        Write-Host "    winget not available -- downloading Python 3.13 installer..." -ForegroundColor Cyan
        $pyUrl  = 'https://www.python.org/ftp/python/3.13.0/python-3.13.0-amd64.exe'
        $pyInst = Join-Path $env:TEMP 'python-3.13.0-amd64.exe'
        try {
            Invoke-WebRequest -Uri $pyUrl -OutFile $pyInst -UseBasicParsing
        } catch {
            Write-Err "Download failed."
            Write-Err "Please install Python 3.11+ manually from https://www.python.org/downloads/ then re-run this script."
            Read-Host "Press Enter to exit"
            exit 1
        }
        Start-Process -FilePath $pyInst -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1' -Wait
        Remove-Item $pyInst -Force
    }

    # Refresh PATH in the current session so the new install is visible
    $machinePath = [System.Environment]::GetEnvironmentVariable('PATH', 'Machine')
    $userPath    = [System.Environment]::GetEnvironmentVariable('PATH', 'User')
    $env:PATH    = "$machinePath;$userPath"

    foreach ($cmd in @('py', 'python', 'python3')) {
        try {
            $raw = & $cmd --version 2>&1
            if ("$raw" -match 'Python 3') {
                $PythonExe = $cmd
                break
            }
        } catch {
            # try next
        }
    }

    if (-not $PythonExe) {
        Write-Err "Python was installed but is not visible in PATH yet."
        Write-Err "Close this terminal, reopen it, and run setup.ps1 again."
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Ok "Python ready: $(& $PythonExe --version 2>&1)"
}

# --- 2. Create virtual environment -------------------------------------------

Write-Step "Setting up virtual environment (.venv)..."

$venvPython = Join-Path $ScriptDir '.venv\Scripts\python.exe'
$venvPip    = Join-Path $ScriptDir '.venv\Scripts\pip.exe'

if (Test-Path $venvPython) {
    Write-Ok ".venv already exists -- skipping creation."
} else {
    & $PythonExe -m venv .venv
    Write-Ok ".venv created."
}

# --- 3. Upgrade pip ----------------------------------------------------------

Write-Step "Upgrading pip..."
& $venvPython -m pip install --upgrade pip --quiet
Write-Ok "pip is up to date."

# --- 4. Install project dependencies -----------------------------------------

Write-Step "Installing dependencies from requirements.txt..."
& $venvPip install -r requirements.txt
Write-Ok "All packages installed."

# --- 5. Quick smoke-test -----------------------------------------------------

Write-Step "Verifying key imports..."

$checkScript = 'import PyQt6.QtWidgets, pyautogui, requests, bs4; print("imports OK")'
$result = & $venvPython -c $checkScript 2>&1

if ("$result" -match 'imports OK') {
    Write-Ok "All core imports verified."
} else {
    Write-Warn "Import check returned unexpected output -- packages may not be fully installed."
    Write-Host "    $result" -ForegroundColor Yellow
}

# --- 6. Done -----------------------------------------------------------------

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  To launch the GUI any time run:" -ForegroundColor White
Write-Host "    .\.venv\Scripts\python.exe gui_main.py" -ForegroundColor Yellow
Write-Host "================================================" -ForegroundColor Green
Write-Host ""

$ans = Read-Host "Launch the GUI now? [Y/n]"
if ($ans -eq '' -or $ans -match '^[Yy]') {
    & $venvPython gui_main.py
}
