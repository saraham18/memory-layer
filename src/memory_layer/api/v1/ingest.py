"""Content ingestion endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from memory_layer.api.dependencies import get_current_user_id, get_key_manager, get_repository
from memory_layer.core.key_manager import KeyManager
from memory_layer.graph.repository import GraphRepository
from memory_layer.models.ingest import IngestHistoryResponse, IngestRequest, IngestResponse, IngestStatus

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_content(
    request: IngestRequest,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    repo: Annotated[GraphRepository, Depends(get_repository)],
    key_mgr: Annotated[KeyManager, Depends(get_key_manager)],
) -> IngestResponse:
    from memory_layer.extraction.pipeline import ExtractionPipeline
    from memory_layer.integrity.checker import IntegrityChecker
    from memory_layer.llm.router import LLMRouter

    provider = request.provider or "openai"
    try:
        api_key = await key_mgr.get_key_for_provider(user_id, provider)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    llm_router = LLMRouter()
    client = llm_router.get_client(provider, api_key)
    pipeline = ExtractionPipeline(client, repo)
    checker = IntegrityChecker(client, repo)

    uid = str(user_id)
    result = await pipeline.run(uid, request.content, request.content_type, request.metadata)
    await checker.check_and_commit(uid, result)

    return IngestResponse(ingest_id=result.ingest_id, status="completed")


@router.get("/{ingest_id}", response_model=IngestStatus)
async def get_ingest_status(
    ingest_id: UUID,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    repo: Annotated[GraphRepository, Depends(get_repository)],
) -> IngestStatus:
    event = await repo.get_node(str(user_id), str(ingest_id))
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingest event not found")
    return IngestStatus(
        ingest_id=UUID(event["id"]),
        status=event.get("status", "unknown"),
        nodes_created=event.get("nodes_created", 0),
        edges_created=event.get("edges_created", 0),
        contradictions_found=event.get("contradictions_found", 0),
        created_at=event["created_at"],
        completed_at=event.get("completed_at"),
        error=event.get("error"),
    )


@router.get("/history", response_model=IngestHistoryResponse)
async def get_ingest_history(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    repo: Annotated[GraphRepository, Depends(get_repository)],
    limit: int = 20,
    offset: int = 0,
) -> IngestHistoryResponse:
    events = await repo.get_nodes_by_label(str(user_id), "IngestEvent", limit=limit, offset=offset)
    items = [
        IngestStatus(
            ingest_id=UUID(e["id"]),
            status=e.get("status", "unknown"),
            nodes_created=e.get("nodes_created", 0),
            edges_created=e.get("edges_created", 0),
            created_at=e["created_at"],
        )
        for e in events
    ]
    return IngestHistoryResponse(events=items, total=len(items))
