<#
.SYNOPSIS
    CloudLens Local Developer Environment Startup Orchestrator (Prompt P00).
.DESCRIPTION
    1. Starts local infrastructure services using docker compose up -d --wait:
       PostgreSQL 16, Valkey/Redis, OpenBao, Keycloak, MinIO, Mailpit.
    2. Verifies health status of all running services.
    3. Executes database migrations to head (alembic upgrade head).
    4. Executes Prompt 49A Pre-Identity System Bootstrap.
    5. Prints verified service endpoint URLs.
    Fully idempotent: safe to execute repeatedly without duplicating state or causing errors.
#>
param (
    [switch]$SkipMigrations,
    [switch]$SkipBootstrap
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$rootDir = (Resolve-Path "$scriptDir\..").Path

Set-Location $rootDir
$env:PYTHONPATH = $rootDir

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "   CLOUDLENS LOCAL DEVELOPER ENVIRONMENT STARTUP (scripts/dev_up.ps1)   " -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan

# 1. Verify Prerequisites
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker is required on PATH but was not found."
    exit 1
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python is required on PATH but was not found."
    exit 1
}

# 2. Load environment variables from .env if present
$envFile = Join-Path $rootDir ".env"
if (Test-Path $envFile) {
    Write-Host "[1/5] Loading environment variables from .env..." -ForegroundColor Gray
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $name = $parts[0].Trim()
            $val = $parts[1].Trim()
            if (-not [Environment]::GetEnvironmentVariable($name, "Process")) {
                [Environment]::SetEnvironmentVariable($name, $val, "Process")
            }
        }
    }
} else {
    Write-Host "[1/5] .env not found; using defaults..." -ForegroundColor Gray
}

# Ensure baseline connectivity environment variables
if (-not $env:DATABASE_URL) {
    $env:DATABASE_URL = "postgresql://cloudlens:cloudlens_dev_password@localhost:5432/cloudlens"
}
if (-not $env:POSTGRES_HOST) { $env:POSTGRES_HOST = "localhost" }
if (-not $env:POSTGRES_PORT) { $env:POSTGRES_PORT = "5432" }
if (-not $env:POSTGRES_USER) { $env:POSTGRES_USER = "cloudlens" }
if (-not $env:POSTGRES_PASSWORD) { $env:POSTGRES_PASSWORD = "cloudlens_dev_password" }
if (-not $env:POSTGRES_DB) { $env:POSTGRES_DB = "cloudlens" }
if (-not $env:CLOUDLENS_REQUIRE_REALDB) { $env:CLOUDLENS_REQUIRE_REALDB = "1" }

# 3. Bring up docker compose infrastructure with --wait
$composeFile = Join-Path $rootDir "ops\docker-compose.yml"
Write-Host "`n[2/5] Starting infrastructure containers (docker compose up -d --wait)..." -ForegroundColor Cyan
docker compose -f $composeFile up -d --wait
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker Compose failed to bring up services."
    exit $LASTEXITCODE
}

Write-Host "`nHealthy Services:" -ForegroundColor Green
docker compose -f $composeFile ps

# 4. Database schema migration to head
if (-not $SkipMigrations) {
    Write-Host "`n[3/5] Applying database schema migrations (alembic upgrade head)..." -ForegroundColor Cyan
    python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Alembic migrations failed."
        exit $LASTEXITCODE
    }
    Write-Host "Database migrations verified at head." -ForegroundColor Green
}

# 5. Prompt 49A Pre-Identity System Bootstrap
if (-not $SkipBootstrap) {
    Write-Host "`n[4/5] Executing Prompt 49A Pre-Identity System Bootstrap..." -ForegroundColor Cyan
    python scripts/bootstrap_pre_identity.py
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Prompt 49A bootstrap failed."
        exit $LASTEXITCODE
    }

    Write-Host "`nProvisioning Keycloak users and roles (Prompt P02)..." -ForegroundColor Cyan
    python scripts/setup_keycloak_users.py
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Keycloak user provisioning failed."
        exit $LASTEXITCODE
    }
}

# 6. Service Endpoints
Write-Host "`n[5/5] Service URLs:" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Green
Write-Host "  API Docs (OpenAPI):   http://localhost:8000/docs" -ForegroundColor Yellow
Write-Host "  API Health Check:     http://localhost:8000/api/v1/health" -ForegroundColor Yellow
Write-Host "  Web Frontend:         http://localhost:3000" -ForegroundColor Yellow
Write-Host "  PostgreSQL 16:        localhost:5432 (db: cloudlens, user: cloudlens)" -ForegroundColor Yellow
Write-Host "  Valkey / Redis:       localhost:6379" -ForegroundColor Yellow
Write-Host "  OpenBao / Vault:      http://localhost:8200 (Token: dev-vault-token-cloudlens)" -ForegroundColor Yellow
Write-Host "  Keycloak (OIDC):      http://localhost:8081 (Admin: admin / DevKeycloakAdmin123!)" -ForegroundColor Yellow
Write-Host "  MinIO S3 Console:     http://localhost:9001 (cloudlens_minio / cloudlens_minio_password)" -ForegroundColor Yellow
Write-Host "  MinIO S3 Endpoint:    http://localhost:9000" -ForegroundColor Yellow
Write-Host "  Mailpit UI:           http://localhost:8025 (SMTP: localhost:1025)" -ForegroundColor Yellow
Write-Host "========================================================================" -ForegroundColor Green
Write-Host "CloudLens developer environment is UP and healthy." -ForegroundColor Green
