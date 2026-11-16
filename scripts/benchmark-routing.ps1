param(
    [int]$Candidates = 100
)

$ErrorActionPreference = "Stop"

$REPO_ROOT = Split-Path -Parent $PSScriptRoot
$BACKEND_DIR = Join-Path $REPO_ROOT "backend"
$VENV_PYTHON = Join-Path $BACKEND_DIR ".venv\Scripts\python.exe"

Write-Host "=== A Social Network for AI Agents -- In-Memory Routing Diagnostic Benchmark ===" -ForegroundColor Cyan

if (-not (Test-Path $VENV_PYTHON)) {
    Write-Error "[ERROR] Virtual environment not found at $VENV_PYTHON. Please run .\scripts\start-backend.ps1 first."
    exit 1
}

Set-Location $BACKEND_DIR
$env:PYTHONPATH = $BACKEND_DIR

& $VENV_PYTHON -m app.workers.benchmark_routing

Write-Host "=== In-Memory Benchmark Finished ===" -ForegroundColor Green
