from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from fincore.core.config import get_settings

_hasher = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return _hasher.verify(encoded, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_access_token(*, user_id: str, organization_id: str, permissions: list[str]) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": user_id,
        "org": organization_id,
        "permissions": permissions,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_minutes)).timestamp()),
        "type": "access",
        "jti": secrets.token_urlsafe(16),
    }
    encoded = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return encoded.decode() if isinstance(encoded, bytes) else encoded


def decode_access_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Wrong token type")
    return dict(payload)


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def new_api_key() -> tuple[str, str]:
    secret = secrets.token_urlsafe(32)
    prefix = f"fc_{secrets.token_hex(4)}"
    return prefix, f"{prefix}.{secret}"


def generate_signing_secret() -> str:
    return secrets.token_urlsafe(32)


def sign_webhook(secret: str, timestamp: int, payload: bytes) -> str:
    message = f"{timestamp}.".encode() + payload
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)
