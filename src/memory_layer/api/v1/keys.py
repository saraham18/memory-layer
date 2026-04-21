"""API key CRUD endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from memory_layer.api.dependencies import get_current_user_id, get_key_manager
from memory_layer.core.key_manager import KeyManager
from memory_layer.models.keys import (
    KeyCreateRequest,
    KeyListResponse,
    KeyResponse,
    KeyUpdateRequest,
    KeyValidateResponse,
)

router = APIRouter(prefix="/keys", tags=["keys"])


@router.post("", response_model=KeyResponse, status_code=status.HTTP_201_CREATED)
async def create_key(
    request: KeyCreateRequest,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    key_mgr: Annotated[KeyManager, Depends(get_key_manager)],
) -> KeyResponse:
    return await key_mgr.store_key(user_id, request)


@router.get("", response_model=KeyListResponse)
async def list_keys(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    key_mgr: Annotated[KeyManager, Depends(get_key_manager)],
) -> KeyListResponse:
    return await key_mgr.get_keys(user_id)


@router.get("/{key_id}", response_model=KeyResponse)
async def get_key(
    key_id: UUID,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    key_mgr: Annotated[KeyManager, Depends(get_key_manager)],
) -> KeyResponse:
    result = await key_mgr.get_key(user_id, key_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    return result


@router.put("/{key_id}", response_model=KeyResponse)
async def update_key(
    key_id: UUID,
    request: KeyUpdateRequest,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    key_mgr: Annotated[KeyManager, Depends(get_key_manager)],
) -> KeyResponse:
    result = await key_mgr.update_key(user_id, key_id, request)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    return result


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(
    key_id: UUID,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    key_mgr: Annotated[KeyManager, Depends(get_key_manager)],
) -> None:
    deleted = await key_mgr.delete_key(user_id, key_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")


@router.post("/{key_id}/validate", response_model=KeyValidateResponse)
async def validate_key(
    key_id: UUID,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    key_mgr: Annotated[KeyManager, Depends(get_key_manager)],
) -> KeyValidateResponse:
    result = await key_mgr.validate_key(user_id, key_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    return result
