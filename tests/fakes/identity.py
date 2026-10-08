"""In-Memory Identity Repository Fake for isolated unit testing."""

from domain.identity.models import (
    MachineClient,
    Session,
    StepUpChallenge,
    User,
)


class InMemoryIdentityRepository:
    is_in_memory: bool = True

    def __init__(self) -> None:
        self._users: dict[str, User] = {}
        self._users_by_email: dict[tuple[str, str], str] = {}
        self._sessions: dict[str, Session] = {}
        self._machine_clients: dict[str, MachineClient] = {}
        self._step_up_challenges: dict[str, StepUpChallenge] = {}
        self._revoked_jtis: dict[str, float] = {}
        self._revoked_sessions: dict[str, float] = {}
        self._revoked_users: dict[str, float] = {}
        self._used_refresh_tokens: set[str] = set()
        self._compromised_families: set[str] = set()

    # Users
    async def get_user(self, user_id: str, session=None) -> User | None:
        return self._users.get(user_id)

    async def get_user_by_email(self, tenant_id: str, email: str, session=None) -> User | None:
        uid = self._users_by_email.get((tenant_id, email.lower()))
        return self._users.get(uid) if uid else None

    async def save_user(self, user: User, session=None) -> User:
        self._users[user.id] = user
        self._users_by_email[(user.tenant_id, user.email.lower())] = user.id
        return user

    async def list_users(self, tenant_id: str, session=None) -> list[User]:
        return [u for u in self._users.values() if u.tenant_id == tenant_id]

    async def delete_user(self, user_id: str, session=None) -> bool:
        user = self._users.pop(user_id, None)
        if user:
            self._users_by_email.pop((user.tenant_id, user.email.lower()), None)
            return True
        return False

    def get_user_sync(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    def get_user_by_email_sync(self, tenant_id: str, email: str) -> User | None:
        uid = self._users_by_email.get((tenant_id, email.lower()))
        return self._users.get(uid) if uid else None

    def save_user_sync(self, user: User) -> User:
        self._users[user.id] = user
        self._users_by_email[(user.tenant_id, user.email.lower())] = user.id
        return user

    def list_users_sync(self, tenant_id: str) -> list[User]:
        return [u for u in self._users.values() if u.tenant_id == tenant_id]

    def delete_user_sync(self, user_id: str) -> bool:
        user = self._users.pop(user_id, None)
        if user:
            self._users_by_email.pop((user.tenant_id, user.email.lower()), None)
            return True
        return False

    # Sessions
    async def get_session(self, session_id: str, session=None) -> Session | None:
        return self._sessions.get(session_id)

    async def save_session(self, session_entity: Session, session=None) -> Session:
        self._sessions[session_entity.id] = session_entity
        return session_entity

    async def list_active_sessions(self, tenant_id: str, user_id: str | None = None, session=None) -> list[Session]:
        return [
            s for s in self._sessions.values()
            if s.tenant_id == tenant_id and s.is_active and (user_id is None or s.user_id == user_id)
        ]

    async def revoke_session(self, session_id: str, reason: str | None = None, session=None) -> bool:
        s = self._sessions.get(session_id)
        if s and s.is_active:
            s.is_active = False
            s.revocation_reason = reason
            await self.revoke_session_tokens(session_id)
            return True
        return False

    async def revoke_all_user_sessions(self, tenant_id: str, user_id: str, reason: str | None = None, session=None) -> int:
        count = 0
        for s in self._sessions.values():
            if s.tenant_id == tenant_id and s.user_id == user_id and s.is_active:
                s.is_active = False
                s.revocation_reason = reason
                count += 1
        await self.revoke_user_tokens(user_id)
        return count

    def get_session_sync(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def save_session_sync(self, s: Session) -> Session:
        self._sessions[s.id] = s
        return s

    def list_active_sessions_sync(self, tenant_id: str, user_id: str | None = None) -> list[Session]:
        return [
            s for s in self._sessions.values()
            if s.tenant_id == tenant_id and s.is_active and (user_id is None or s.user_id == user_id)
        ]

    def revoke_session_sync(self, session_id: str, reason: str | None = None) -> bool:
        s = self._sessions.get(session_id)
        if s and s.is_active:
            s.is_active = False
            s.revocation_reason = reason
            self.revoke_session_tokens_sync(session_id)
            return True
        return False

    def revoke_all_user_sessions_sync(self, tenant_id: str, user_id: str, reason: str | None = None) -> int:
        count = 0
        for s in self._sessions.values():
            if s.tenant_id == tenant_id and s.user_id == user_id and s.is_active:
                s.is_active = False
                s.revocation_reason = reason
                count += 1
        self.revoke_user_tokens_sync(user_id)
        return count

    # Machine Clients
    async def get_machine_client(self, client_id: str, session=None) -> MachineClient | None:
        return self._machine_clients.get(client_id)

    async def save_machine_client(self, client: MachineClient, session=None) -> MachineClient:
        self._machine_clients[client.client_id] = client
        return client

    async def list_machine_clients(self, tenant_id: str, session=None) -> list[MachineClient]:
        return [c for c in self._machine_clients.values() if c.tenant_id == tenant_id]

    async def delete_machine_client(self, client_id: str, session=None) -> bool:
        return bool(self._machine_clients.pop(client_id, None))

    def get_machine_client_sync(self, client_id: str) -> MachineClient | None:
        return self._machine_clients.get(client_id)

    def save_machine_client_sync(self, client: MachineClient) -> MachineClient:
        self._machine_clients[client.client_id] = client
        return client

    def list_machine_clients_sync(self, tenant_id: str) -> list[MachineClient]:
        return [c for c in self._machine_clients.values() if c.tenant_id == tenant_id]

    def delete_machine_client_sync(self, client_id: str) -> bool:
        return bool(self._machine_clients.pop(client_id, None))

    # Step-Up Challenges
    async def get_step_up_challenge(self, challenge_id: str, session=None) -> StepUpChallenge | None:
        return self._step_up_challenges.get(challenge_id)

    async def save_step_up_challenge(self, challenge: StepUpChallenge, session=None) -> StepUpChallenge:
        self._step_up_challenges[challenge.id] = challenge
        return challenge

    async def delete_step_up_challenge(self, challenge_id: str, session=None) -> bool:
        return bool(self._step_up_challenges.pop(challenge_id, None))

    def get_step_up_challenge_sync(self, challenge_id: str) -> StepUpChallenge | None:
        return self._step_up_challenges.get(challenge_id)

    def save_step_up_challenge_sync(self, challenge: StepUpChallenge) -> StepUpChallenge:
        self._step_up_challenges[challenge.id] = challenge
        return challenge

    def delete_step_up_challenge_sync(self, challenge_id: str) -> bool:
        return bool(self._step_up_challenges.pop(challenge_id, None))

    # Revocation & Token Families
    async def revoke_token(self, jti: str, expires_at: float, session=None) -> None:
        self._revoked_jtis[jti] = expires_at

    async def revoke_session_tokens(self, session_id: str, session=None) -> None:
        import time
        self._revoked_sessions[session_id] = time.time()

    async def revoke_user_tokens(self, user_id: str, session=None) -> None:
        import time
        self._revoked_users[user_id] = time.time()

    async def is_token_revoked(
        self, jti: str, user_id: str | None = None, session_id: str | None = None,
        issued_at: float | None = None, family_id: str | None = None, session=None
    ) -> bool:
        if jti in self._revoked_jtis:
            return True
        if session_id and session_id in self._revoked_sessions:
            return True
        if user_id and user_id in self._revoked_users:
            if issued_at is None or issued_at <= self._revoked_users[user_id]:
                return True
        if family_id and family_id in self._compromised_families:
            return True
        return False

    async def record_refresh_token_use(self, token_id: str, family_id: str, session=None) -> bool:
        if family_id in self._compromised_families:
            return False
        if token_id in self._used_refresh_tokens:
            self._compromised_families.add(family_id)
            return False
        self._used_refresh_tokens.add(token_id)
        return True

    def revoke_token_sync(self, jti: str, expires_at: float) -> None:
        self._revoked_jtis[jti] = expires_at

    def revoke_session_tokens_sync(self, session_id: str) -> None:
        import time
        self._revoked_sessions[session_id] = time.time()

    def revoke_user_tokens_sync(self, user_id: str) -> None:
        import time
        self._revoked_users[user_id] = time.time()

    def is_token_revoked_sync(
        self, jti: str, user_id: str | None = None, session_id: str | None = None,
        issued_at: float | None = None, family_id: str | None = None
    ) -> bool:
        if jti in self._revoked_jtis:
            return True
        if session_id and session_id in self._revoked_sessions:
            return True
        if user_id and user_id in self._revoked_users:
            if issued_at is None or issued_at <= self._revoked_users[user_id]:
                return True
        if family_id and family_id in self._compromised_families:
            return True
        return False

    def record_refresh_token_use_sync(self, token_id: str, family_id: str) -> bool:
        if family_id in self._compromised_families:
            return False
        if token_id in self._used_refresh_tokens:
            self._compromised_families.add(family_id)
            return False
        self._used_refresh_tokens.add(token_id)
        return True
