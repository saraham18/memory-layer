"""Ingest request/response models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class ContentType(str, Enum):
    TEXT = "text"
    CONVERSATION = "conversation"
    DOCUMENT = "document"


class IngestRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    content_type: ContentType = ContentType.TEXT
    metadata: dict | None = None
    provider: str | None = None  # Override default LLM provider


class IngestResponse(BaseModel):
    ingest_id: UUID
    status: str = "processing"
    message: str = "Content queued for ingestion"


class IngestStatus(BaseModel):
    ingest_id: UUID
    status: str  # processing, completed, failed
    nodes_created: int = 0
    edges_created: int = 0
    contradictions_found: int = 0
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


class IngestHistoryResponse(BaseModel):
    events: list[IngestStatus]
    total: int
