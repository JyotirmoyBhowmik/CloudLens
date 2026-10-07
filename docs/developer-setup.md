# CloudLens Developer Setup Guide (Windows & WSL2)

This guide walks through configuring and running the CloudLens local development environment on native **Windows (PowerShell)** and **WSL2 (Ubuntu/Debian)**.

---

## 1. Prerequisites

Ensure the following tools are installed on your host machine:

| Tool | Version Requirement | Verification Command | Notes |
| :--- | :--- | :--- | :--- |
| **Python** | `>= 3.11` | `python --version` | Recommended: Python 3.11.x virtual environment |
| **Docker Desktop** | `>= 25.0` | `docker --version` | Ensure WSL2 backend is enabled in Docker settings |
| **Node.js** | `>= 20.0` | `node --version` | Required for the Next.js / React web shell |
| **pnpm** | `>= 9.0` | `pnpm --version` | Package manager for `web/` workspace |
| **Git** | `>= 2.40` | `git --version` | Standard version control |

---

## 2. Environment Configuration

1. Copy the provided `.env.example` template to `.env`:
   ```powershell
   # Windows PowerShell
   Copy-Item .env.example .env
   ```
   ```bash
   # WSL2 / Linux Bash
   cp .env.example .env
   ```

2. `.env` is ignored by `.gitignore` and must never contain real production secrets. The development default values match the local docker compose services.

---

## 3. Starting Infrastructure Services

CloudLens provides a single-command orchestrator script that brings up all required infrastructure containers, verifies healthchecks, runs database migrations, and performs pre-identity bootstrapping:

### Windows PowerShell
```powershell
.\scripts\dev_up.ps1
```

### WSL2 / Linux
```bash
# 1. Bring up containers and wait for healthchecks
docker compose -f ops/docker-compose.yml up -d --wait

# 2. Apply database migrations to head
python -m alembic upgrade head

# 3. Execute pre-identity bootstrapping (Prompt 49A)
python scripts/bootstrap_pre_identity.py
```

The script is **completely idempotent** and safe to run repeatedly.

---

## 4. Local Service Ports & Access Credentials

When started via `dev_up.ps1`, the following infrastructure services are available:

| Service | Container Name | Host Port | Internal Port | Healthcheck / Readiness | Credentials / Token |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **PostgreSQL 16** | `cloudlens-postgres` | `5432` | `5432` | `pg_isready` | user: `cloudlens`<br>pass: `cloudlens_dev_password`<br>db: `cloudlens` |
| **Valkey / Redis** | `cloudlens-redis` | `6379` | `6379` | `redis-cli ping` | (No auth for local dev) |
| **OpenBao (Dev Mode)** | `cloudlens-openbao` | `8200` | `8200` | `GET /v1/sys/health` | Token: `dev-vault-token-cloudlens` |
| **Keycloak (OIDC)** | `cloudlens-keycloak` | `8081` | `8080` | `GET /realms/cloudlens` | user: `admin`<br>pass: `DevKeycloakAdmin123!` |
| **MinIO S3** | `cloudlens-minio` | `9000` (API)<br>`9001` (Web) | `9000`<br>`9001` | `GET /minio/health/live` | user: `cloudlens_minio`<br>pass: `cloudlens_minio_password` |
| **Mailpit** | `cloudlens-mailpit` | `1025` (SMTP)<br>`8025` (Web) | `1025`<br>`8025` | `/mailpit readyz` | Web UI: http://localhost:8025 |

---

## 5. Running Real-Database Tests

Per Enterprise Production Standards and Guardrail 9, integration tests do not use SQLite or mocks. Tests marked with `realdb` connect to the genuine PostgreSQL 16 instance:

```powershell
# Set environment flag requiring real database (any skip will cause failure)
$env:CLOUDLENS_REQUIRE_REALDB = "1"

# Run the real database integration test suite
pytest -m realdb -v
```

Expected result:
```text
tests/integration/test_database_real.py::test_real_postgres_dialect_and_version PASSED
tests/integration/test_database_real.py::test_real_postgres_ddl_and_partitioning PASSED
tests/integration/test_database_real.py::test_real_postgres_transactional_rollback PASSED
tests/integration/test_database_real.py::test_real_postgres_audit_event_append_only_enforcement PASSED
====== 4 passed in ... ======
```

---

## 6. Verifying Async Database Connectivity

Verify asynchronous SQLAlchemy 2.0 connectivity with `asyncpg`:

```powershell
python -c "import asyncpg; print('asyncpg version:', asyncpg.__version__)"
python -c "import asyncio; from sqlalchemy import text; from db.session import get_async_engine; async def run(): engine = get_async_engine(); async with engine.connect() as conn: res = await conn.execute(text('SELECT 1')); print('Async SELECT 1 result:', res.scalar()); asyncio.run(run())"
```

---

## 7. Running the Application Locally

### Starting the FastAPI Backend
```powershell
uvicorn api.cloudlens_api.main:app --reload --port 8000
```
- OpenAPI Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
- API Health Endpoint: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

### Starting the Web Frontend
```powershell
cd web
pnpm install
pnpm dev
```
- Web Application Shell: [http://localhost:3000](http://localhost:3000)

---

## 8. Stopping or Resetting Infrastructure

To stop containers:
```powershell
docker compose -f ops/docker-compose.yml down
```

To stop containers and wipe persistent data volumes (clean slate):
```powershell
docker compose -f ops/docker-compose.yml down -v
```
After wiping volumes, rerun `.\scripts\dev_up.ps1` to re-initialize schema migrations and master catalogues.
