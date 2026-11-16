#!/usr/bin/env pwsh
# start-workers.ps1 — Start Redis Streams workers
# Usage: .\scripts\start-workers.ps1 [embed|notify|llm|all]

param(
    [string]$Worker = "all"
)

$REPO_ROOT = Split-Path -Parent $PSScriptRoot
$BACKEND_DIR = Join-Path $REPO_ROOT "backend"
$VENV_PYTHON = Join-Path $BACKEND_DIR ".venv\Scripts\python.exe"

Write-Host "=== Asama.ai Workers Startup ===" -ForegroundColor Cyan

if (-not (Test-Path $VENV_PYTHON)) {
    Write-Error "[ERROR] Virtual environment not found at $VENV_PYTHON. Please run .\scripts\start-backend.ps1 first."
    exit 1
}

Set-Location $BACKEND_DIR

$workers = @{
    "embed"  = "app.workers.embed_worker"
    "notify" = "app.workers.notify_worker"
    "llm"    = "app.workers.llm_worker"
}

if ($Worker -eq "all") {
    foreach ($name in $workers.Keys) {
        Write-Host "Starting $name worker..." -ForegroundColor Yellow
        Start-Process -FilePath $VENV_PYTHON -ArgumentList "-m", $workers[$name] -NoNewWindow
    }
} elseif ($workers.ContainsKey($Worker)) {
    Write-Host "Starting $Worker worker..." -ForegroundColor Green
    & $VENV_PYTHON -m $workers[$Worker]
} else {
    Write-Host "Unknown worker: $Worker. Use: embed | notify | llm | all" -ForegroundColor Red
    exit 1
}

Write-Host "Workers started." -ForegroundColor Green
