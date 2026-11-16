#!/usr/bin/env pwsh
# start-workers.ps1 — Start Redis Streams workers
# Usage: .\scripts\start-workers.ps1 [embed|notify|llm|all]

param(
    [string]$Worker = "all"
)

$VENV = "$PSScriptRoot\..\backend\.venv"
$PYTHON = "$VENV\Scripts\python.exe"
$BACKEND_DIR = "$PSScriptRoot\..\backend"

Write-Host "=== Asama.ai Workers Startup ===" -ForegroundColor Cyan

Set-Location $BACKEND_DIR

$workers = @{
    "embed"  = "app.workers.embed_worker"
    "notify" = "app.workers.notify_worker"
    "llm"    = "app.workers.llm_worker"
}

if ($Worker -eq "all") {
    foreach ($name in $workers.Keys) {
        Write-Host "Starting $name worker..." -ForegroundColor Yellow
        Start-Process -FilePath $PYTHON -ArgumentList "-m", $workers[$name] -NoNewWindow
    }
} elseif ($workers.ContainsKey($Worker)) {
    Write-Host "Starting $Worker worker..." -ForegroundColor Green
    & $PYTHON -m $workers[$Worker]
} else {
    Write-Host "Unknown worker: $Worker. Use: embed | notify | llm | all" -ForegroundColor Red
    exit 1
}

Write-Host "Workers started." -ForegroundColor Green
