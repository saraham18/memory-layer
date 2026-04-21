"""Graph management models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class GraphStats(BaseModel):
    total_nodes: int
    total_edges: int
    node_counts: dict[str, int]
    edge_counts: dict[str, int]


class NodeCreateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=500)
    properties: dict = {}
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class NodeResponse(BaseModel):
    id: UUID
    label: str
    name: str
    properties: dict
    confidence: float
    created_at: datetime


class NodeUpdateRequest(BaseModel):
    name: str | None = None
    properties: dict | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class EdgeCreateRequest(BaseModel):
    source_id: UUID
    target_id: UUID
    relationship: str = Field(min_length=1, max_length=50)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = "manual"


class EdgeResponse(BaseModel):
    source_id: UUID
    target_id: UUID
    relationship: str
    confidence: float
    created_at: datetime
    source: str


class GraphExportResponse(BaseModel):
    nodes: list[NodeResponse]
    edges: list[EdgeResponse]
