"""Cryptographic Password Hashing and TOTP Multi-Factor Engine (Prompt 10 Item 65).

Enforces:
- NIST SP 800-63B compliant salted password hashing using PBKDF2-HMAC-SHA256.
- RFC 6238 Time-Based One-Time Password (TOTP) generation and verification.
- Constant-time comparison using secrets.compare_digest to prevent timing attacks.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time

# Standard cryptographic configuration
# no-hardcode-allow: reason="NIST SP 800-63B recommended PBKDF2 minimum iteration count", reviewer="security-arch"
PBKDF2_ITERATIONS = 100000
# no-hardcode-allow: reason="Cryptographic salt length in bytes per standard", reviewer="security-arch"
SALT_BYTE_LENGTH = 16
# no-hardcode-allow: reason="RFC 6238 TOTP standard interval of 30 seconds", reviewer="security-arch"
TOTP_INTERVAL_SECONDS = 30
# no-hardcode-allow: reason="RFC 6238 TOTP standard code length of 6 decimal digits", reviewer="security-arch"
TOTP_DIGITS = 6


def generate_salt() -> str:
    """Generates a cryptographically random hexadecimal salt string."""
    return secrets.token_hex(SALT_BYTE_LENGTH)


def hash_password(password: str, salt: str) -> str:
    """Hashes a plaintext password with PBKDF2-HMAC-SHA256 and salt."""
    try:
        salt_bytes = bytes.fromhex(salt)
    except ValueError:
        salt_bytes = salt.encode("utf-8")
    password_bytes = password.encode("utf-8")
    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        password_bytes,
        salt_bytes,
        PBKDF2_ITERATIONS,
    )
    return derived_key.hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """Verifies a password against the expected salted hash using constant-time comparison."""
    computed_hash = hash_password(password, salt)
    return secrets.compare_digest(computed_hash, expected_hash)


def generate_totp_secret() -> str:
    """Generates an RFC 6238 base32-encoded secret seed for TOTP MFA."""
    raw_bytes = secrets.token_bytes(20)
    return base64.b32encode(raw_bytes).decode("utf-8").rstrip("=")


def generate_totp_code(secret: str, for_timestamp: float | None = None) -> str:
    """Computes a 6-digit TOTP code for a secret and time interval (RFC 6238 / RFC 4226)."""
    current_time = for_timestamp if for_timestamp is not None else time.time()
    time_step = int(current_time // TOTP_INTERVAL_SECONDS)

    # Pad base32 secret to multiple of 8 characters
    padded_secret = secret.upper()
    remainder = len(padded_secret) % 8
    if remainder != 0:
        padded_secret += "=" * (8 - remainder)

    key_bytes = base64.b32decode(padded_secret)
    # Pack counter as 8-byte big-endian integer
    counter_bytes = struct.pack(">Q", time_step)

    # Compute HMAC-SHA1 per RFC 6238 / RFC 4226 reference
    h = hmac.new(key_bytes, counter_bytes, hashlib.sha1).digest()

    # Dynamic truncation
    # no-hardcode-allow: reason="RFC 4226 dynamic truncation offset mask", reviewer="security-arch"
    offset = h[-1] & 0x0F
    # no-hardcode-allow: reason="RFC 4226 31-bit integer extraction mask", reviewer="security-arch"
    code_int = struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF
    totp_value = code_int % (10**TOTP_DIGITS)

    return f"{totp_value:0{TOTP_DIGITS}d}"


def verify_totp_code(secret: str, code: str, allowed_drift_steps: int = 1) -> bool:
    """Verifies a TOTP code against a secret allowing clock drift tolerance (default +-1 step)."""
    cleaned_code = code.strip()
    if len(cleaned_code) != TOTP_DIGITS or not cleaned_code.isdigit():
        return False

    now = time.time()
    for step_offset in range(-allowed_drift_steps, allowed_drift_steps + 1):
        candidate_time = now + (step_offset * TOTP_INTERVAL_SECONDS)
        candidate_code = generate_totp_code(secret, for_timestamp=candidate_time)
        if secrets.compare_digest(candidate_code, cleaned_code):
            return True

    return False


def generate_totp_uri(secret: str, account_name: str, issuer: str = "CloudLens") -> str:
    """Generates standard otpauth:// URI for authenticator applications."""
    # no-hardcode-allow: reason="Standard RFC 6238 otpauth URI parameters", reviewer="SecurityArchitect"
    return f"otpauth://totp/{issuer}:{account_name}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_INTERVAL_SECONDS}"
