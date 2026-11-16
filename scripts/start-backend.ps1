#!/usr/bin/env pwsh
# start-backend.ps1 — Start the Asama.ai FastAPI backend
# Usage: .\scripts\start-backend.ps1

$ErrorActionPreference = "Stop"

# Determine repository root dynamically
$REPO_ROOT = Split-Path -Parent $PSScriptRoot
$BACKEND_DIR = Join-Path $REPO_ROOT "backend"
$VENV_DIR = Join-Path $BACKEND_DIR ".venv"
$VENV_PYTHON = Join-Path $VENV_DIR "Scripts\python.exe"
$VENV_UVICORN = Join-Path $VENV_DIR "Scripts\uvicorn.exe"
$VENV_PIP = Join-Path $VENV_DIR "Scripts\pip.exe"

Write-Host "=== Asama.ai Backend Startup ===" -ForegroundColor Cyan
Write-Host "Repository root: $REPO_ROOT" -ForegroundColor DarkGray

function Find-SystemPython {
    # 1. Check Python launcher
    $pyCmd = Get-Command "py" -ErrorAction SilentlyContinue
    if ($pyCmd) {
        try {
            $path = & py -3 -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $path -and (Test-Path $path.Trim())) {
                return $path.Trim()
            }
        } catch {}
    }

    # 2. Check python executable on PATH (excluding WindowsApps redirector)
    $pythonCmds = Get-Command "python" -All -ErrorAction SilentlyContinue
    foreach ($cmd in $pythonCmds) {
        if ($cmd.Source -notmatch "WindowsApps") {
            try {
                $path = & $cmd.Source -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $path -and (Test-Path $path.Trim())) {
                    return $path.Trim()
                }
            } catch {}
        }
    }

    # 3. Check common Windows user installation paths
    $commonPaths = @(
        "$env:LOCALAPPDATA\Python\bin\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python315\python.exe",
        "C:\Python311\python.exe",
        "C:\Python312\python.exe",
        "C:\Python313\python.exe"
    )

    foreach ($p in $commonPaths) {
        if (Test-Path $p) {
            return $p
        }
    }

    return $null
}

# Ensure virtual environment exists
if (-not (Test-Path $VENV_PYTHON)) {
    Write-Host "[1/3] Virtual environment not found. Locating Python 3..." -ForegroundColor Yellow
    $systemPython = Find-SystemPython

    if (-not $systemPython) {
        Write-Error @"
[ERROR] Python executable not found on this system.
Please install Python 3.11+ and ensure it is available in PATH or LOCALAPPDATA.
Download: https://www.python.org/downloads/
"@
        exit 1
    }

    Write-Host "Found Python: $systemPython" -ForegroundColor DarkGray
    Write-Host "Creating virtual environment at $VENV_DIR..." -ForegroundColor Yellow
    & $systemPython -m venv $VENV_DIR
    if ($LASTEXITCODE -ne 0) {
        Write-Error "[ERROR] Failed to create virtual environment at $VENV_DIR"
        exit 1
    }
}

# Verify pip in venv
if (-not (Test-Path $VENV_PIP)) {
    Write-Error "[ERROR] pip not found in virtual environment at $VENV_PIP"
    exit 1
}

# Install dependencies if not installed
Write-Host "[2/3] Verifying backend dependencies..." -ForegroundColor Yellow
& $VENV_PIP install -e "$BACKEND_DIR[dev]" --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Warning "[WARN] pip install encountered warnings or errors. Ensure dependencies are installed."
}

# Copy .env.example to .env if .env doesn't exist
$ENV_FILE = Join-Path $BACKEND_DIR ".env"
$ENV_EXAMPLE = Join-Path $BACKEND_DIR ".env.example"
if (-not (Test-Path $ENV_FILE)) {
    if (Test-Path $ENV_EXAMPLE) {
        Write-Host "[!] No .env found — copying from .env.example" -ForegroundColor Yellow
        Copy-Item $ENV_EXAMPLE $ENV_FILE
        Write-Host "[!] Notice: Please configure $ENV_FILE for your environment." -ForegroundColor Yellow
    }
}

# Start server
if (-not (Test-Path $VENV_UVICORN)) {
    Write-Error "[ERROR] uvicorn executable not found at $VENV_UVICORN. Run: pip install uvicorn"
    exit 1
}

Write-Host "[3/3] Starting FastAPI server on http://localhost:8000" -ForegroundColor Green
Set-Location $BACKEND_DIR
& $VENV_UVICORN app.main:app --host 0.0.0.0 --port 8000 --reload
