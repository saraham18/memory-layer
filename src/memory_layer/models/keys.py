"""API key management models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"


class KeyCreateRequest(BaseModel):
    provider: LLMProvider
    api_key: str = Field(min_length=1)
    label: str = Field(default="default", max_length=100)


class KeyUpdateRequest(BaseModel):
    api_key: str = Field(min_length=1)
    label: str | None = None


class KeyResponse(BaseModel):
    key_id: UUID
    provider: LLMProvider
    label: str
    created_at: datetime
    last_used: datetime | None = None
    is_valid: bool | None = None
    # Never expose actual key — only masked
    masked_key: str


class KeyListResponse(BaseModel):
    keys: list[KeyResponse]


class KeyValidateResponse(BaseModel):
    key_id: UUID
    provider: LLMProvider
    is_valid: bool
    message: str
