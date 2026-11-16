#!/usr/bin/env pwsh
# start-frontend.ps1 — Start the Asama.ai Next.js frontend

Set-Location $PSScriptRoot\..\frontend

Write-Host "=== Asama.ai Frontend Startup ===" -ForegroundColor Cyan

# Install dependencies if node_modules missing
if (-not (Test-Path "node_modules")) {
    Write-Host "[1/2] Installing frontend dependencies (pnpm)..." -ForegroundColor Yellow
    pnpm install
}

# Create .env.local if missing
if (-not (Test-Path ".env.local")) {
    Write-Host "[!] Creating .env.local" -ForegroundColor Yellow
    @"
# Frontend environment (no secrets here)
BACKEND_URL=http://localhost:8000
NEXT_PUBLIC_APP_NAME=Asama.ai
"@ | Out-File -FilePath ".env.local" -Encoding utf8
}

Write-Host "[2/2] Starting Next.js dev server on http://localhost:3000" -ForegroundColor Green
pnpm dev
