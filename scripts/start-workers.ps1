#!/usr/bin/env pwsh
# start-workers.ps1 — Start Redis Streams workers
# Usage: .\scripts\start-workers.ps1 [embed|notify|llm|all]

$ErrorActionPreference = "Stop"

param(
    [string]$Worker = "all"
)

$REPO_ROOT = Split-Path -Parent $PSScriptRoot
$BACKEND_DIR = Join-Path $REPO_ROOT "backend"
$VENV_PYTHON = Join-Path $BACKEND_DIR ".venv\Scripts\python.exe"

Write-Host "=== A Social Network for AI Agents — Workers Startup ===" -ForegroundColor Cyan

if (-not (Test-Path $VENV_PYTHON)) {
    Write-Error "[ERROR] Virtual environment not found at $VENV_PYTHON. Please run .\scripts\start-backend.ps1 first."
    exit 1
}

# Set working directory and PYTHONPATH to backend directory
Set-Location $BACKEND_DIR
$env:PYTHONPATH = $BACKEND_DIR

$workers = @{
    "embed"       = "app.workers.embed_worker"
    "routing"     = "app.workers.routing_worker"
    "notify"      = "app.workers.notify_worker"
    "llm"         = "app.workers.llm_worker"
    "interaction" = "app.workers.llm_worker"
    "feedback"    = "app.workers.feedback_worker"
}

if ($Worker -eq "all") {
    foreach ($name in @("embed", "routing", "notify", "llm", "feedback")) {
        Write-Host "Starting $name worker..." -ForegroundColor Yellow
        Start-Process -FilePath $VENV_PYTHON -ArgumentList "-m", $workers[$name] -NoNewWindow
    }
} elseif ($workers.ContainsKey($Worker)) {
    Write-Host "Starting $Worker worker..." -ForegroundColor Green
    & $VENV_PYTHON -m $workers[$Worker]
} else {
    Write-Host "Unknown worker: $Worker. Use: embed | routing | notify | llm | interaction | feedback | all" -ForegroundColor Red
    exit 1
}

Write-Host "Workers started." -ForegroundColor Green
