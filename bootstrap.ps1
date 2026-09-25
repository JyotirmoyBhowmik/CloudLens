<#
.SYNOPSIS
    CloudLens One-Command Developer Bootstrap (Windows PowerShell)
.DESCRIPTION
    Brings up PostgreSQL, Redis, MinIO S3 store, Vault secret store, applies migrations,
    seeds reference data, and runs health verification.
#>

$ErrorActionPreference = "Stop"
Write-Host ">>> Starting CloudLens Developer Bootstrap..." -ForegroundColor Cyan

# 1. Check Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python is required but was not found on PATH."
    exit 1
}

# 2. Run Python Bootstrap Orchestrator
python scripts/bootstrap.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "Bootstrap failed with exit code $LASTEXITCODE."
    exit $LASTEXITCODE
}

Write-Host ">>> To start the API server locally: uvicorn api.cloudlens_api.main:app --reload --port 8000" -ForegroundColor Green
Write-Host ">>> To start the Web server: cd web; pnpm dev" -ForegroundColor Green
