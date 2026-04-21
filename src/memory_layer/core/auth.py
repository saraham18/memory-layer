"""JWT token management and bcrypt password hashing."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(
    subject: str,
    secret_key: str,
    algorithm: str = "HS256",
    expires_hours: int = 24,
    extra_claims: dict | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(hours=expires_hours),
        **(extra_claims or {}),
    }
    return jwt.encode(claims, secret_key, algorithm=algorithm)


def decode_access_token(
    token: str,
    secret_key: str,
    algorithm: str = "HS256",
) -> dict:
    """Decode and validate a JWT. Raises JWTError on invalid/expired."""
    try:
        return jwt.decode(token, secret_key, algorithms=[algorithm])
    except JWTError:
        raise
