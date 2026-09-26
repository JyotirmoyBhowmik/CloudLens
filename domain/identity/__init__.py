"""CloudLens Identity and Authentication Package (Prompt 10)."""

from domain.identity.models import (
    AuthContext,
    BreakGlassAccount,
    MachineClient,
    Session,
    StepUpChallenge,
    StepUpToken,
    TokenPair,
    User,
)
from domain.identity.password_hasher import (
    generate_salt,
    generate_totp_code,
    generate_totp_secret,
    generate_totp_uri,
    hash_password,
    verify_password,
    verify_totp_code,
)
from domain.identity.service import (
    IdentityService,
    get_identity_service,
)
from domain.identity.token_engine import (
    CryptographicTokenEngine,
    TokenRevocationRegistry,
)

__all__ = [
    "AuthContext",
    "BreakGlassAccount",
    "CryptographicTokenEngine",
    "IdentityService",
    "MachineClient",
    "Session",
    "StepUpChallenge",
    "StepUpToken",
    "TokenPair",
    "TokenRevocationRegistry",
    "User",
    "generate_salt",
    "generate_totp_code",
    "generate_totp_secret",
    "generate_totp_uri",
    "get_identity_service",
    "hash_password",
    "verify_password",
    "verify_totp_code",
]
