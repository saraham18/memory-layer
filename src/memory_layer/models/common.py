"""Common Pydantic models shared across the application."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TimestampMixin(BaseModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    updated_at: datetime | None = None


class APIResponse(BaseModel):
    success: bool = True
    message: str = "OK"


class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    detail: str | None = None


class PaginatedResponse(BaseModel):
    items: list = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class NodeBase(BaseModel):
    """Base for all graph node representations."""
    id: UUID
    user_id: UUID
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime


class EdgeBase(BaseModel):
    """Base for all graph edge representations."""
    source_id: UUID
    target_id: UUID
    relationship: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime
    source: str = "extraction"
