"""Query (GraphRAG/Briefing) request/response models."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    max_hops: int = Field(default=3, ge=1, le=5)
    max_tokens: int = Field(default=4000, ge=100, le=16000)
    provider: str | None = None


class SubgraphNode(BaseModel):
    id: UUID
    label: str
    name: str
    properties: dict = {}
    confidence: float
    hop_distance: int


class SubgraphEdge(BaseModel):
    source_id: UUID
    target_id: UUID
    relationship: str
    confidence: float


class Subgraph(BaseModel):
    nodes: list[SubgraphNode]
    edges: list[SubgraphEdge]


class QueryResponse(BaseModel):
    master_context: str
    subgraph: Subgraph
    seed_terms: list[str]
    token_count: int


class ExplainResponse(BaseModel):
    master_context: str
    subgraph: Subgraph
    seed_terms: list[str]
    token_count: int
    traversal_trace: list[dict]
    scoring_details: list[dict]
