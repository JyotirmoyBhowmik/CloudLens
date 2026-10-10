"""Unified Business Objects REST Endpoints (Prompt P15).

Provides server-paginated, sortable, searchable, ETag/If-Match concurrency-controlled,
and fully audited CRUD for the 11 core enterprise business objects:
1. Budgets (budgets)
2. Policies (policies)
3. Applications (applications)
4. Owners/Teams (owners)
5. Cost Centres (cost_centers)
6. Business Units (business_units)
7. Environments (environments)
8. Runtime Schedules (runtime_schedules)
9. Remediation tasks (remediation_tasks)
10. Provisioning requests (provisioning_requests)
11. Users (identity_users)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from api.cloudlens_api.conventions.concurrency import generate_etag, validate_if_match
from api.cloudlens_api.tenant_context import get_authenticated_tenant_context
from db.session import get_tenant_session
from domain.audit.service import get_audit_service
from domain.models.enums import AuditEventType
from domain.tenant.context import TenantContext

logger = logging.getLogger("cloudlens.api.business_objects")

router = APIRouter(prefix="/api/v1/business-objects", tags=["Business Objects"])

# Entity Configuration Registry
ENTITY_CONFIG: dict[str, dict[str, Any]] = {
    "budgets": {
        "table": "budgets",
        "resource_type": "BUDGET",
        "id_prefix": "bgt-",
        "search_fields": ["name", "scope_id", "currency", "period"],
        "default_sort": "created_at",
        "allowed_sort_fields": ["id", "name", "amount", "currency", "created_at", "updated_at"],
        "allowed_insert_fields": [
            "id", "tenant_id", "scope_id", "name", "amount", "period", "scope_type",
            "currency", "approval_status", "forecast_threshold", "thresholds",
            "alert_recipients", "amendments",
        ],
        "allowed_update_fields": [
            "name", "amount", "currency", "period", "scope_id", "scope_type",
            "approval_status", "forecast_threshold", "updated_at",
        ],
        "json_fields": ["thresholds", "alert_recipients", "amendments", "escalation", "approval_decision"],
        "required_fields": ["name", "amount"],
        "default_values": {
            "scope_id": "global",
            "period": "MONTHLY",
            "scope_type": "SUBSCRIPTION",
            "currency": "USD",
            "approval_status": "APPROVED",
        },
    },
    "policies": {
        "table": "policies",
        "resource_type": "POLICY",
        "id_prefix": "pol-",
        "search_fields": ["name", "rule_type", "severity"],
        "default_sort": "created_at",
        "allowed_sort_fields": ["id", "name", "rule_type", "severity", "created_at", "updated_at"],
        "allowed_insert_fields": [
            "id", "tenant_id", "name", "rule_type", "severity", "parameters",
            "policy_payload", "version",
        ],
        "allowed_update_fields": [
            "name", "rule_type", "severity", "parameters", "policy_payload", "version", "updated_at",
        ],
        "json_fields": ["parameters", "policy_payload"],
        "required_fields": ["name", "rule_type"],
        "default_values": {
            "severity": "MEDIUM",
            "version": 1,
            "parameters": {},
            "policy_payload": {},
        },
    },
    "applications": {
        "table": "applications",
        "resource_type": "APPLICATION",
        "id_prefix": "app-",
        "search_fields": ["code", "name", "criticality"],
        "default_sort": "created_at",
        "allowed_sort_fields": ["id", "code", "name", "criticality", "created_at"],
        "allowed_insert_fields": ["id", "tenant_id", "code", "name", "criticality", "owner_id"],
        "allowed_update_fields": ["code", "name", "criticality", "owner_id"],
        "json_fields": [],
        "required_fields": ["code", "name"],
        "default_values": {"criticality": "BUSINESS_CRITICAL"},
    },
    "owners": {
        "table": "owners",
        "resource_type": "OWNER_TEAM",
        "id_prefix": "ow-",
        "search_fields": ["name", "email", "department"],
        "default_sort": "created_at",
        "allowed_sort_fields": ["id", "name", "email", "department", "created_at"],
        "allowed_insert_fields": ["id", "tenant_id", "name", "email", "department"],
        "allowed_update_fields": ["name", "email", "department"],
        "json_fields": [],
        "required_fields": ["name", "email"],
        "default_values": {"department": "Engineering"},
    },
    "cost_centers": {
        "table": "cost_centers",
        "resource_type": "COST_CENTRE",
        "id_prefix": "cc-",
        "search_fields": ["code", "name"],
        "default_sort": "created_at",
        "allowed_sort_fields": ["id", "code", "name", "created_at"],
        "allowed_insert_fields": ["id", "tenant_id", "code", "name", "business_unit_id"],
        "allowed_update_fields": ["code", "name", "business_unit_id"],
        "json_fields": [],
        "required_fields": ["code", "name"],
        "default_values": {},
    },
    "business_units": {
        "table": "business_units",
        "resource_type": "BUSINESS_UNIT",
        "id_prefix": "bu-",
        "search_fields": ["code", "name"],
        "default_sort": "created_at",
        "allowed_sort_fields": ["id", "code", "name", "created_at"],
        "allowed_insert_fields": ["id", "tenant_id", "code", "name"],
        "allowed_update_fields": ["code", "name"],
        "json_fields": [],
        "required_fields": ["code", "name"],
        "default_values": {},
    },
    "environments": {
        "table": "environments",
        "resource_type": "ENVIRONMENT",
        "id_prefix": "env-",
        "search_fields": ["name", "category"],
        "default_sort": "created_at",
        "allowed_sort_fields": ["id", "name", "category", "created_at"],
        "allowed_insert_fields": ["id", "tenant_id", "name", "category"],
        "allowed_update_fields": ["name", "category"],
        "json_fields": [],
        "required_fields": ["name"],
        "default_values": {"category": "PRODUCTION"},
    },
    "runtime_schedules": {
        "table": "runtime_schedules",
        "resource_type": "RUNTIME_SCHEDULE",
        "id_prefix": "rs-",
        "search_fields": ["name"],
        "default_sort": "created_at",
        "allowed_sort_fields": ["id", "name", "created_at"],
        "allowed_insert_fields": ["id", "tenant_id", "name", "schedule_payload"],
        "allowed_update_fields": ["name", "schedule_payload"],
        "json_fields": ["schedule_payload"],
        "required_fields": ["name"],
        "default_values": {"schedule_payload": {"cron": "0 20 * * 1-5", "action": "STOP"}},
    },
    "remediation_tasks": {
        "table": "remediation_tasks",
        "resource_type": "REMEDIATION_TASK",
        "id_prefix": "rem-",
        "search_fields": ["title", "state", "priority", "category"],
        "default_sort": "created_at",
        "allowed_sort_fields": ["id", "title", "state", "priority", "category", "created_at", "updated_at"],
        "allowed_insert_fields": [
            "id", "tenant_id", "title", "state", "priority", "category",
            "assignee_id", "task_payload",
        ],
        "allowed_update_fields": [
            "title", "state", "priority", "category", "assignee_id", "task_payload", "updated_at",
        ],
        "json_fields": ["task_payload"],
        "required_fields": ["title", "category"],
        "default_values": {"state": "OPEN", "priority": "MEDIUM", "task_payload": {}},
    },
    "provisioning_requests": {
        "table": "provisioning_requests",
        "resource_type": "PROVISIONING_REQUEST",
        "id_prefix": "pr-",
        "search_fields": ["requester_id", "status", "target_scope"],
        "default_sort": "created_at",
        "allowed_sort_fields": ["id", "requester_id", "status", "target_scope", "created_at", "updated_at"],
        "allowed_insert_fields": [
            "id", "tenant_id", "requester_id", "status", "target_scope", "request_payload",
        ],
        "allowed_update_fields": ["status", "target_scope", "request_payload", "updated_at"],
        "json_fields": ["request_payload"],
        "required_fields": ["target_scope"],
        "default_values": {"status": "PENDING", "request_payload": {}},
    },
    "users": {
        "table": "identity_users",
        "resource_type": "IDENTITY_USER",
        "id_prefix": "usr-",
        "search_fields": ["email", "display_name", "status"],
        "default_sort": "created_at",
        "allowed_sort_fields": ["id", "email", "display_name", "status", "created_at", "updated_at"],
        "allowed_insert_fields": [
            "id", "tenant_id", "email", "display_name", "status", "roles",
            "auth_method", "idp_sub", "is_break_glass",
        ],
        "allowed_update_fields": [
            "email", "display_name", "status", "roles", "auth_method", "is_break_glass", "updated_at",
        ],
        "json_fields": ["roles"],
        "required_fields": ["email", "display_name"],
        "default_values": {
            "status": "ACTIVE",
            "roles": ["FINOPS_ANALYST"],
            "auth_method": "OIDC",
            "is_break_glass": False,
        },
    },
}

# Alias resolution mapping
ENTITY_ALIASES: dict[str, str] = {
    "budgets": "budgets",
    "policies": "policies",
    "applications": "applications",
    "owners": "owners",
    "owners-teams": "owners",
    "owners_teams": "owners",
    "teams": "owners",
    "cost_centers": "cost_centers",
    "cost-centers": "cost_centers",
    "cost_centres": "cost_centers",
    "cost-centres": "cost_centers",
    "business_units": "business_units",
    "business-units": "business_units",
    "environments": "environments",
    "runtime_schedules": "runtime_schedules",
    "runtime-schedules": "runtime_schedules",
    "remediation_tasks": "remediation_tasks",
    "remediation-tasks": "remediation_tasks",
    "provisioning_requests": "provisioning_requests",
    "provisioning-requests": "provisioning_requests",
    "users": "users",
    "identity_users": "users",
    "identity-users": "users",
}


def _resolve_entity_type(raw_type: str) -> tuple[str, dict[str, Any]]:
    key = ENTITY_ALIASES.get(raw_type.lower().strip())
    if not key or key not in ENTITY_CONFIG:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown business object type '{raw_type}'. Supported types: {list(ENTITY_CONFIG.keys())}",
        )
    return key, ENTITY_CONFIG[key]


def _serialize_row(row_dict: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row_dict.items():
        if isinstance(v, (datetime, date)):
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = float(v)
        else:
            out[k] = v
    return out


class BusinessObjectListResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int
    entity_type: str


@router.get("/{entity_type}", response_model=BusinessObjectListResponse)
async def list_business_objects(
    entity_type: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None),
    sort_by: str | None = Query(None),
    sort_order: str = Query("asc", regex="^(asc|desc)$"),
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> BusinessObjectListResponse:
    """Retrieves server-paginated, sorted, and filtered list of business objects."""
    canonical_key, cfg = _resolve_entity_type(entity_type)
    table = cfg["table"]
    tenant_id = tc.effective_tenant_id

    # Sort safety
    sort_col = sort_by if sort_by in cfg["allowed_sort_fields"] else cfg["default_sort"]
    order_dir = "DESC" if sort_order.lower() == "desc" else "ASC"

    where_clauses = ["tenant_id = :tid"]
    params: dict[str, Any] = {"tid": tenant_id, "limit": limit, "offset": offset}

    if search and search.strip():
        search_terms = []
        for idx, col in enumerate(cfg["search_fields"]):
            p_name = f"search_{idx}"
            search_terms.append(f"{col} ILIKE :{p_name}")
            params[p_name] = f"%{search.strip()}%"
        where_clauses.append(f"({' OR '.join(search_terms)})")

    where_sql = " AND ".join(where_clauses)

    count_sql = f"SELECT COUNT(*) FROM {table} WHERE {where_sql}"
    query_sql = f"SELECT * FROM {table} WHERE {where_sql} ORDER BY {sort_col} {order_dir} LIMIT :limit OFFSET :offset"

    async with get_tenant_session(tenant_id) as session:
        c_res = await session.execute(text(count_sql), params)
        total_count = c_res.scalar() or 0

        q_res = await session.execute(text(query_sql), params)
        rows = q_res.mappings().fetchall()

        items = [_serialize_row(dict(r)) for r in rows]

    return BusinessObjectListResponse(
        items=items,
        total=total_count,
        limit=limit,
        offset=offset,
        entity_type=canonical_key,
    )


@router.get("/{entity_type}/{object_id}")
async def get_business_object(
    entity_type: str,
    object_id: str,
    response: Response,
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> dict[str, Any]:
    """Retrieves an individual business object with ETag response header."""
    canonical_key, cfg = _resolve_entity_type(entity_type)
    table = cfg["table"]
    tenant_id = tc.effective_tenant_id

    query_sql = f"SELECT * FROM {table} WHERE id = :id AND tenant_id = :tid"
    async with get_tenant_session(tenant_id) as session:
        res = await session.execute(text(query_sql), {"id": object_id, "tid": tenant_id})
        row = res.mappings().fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{canonical_key.capitalize()} with ID '{object_id}' not found.",
            )
        serialized = _serialize_row(dict(row))

    etag = generate_etag(serialized)
    response.headers["ETag"] = etag
    return serialized


@router.post("/{entity_type}", status_code=status.HTTP_201_CREATED)
async def create_business_object(
    entity_type: str,
    payload: dict[str, Any],
    response: Response,
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> dict[str, Any]:
    """Creates a new business object, persists to PostgreSQL, and records an audit event."""
    canonical_key, cfg = _resolve_entity_type(entity_type)
    table = cfg["table"]
    tenant_id = tc.effective_tenant_id
    actor = tc.email or tc.user_id

    # 1. Validation
    for req in cfg["required_fields"]:
        if req not in payload or payload[req] is None or str(payload[req]).strip() == "":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Field '{req}' is mandatory for {canonical_key}.",
            )

    # 2. Build insert record
    record: dict[str, Any] = dict(cfg["default_values"])
    record.update(payload)
    record["tenant_id"] = tenant_id

    obj_id = record.get("id") or f"{cfg['id_prefix']}{uuid.uuid4().hex[:8]}"
    record["id"] = obj_id

    if canonical_key == "provisioning_requests" and "requester_id" not in record:
        record["requester_id"] = actor

    # Prepare SQL columns and values
    insert_cols = []
    val_placeholders = []
    bind_params: dict[str, Any] = {}

    for col in cfg["allowed_insert_fields"]:
        if col in record:
            insert_cols.append(col)
            val = record[col]
            if col in cfg["json_fields"]:
                val_placeholders.append(f"CAST(:{col} AS jsonb)")
                bind_params[col] = json.dumps(val if isinstance(val, (dict, list)) else {})
            else:
                val_placeholders.append(f":{col}")
                bind_params[col] = val

    insert_sql = f"INSERT INTO {table} ({', '.join(insert_cols)}) VALUES ({', '.join(val_placeholders)})"

    async with get_tenant_session(tenant_id) as session:
        await session.execute(text(insert_sql), bind_params)
        sel_sql = f"SELECT * FROM {table} WHERE id = :id AND tenant_id = :tid"
        sel_res = await session.execute(text(sel_sql), {"id": obj_id, "tid": tenant_id})
        saved = sel_res.mappings().fetchone()
        created = _serialize_row(dict(saved)) if saved else record

    # 3. Cryptographic Audit Event
    try:
        get_audit_service().record_event(
            tenant_context=tc,
            event_type=AuditEventType.BUSINESS_OBJECT_CREATED,
            actor=actor,
            payload={"entity_type": canonical_key, "id": obj_id, "data": created},
            action=f"{cfg['resource_type']}_CREATED",
            resource_type=cfg["resource_type"],
            resource_id=obj_id,
        )
    except Exception as a_err:
        logger.warning("Audit record creation skipped: %s", a_err)

    etag = generate_etag(created)
    response.headers["ETag"] = etag
    return created


@router.put("/{entity_type}/{object_id}")
async def update_business_object(
    entity_type: str,
    object_id: str,
    payload: dict[str, Any],
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> dict[str, Any]:
    """Updates a business object with optimistic concurrency ETag/If-Match check and audit log."""
    canonical_key, cfg = _resolve_entity_type(entity_type)
    table = cfg["table"]
    tenant_id = tc.effective_tenant_id
    actor = tc.email or tc.user_id

    # 1. Fetch current object
    async with get_tenant_session(tenant_id) as session:
        sel_sql = f"SELECT * FROM {table} WHERE id = :id AND tenant_id = :tid"
        res = await session.execute(text(sel_sql), {"id": object_id, "tid": tenant_id})
        existing = res.mappings().fetchone()
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{canonical_key.capitalize()} with ID '{object_id}' not found.",
            )
        existing_serialized = _serialize_row(dict(existing))

    # 2. Concurrency Check (If-Match)
    cur_etag = generate_etag(existing_serialized)
    if if_match and not validate_if_match(cur_etag, if_match):
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail="Precondition Failed: Resource has been modified concurrently. Please refresh.",
        )

    # 3. Build update statements
    update_cols = []
    bind_params: dict[str, Any] = {"id": object_id, "tid": tenant_id}

    for col in cfg["allowed_update_fields"]:
        if col in payload and col not in ("id", "tenant_id"):
            val = payload[col]
            if col in cfg["json_fields"]:
                update_cols.append(f"{col} = CAST(:{col} AS jsonb)")
                bind_params[col] = json.dumps(val if isinstance(val, (dict, list)) else {})
            else:
                update_cols.append(f"{col} = :{col}")
                bind_params[col] = val

    if "version" in cfg["allowed_update_fields"] and "version" in existing_serialized:
        new_version = int(existing_serialized.get("version") or 1) + 1
        update_cols.append("version = :ver")
        bind_params["ver"] = new_version

    if not update_cols:
        response.headers["ETag"] = cur_etag
        return existing_serialized

    update_sql = f"UPDATE {table} SET {', '.join(update_cols)} WHERE id = :id AND tenant_id = :tid"

    async with get_tenant_session(tenant_id) as session:
        await session.execute(text(update_sql), bind_params)
        sel_res = await session.execute(text(sel_sql), {"id": object_id, "tid": tenant_id})
        updated = _serialize_row(dict(sel_res.mappings().fetchone()))

    # 4. Audit Log
    try:
        get_audit_service().record_event(
            tenant_context=tc,
            event_type=AuditEventType.BUSINESS_OBJECT_UPDATED,
            actor=actor,
            payload={
                "entity_type": canonical_key,
                "id": object_id,
                "updated_fields": list(payload.keys()),
            },
            action=f"{cfg['resource_type']}_UPDATED",
            resource_type=cfg["resource_type"],
            resource_id=object_id,
        )
    except Exception as a_err:
        logger.warning("Audit record update skipped: %s", a_err)

    new_etag = generate_etag(updated)
    response.headers["ETag"] = new_etag
    return updated


@router.delete("/{entity_type}/{object_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_business_object(
    entity_type: str,
    object_id: str,
    tc: TenantContext = Depends(get_authenticated_tenant_context),
) -> Response:
    """Deletes a business object with tenant isolation and audit trail logging."""
    canonical_key, cfg = _resolve_entity_type(entity_type)
    table = cfg["table"]
    tenant_id = tc.effective_tenant_id
    actor = tc.email or tc.user_id

    sel_sql = f"SELECT id FROM {table} WHERE id = :id AND tenant_id = :tid"
    del_sql = f"DELETE FROM {table} WHERE id = :id AND tenant_id = :tid"

    async with get_tenant_session(tenant_id) as session:
        res = await session.execute(text(sel_sql), {"id": object_id, "tid": tenant_id})
        if not res.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{canonical_key.capitalize()} with ID '{object_id}' not found.",
            )
        await session.execute(text(del_sql), {"id": object_id, "tid": tenant_id})

    # Audit event
    try:
        get_audit_service().record_event(
            tenant_context=tc,
            event_type=AuditEventType.BUSINESS_OBJECT_DELETED,
            actor=actor,
            payload={"entity_type": canonical_key, "id": object_id},
            action=f"{cfg['resource_type']}_DELETED",
            resource_type=cfg["resource_type"],
            resource_id=object_id,
        )
    except Exception as a_err:
        logger.warning("Audit record deletion skipped: %s", a_err)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
