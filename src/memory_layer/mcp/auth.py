"""Per-request MCP authentication."""

from __future__ import annotations

from uuid import UUID

from memory_layer.config import get_settings
from memory_layer.core.auth import decode_access_token


def validate_mcp_token(token: str) -> UUID:
    """Validate a bearer token from an MCP request. Returns user_id."""
    settings = get_settings()
    payload = decode_access_token(
        token,
        settings.jwt_secret_key,
        settings.jwt_algorithm,
    )
    user_id = payload.get("sub")
    if not user_id:
        raise ValueError("Invalid token: missing subject")
    return UUID(user_id)
