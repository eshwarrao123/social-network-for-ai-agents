#!/usr/bin/env pwsh
# backfill-embeddings.ps1 — Backfill missing embeddings for Posts and Agents
# Usage: .\scripts\backfill-embeddings.ps1 [-Mode enqueue|direct] [-Limit 200]

$ErrorActionPreference = "Stop"

param(
    [ValidateSet("enqueue", "direct")]
    [string]$Mode = "enqueue",
    [int]$Limit = 200
)

$REPO_ROOT = Split-Path -Parent $PSScriptRoot
$BACKEND_DIR = Join-Path $REPO_ROOT "backend"
$VENV_PYTHON = Join-Path $BACKEND_DIR ".venv\Scripts\python.exe"

Write-Host "=== A Social Network for AI Agents — Semantic Embedding Backfill ===" -ForegroundColor Cyan
Write-Host "Mode: $Mode | Limit: $Limit" -ForegroundColor DarkGray

if (-not (Test-Path $VENV_PYTHON)) {
    Write-Error "[ERROR] Virtual environment not found at $VENV_PYTHON. Please run .\scripts\start-backend.ps1 first."
    exit 1
}

# Set working directory and PYTHONPATH to backend directory
Set-Location $BACKEND_DIR
$env:PYTHONPATH = $BACKEND_DIR

& $VENV_PYTHON -m app.workers.backfill --mode $Mode --limit $Limit

Write-Host "=== Backfill Execution Finished ===" -ForegroundColor Green
