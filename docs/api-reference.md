# CloudLens API Reference (OpenAPI 3.1)

> **Specification**: OpenAPI 3.1.0  
> **Interactive Documentation**: `http://localhost:8000/docs` (Swagger UI), `http://localhost:8000/redoc` (ReDoc)  
> **Raw Schema**: `http://localhost:8000/openapi.json`

---

## 1. Global Request & Response Headers

### Request Headers:
- `Authorization: Bearer <JWT>` — Required on all protected endpoints.
- `X-Correlation-ID: <UUID>` — Optional client trace identifier (generated automatically if omitted).

### Response Headers:
- `X-Correlation-ID: <UUID>` — Unique request trace identifier.
- `X-Response-Time-MS: <float>` — Execution latency in milliseconds.

---

## 2. Standardized JSON Error Envelope (Rule 2.4)

All API errors return a uniform schema with zero internal stack traces:

```json
{
  "timestamp": "2026-09-25T17:00:00.000000Z",
  "status_code": 404,
  "error_code": "RESOURCE_NOT_FOUND",
  "correlation_id": "c1f7b889-4e78-4395-8e47-5e9e048386b2",
  "message": "The requested resource could not be found."
}
```

---

## 3. Core Endpoint Catalog

### System & Health:
- `GET /api/v1/health` — Liveness & readiness probe (`API-001`).
- `GET /` — Service identification and root documentation link.

### Authentication & Identity (`Prompt 10`):
- `POST /api/v1/auth/login` — Superuser local break-glass login (`API-003`).
- `GET /api/v1/auth/session` — Current session identity and scope grants (`API-002`).
- `POST /api/v1/auth/logout` — Invalidate session tokens (`API-004`).

### Inventory & Governance (`Prompts 08, 14, 22, 28`):
- `GET /api/v1/connectors` — List cloud connectors (`API-011`).
- `GET /api/v1/inventory/resources` — Multi-cloud resource inventory (`API-018`).
- `GET /api/v1/cost/summary` — FOCUS-aligned cost aggregation summary (`API-023`).
- `GET /api/v1/budgets` — Active budget tracking (`API-037`).
- `POST /api/v1/pricing/estimate` — Pre-deployment cost estimation (`API-030`).
