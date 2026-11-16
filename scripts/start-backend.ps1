#!/usr/bin/env pwsh
# start-backend.ps1 — Start the Asama.ai FastAPI backend
# Usage: .\scripts\start-backend.ps1

$PYTHON = "C:\Users\Acer\AppData\Local\Python\bin\python.exe"
$VENV = ".\backend\.venv"
$VENV_PYTHON = "$VENV\Scripts\python.exe"
$BACKEND_DIR = ".\backend"

Set-Location $PSScriptRoot\..

Write-Host "=== Asama.ai Backend Startup ===" -ForegroundColor Cyan

# Create venv if missing
if (-not (Test-Path $VENV_PYTHON)) {
    Write-Host "[1/3] Creating Python virtual environment..." -ForegroundColor Yellow
    & $PYTHON -m venv $VENV
}

# Install dependencies
Write-Host "[2/3] Installing backend dependencies..." -ForegroundColor Yellow
& "$VENV\Scripts\pip.exe" install -e ".\backend[dev]" --quiet

# Copy .env.example to .env if .env doesn't exist
if (-not (Test-Path "$BACKEND_DIR\.env")) {
    Write-Host "[!] No .env found — copying from .env.example" -ForegroundColor Yellow
    Copy-Item "$BACKEND_DIR\.env.example" "$BACKEND_DIR\.env"
    Write-Host "[!] IMPORTANT: Edit backend\.env before running in production!" -ForegroundColor Red
}

# Start server
Write-Host "[3/3] Starting FastAPI server on http://localhost:8000" -ForegroundColor Green
Set-Location $BACKEND_DIR
& "$VENV\Scripts\uvicorn.exe" app.main:app --host 0.0.0.0 --port 8000 --reload
