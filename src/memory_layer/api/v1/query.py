"""GraphRAG query endpoints ("The Briefing")."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from memory_layer.api.dependencies import get_current_user_id, get_key_manager, get_repository
from memory_layer.core.key_manager import KeyManager
from memory_layer.graph.repository import GraphRepository
from memory_layer.models.query import ExplainResponse, QueryRequest, QueryResponse

router = APIRouter(prefix="/query", tags=["query"])


async def _build_engine(
    user_id: UUID,
    provider: str | None,
    key_mgr: KeyManager,
    repo: GraphRepository,
):
    from memory_layer.llm.router import LLMRouter
    from memory_layer.retrieval.engine import RetrievalEngine

    provider = provider or "openai"
    try:
        api_key = await key_mgr.get_key_for_provider(user_id, provider)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    client = LLMRouter().get_client(provider, api_key)
    return RetrievalEngine(client, repo)


@router.post("", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    repo: Annotated[GraphRepository, Depends(get_repository)],
    key_mgr: Annotated[KeyManager, Depends(get_key_manager)],
) -> QueryResponse:
    engine = await _build_engine(user_id, request.provider, key_mgr, repo)
    return await engine.query(
        user_id=str(user_id),
        query=request.query,
        max_hops=request.max_hops,
        max_tokens=request.max_tokens,
    )


@router.post("/explain", response_model=ExplainResponse)
async def query_explain(
    request: QueryRequest,
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    repo: Annotated[GraphRepository, Depends(get_repository)],
    key_mgr: Annotated[KeyManager, Depends(get_key_manager)],
) -> ExplainResponse:
    engine = await _build_engine(user_id, request.provider, key_mgr, repo)
    return await engine.query_explain(
        user_id=str(user_id),
        query=request.query,
        max_hops=request.max_hops,
        max_tokens=request.max_tokens,
    )
