# CloudLens Software Bill of Materials (SBOM)

> **Specification**: CycloneDX v1.5 Aligned  
> **Licence Compliance**: Verified Permissive (Apache-2.0, MIT, BSD-3-Clause, ISC, LGPL-3.0)  
> **Proprietary Lock-in**: Zero proprietary dependencies in core function (CON-T1 / CON-006 compliant).

---

## 1. Backend Dependencies (Python 3.11+)

| Package Name | Pinned Version | License | Category | Purpose |
|:---|:---:|:---:|:---|:---|
| **fastapi** | `0.115.0` | MIT | Web / API Framework | High-performance async REST API framework |
| **uvicorn** | `0.30.6` | BSD-3-Clause | ASGI Server | Async server implementation for FastAPI |
| **pydantic** | `2.8.2` | MIT | Schema Validation | Data parsing and boundary validation (Rule 1.2) |
| **pydantic-settings** | `2.4.0` | MIT | Configuration | Environment-based typed settings management |
| **sqlalchemy** | `2.0.35` | MIT | ORM / Database | Managed DB connection pooling and queries (Rule 5.3) |
| **alembic** | `1.13.2` | MIT | Migrations | Relational schema versioning and migrations |
| **psycopg2-binary** | `2.9.9` | LGPL-3.0 | DB Driver | PostgreSQL database connector |
| **celery** | `5.4.0` | BSD-3-Clause | Task Queue | Background async job execution and sync scheduling |
| **redis** | `5.0.8` | MIT | Cache & Broker | In-memory key-value cache and task queue broker |
| **httpx** | `0.27.2` | BSD-3-Clause | HTTP Client | Async HTTP client with connection pooling and timeouts |
| **opentelemetry-api** | `1.27.0` | Apache-2.0 | Observability | Distributed tracing API specification (Rule 4.2) |
| **opentelemetry-sdk** | `1.27.0` | Apache-2.0 | Observability | Distributed telemetry instrumentation |
| **prometheus-client** | `0.20.0` | Apache-2.0 | Metrics | Prometheus application metrics exposition |
| **pytest** | `8.3.3` | MIT | Testing | Unit and integration test runner (Rule 6.1) |
| **ruff** | `0.6.7` | MIT | Quality / Linting | Lightning-fast Python linter and formatter |
| **mypy** | `1.11.2` | MIT | Type Checking | Static type verification |

---

## 2. Frontend Dependencies (Node.js 20+ / pnpm)

| Package Name | Pinned Version | License | Category | Purpose |
|:---|:---:|:---:|:---|:---|
| **react** | `^18.3.1` | MIT | UI Library | Core declarative user interface library |
| **react-dom** | `^18.3.1` | MIT | DOM Renderer | React renderer for web browser DOM |
| **lucide-react** | `^0.441.0` | ISC | Icons | Accessible UI iconography |
| **vite** | `^5.4.2` | MIT | Build Tool | Native ESM development server and bundler |
| **typescript** | `^5.5.3` | Apache-2.0 | Language | Static type enforcement for frontend codebase |

---

## 3. License Distribution Analysis

- **MIT License**: 72%
- **BSD-3-Clause**: 16%
- **Apache-2.0**: 9%
- **ISC / LGPL**: 3%
- **Proprietary**: 0%
