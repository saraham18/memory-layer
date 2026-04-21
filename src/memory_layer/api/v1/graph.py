"""Graph node/edge management endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from memory_layer.api.dependencies import get_current_user_id, get_repository
from memory_layer.graph.repository import GraphRepository
from memory_layer.models.graph import (
    EdgeCreateRequest,
    EdgeResponse,
    GraphExportResponse,
    GraphStats,
    NodeCreateRequest,
    NodeResponse,
    NodeUpdateRequest,
)

router = APIRouter(prefix="/graph", tags=["graph"])


def _uid(user_id: UUID) -> str:
    return str(user_id)


@router.get("/stats", response_model=GraphStats)
async def graph_stats(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    repo: Annotated[GraphRepository, Depends(get_repository)],
) -> GraphStats:
    stats = await repo.get_stats(_uid(user_id))
    node_counts = stats.get("nodes", {})
    total_nodes = sum(node_counts.values())
    return GraphStats(
        total_nodes=total_nodes,
        total_edges=stats.get("edges", 0),
        node_counts=node_counts,
        edge_counts={},
    )


@router.post("/nodes", response_model=NodeResponse, status_code=status.HTTP_201_CREATED)
async def create_node(
    request: NodeCreateRequest,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    repo: Annotated[GraphRepository, Depends(get_repository)],
) -> NodeResponse:
    node = await repo.create_node(_uid(user_id), request.label, {
        "name": request.name,
        **request.properties,
        "confidence": request.confidence,
    })
    return NodeResponse(**node)


@router.get("/nodes/{node_id}", response_model=NodeResponse)
async def get_node(
    node_id: UUID,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    repo: Annotated[GraphRepository, Depends(get_repository)],
) -> NodeResponse:
    node = await repo.get_node(_uid(user_id), str(node_id))
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    return NodeResponse(**node)


@router.put("/nodes/{node_id}", response_model=NodeResponse)
async def update_node(
    node_id: UUID,
    request: NodeUpdateRequest,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    repo: Annotated[GraphRepository, Depends(get_repository)],
) -> NodeResponse:
    updates = {k: v for k, v in request.model_dump(exclude_none=True).items()}
    node = await repo.update_node(_uid(user_id), str(node_id), updates)
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    return NodeResponse(**node)


@router.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(
    node_id: UUID,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    repo: Annotated[GraphRepository, Depends(get_repository)],
) -> None:
    deleted = await repo.delete_node(_uid(user_id), str(node_id))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")


@router.post("/edges", response_model=EdgeResponse, status_code=status.HTTP_201_CREATED)
async def create_edge(
    request: EdgeCreateRequest,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    repo: Annotated[GraphRepository, Depends(get_repository)],
) -> EdgeResponse:
    edge = await repo.create_edge(
        _uid(user_id), str(request.source_id), str(request.target_id), request.relationship,
        {"confidence": request.confidence, "source": request.source},
    )
    return EdgeResponse(**edge)


@router.get("/edges/{node_id}", response_model=list[EdgeResponse])
async def get_edges(
    node_id: UUID,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    repo: Annotated[GraphRepository, Depends(get_repository)],
) -> list[EdgeResponse]:
    edges = await repo.get_edges(_uid(user_id), str(node_id))
    return [EdgeResponse(**e) for e in edges]


@router.delete("/edges", status_code=status.HTTP_204_NO_CONTENT)
async def delete_edge(
    source_id: UUID,
    target_id: UUID,
    relationship: str,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    repo: Annotated[GraphRepository, Depends(get_repository)],
) -> None:
    deleted = await repo.delete_edge(_uid(user_id), str(source_id), str(target_id), relationship)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Edge not found")


@router.get("/export", response_model=GraphExportResponse)
async def export_graph(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    repo: Annotated[GraphRepository, Depends(get_repository)],
) -> GraphExportResponse:
    data = await repo.export_graph(_uid(user_id))
    return GraphExportResponse(**data)
