#!/usr/bin/env pwsh
# start-frontend.ps1 — Start the Asama.ai Next.js frontend

$REPO_ROOT = Split-Path -Parent $PSScriptRoot
$FRONTEND_DIR = Join-Path $REPO_ROOT "frontend"

Set-Location $FRONTEND_DIR

Write-Host "=== Asama.ai Frontend Startup ===" -ForegroundColor Cyan

# Check for package manager
$pkgManager = Get-Command "pnpm" -ErrorAction SilentlyContinue
if (-not $pkgManager) {
    $pkgManager = Get-Command "npm" -ErrorAction SilentlyContinue
    if (-not $pkgManager) {
        Write-Error "[ERROR] Neither pnpm nor npm found on PATH. Please install Node.js."
        exit 1
    }
    $cmd = "npm"
} else {
    $cmd = "pnpm"
}

# Install dependencies if node_modules missing
if (-not (Test-Path "node_modules")) {
    Write-Host "[1/2] Installing frontend dependencies ($cmd)..." -ForegroundColor Yellow
    & $cmd install
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
if ($cmd -eq "pnpm") {
    pnpm dev
} else {
    npm run dev
}
