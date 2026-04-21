"""Task definitions for background processing."""

from __future__ import annotations

from uuid import UUID

from memory_layer.core.key_manager import KeyManager
from memory_layer.graph.repository import GraphRepository
from memory_layer.llm.router import LLMRouter


async def ingest_content_task(
    user_id: UUID,
    content: str,
    content_type: str,
    metadata: dict | None,
    provider: str,
    repo: GraphRepository,
    key_mgr: KeyManager,
) -> dict:
    """Background task for content ingestion."""
    from memory_layer.extraction.pipeline import ExtractionPipeline
    from memory_layer.integrity.checker import IntegrityChecker

    api_key = await key_mgr.get_key_for_provider(user_id, provider)
    client = LLMRouter().get_client(provider, api_key)

    pipeline = ExtractionPipeline(client, repo)
    checker = IntegrityChecker(client, repo)

    result = await pipeline.run(user_id, content, content_type, metadata)
    summary = await checker.check_and_commit(user_id, result)

    return {
        "ingest_id": str(result.ingest_id),
        "nodes_created": summary.get("committed", 0),
        "contradictions": summary.get("contradictions", 0),
    }


async def sleep_cycle_task(
    user_id: UUID,
    provider: str,
    repo: GraphRepository,
    key_mgr: KeyManager,
) -> dict:
    """Background task for sleep cycle on a single user."""
    from memory_layer.sleep.consolidator import Consolidator
    from memory_layer.sleep.pruner import Pruner

    api_key = await key_mgr.get_key_for_provider(user_id, provider)
    client = LLMRouter().get_client(provider, api_key)

    pruner = Pruner(repo)
    consolidator = Consolidator(client, repo)

    pruned = await pruner.prune(user_id)
    consolidated = await consolidator.consolidate(user_id)

    return {"pruned": pruned, "consolidated": consolidated}
