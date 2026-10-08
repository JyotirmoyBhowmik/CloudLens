"""CloudLens Identity, Sessions, Revocations & Principal SQL Repository (Prompt P04).

Enforces:
- Pattern P1: Protocol + SqlIdentityRepository (SQLAlchemy 2.0 async).
- Pattern P3: Injected dependency, zero mutable dict singletons as sources of truth.
- Pattern P4: Transactional RLS isolation via get_tenant_session().
- Pattern P6: Startup guard preventing InMemory repository outside development.
- Persistent session storage, user lookup by email/ID, machine clients, step-up challenges,
  and token revocation registry surviving process restarts.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session
from domain.identity.models import (
    BreakGlassAccount,
    MachineClient,
    Session,
    StepUpChallenge,
    User,
)
from domain.models.enums import AuthMethod, StepUpAction, SystemRole, UserStatus

logger = logging.getLogger("cloudlens.domain.identity.repository")


@runtime_checkable
class IdentityRepository(Protocol):
    """Authoritative protocol for identity, session, and revocation persistence."""

    # Users
    async def get_user(self, user_id: str, session: AsyncSession | None = None) -> User | None:
        ...

    async def get_user_by_email(self, tenant_id: str, email: str, session: AsyncSession | None = None) -> User | None:
        ...

    async def save_user(self, user: User, session: AsyncSession | None = None) -> User:
        ...

    async def list_users(self, tenant_id: str, session: AsyncSession | None = None) -> list[User]:
        ...

    async def delete_user(self, user_id: str, session: AsyncSession | None = None) -> bool:
        ...

    # Sessions
    async def get_session(self, session_id: str, session: AsyncSession | None = None) -> Session | None:
        ...

    async def save_session(self, session_entity: Session, session: AsyncSession | None = None) -> Session:
        ...

    async def list_active_sessions(self, tenant_id: str, user_id: str | None = None, session: AsyncSession | None = None) -> list[Session]:
        ...

    async def revoke_session(self, session_id: str, reason: str | None = None, session: AsyncSession | None = None) -> bool:
        ...

    async def revoke_all_user_sessions(self, tenant_id: str, user_id: str, reason: str | None = None, session: AsyncSession | None = None) -> int:
        ...

    # Machine Clients
    async def get_machine_client(self, client_id: str, session: AsyncSession | None = None) -> MachineClient | None:
        ...

    async def save_machine_client(self, client: MachineClient, session: AsyncSession | None = None) -> MachineClient:
        ...

    async def list_machine_clients(self, tenant_id: str, session: AsyncSession | None = None) -> list[MachineClient]:
        ...

    async def delete_machine_client(self, client_id: str, session: AsyncSession | None = None) -> bool:
        ...

    # Step-Up Challenges
    async def get_step_up_challenge(self, challenge_id: str, session: AsyncSession | None = None) -> StepUpChallenge | None:
        ...

    async def save_step_up_challenge(self, challenge: StepUpChallenge, session: AsyncSession | None = None) -> StepUpChallenge:
        ...

    async def delete_step_up_challenge(self, challenge_id: str, session: AsyncSession | None = None) -> bool:
        ...

    # Revocation Registry & Token Families
    async def revoke_token(self, jti: str, expires_at: float, session: AsyncSession | None = None) -> None:
        ...

    async def revoke_session_tokens(self, session_id: str, session: AsyncSession | None = None) -> None:
        ...

    async def revoke_user_tokens(self, user_id: str, session: AsyncSession | None = None) -> None:
        ...

    async def is_token_revoked(
        self,
        jti: str,
        user_id: str | None = None,
        session_id: str | None = None,
        issued_at: float | None = None,
        family_id: str | None = None,
        session: AsyncSession | None = None,
    ) -> bool:
        ...

    async def record_refresh_token_use(self, token_id: str, family_id: str, session: AsyncSession | None = None) -> bool:
        ...


class SqlIdentityRepository:
    """PostgreSQL production implementation for Identity, Sessions, and Revocations."""

    is_in_memory: bool = False

    def _run_async(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()

    # -------------------------------------------------------------------------
    # Users
    # -------------------------------------------------------------------------

    async def get_user(self, user_id: str, session: AsyncSession | None = None) -> User | None:
        if session is not None:
            return await self._get_user_with_session(user_id, session)
        async with get_tenant_session() as sess:
            return await self._get_user_with_session(user_id, sess)

    async def _get_user_with_session(self, user_id: str, session: AsyncSession) -> User | None:
        await session.execute(text("SELECT set_config('cloudlens.bypass_rls', 'on', true);"))
        query = text("""
            SELECT id, tenant_id, email, display_name, status, roles, auth_method, idp_sub,
                   is_break_glass, last_login_at, created_at, updated_at
            FROM identity_users
            WHERE id = :uid
            LIMIT 1;
        """)
        result = await session.execute(query, {"uid": user_id})
        row = result.fetchone()
        if not row:
            return None
        return self._row_to_user(row)

    async def get_user_by_email(self, tenant_id: str, email: str, session: AsyncSession | None = None) -> User | None:
        if session is not None:
            return await self._get_user_by_email_with_session(tenant_id, email, session)
        async with get_tenant_session(tenant_id) as sess:
            return await self._get_user_by_email_with_session(tenant_id, email, sess)

    async def _get_user_by_email_with_session(self, tenant_id: str, email: str, session: AsyncSession) -> User | None:
        query = text("""
            SELECT id, tenant_id, email, display_name, status, roles, auth_method, idp_sub,
                   is_break_glass, last_login_at, created_at, updated_at
            FROM identity_users
            WHERE tenant_id = :tid AND LOWER(email) = LOWER(:email)
            LIMIT 1;
        """)
        result = await session.execute(query, {"tid": tenant_id, "email": email.strip()})
        row = result.fetchone()
        if not row:
            return None
        return self._row_to_user(row)

    def _row_to_user(self, row) -> User:
        roles_raw = row[5]
        if isinstance(roles_raw, str):
            roles_raw = json.loads(roles_raw)
        roles = [SystemRole(r) for r in roles_raw if r in SystemRole._value2member_map_]
        return User(
            id=row[0],
            tenant_id=row[1],
            email=row[2],
            display_name=row[3],
            status=UserStatus(row[4]),
            roles=roles,
            auth_method=AuthMethod(row[6]) if row[6] else AuthMethod.OIDC,
            idp_sub=row[7],
            is_break_glass=bool(row[8]),
            last_login_at=row[9],
            created_at=row[10],
            updated_at=row[11],
        )

    async def save_user(self, user: User, session: AsyncSession | None = None) -> User:
        if session is not None:
            return await self._save_user_with_session(user, session)
        async with get_tenant_session(user.tenant_id) as sess:
            res = await self._save_user_with_session(user, sess)
            await sess.commit()
            return res

    async def _save_user_with_session(self, user: User, session: AsyncSession) -> User:
        await session.execute(text("SELECT set_config('cloudlens.bypass_rls', 'on', true);"))
        roles_json = json.dumps([r.value for r in user.roles])
        query = text("""
            INSERT INTO identity_users (
                id, tenant_id, email, display_name, status, roles, auth_method,
                idp_sub, is_break_glass, last_login_at, created_at, updated_at
            )
            VALUES (
                :id, :tenant_id, :email, :display_name, :status, CAST(:roles AS jsonb), :auth_method,
                :idp_sub, :is_break_glass, :last_login_at, :created_at, NOW()
            )
            ON CONFLICT (id)
            DO UPDATE SET
                display_name = EXCLUDED.display_name,
                status = EXCLUDED.status,
                roles = EXCLUDED.roles,
                auth_method = EXCLUDED.auth_method,
                idp_sub = EXCLUDED.idp_sub,
                is_break_glass = EXCLUDED.is_break_glass,
                last_login_at = EXCLUDED.last_login_at,
                updated_at = NOW();
        """)
        await session.execute(
            query,
            {
                "id": user.id,
                "tenant_id": user.tenant_id,
                "email": user.email,
                "display_name": user.display_name,
                "status": user.status.value,
                "roles": roles_json,
                "auth_method": user.auth_method.value,
                "idp_sub": user.idp_sub,
                "is_break_glass": user.is_break_glass,
                "last_login_at": user.last_login_at,
                "created_at": user.created_at,
            },
        )
        return user

    async def list_users(self, tenant_id: str, session: AsyncSession | None = None) -> list[User]:
        if session is not None:
            return await self._list_users_with_session(tenant_id, session)
        async with get_tenant_session(tenant_id) as sess:
            return await self._list_users_with_session(tenant_id, sess)

    async def _list_users_with_session(self, tenant_id: str, session: AsyncSession) -> list[User]:
        query = text("""
            SELECT id, tenant_id, email, display_name, status, roles, auth_method, idp_sub,
                   is_break_glass, last_login_at, created_at, updated_at
            FROM identity_users
            WHERE tenant_id = :tid
            ORDER BY email;
        """)
        result = await session.execute(query, {"tid": tenant_id})
        return [self._row_to_user(r) for r in result.fetchall()]

    async def delete_user(self, user_id: str, session: AsyncSession | None = None) -> bool:
        if session is not None:
            return await self._delete_user_with_session(user_id, session)
        async with get_tenant_session() as sess:
            res = await self._delete_user_with_session(user_id, sess)
            await sess.commit()
            return res

    async def _delete_user_with_session(self, user_id: str, session: AsyncSession) -> bool:
        await session.execute(text("SELECT set_config('cloudlens.bypass_rls', 'on', true);"))
        query = text("DELETE FROM identity_users WHERE id = :uid;")
        res = await session.execute(query, {"uid": user_id})
        return res.rowcount > 0

    # Sync User methods
    def get_user_sync(self, user_id: str) -> User | None:
        return self._run_async(self.get_user(user_id))

    def get_user_by_email_sync(self, tenant_id: str, email: str) -> User | None:
        return self._run_async(self.get_user_by_email(tenant_id, email))

    def save_user_sync(self, user: User) -> User:
        return self._run_async(self.save_user(user))

    def list_users_sync(self, tenant_id: str) -> list[User]:
        return self._run_async(self.list_users(tenant_id))

    def delete_user_sync(self, user_id: str) -> bool:
        return self._run_async(self.delete_user(user_id))

    # -------------------------------------------------------------------------
    # Sessions
    # -------------------------------------------------------------------------

    async def get_session(self, session_id: str, session: AsyncSession | None = None) -> Session | None:
        if session is not None:
            return await self._get_session_with_session(session_id, session)
        async with get_tenant_session() as sess:
            return await self._get_session_with_session(session_id, sess)

    async def _get_session_with_session(self, session_id: str, session: AsyncSession) -> Session | None:
        await session.execute(text("SELECT set_config('cloudlens.bypass_rls', 'on', true);"))
        query = text("""
            SELECT session_id, tenant_id, user_id, token_family_id, expires_at,
                   last_activity_at, is_active, revoked_at, revocation_reason,
                   ip_address, user_agent, created_at
            FROM identity_sessions
            WHERE session_id = :sid
            LIMIT 1;
        """)
        result = await session.execute(query, {"sid": session_id})
        row = result.fetchone()
        if not row:
            return None
        return self._row_to_session(row)

    def _row_to_session(self, row) -> Session:
        return Session(
            id=row[0],
            tenant_id=row[1],
            user_id=row[2],
            token_family_id=row[3],
            expires_at=row[4],
            last_activity_at=row[5],
            is_active=bool(row[6]),
            revoked_at=row[7],
            revocation_reason=row[8],
            ip_address=row[9],
            user_agent=row[10],
            created_at=row[11],
        )

    async def save_session(self, session_entity: Session, session: AsyncSession | None = None) -> Session:
        if session is not None:
            return await self._save_session_with_session(session_entity, session)
        async with get_tenant_session(session_entity.tenant_id) as sess:
            res = await self._save_session_with_session(session_entity, sess)
            await sess.commit()
            return res

    async def _save_session_with_session(self, s: Session, session: AsyncSession) -> Session:
        await session.execute(text("SELECT set_config('cloudlens.bypass_rls', 'on', true);"))
        query = text("""
            INSERT INTO identity_sessions (
                session_id, tenant_id, user_id, token_family_id, expires_at,
                last_activity_at, is_active, revoked_at, revocation_reason,
                ip_address, user_agent, created_at
            )
            VALUES (
                :sid, :tenant_id, :user_id, :token_family_id, :expires_at,
                :last_activity_at, :is_active, :revoked_at, :revocation_reason,
                :ip_address, :user_agent, :created_at
            )
            ON CONFLICT (session_id)
            DO UPDATE SET
                last_activity_at = EXCLUDED.last_activity_at,
                is_active = EXCLUDED.is_active,
                revoked_at = EXCLUDED.revoked_at,
                revocation_reason = EXCLUDED.revocation_reason;
        """)
        await session.execute(
            query,
            {
                "sid": s.id,
                "tenant_id": s.tenant_id,
                "user_id": s.user_id,
                "token_family_id": s.token_family_id,
                "expires_at": s.expires_at,
                "last_activity_at": s.last_activity_at,
                "is_active": s.is_active,
                "revoked_at": s.revoked_at,
                "revocation_reason": s.revocation_reason,
                "ip_address": s.ip_address,
                "user_agent": s.user_agent,
                "created_at": s.created_at,
            },
        )
        return s

    async def list_active_sessions(
        self, tenant_id: str, user_id: str | None = None, session: AsyncSession | None = None
    ) -> list[Session]:
        if session is not None:
            return await self._list_active_sessions_with_session(tenant_id, user_id, session)
        async with get_tenant_session(tenant_id) as sess:
            return await self._list_active_sessions_with_session(tenant_id, user_id, sess)

    async def _list_active_sessions_with_session(
        self, tenant_id: str, user_id: str | None, session: AsyncSession
    ) -> list[Session]:
        if user_id:
            query = text("""
                SELECT session_id, tenant_id, user_id, token_family_id, expires_at,
                       last_activity_at, is_active, revoked_at, revocation_reason,
                       ip_address, user_agent, created_at
                FROM identity_sessions
                WHERE tenant_id = :tid AND user_id = :uid AND is_active = true AND expires_at > NOW()
                ORDER BY created_at DESC;
            """)
            result = await session.execute(query, {"tid": tenant_id, "uid": user_id})
        else:
            query = text("""
                SELECT session_id, tenant_id, user_id, token_family_id, expires_at,
                       last_activity_at, is_active, revoked_at, revocation_reason,
                       ip_address, user_agent, created_at
                FROM identity_sessions
                WHERE tenant_id = :tid AND is_active = true AND expires_at > NOW()
                ORDER BY created_at DESC;
            """)
            result = await session.execute(query, {"tid": tenant_id})
        return [self._row_to_session(r) for r in result.fetchall()]

    async def revoke_session(self, session_id: str, reason: str | None = None, session: AsyncSession | None = None) -> bool:
        if session is not None:
            return await self._revoke_session_with_session(session_id, reason, session)
        async with get_tenant_session() as sess:
            res = await self._revoke_session_with_session(session_id, reason, sess)
            await sess.commit()
            return res

    async def _revoke_session_with_session(self, session_id: str, reason: str | None, session: AsyncSession) -> bool:
        await session.execute(text("SELECT set_config('cloudlens.bypass_rls', 'on', true);"))
        query = text("""
            UPDATE identity_sessions
            SET is_active = false, revoked_at = NOW(), revocation_reason = :reason
            WHERE session_id = :sid AND is_active = true;
        """)
        res = await session.execute(query, {"sid": session_id, "reason": reason or "REVOKED"})
        # Also register in token_revocations
        await self.revoke_session_tokens(session_id, session=session)
        return res.rowcount > 0

    async def revoke_all_user_sessions(
        self, tenant_id: str, user_id: str, reason: str | None = None, session: AsyncSession | None = None
    ) -> int:
        if session is not None:
            return await self._revoke_all_user_sessions_with_session(tenant_id, user_id, reason, session)
        async with get_tenant_session(tenant_id) as sess:
            res = await self._revoke_all_user_sessions_with_session(tenant_id, user_id, reason, sess)
            await sess.commit()
            return res

    async def _revoke_all_user_sessions_with_session(
        self, tenant_id: str, user_id: str, reason: str | None, session: AsyncSession
    ) -> int:
        query = text("""
            UPDATE identity_sessions
            SET is_active = false, revoked_at = NOW(), revocation_reason = :reason
            WHERE tenant_id = :tid AND user_id = :uid AND is_active = true;
        """)
        res = await session.execute(query, {"tid": tenant_id, "uid": user_id, "reason": reason or "USER_REVOKED"})
        await self.revoke_user_tokens(user_id, session=session)
        return res.rowcount

    # Sync Session methods
    def get_session_sync(self, session_id: str) -> Session | None:
        return self._run_async(self.get_session(session_id))

    def save_session_sync(self, s: Session) -> Session:
        return self._run_async(self.save_session(s))

    def list_active_sessions_sync(self, tenant_id: str, user_id: str | None = None) -> list[Session]:
        return self._run_async(self.list_active_sessions(tenant_id, user_id))

    def revoke_session_sync(self, session_id: str, reason: str | None = None) -> bool:
        return self._run_async(self.revoke_session(session_id, reason))

    def revoke_all_user_sessions_sync(self, tenant_id: str, user_id: str, reason: str | None = None) -> int:
        return self._run_async(self.revoke_all_user_sessions(tenant_id, user_id, reason))

    # -------------------------------------------------------------------------
    # Machine Clients
    # -------------------------------------------------------------------------

    async def get_machine_client(self, client_id: str, session: AsyncSession | None = None) -> MachineClient | None:
        if session is not None:
            return await self._get_machine_client_with_session(client_id, session)
        async with get_tenant_session() as sess:
            return await self._get_machine_client_with_session(client_id, sess)

    async def _get_machine_client_with_session(self, client_id: str, session: AsyncSession) -> MachineClient | None:
        await session.execute(text("SELECT set_config('cloudlens.bypass_rls', 'on', true);"))
        query = text("""
            SELECT client_id, tenant_id, name, secret_hash, secondary_secret_hash,
                   scoped_permissions, is_active, secret_expires_at, last_used_at, created_at
            FROM machine_clients
            WHERE client_id = :cid
            LIMIT 1;
        """)
        result = await session.execute(query, {"cid": client_id})
        row = result.fetchone()
        if not row:
            return None
        perms = row[5]
        if isinstance(perms, str):
            perms = json.loads(perms)
        return MachineClient(
            id=row[0],
            client_id=row[0],
            tenant_id=row[1],
            name=row[2],
            secret_hash=row[3],
            secondary_secret_hash=row[4],
            scoped_permissions=perms or [],
            is_active=bool(row[6]),
            secret_expires_at=row[7],
            last_used_at=row[8],
            created_at=row[9],
        )

    async def save_machine_client(self, client: MachineClient, session: AsyncSession | None = None) -> MachineClient:
        if session is not None:
            return await self._save_machine_client_with_session(client, session)
        async with get_tenant_session(client.tenant_id) as sess:
            res = await self._save_machine_client_with_session(client, sess)
            await sess.commit()
            return res

    async def _save_machine_client_with_session(self, client: MachineClient, session: AsyncSession) -> MachineClient:
        await session.execute(text("SELECT set_config('cloudlens.bypass_rls', 'on', true);"))
        perms_json = json.dumps(client.scoped_permissions)
        query = text("""
            INSERT INTO machine_clients (
                client_id, tenant_id, name, secret_hash, secondary_secret_hash,
                scoped_permissions, is_active, secret_expires_at, last_used_at, created_at
            )
            VALUES (
                :cid, :tenant_id, :name, :secret_hash, :secondary_secret_hash,
                CAST(:perms AS jsonb), :is_active, :secret_expires_at, :last_used_at, :created_at
            )
            ON CONFLICT (client_id)
            DO UPDATE SET
                name = EXCLUDED.name,
                secret_hash = EXCLUDED.secret_hash,
                secondary_secret_hash = EXCLUDED.secondary_secret_hash,
                scoped_permissions = EXCLUDED.scoped_permissions,
                is_active = EXCLUDED.is_active,
                secret_expires_at = EXCLUDED.secret_expires_at,
                last_used_at = EXCLUDED.last_used_at;
        """)
        await session.execute(
            query,
            {
                "cid": client.client_id,
                "tenant_id": client.tenant_id,
                "name": client.name,
                "secret_hash": client.secret_hash,
                "secondary_secret_hash": client.secondary_secret_hash,
                "perms": perms_json,
                "is_active": client.is_active,
                "secret_expires_at": client.secret_expires_at,
                "last_used_at": client.last_used_at,
                "created_at": client.created_at,
            },
        )
        return client

    async def list_machine_clients(self, tenant_id: str, session: AsyncSession | None = None) -> list[MachineClient]:
        if session is not None:
            return await self._list_machine_clients_with_session(tenant_id, session)
        async with get_tenant_session(tenant_id) as sess:
            return await self._list_machine_clients_with_session(tenant_id, sess)

    async def _list_machine_clients_with_session(self, tenant_id: str, session: AsyncSession) -> list[MachineClient]:
        query = text("""
            SELECT client_id, tenant_id, name, secret_hash, secondary_secret_hash,
                   scoped_permissions, is_active, secret_expires_at, last_used_at, created_at
            FROM machine_clients
            WHERE tenant_id = :tid
            ORDER BY created_at DESC;
        """)
        result = await session.execute(query, {"tid": tenant_id})
        clients = []
        for row in result.fetchall():
            perms = row[5]
            if isinstance(perms, str):
                perms = json.loads(perms)
            clients.append(
                MachineClient(
                    id=row[0],
                    client_id=row[0],
                    tenant_id=row[1],
                    name=row[2],
                    secret_hash=row[3],
                    secondary_secret_hash=row[4],
                    scoped_permissions=perms or [],
                    is_active=bool(row[6]),
                    secret_expires_at=row[7],
                    last_used_at=row[8],
                    created_at=row[9],
                )
            )
        return clients

    async def delete_machine_client(self, client_id: str, session: AsyncSession | None = None) -> bool:
        if session is not None:
            return await self._delete_machine_client_with_session(client_id, session)
        async with get_tenant_session() as sess:
            res = await self._delete_machine_client_with_session(client_id, sess)
            await sess.commit()
            return res

    async def _delete_machine_client_with_session(self, client_id: str, session: AsyncSession) -> bool:
        await session.execute(text("SELECT set_config('cloudlens.bypass_rls', 'on', true);"))
        query = text("DELETE FROM machine_clients WHERE client_id = :cid;")
        res = await session.execute(query, {"cid": client_id})
        return res.rowcount > 0

    # Sync Machine Client methods
    def get_machine_client_sync(self, client_id: str) -> MachineClient | None:
        return self._run_async(self.get_machine_client(client_id))

    def save_machine_client_sync(self, client: MachineClient) -> MachineClient:
        return self._run_async(self.save_machine_client(client))

    def list_machine_clients_sync(self, tenant_id: str) -> list[MachineClient]:
        return self._run_async(self.list_machine_clients(tenant_id))

    def delete_machine_client_sync(self, client_id: str) -> bool:
        return self._run_async(self.delete_machine_client(client_id))

    # -------------------------------------------------------------------------
    # Step-Up Challenges
    # -------------------------------------------------------------------------

    async def get_step_up_challenge(self, challenge_id: str, session: AsyncSession | None = None) -> StepUpChallenge | None:
        if session is not None:
            return await self._get_step_up_challenge_with_session(challenge_id, session)
        async with get_tenant_session() as sess:
            return await self._get_step_up_challenge_with_session(challenge_id, sess)

    async def _get_step_up_challenge_with_session(self, challenge_id: str, session: AsyncSession) -> StepUpChallenge | None:
        await session.execute(text("SELECT set_config('cloudlens.bypass_rls', 'on', true);"))
        query = text("""
            SELECT challenge_id, tenant_id, user_id, action, target_entity_id,
                   challenge_code, expires_at, is_verified, created_at
            FROM step_up_challenges
            WHERE challenge_id = :cid
            LIMIT 1;
        """)
        result = await session.execute(query, {"cid": challenge_id})
        row = result.fetchone()
        if not row:
            return None
        return StepUpChallenge(
            id=row[0],
            tenant_id=row[1],
            user_id=row[2],
            action=StepUpAction(row[3]),
            target_entity_id=row[4],
            challenge_code=row[5],
            expires_at=row[6],
            is_verified=bool(row[7]),
        )

    async def save_step_up_challenge(self, challenge: StepUpChallenge, session: AsyncSession | None = None) -> StepUpChallenge:
        if session is not None:
            return await self._save_step_up_challenge_with_session(challenge, session)
        async with get_tenant_session(challenge.tenant_id) as sess:
            res = await self._save_step_up_challenge_with_session(challenge, sess)
            await sess.commit()
            return res

    async def _save_step_up_challenge_with_session(self, c: StepUpChallenge, session: AsyncSession) -> StepUpChallenge:
        await session.execute(text("SELECT set_config('cloudlens.bypass_rls', 'on', true);"))
        query = text("""
            INSERT INTO step_up_challenges (
                challenge_id, tenant_id, user_id, action, target_entity_id,
                challenge_code, expires_at, is_verified, created_at
            )
            VALUES (
                :cid, :tenant_id, :user_id, :action, :target_entity_id,
                :challenge_code, :expires_at, :is_verified, NOW()
            )
            ON CONFLICT (challenge_id)
            DO UPDATE SET
                is_verified = EXCLUDED.is_verified,
                expires_at = EXCLUDED.expires_at;
        """)
        await session.execute(
            query,
            {
                "cid": c.id,
                "tenant_id": c.tenant_id,
                "user_id": c.user_id,
                "action": c.action.value,
                "target_entity_id": c.target_entity_id,
                "challenge_code": c.challenge_code,
                "expires_at": c.expires_at,
                "is_verified": c.is_verified,
            },
        )
        return c

    async def delete_step_up_challenge(self, challenge_id: str, session: AsyncSession | None = None) -> bool:
        if session is not None:
            return await self._delete_step_up_challenge_with_session(challenge_id, session)
        async with get_tenant_session() as sess:
            res = await self._delete_step_up_challenge_with_session(challenge_id, sess)
            await sess.commit()
            return res

    async def _delete_step_up_challenge_with_session(self, challenge_id: str, session: AsyncSession) -> bool:
        await session.execute(text("SELECT set_config('cloudlens.bypass_rls', 'on', true);"))
        query = text("DELETE FROM step_up_challenges WHERE challenge_id = :cid;")
        res = await session.execute(query, {"cid": challenge_id})
        return res.rowcount > 0

    # Sync Step-Up methods
    def get_step_up_challenge_sync(self, challenge_id: str) -> StepUpChallenge | None:
        return self._run_async(self.get_step_up_challenge(challenge_id))

    def save_step_up_challenge_sync(self, challenge: StepUpChallenge) -> StepUpChallenge:
        return self._run_async(self.save_step_up_challenge(challenge))

    def delete_step_up_challenge_sync(self, challenge_id: str) -> bool:
        return self._run_async(self.delete_step_up_challenge(challenge_id))

    # -------------------------------------------------------------------------
    # Revocation Registry & Token Families (Revocation survives restart)
    # -------------------------------------------------------------------------

    async def revoke_token(self, jti: str, expires_at: float, session: AsyncSession | None = None) -> None:
        if session is not None:
            await self._revoke_token_with_session(jti, expires_at, session)
            return
        async with get_tenant_session() as sess:
            await self._revoke_token_with_session(jti, expires_at, sess)
            await sess.commit()

    async def _revoke_token_with_session(self, jti: str, expires_at: float, session: AsyncSession) -> None:
        exp_dt = datetime.fromtimestamp(expires_at, tz=UTC)
        query = text("""
            INSERT INTO token_revocations (revocation_key, revocation_type, target_id, revoked_at, expires_at)
            VALUES (:key, 'JTI', :tid, NOW(), :exp)
            ON CONFLICT (revocation_key) DO NOTHING;
        """)
        await session.execute(query, {"key": f"jti:{jti}", "tid": jti, "exp": exp_dt})

    async def revoke_session_tokens(self, session_id: str, session: AsyncSession | None = None) -> None:
        if session is not None:
            await self._revoke_session_tokens_with_session(session_id, session)
            return
        async with get_tenant_session() as sess:
            await self._revoke_session_tokens_with_session(session_id, sess)
            await sess.commit()

    async def _revoke_session_tokens_with_session(self, session_id: str, session: AsyncSession) -> None:
        query = text("""
            INSERT INTO token_revocations (revocation_key, revocation_type, target_id, revoked_at)
            VALUES (:key, 'SESSION', :tid, NOW())
            ON CONFLICT (revocation_key) DO UPDATE SET revoked_at = NOW();
        """)
        await session.execute(query, {"key": f"session:{session_id}", "tid": session_id})

    async def revoke_user_tokens(self, user_id: str, session: AsyncSession | None = None) -> None:
        if session is not None:
            await self._revoke_user_tokens_with_session(user_id, session)
            return
        async with get_tenant_session() as sess:
            await self._revoke_user_tokens_with_session(user_id, sess)
            await sess.commit()

    async def _revoke_user_tokens_with_session(self, user_id: str, session: AsyncSession) -> None:
        query = text("""
            INSERT INTO token_revocations (revocation_key, revocation_type, target_id, revoked_at)
            VALUES (:key, 'USER', :tid, NOW())
            ON CONFLICT (revocation_key) DO UPDATE SET revoked_at = NOW();
        """)
        await session.execute(query, {"key": f"user:{user_id}", "tid": user_id})

    async def is_token_revoked(
        self,
        jti: str,
        user_id: str | None = None,
        session_id: str | None = None,
        issued_at: float | None = None,
        family_id: str | None = None,
        session: AsyncSession | None = None,
    ) -> bool:
        if session is not None:
            return await self._is_token_revoked_with_session(jti, user_id, session_id, issued_at, family_id, session)
        async with get_tenant_session() as sess:
            return await self._is_token_revoked_with_session(jti, user_id, session_id, issued_at, family_id, sess)

    async def _is_token_revoked_with_session(
        self,
        jti: str,
        user_id: str | None,
        session_id: str | None,
        issued_at: float | None,
        family_id: str | None,
        session: AsyncSession,
    ) -> bool:
        # Check direct JTI revocation
        query = text("""
            SELECT 1 FROM token_revocations
            WHERE revocation_key = :k AND (expires_at IS NULL OR expires_at > NOW())
            LIMIT 1;
        """)
        res = await session.execute(query, {"k": f"jti:{jti}"})
        if res.fetchone():
            return True

        # Check session revocation
        if session_id:
            res_sess = await session.execute(query, {"k": f"session:{session_id}"})
            if res_sess.fetchone():
                return True

        # Check user revocation
        if user_id:
            query_u = text("""
                SELECT revoked_at FROM token_revocations
                WHERE revocation_key = :k
                LIMIT 1;
            """)
            res_u = await session.execute(query_u, {"k": f"user:{user_id}"})
            row_u = res_u.fetchone()
            if row_u:
                revoked_epoch = row_u[0].timestamp()
                if issued_at is None or issued_at <= revoked_epoch:
                    return True

        # Check family compromise
        if family_id:
            query_f = text("SELECT is_compromised FROM token_families WHERE family_id = :fid LIMIT 1;")
            res_f = await session.execute(query_f, {"fid": family_id})
            row_f = res_f.fetchone()
            if row_f and row_f[0]:
                return True

        return False

    async def record_refresh_token_use(
        self, token_id: str, family_id: str, session: AsyncSession | None = None
    ) -> bool:
        if session is not None:
            return await self._record_refresh_token_use_with_session(token_id, family_id, session)
        async with get_tenant_session() as sess:
            res = await self._record_refresh_token_use_with_session(token_id, family_id, sess)
            await sess.commit()
            return res

    async def _record_refresh_token_use_with_session(
        self, token_id: str, family_id: str, session: AsyncSession
    ) -> bool:
        # Check if family exists
        query_sel = text("SELECT is_compromised, used_tokens FROM token_families WHERE family_id = :fid LIMIT 1;")
        res = await session.execute(query_sel, {"fid": family_id})
        row = res.fetchone()

        if row is None:
            # First use in new family
            query_ins = text("""
                INSERT INTO token_families (family_id, is_compromised, used_tokens, created_at, updated_at)
                VALUES (:fid, false, CAST(:toks AS jsonb), NOW(), NOW());
            """)
            await session.execute(query_ins, {"fid": family_id, "toks": json.dumps([token_id])})
            return True

        is_compromised = row[0]
        used_tokens = row[1]
        if isinstance(used_tokens, str):
            used_tokens = json.loads(used_tokens)
        used_tokens = set(used_tokens or [])

        if is_compromised:
            return False

        if token_id in used_tokens:
            # REUSE DETECTED! Mark compromised!
            query_comp = text("UPDATE token_families SET is_compromised = true, updated_at = NOW() WHERE family_id = :fid;")
            await session.execute(query_comp, {"fid": family_id})
            return False

        used_tokens.add(token_id)
        query_upd = text("""
            UPDATE token_families
            SET used_tokens = CAST(:toks AS jsonb), updated_at = NOW()
            WHERE family_id = :fid;
        """)
        await session.execute(query_upd, {"fid": family_id, "toks": json.dumps(list(used_tokens))})
        return True

    # Sync Revocation methods
    def revoke_token_sync(self, jti: str, expires_at: float) -> None:
        self._run_async(self.revoke_token(jti, expires_at))

    def revoke_session_tokens_sync(self, session_id: str) -> None:
        self._run_async(self.revoke_session_tokens(session_id))

    def revoke_user_tokens_sync(self, user_id: str) -> None:
        self._run_async(self.revoke_user_tokens(user_id))

    def is_token_revoked_sync(
        self,
        jti: str,
        user_id: str | None = None,
        session_id: str | None = None,
        issued_at: float | None = None,
        family_id: str | None = None,
    ) -> bool:
        return self._run_async(self.is_token_revoked(jti, user_id, session_id, issued_at, family_id))

    def record_refresh_token_use_sync(self, token_id: str, family_id: str) -> bool:
        return self._run_async(self.record_refresh_token_use(token_id, family_id))


_identity_repo_instance: IdentityRepository | None = None


def get_identity_repository() -> IdentityRepository:
    """Dependency provider for IdentityRepository."""
    global _identity_repo_instance
    mode = os.getenv("PERSISTENCE_MODE", "sql").strip().lower()
    env = os.getenv("CLOUDLENS_ENV", "development").strip().lower()

    if mode == "inmemory":
        if env in ("staging", "production"):
            logger.critical("FATAL STARTUP GUARD: Staging/production refuses InMemory repository.")
            sys.exit(1)
        from tests.fakes.identity import InMemoryIdentityRepository
        return InMemoryIdentityRepository()

    if _identity_repo_instance is None:
        _identity_repo_instance = SqlIdentityRepository()
    return _identity_repo_instance
