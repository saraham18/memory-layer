"""MCP tool definitions — memory_ingest, memory_query, memory_status."""

from __future__ import annotations

from uuid import UUID

import structlog

from memory_layer.core.key_manager import KeyManager
from memory_layer.core.security import KeyEncryptor
from memory_layer.graph.repository import GraphRepository
from memory_layer.llm.router import LLMRouter
from memory_layer.models.mcp import MCPIngestInput, MCPQueryInput, MCPStatusResponse

log = structlog.get_logger()


async def memory_ingest(
    user_id: UUID,
    input_data: MCPIngestInput,
    repo: GraphRepository,
    key_mgr: KeyManager,
) -> dict:
    """Ingest content into the user's knowledge graph."""
    from memory_layer.extraction.pipeline import ExtractionPipeline
    from memory_layer.integrity.checker import IntegrityChecker

    provider = "openai"
    try:
        api_key = await key_mgr.get_key_for_provider(user_id, provider)
    except ValueError:
        for p in ["anthropic", "google"]:
            try:
                api_key = await key_mgr.get_key_for_provider(user_id, p)
                provider = p
                break
            except ValueError:
                continue
        else:
            return {"error": "No valid API key found. Please store an API key first."}

    client = LLMRouter().get_client(provider, api_key)
    pipeline = ExtractionPipeline(client, repo)
    checker = IntegrityChecker(client, repo)

    result = await pipeline.run(user_id, input_data.content, input_data.content_type, input_data.metadata)
    summary = await checker.check_and_commit(user_id, result)

    return {
        "ingest_id": str(result.ingest_id),
        "nodes_created": summary.get("committed", 0),
        "contradictions": summary.get("contradictions", 0),
        "status": "completed",
    }


async def memory_query(
    user_id: UUID,
    input_data: MCPQueryInput,
    repo: GraphRepository,
    key_mgr: KeyManager,
) -> dict:
    """Query the user's knowledge graph."""
    from memory_layer.retrieval.engine import RetrievalEngine

    provider = "openai"
    try:
        api_key = await key_mgr.get_key_for_provider(user_id, provider)
    except ValueError:
        for p in ["anthropic", "google"]:
            try:
                api_key = await key_mgr.get_key_for_provider(user_id, p)
                provider = p
                break
            except ValueError:
                continue
        else:
            return {"error": "No valid API key found."}

    client = LLMRouter().get_client(provider, api_key)
    engine = RetrievalEngine(client, repo)
    response = await engine.query(
        user_id=user_id,
        query=input_data.query,
        max_hops=input_data.max_hops,
        max_tokens=input_data.max_tokens,
    )
    return {
        "master_context": response.master_context,
        "seed_terms": response.seed_terms,
        "node_count": len(response.subgraph.nodes),
        "edge_count": len(response.subgraph.edges),
        "token_count": response.token_count,
    }


async def memory_status(
    user_id: UUID,
    repo: GraphRepository,
) -> dict:
    """Get the status of the user's knowledge graph."""
    stats = await repo.get_stats(user_id)
    return {
        "connected": True,
        "graph_nodes": stats.get("total_nodes", 0),
        "graph_edges": stats.get("total_edges", 0),
    }
