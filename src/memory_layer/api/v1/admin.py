"""Admin endpoints — sleep cycle trigger, stats."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from memory_layer.api.dependencies import get_current_user_id, get_key_manager, get_repository
from memory_layer.core.key_manager import KeyManager
from memory_layer.graph.repository import GraphRepository
from memory_layer.models.common import APIResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/sleep/trigger", response_model=APIResponse)
async def trigger_sleep(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    repo: Annotated[GraphRepository, Depends(get_repository)],
    key_mgr: Annotated[KeyManager, Depends(get_key_manager)],
    provider: str = "openai",
) -> APIResponse:
    from memory_layer.llm.router import LLMRouter
    from memory_layer.sleep.consolidator import Consolidator
    from memory_layer.sleep.pruner import Pruner

    uid = str(user_id)
    try:
        api_key = await key_mgr.get_key_for_provider(user_id, provider)
    except ValueError as e:
        return APIResponse(success=False, message=str(e))

    client = LLMRouter().get_client(provider, api_key)

    pruner = Pruner(repo)
    consolidator = Consolidator(client, repo)

    pruned = await pruner.prune(uid)
    consolidated = await consolidator.consolidate(uid)

    return APIResponse(
        message=f"Sleep cycle complete: {pruned} pruned, {consolidated} consolidated"
    )


@router.get("/sleep/status")
async def sleep_status(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    repo: Annotated[GraphRepository, Depends(get_repository)],
) -> dict:
    stats = await repo.get_stats(str(user_id))
    return {
        "total_nodes": sum(stats.get("nodes", {}).values()),
        "total_edges": stats.get("edges", 0),
    }
