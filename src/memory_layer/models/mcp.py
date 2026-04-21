"""MCP-related models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MCPIngestInput(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    content_type: str = "text"
    metadata: dict | None = None


class MCPQueryInput(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    max_hops: int = Field(default=3, ge=1, le=5)
    max_tokens: int = Field(default=4000, ge=100, le=16000)


class MCPStatusResponse(BaseModel):
    connected: bool
    graph_nodes: int
    graph_edges: int
    last_ingest: str | None = None
    last_sleep_cycle: str | None = None
