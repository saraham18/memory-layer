"""FastAPI dependencies — auth, DB session, managers."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from memory_layer.config import Settings, get_settings
from memory_layer.core.auth import decode_access_token
from memory_layer.core.key_manager import KeyManager
from memory_layer.core.security import KeyEncryptor
from memory_layer.core.user_manager import UserManager
from memory_layer.graph.driver import GraphDriver
from memory_layer.graph.repository import GraphRepository
from memory_layer.llm.router import LLMRouter

bearer_scheme = HTTPBearer()

# --- Singletons set during lifespan ---
_graph_driver: GraphDriver | None = None
_llm_router: LLMRouter | None = None


def set_graph_driver(driver: GraphDriver) -> None:
    global _graph_driver
    _graph_driver = driver


def set_llm_router(router: LLMRouter) -> None:
    global _llm_router
    _llm_router = router


def get_graph_driver() -> GraphDriver:
    if _graph_driver is None:
        raise RuntimeError("Graph driver not initialized")
    return _graph_driver


def get_llm_router() -> LLMRouter:
    if _llm_router is None:
        raise RuntimeError("LLM router not initialized")
    return _llm_router


def get_repository(
    driver: Annotated[GraphDriver, Depends(get_graph_driver)],
) -> GraphRepository:
    return GraphRepository(driver)


def get_encryptor(
    settings: Annotated[Settings, Depends(get_settings)],
) -> KeyEncryptor:
    return KeyEncryptor(settings.fernet_keys)


def get_user_manager(
    repo: Annotated[GraphRepository, Depends(get_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserManager:
    return UserManager(repo, settings)


def get_key_manager(
    repo: Annotated[GraphRepository, Depends(get_repository)],
    encryptor: Annotated[KeyEncryptor, Depends(get_encryptor)],
) -> KeyManager:
    return KeyManager(repo, encryptor)


async def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UUID:
    """Extract and validate user_id from JWT bearer token."""
    try:
        payload = decode_access_token(
            credentials.credentials,
            settings.jwt_secret_key,
            settings.jwt_algorithm,
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return UUID(user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
