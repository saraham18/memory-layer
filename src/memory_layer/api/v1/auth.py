"""Auth endpoints — register, login, refresh."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from memory_layer.api.dependencies import get_current_user_id, get_user_manager
from memory_layer.config import Settings, get_settings
from memory_layer.core.auth import create_access_token, verify_password
from memory_layer.core.user_manager import UserManager
from memory_layer.models.auth import (
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    TokenRequest,
    TokenResponse,
    UserProfile,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    user_mgr: Annotated[UserManager, Depends(get_user_manager)],
) -> RegisterResponse:
    existing = await user_mgr.get_user_by_email(request.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    return await user_mgr.register(request)


@router.post("/token", response_model=TokenResponse)
async def login(
    request: TokenRequest,
    user_mgr: Annotated[UserManager, Depends(get_user_manager)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    user_data = await user_mgr.get_user_by_email(request.email)
    if not user_data or not verify_password(request.password, user_data["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(
        subject=user_data["id"],
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expires_hours=settings.jwt_expiry_hours,
    )
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expiry_hours * 3600,
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    settings: Annotated[Settings, Depends(get_settings)],
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> RefreshResponse:
    token = create_access_token(
        subject=str(user_id),
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expires_hours=settings.jwt_expiry_hours,
    )
    return RefreshResponse(
        access_token=token,
        expires_in=settings.jwt_expiry_hours * 3600,
    )


@router.get("/me", response_model=UserProfile)
async def get_me(
    user_id: Annotated[str, Depends(get_current_user_id)],
    user_mgr: Annotated[UserManager, Depends(get_user_manager)],
) -> UserProfile:
    user = await user_mgr.get_user(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user
